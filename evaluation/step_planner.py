"""
=============================================================================
STEP_PLANNER.PY - Step Plan Generation via LLM
=============================================================================

This module uses a Large Language Model (LLM) to generate detailed
implementation plans from Pull Request context.

PURPOSE:

When analyzing a PR, we have already extracted:
- Modified files (from diff_parser)
- Modified functions (from function_matcher)

But we're missing the "WHY" and "HOW":
- Why were these changes made?
- In what logical order were they implemented?
- What dependencies exist between the changes?

This module uses GPT to answer these questions.

ARCHITECTURE:

    ┌─────────────────────────────────────────────────────────────────┐
    │                         INPUT                                   │
    │  - PR Title                                                     │
    │  - PR Body (description)                                        │
    │  - Commit Messages                                              │
    │  - Files Changed [{filename, additions, deletions, patch}]      │
    └──────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    StepPlanner                                  │
    │  1. Builds context (_build_context)                             │
    │  2. Creates an Agent with structured output                     │
    │  3. Runs the agent and gets StepPlan                            │
    │  4. Converts to StepPlan (from models module)                   │
    └──────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                         OUTPUT                                  │
    │  StepPlan:                                                      │
    │  - summary: "PR summary in 1-2 sentences"                       │
    │  - steps: [                                                     │
    │      Step(operation, file_to_modify, function_to_modify, ...),  │
    │      Step(operation, file_to_modify, function_to_modify, ...),  │
    │      ... (exactly 5 steps)                                      │
    │    ]                                                            │
    └─────────────────────────────────────────────────────────────────┘


The Pydantic constraint is the main guarantee - if the model
generates more or fewer than 5 steps, Pydantic will raise ValidationError.

RETRY LOGIC:

The StepPlannerWithRetry class extends StepPlanner with:
- Automatic retries on API errors
- Exponential backoff (2^attempt seconds between attempts)
- Maximum 3 attempts by default
=============================================================================
"""

import logging
from typing import Optional, List, Dict
import asyncio
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner
from .models import Step, StepPlan
import os
from dotenv import load_dotenv
from GenAI.prompts import get_step_planner_prompt

load_dotenv()

logger = logging.getLogger('ground_truth_extractor')

# =============================================================================
# CLASS StepPlanner - Base Step Plan Generator

class StepPlanner:
    """
    Step plan generator using LLM (Large Language Model).

    This class:
    1. Connects to the OpenAI API
    2. Builds a contextualized prompt from the PR
    3. Uses an Agent with structured output to generate the plan
    4. Returns a validated StepPlan object

    EXECUTION FLOW:

        generate_step_plan()
               │
               ▼
        generate_step_plan_async()
               │
               ├──► _build_context()     → Builds the prompt
               │
               ├──► Agent()              → Creates the agent
               │
               ├──► Runner.run()         → Executes and waits for response
               │
               └──► StepPlan()           → Converts output to model

    MODEL USED:

    Currently uses gpt-5.2-2025-12-11, an economical and fast model.
    The model can be changed by modifying the parameter in __init__.

    Attributes:
        api_key (str): OpenAI API key (from .env or passed directly)
        client (AsyncOpenAI): Async client for API calls
        model (OpenAIChatCompletionsModel): Model wrapper for the Agent
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the planner with API configuration.

        API KEY PRECEDENCE ORDER:
        1. api_key parameter (if provided)
        2. OPENAI_API_KEY environment variable
        3. Error if neither is available

        Args:
            api_key (Optional[str]): OpenAI API key. If None, it is
                                    read from OPENAI_API_KEY in environment.

        Raises:
            ValueError: If API key is not found as parameter
                       or as environment variable.
        """

        self.api_key = api_key or os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        # ---------------------------------------------------------------------
        # OpenAI Client Configuration
        self.client = AsyncOpenAI(api_key=self.api_key, timeout=120.0)

        # ---------------------------------------------------------------------
        # Model Configuration
        self.model = OpenAIChatCompletionsModel(
            model="gpt-5.2-2025-12-11",
            openai_client=self.client
        )

    async def generate_step_plan_async(
        self,
        pr_title: str,
        pr_body: Optional[str],
        commit_messages: List[str],
        diff_summaries: List[Dict],  # [{filename, additions, deletions, patch}]
        num_steps: int
    ) -> StepPlan:
        """
        Generate a step plan from the PR using the LLM (async version).

        This is the main function that orchestrates the generation.
        It is async to allow non-blocking execution.

        PROCESS:

        1. CONTEXT BUILDING:
           Combines all PR information into a readable format
           for the LLM (see _build_context).

        2. AGENT CREATION:
           Creates an Agent with:
           - instructions: The prompt template with instructions
           - output_type: StepPlan for structured output

        3. EXECUTION:
           Runner.run() sends the context to the agent and waits for response.
           The output is automatically validated against StepPlan.

        4. VALIDATION:
           Verifies that the number of generated steps matches num_steps.
           If it doesn't match, raises ValueError.

        num_steps CALCULATION:
        The number of steps is calculated by the caller (ground_truth_extractor) as:
        - For .py files: number of modified FUNCTIONS
        - For non-.py files: counts as 1 file

        Args:
            pr_title (str): Pull Request title.
                           E.g.: "Fix memory leak in cache module"

            pr_body (Optional[str]): PR description/body.
                                    Can be None if PR has no description.
                                    E.g.: "This PR fixes the memory leak by..."

            commit_messages (List[str]): List of commit messages.
                                        E.g.: ["Fix leak", "Add tests", "Update docs"]

            diff_summaries (List[Dict]): Summary of changes per file.
                                        Each dictionary must contain:
                                        - filename: file name
                                        - additions: lines added
                                        - deletions: lines removed
                                        - patch: unified diff content (optional)
                                        E.g.: [{"filename": "cache.py", "additions": 10, "deletions": 2, "patch": "@@ -1,3 +1,5 @@..."}]

            num_steps (int): Exact number of steps to generate.
                            Calculated as: modified functions (.py files) + non-.py files.

        Returns:
            StepPlan: Plan with summary and list of num_steps Steps.
                     Each Step has: operation, file_to_modify, function_to_modify, reason, side_effects.

        Raises:
            ValueError: If LLM doesn't generate exactly num_steps steps.
            OpenAIError: If API call fails.

        Example:
            plan = await planner.generate_step_plan_async(
                pr_title="Add input validation",
                pr_body="Prevents SQL injection attacks",
                commit_messages=["Add sanitization", "Update tests"],
                diff_summaries=[{"filename": "api/input.py", "additions": 20, "deletions": 5}],
                num_steps=3  # 2 modified functions + 1 config file
            )
            print(plan.summary)
            for step in plan.steps:
                print(f"  - {step.operation}")
        """

        # Validate num_steps parameter
        if num_steps < 1:
            raise ValueError(f"num_steps must be at least 1, got {num_steps}")

        # ---------------------------------------------------------------------
        # Step 1: Build context for the LLM
        # ---------------------------------------------------------------------
        # The context is a formatted string with all PR info
        context = self._build_context(
            pr_title, pr_body, commit_messages,
            diff_summaries
        )

        # ---------------------------------------------------------------------
        # Step 2: Create Agent with structured output
        # ---------------------------------------------------------------------
        # The Agent combines:
        # - name: identifier for logging/debug
        # - instructions: prompt template (what the LLM should do)
        # - model: which model to use
        # - output_type: Pydantic schema to validate output
        agent = Agent(
            name="step_planner",
            instructions=get_step_planner_prompt(num_steps),
            model=self.model,
            output_type=StepPlan  # Forces structured output
        )

        # ---------------------------------------------------------------------
        # Step 3: Execute the Agent
        # ---------------------------------------------------------------------
        # Runner.run() is async and:
        # 1. Sends context to the model
        # 2. Waits for response
        # 3. Parses output into StepPlan
        # 4. Raises error if validation fails
        result = await Runner.run(agent, context)

        # ---------------------------------------------------------------------
        # Step 4: Validate number of steps
        # ---------------------------------------------------------------------
        # Verify that LLM generated exactly num_steps steps
        generated_steps = len(result.final_output.steps)
        if generated_steps != num_steps:
            raise ValueError(
                f"Expected {num_steps} steps, but LLM generated {generated_steps}. "
                f"This will be retried by StepPlannerWithRetry."
            )

        return result.final_output

    def generate_step_plan(self, *args, **kwargs) -> StepPlan:
        """
        Synchronous wrapper for generate_step_plan_async.

        Allows using the planner without having to handle async/await.
        Internally uses asyncio.run() to execute the async version.

        WHEN TO USE SYNC vs ASYNC:

        - SYNC (this method): When processing one PR at a time
          or when calling code is not async.

        - ASYNC: When you want to process multiple PRs in parallel
          or when calling code is already async.

        Args:
            *args: Passed to generate_step_plan_async
            **kwargs: Passed to generate_step_plan_async

        Returns:
            StepPlan: The generated plan (see generate_step_plan_async).

        Example:
            # Simple synchronous usage
            planner = StepPlanner()
            plan = planner.generate_step_plan(
                pr_title="...",
                pr_body="...",
                commit_messages=[...],
    
                diff_summaries=[...]
            )
        """
        # asyncio.run() creates an event loop, executes the coroutine,
        # and closes the loop when done
        return asyncio.run(self.generate_step_plan_async(*args, **kwargs))

    def _build_context(
        self,
        pr_title: str,
        pr_body: Optional[str],
        commit_messages: List[str],
        diff_summaries: List[Dict]
    ) -> str:
        """
        Build the formatted context string for the LLM.

        The context is structured in Markdown sections to facilitate
        comprehension by the LLM.

        OUTPUT FORMAT:

            # Pull Request Analysis

            ## Title: Fix memory leak in cache

            ## Description:
            This PR fixes a memory leak that occurs when...

            ## Commit Messages:

            1. Fix cache cleanup logic
            2. Add unit tests for cleanup
            3. Update documentation

            ## Files Changed:

            - src/cache.py: +10 -2
            - tests/test_cache.py: +25 -0
            - README.md: +5 -1

            ## Patch Content:

            ### src/cache.py
            ```diff
            @@ -10,5 +10,8 @@
            - old_code()
            + new_code()
            ```

        TRUNCATION:

        Long commit messages are truncated to 200 characters
        to avoid exceeding model token limits.

        Args:
            pr_title (str): PR title
            pr_body (Optional[str]): Description (can be None/empty)
            commit_messages (List[str]): List of commit messages
            diff_summaries (List[Dict]): Info on changes per file, including patch content

        Returns:
            str: Formatted string ready for the LLM

        Example:
            context = planner._build_context(
                "Fix bug", "Description", ["commit 1"],
                [{"filename": "file.py", "additions": 5, "deletions": 2}]
            )
            # Returns formatted Markdown string
        """

        # Start with header and title
        lines = [
            "# Pull Request Analysis",
            "",
            f"## Title: {pr_title}",
            ""
        ]

        # ---------------------------------------------------------------------
        # Description Section (optional)
        # ---------------------------------------------------------------------
        # Add only if pr_body exists and is not empty
        if pr_body:
            lines.extend([
                "## Description:",
                pr_body,
                ""
            ])

        # ---------------------------------------------------------------------
        # Commit Messages Section
        # ---------------------------------------------------------------------
        lines.extend([
            "## Commit Messages:",
            ""
        ])

        for i, msg in enumerate(commit_messages, 1):
            # Truncate overly long messages to save tokens
            # 200 characters are sufficient to understand the intent
            msg_preview = msg[:200] + "..." if len(msg) > 200 else msg
            lines.append(f"{i}. {msg_preview}")

        lines.append("")  # Empty line after the list

        # ---------------------------------------------------------------------
        # Files Changed Section
        # ---------------------------------------------------------------------
        lines.extend([
            "## Files Changed:",
            ""
        ])

        for summary in diff_summaries:
            # Format: "- filename: +additions -deletions"
            lines.append(
                f"- {summary['filename']}: "
                f"+{summary['additions']} -{summary['deletions']}"
            )

        lines.append("")  # Empty line after file list

        # ---------------------------------------------------------------------
        # Patch Content Section
        # ---------------------------------------------------------------------
        lines.extend([
            "## Patch Content:",
            ""
        ])

        for summary in diff_summaries:
            patch = summary.get('patch')
            if patch:
                lines.append(f"### {summary['filename']}")
                lines.append("```diff")
                lines.append(patch)
                lines.append("```")
                lines.append("")

        lines.append("")  # Final empty line

        # Join all lines with newline
        return "\n".join(lines)


# =============================================================================
# CLASS StepPlannerWithRetry - Planner with Robust Error Handling
# =============================================================================

class StepPlannerWithRetry(StepPlanner):
    """
    Step planner with automatic retry on API errors.

    Extends StepPlanner by adding:
    - Automatic retries for transient errors (rate limit, timeout, etc.)
    - Exponential backoff between attempts
    - Logging of errors and retries

    WHEN TO USE THIS CLASS:

    Use StepPlannerWithRetry instead of StepPlanner when:
    - Processing many PRs and want to handle transient errors
    - Network might be unstable
    - You want to maximize success rate

    Use base StepPlanner when:
    - You want to handle errors manually
    - You're debugging and want to see errors immediately
    - You need fine control over retry logic

    EXPONENTIAL BACKOFF:

    Wait times between retries grow exponentially:
    - Attempt 1 failed → wait 2^0 = 1 second
    - Attempt 2 failed → wait 2^1 = 2 seconds
    - Attempt 3 failed → return None

    This pattern:
    - Avoids overloading the API after an error
    - Gives the system time to recover
    - Respects OpenAI rate limits

    BEHAVIOR ON ERROR:

    1. TRANSIENT ERROR (rate limit, timeout):
       - Retry up to max_retries
       - Returns None if all fail

    2. PERMANENT ERROR (invalid API key):
       - Still retried (we don't distinguish)
       - Could improve by filtering by error type

    3. PYDANTIC VALIDATION (steps != 5):
       - Retried (LLM might generate correctly)
       - Often happens on first attempt with complex PRs

    Example:
        planner = StepPlannerWithRetry()

        # Generate plan with automatic retries
        plan = planner.generate_step_plan(
            pr_title="...",
            # ...other parameters
        )

        if plan is None:
            print("Generation failed after 3 attempts")
        else:
            print(f"Plan generated: {plan.summary}")

        # With custom number of retries
        plan = await planner.generate_step_plan_async(
            pr_title="...",
            # ...other parameters,
            max_retries=5  # More attempts for critical PRs
        )
    """

    async def generate_step_plan_async(
        self,
        *args,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[StepPlan]:
        """
        Generate step plan with retry logic.

        Overrides base class method to add
        error handling and retry with exponential backoff.

        FLOW:

            Attempt 1
               │
               ├── Success → Return StepPlan
               │
               └── Error → Log, wait 1s
                      │
                      ▼
            Attempt 2
               │
               ├── Success → Return StepPlan
               │
               └── Error → Log, wait 2s
                      │
                      ▼
            Attempt 3
               │
               ├── Success → Return StepPlan
               │
               └── Error → Log, return None

        Args:
            *args: Arguments passed to StepPlanner.generate_step_plan_async
            max_retries (int): Maximum number of attempts. Default: 3.
                              Reasonable values: 2-5.
            **kwargs: Keyword arguments passed to StepPlanner.generate_step_plan_async

        Returns:
            Optional[StepPlan]: Plan if generated successfully, None otherwise.

        Note:
            Unlike the base class, this method:
            - Does not raise exceptions (catches everything)
            - Returns None on failure
            - Logs all attempts to stdout
        """

        # Loop over attempts
        for attempt in range(max_retries):
            try:
                # -------------------------------------------------------------
                # Attempt generation
                # -------------------------------------------------------------
                # Call base class method
                return await super().generate_step_plan_async(*args, **kwargs)

            except Exception as e:
                # ---------------------------------------------------------
                # Error handling
                # ---------------------------------------------------------

                if attempt == max_retries - 1:
                    # Last attempt failed - log and return None
                    logger.error(f"Step planning failed after {max_retries} attempts: {e}")
                    return None
                else:
                    # There are still attempts available
                    # Calculate wait time with exponential backoff
                    # 2^0 = 1s, 2^1 = 2s, 2^2 = 4s, ...
                    wait_time = 2 ** attempt

                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")

                    # Wait asynchronously (doesn't block other tasks)
                    await asyncio.sleep(wait_time)

        # Reached only if max_retries == 0 (edge case)
        return None
