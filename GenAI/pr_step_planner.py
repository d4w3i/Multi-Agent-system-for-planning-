"""
PR Step Planner - Multi-Agent System
=====================================

Multi-agent system for generating structured step plans
that can be compared with ground_truth.json.

================================================================================
USAGE GUIDE
================================================================================

1. REQUIREMENTS
---------------
- Python 3.10+
- OpenAI API key in .env file: OPENAI_API_KEY=sk-...
- Dependencies: openai, agents, pydantic, colorama, python-dotenv

2. REQUIRED PR DIRECTORY STRUCTURE
----------------------------------
The PR directory must have this structure:

    pr_XXX/
    ├── data.json                    # PR metadata (title, body, diff, etc.)
    ├── base_project/                # Repository snapshot
    │   ├── src/
    │   ├── README.md
    │   └── ...
    └── base_project/context_output/ # Context analysis output (optional)
        ├── masca_analysis.md        # MASCA analysis
        ├── call_graph.json          # Call graph
        └── context_files/           # Context files per function
            └── ...


3. CLI USAGE
------------
# Single PR
python -m GenAI.pr_step_planner <pr_directory>

# With options
python -m GenAI.pr_step_planner <pr_directory> -m gpt-5.2-2025-12-11 -o output.json -q

Options:
    -m, --model     OpenAI model (default: gpt-5.2-2025-12-11)
    -o, --output    Output file path (default: pr_dir/predicted_plan.json)
    -q, --quiet     Quiet mode


4. PYTHON USAGE
---------------
from GenAI.pr_step_planner import PRStepPlanner

# Initialize
planner = PRStepPlanner(
    pr_dir="PR4Code/dataset_pr_commits_py/owner_repo/pr_123/",
    model_name="gpt-5.2-2025-12-11",  # OpenAI model
    verbose=True                          # Detailed output
)

# Run and get dict + session log
output, session_log = planner.run_sync()

# Or run and save directly (saves predicted_plan.json, token_usage.json, session_log.json)
output_path, token_path, session_path = planner.save_output()  # Saves to pr_dir/
output_path, token_path, session_path = planner.save_output("custom_output.json")

# Async usage
import asyncio
output, session_log = asyncio.run(planner.run())


5. BATCH PROCESSING
-------------------
To process multiple PRs, use batch_predict.py:

# Process N PRs
python -m GenAI.batch_predict <base_path> --limit N

# Process all PRs
python -m GenAI.batch_predict <base_path> --all

# With options
python -m GenAI.batch_predict <base_path> --limit 10 -m gpt-5.2-2025-12-11 --skip-existing

See batch_predict.py for complete documentation.


6. OUTPUT FORMAT
----------------
The output is a JSON compatible with ground_truth.json:

{
    "pr_number": 123,
    "repository": "owner/repo",
    "title": "PR Title",
    "body": "PR Description",
    "extraction_metadata": {
        "extracted_at": "2024-01-15T10:30:00",
        "extractor_version": "2.0.0-multiagent",
        "success": true,
        "error_message": null
    },
    "files_modified": [
        {
            "filename": "src/module.py",
            "status": "modified",
            "additions": 0,
            "deletions": 0,
            "functions_modified": [
                {
                    "function_name": "my_function",
                    "class_name": null,
                    "full_name": "my_function",
                    "start_line": 0,
                    "end_line": 0,
                    "lines_changed": []
                }
            ]
        }
    ],
    "step_plan": {
        "summary": "Brief description of the PR changes",
        "steps": [
            {
                "operation": "Add validation method",
                "file_to_modify": "src/module.py",
                "function_to_modify": "ClassName.method_name",
                "reason": "To ensure input is validated before processing",
                "side_effects": "May require updating tests"
            }
        ]
    }
}


7. SESSION LOG FORMAT (session_log.json)
-----------------------------------------
Full session trace for dashboard consumption:

{
    "session_id": "pr123_20260225_143022",
    "pr_number": 123,
    "repository": "owner/repo",
    "model": "gpt-5.2-2025-12-11",
    "extractor_version": "2.0.0-multiagent",
    "started_at": "2026-02-25T14:30:22.123456",
    "completed_at": "2026-02-25T14:30:45.654321",
    "duration_seconds": 23.53,
    "success": true,
    "error": null,
    "context": {
        "pr_title": "...",
        "pr_body": "...",
        "masca_available": true,
        "masca_chars": 4500,
        "call_graph_available": true,
        "context_files_available": true
    },
    "agents": [
        {
            "name": "analysis_agent",
            "phase": 1,
            "started_at": "...",
            "completed_at": "...",
            "duration_seconds": 12.3,
            "system_prompt": "full system prompt text...",
            "system_prompt_chars": 3200,
            "input_prompt": "full user prompt text...",
            "input_prompt_chars": 650,
            "token_usage": { "requests": 4, "input_tokens": 2500, ... },
            "retry_count": 0,
            "retry_events": [],
            "tool_calls": [
                {
                    "index": 0,
                    "tool_name": "list_base_project_directory",
                    "arguments": { "directory": ".", "pattern": "*", "recursive": false },
                    "result": "full untruncated return value...",
                    "result_chars": 1200,
                    "truncated": false,
                    "called_at": "...",
                    "duration_seconds": 0.03
                }
            ],
            "output": { "files_to_modify": [...], "functions_to_modify": [...], ... }
        }
    ],
    "token_summary": {
        "total_requests": 8,
        "total_input_tokens": 5000,
        "total_output_tokens": 700,
        "total_tokens": 5700
    }
}


8. MULTI-AGENT ARCHITECTURE
---------------------------
The system uses two agents in sequence:

AGENT 1: Analysis Agent
    - Input: PR title + body
    - System prompt: Contains project's MASCA analysis
    - Tools:
        * read_base_project_file(path): Reads files from the project
        * list_base_project_directory(dir, pattern, recursive): Lists files
    - Output: AnalysisOutput with files_to_modify and functions_to_modify

AGENT 2: Context Planner Agent
    - Input: Agent 1's output (handoff)
    - Tools:
        * read_context_file(path): Reads pre-generated context files
        * list_context_files(dir, pattern): Lists context files
        * read_call_graph(section): Reads call graph (stats/functions/edges)
    - Output: PlannerOutput with detailed step_plan


9. LIMITS AND RATE LIMITING
---------------------------
- Files are truncated to 60,000 characters (~20k tokens) to avoid
  rate limit errors. The session_log.json stores the full untruncated
  content for dashboard inspection.
- If you receive error 429 (rate limit), try:
    * Use a model with higher limits
    * Wait a few minutes
    * Upgrade your OpenAI account tier


10. TROUBLESHOOTING
------------------
Error: "OPENAI_API_KEY not found"
    -> Create .env file with: OPENAI_API_KEY=sk-...

Error: "data.json not found"
    -> Verify that the PR directory contains data.json

Error: "base_project not found"
    -> Verify that the PR directory contains base_project/

Error 429 (rate limit)
    -> Use -m gpt-5.2-2025-12-11 or wait a few minutes

Error "attempted relative import"
    -> Run from project root, not from the GenAI folder


================================================================================

"""

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
)

from colorama import Fore, Style, init

# Import existing implementations from tools.py to avoid duplication
from GenAI.tools import _read_file_impl, _list_directory_impl, _read_text_file
from GenAI.prompts import get_analysis_agent_prompt, CONTEXT_PLANNER_PROMPT
from GenAI.utils import run_async_safely
from GenAI.config_loader import load_config
from evaluation.models import Step, StepPlan

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

# Maximum characters sent per file to agents, to stay within rate limits.
# ~60 k chars ≈ 20 k tokens, a safe ceiling for gpt-5.2-2025-12-11 context windows.
# NOTE: session_log.json stores the full untruncated content regardless.
MAX_FILE_CHARS: int = 60_000

# =============================================================================
# PYDANTIC MODELS - Structured I/O


class FunctionToModify(BaseModel):
    """Function identified as a modification target."""

    function_name: str = Field(
        description="Function name (e.g., 'my_function' or 'ClassName.method_name')"
    )
    file_path: str = Field(
        description="Relative path of the file containing the function"
    )
    reason: str = Field(description="Reason why this function needs to be modified")


class FileToModify(BaseModel):
    """File identified as a modification target."""

    file_path: str = Field(description="Relative path of the file to modify")
    reason: str = Field(description="Reason why this file needs to be modified")


class AnalysisOutput(BaseModel):
    """Structured output of the Analysis Agent."""

    pr_title: str = Field(description="Pull request title")
    pr_body: str = Field(description="Pull request body/description")
    masca_optimized: str = Field(
        description="MASCA analysis optimized and focused on the specific PR"
    )
    files_to_modify: List[FileToModify] = Field(description="List of files to modify")
    functions_to_modify: List[FunctionToModify] = Field(
        description="List of functions to modify"
    )
    analysis_summary: str = Field(description="Summary of the analysis conducted")


class PlannerOutput(BaseModel):
    """Final output of the multi-agent system."""

    step_plan: StepPlan = Field(description="Complete implementation plan")


class AgentTokenUsage(BaseModel):
    """Token usage for a single agent."""

    agent_name: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class TokenUsageReport(BaseModel):
    """Complete token usage report for a PR run (backward-compatible output)."""

    pr_number: int
    repository: str
    timestamp: str
    model_name: str
    agents: List[AgentTokenUsage]
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    duration_seconds: Optional[float] = None


# =============================================================================
# SESSION LOG MODELS - Full trace for dashboard consumption


class ToolCallSummarization(BaseModel):
    """Details of the LLM call made to summarize a file read."""

    model: str
    system_prompt: str
    user_prompt: str  # includes reason + expected_information + raw file content
    summary: str  # LLM response text
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_seconds: float
    error: Optional[str] = None  # set if the LLM call failed


class ToolCall(BaseModel):
    """A single tool invocation captured during an agent run."""

    index: int
    tool_name: str
    arguments: dict
    raw_result: Optional[str] = None  # original file content before summarization
    result: str  # what the agent received (summary, or raw on error)
    result_chars: int
    truncated: (
        bool  # True if raw_result was truncated before being fed to the summarizer
    )
    called_at: str  # ISO timestamp
    duration_seconds: float
    summarization: Optional[ToolCallSummarization] = (
        None  # present only for read_base_project_file
    )


class RetryEvent(BaseModel):
    """A retry attempt that occurred during agent execution."""

    attempt: int
    error_type: str
    error_message: str
    timestamp: str
    waited_seconds: float


class AgentSession(BaseModel):
    """Complete trace for a single agent phase."""

    name: str
    phase: int
    started_at: str
    completed_at: str
    duration_seconds: float
    system_prompt: str
    system_prompt_chars: int
    input_prompt: str
    input_prompt_chars: int
    token_usage: AgentTokenUsage
    retry_count: int
    retry_events: List[RetryEvent]
    tool_calls: List[ToolCall]
    output: dict  # agent final output serialized via model_dump()


class SessionContext(BaseModel):
    """Context availability and full PR input data."""

    pr_title: str
    pr_body: str  # full body, no truncation
    masca_available: bool
    masca_chars: int
    call_graph_available: bool
    context_files_available: bool
    ablation: bool = False


class SessionLog(BaseModel):
    """
    Complete session log for a PR pipeline run.
    Saved as session_log.json — primary data source for the dashboard.
    """

    session_id: str
    pr_number: int
    repository: str
    model: str
    extractor_version: str
    started_at: str
    completed_at: str
    duration_seconds: float
    success: bool
    error: Optional[str]
    context: SessionContext
    agents: List[AgentSession]
    token_summary: dict


# =============================================================================
# TOOL FACTORY - Creates sandboxed tools for agents


def create_base_project_tools(
    base_project_path: Path,
    tool_call_log: list,
    client: AsyncOpenAI,
    model_name: str,
):
    """
    Create sandboxed tools for the Analysis Agent.
    Allows only access to base_project directory.
    Reuses _read_file_impl and _list_directory_impl from tools.py.

    tool_call_log: mutable list — each tool call appends a ToolCall-compatible dict.
    client / model_name: used by read_base_project_file to summarize file content via LLM.
    """
    base_dir_str = str(base_project_path.resolve())

    _SUMMARIZER_SYSTEM_PROMPT = (
        "You are a code analysis assistant. Your task is to summarize source code files "
        "for an AI agent that is planning code modifications for a Pull Request.\n\n"
        "Your summary MUST:\n"
        "1. Preserve ALL exact function names, class names, and method names exactly as "
        "they appear in the source code — never rename or abbreviate them.\n"
        "2. Explain the overall architecture and purpose of the file.\n"
        "3. Describe the role and importance of each function, class, and method.\n"
        "4. Highlight the parts most relevant to the agent's stated goal.\n\n"
        "Format your response with these sections:\n"
        "### File Overview\n"
        "[1-2 sentences on the file's purpose]\n\n"
        "### Architecture\n"
        "[How the main components are organised and interact]\n\n"
        "### Functions & Classes\n"
        "[For each function/class/method: `exact_name` — description and its importance]\n\n"
        "### Relevance to Agent's Goal\n"
        "[How this file relates to the agent's reason for reading it]"
    )

    @function_tool
    async def read_base_project_file(
        file_path: str,
        reason: str,
        expected_information: str,
    ) -> str:
        """
        Read and summarize a file from the base_project directory.

        An LLM will summarize the file content, preserving all exact function and
        class names while explaining the architecture and the role of each symbol.

        Args:
            file_path: Relative path to the file inside base_project.
                       E.g.: "src/module.py", "README.md"
            reason: Why you are reading this file (used to focus the summary).
            expected_information: What specific information you expect to find.

        Returns:
            LLM-generated summary of the file, or an error message.
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}🔧 TOOL: read_base_project_file")
        print(f"{Fore.CYAN}   📥 file_path:             {file_path}")
        print(f"{Fore.CYAN}   📥 reason:                {reason[:120]}")
        print(
            f"{Fore.CYAN}   📥 expected_information:  {expected_information[:120]}{Style.RESET_ALL}"
        )

        full_path = str(base_project_path / file_path)
        raw_content = _read_file_impl(
            file_path=full_path,
            base_dir=base_dir_str,
            include_metadata=False,
            verbose=False,
        )

        is_error = raw_content.startswith("❌")

        if is_error:
            duration = round(time.perf_counter() - t0, 4)
            tool_call_log.append(
                {
                    "index": len(tool_call_log),
                    "tool_name": "read_base_project_file",
                    "arguments": {
                        "file_path": file_path,
                        "reason": reason,
                        "expected_information": expected_information,
                    },
                    "raw_result": raw_content,
                    "result": raw_content,
                    "result_chars": len(raw_content),
                    "truncated": False,
                    "called_at": called_at,
                    "duration_seconds": duration,
                    "summarization": None,
                }
            )
            print(f"{Fore.RED}   {raw_content}{Style.RESET_ALL}")
            return raw_content

        lines = raw_content.count("\n") + 1
        content_for_llm = raw_content

        print(
            f"{Fore.CYAN}   📄 {lines} lines read — requesting LLM summary...{Style.RESET_ALL}"
        )

        user_prompt = (
            f"## File: {file_path}\n\n"
            f"## Agent's reason for reading this file:\n{reason}\n\n"
            f"## What the agent expects to find:\n{expected_information}\n\n"
            f"## Source Code:\n{content_for_llm}"
        )

        t_llm = time.perf_counter()
        summarization_data: dict
        result: str
        truncated: bool = False

        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _SUMMARIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            summary = response.choices[0].message.content or ""
            llm_duration = round(time.perf_counter() - t_llm, 4)
            usage = response.usage

            summarization_data = {
                "model": model_name,
                "system_prompt": _SUMMARIZER_SYSTEM_PROMPT,
                "user_prompt": user_prompt,
                "summary": summary,
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
                "duration_seconds": llm_duration,
                "error": None,
            }
            result = summary
            print(
                f"{Fore.GREEN}   ✅ Summary generated ({len(summary)} chars, {summarization_data['total_tokens']} tokens){Style.RESET_ALL}"
            )

        except Exception as e:
            llm_duration = round(time.perf_counter() - t_llm, 4)
            print(
                f"{Fore.YELLOW}   ⚠️  Summarization failed ({e}) — falling back to raw content{Style.RESET_ALL}"
            )

            # Fallback: truncated raw content so the agent still gets something useful
            truncated = len(raw_content) > MAX_FILE_CHARS
            result = (
                raw_content[:MAX_FILE_CHARS]
                + f"\n\n... [TRUNCATED: showing first {MAX_FILE_CHARS} of {len(raw_content)} chars] ..."
                if truncated
                else raw_content
            )
            summarization_data = {
                "model": model_name,
                "system_prompt": _SUMMARIZER_SYSTEM_PROMPT,
                "user_prompt": user_prompt,
                "summary": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "duration_seconds": llm_duration,
                "error": str(e),
            }

        duration = round(time.perf_counter() - t0, 4)
        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "read_base_project_file",
                "arguments": {
                    "file_path": file_path,
                    "reason": reason,
                    "expected_information": expected_information,
                },
                "raw_result": raw_content,  # full original file content
                "result": result,  # LLM summary (what the agent receives)
                "result_chars": len(result),
                "truncated": truncated,
                "called_at": called_at,
                "duration_seconds": duration,
                "summarization": summarization_data,
            }
        )

        return result

    @function_tool
    def list_base_project_directory(
        directory: str = ".", pattern: str = "*", recursive: bool = False
    ) -> str:
        """
        List files and folders in the base_project directory.

        Args:
            directory: Subdirectory to explore (relative to base_project)
            pattern: Glob pattern (e.g., "*.py", "*.{py,js}")
            recursive: If True, search recursively

        Returns:
            Formatted list of files
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}TOOL: list_base_project_directory")
        print(f"{Fore.CYAN}   directory: {directory}")
        print(f"{Fore.CYAN}   pattern: {pattern}")
        print(f"{Fore.CYAN}   recursive: {recursive}{Style.RESET_ALL}")

        full_dir = str(base_project_path / directory)

        result = _list_directory_impl(
            dir_path=full_dir,
            pattern=pattern,
            recursive=recursive,
            base_dir=base_dir_str,
            show_hidden=False,
            max_items=150,
            verbose=False,
        )

        duration = round(time.perf_counter() - t0, 4)

        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "list_base_project_directory",
                "arguments": {
                    "directory": directory,
                    "pattern": pattern,
                    "recursive": recursive,
                },
                "result": result,
                "result_chars": len(result),
                "truncated": False,
                "called_at": called_at,
                "duration_seconds": duration,
            }
        )

        if not result.startswith("❌"):
            print(f"{Fore.GREEN}   Directory listed{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}   {result}{Style.RESET_ALL}")

        return result

    return [read_base_project_file, list_base_project_directory]


def create_base_project_tools_ablation(
    base_project_path: Path,
    tool_call_log: list,
):
    """
    Ablation variant of create_base_project_tools.
    Returns raw truncated file content directly — no LLM summarization.
    Tool signature is reduced to file_path only (no reason / expected_information).
    """
    base_dir_str = str(base_project_path.resolve())

    @function_tool
    def read_base_project_file(file_path: str) -> str:
        """
        Read a file from the base_project directory and return its raw content.
        Large files are truncated to 60,000 characters.

        Args:
            file_path: Relative path inside base_project
                       (e.g. "src/module.py", "README.md")

        Returns:
            Raw file content, or an error message starting with ❌.
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}🔧 TOOL [ablation]: read_base_project_file")
        print(f"{Fore.CYAN}   📥 file_path: {file_path}{Style.RESET_ALL}")

        full_path = str(base_project_path / file_path)
        raw_content = _read_file_impl(
            file_path=full_path,
            base_dir=base_dir_str,
            include_metadata=False,
            verbose=False,
        )

        is_error = raw_content.startswith("❌")
        duration = round(time.perf_counter() - t0, 4)

        if is_error:
            tool_call_log.append(
                {
                    "index": len(tool_call_log),
                    "tool_name": "read_base_project_file",
                    "arguments": {"file_path": file_path},
                    "raw_result": raw_content,
                    "result": raw_content,
                    "result_chars": len(raw_content),
                    "truncated": False,
                    "called_at": called_at,
                    "duration_seconds": duration,
                    "summarization": None,
                }
            )
            print(f"{Fore.RED}   {raw_content}{Style.RESET_ALL}")
            return raw_content

        truncated = len(raw_content) > MAX_FILE_CHARS
        result = (
            raw_content[:MAX_FILE_CHARS]
            + f"\n\n... [TRUNCATED: showing first {MAX_FILE_CHARS} of {len(raw_content)} chars] ..."
            if truncated
            else raw_content
        )
        lines = raw_content.count("\n") + 1
        print(
            f"{Fore.GREEN}   ✅ {lines} lines read (raw, no summarizer){Style.RESET_ALL}"
        )

        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "read_base_project_file",
                "arguments": {"file_path": file_path},
                "raw_result": raw_content,
                "result": result,
                "result_chars": len(result),
                "truncated": truncated,
                "called_at": called_at,
                "duration_seconds": duration,
                "summarization": None,
            }
        )
        return result

    @function_tool
    def list_base_project_directory(
        directory: str = ".", pattern: str = "*", recursive: bool = False
    ) -> str:
        """
        List files and folders in the base_project directory.

        Args:
            directory: Subdirectory to explore (relative to base_project)
            pattern: Glob pattern (e.g., "*.py")
            recursive: If True, search recursively

        Returns:
            Formatted list of files
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}TOOL: list_base_project_directory")
        print(
            f"{Fore.CYAN}   directory: {directory} | pattern: {pattern} | recursive: {recursive}{Style.RESET_ALL}"
        )

        full_dir = str(base_project_path / directory)
        result = _list_directory_impl(
            dir_path=full_dir,
            pattern=pattern,
            recursive=recursive,
            base_dir=base_dir_str,
            show_hidden=False,
            max_items=150,
            verbose=False,
        )

        duration = round(time.perf_counter() - t0, 4)
        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "list_base_project_directory",
                "arguments": {
                    "directory": directory,
                    "pattern": pattern,
                    "recursive": recursive,
                },
                "result": result,
                "result_chars": len(result),
                "truncated": False,
                "called_at": called_at,
                "duration_seconds": duration,
            }
        )
        if not result.startswith("❌"):
            print(f"{Fore.GREEN}   Directory listed{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}   {result}{Style.RESET_ALL}")
        return result

    return [read_base_project_file, list_base_project_directory]


def create_context_files_tools(context_output_path: Path, tool_call_log: list):
    """
    Create sandboxed tools for the Context Planner Agent.
    Allows only access to context_output/context_files directory.
    Reuses _read_file_impl and _list_directory_impl from tools.py.

    tool_call_log: mutable list — each tool call appends a ToolCall-compatible dict.
    """
    context_files_path = context_output_path / "context_files"
    base_dir_str = (
        str(context_files_path.resolve())
        if context_files_path.exists()
        else str(context_output_path.resolve())
    )

    @function_tool
    def read_context_file(file_path: str) -> str:
        """
        Read a pre-generated context file.

        Args:
            file_path: Relative path to the context file
                      E.g.: "src/module/function_name_context.txt"

        Returns:
            Context file content or error message.
            Very large files are truncated.
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}🔧 TOOL: read_context_file")
        print(f"{Fore.CYAN}   📥 file_path: {file_path}{Style.RESET_ALL}")

        if not context_files_path.exists():
            result = f"❌ context_files directory not found in {context_output_path}"
            duration = round(time.perf_counter() - t0, 4)
            tool_call_log.append(
                {
                    "index": len(tool_call_log),
                    "tool_name": "read_context_file",
                    "arguments": {"file_path": file_path},
                    "result": result,
                    "result_chars": len(result),
                    "truncated": False,
                    "called_at": called_at,
                    "duration_seconds": duration,
                }
            )
            return result

        full_path = str(context_files_path / file_path)

        result = _read_file_impl(
            file_path=full_path,
            base_dir=base_dir_str,
            include_metadata=False,
            verbose=False,
        )

        duration = round(time.perf_counter() - t0, 4)
        is_error = result.startswith("❌")
        will_truncate = not is_error and len(result) > MAX_FILE_CHARS

        # Log with full untruncated result
        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "read_context_file",
                "arguments": {"file_path": file_path},
                "result": result,
                "result_chars": len(result),
                "truncated": will_truncate,
                "called_at": called_at,
                "duration_seconds": duration,
            }
        )

        if not is_error:
            lines = result.count("\n") + 1
            if will_truncate:
                truncated_lines = result[:MAX_FILE_CHARS].count("\n") + 1
                result = (
                    result[:MAX_FILE_CHARS]
                    + f"\n\n... [TRUNCATED: file too large, showing {truncated_lines}/{lines} lines] ..."
                )
                print(
                    f"{Fore.YELLOW}   ⚠️ Read and TRUNCATED: {truncated_lines}/{lines} lines{Style.RESET_ALL}"
                )
            else:
                print(f"{Fore.GREEN}   ✅ Read: {lines} lines{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}   {result}{Style.RESET_ALL}")

        return result

    @function_tool
    def list_context_files(directory: str = ".", pattern: str = "*_context.txt") -> str:
        """
        List available context files.

        Args:
            directory: Subdirectory to explore
            pattern: Glob pattern (default: *_context.txt)

        Returns:
            List of context files found
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}🔧 TOOL: list_context_files")
        print(f"{Fore.CYAN}   📥 directory: {directory}")
        print(f"{Fore.CYAN}   📥 pattern: {pattern}{Style.RESET_ALL}")

        if not context_files_path.exists():
            result = f"❌ context_files directory not found in {context_output_path}"
            duration = round(time.perf_counter() - t0, 4)
            tool_call_log.append(
                {
                    "index": len(tool_call_log),
                    "tool_name": "list_context_files",
                    "arguments": {"directory": directory, "pattern": pattern},
                    "result": result,
                    "result_chars": len(result),
                    "truncated": False,
                    "called_at": called_at,
                    "duration_seconds": duration,
                }
            )
            return result

        full_dir = (
            str(context_files_path / directory)
            if directory != "."
            else str(context_files_path)
        )

        result = _list_directory_impl(
            dir_path=full_dir,
            pattern=pattern,
            recursive=True,
            base_dir=base_dir_str,
            show_hidden=False,
            max_items=200,
            verbose=False,
        )

        duration = round(time.perf_counter() - t0, 4)

        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "list_context_files",
                "arguments": {"directory": directory, "pattern": pattern},
                "result": result,
                "result_chars": len(result),
                "truncated": False,
                "called_at": called_at,
                "duration_seconds": duration,
            }
        )

        if not result.startswith("❌"):
            print(f"{Fore.GREEN}   ✅ Context files listed{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}   {result}{Style.RESET_ALL}")

        return result

    @function_tool
    def read_call_graph(section: str = "all") -> str:
        """
        Read information from the generated call graph.

        Args:
            section: Section to read:
                    - "all": Complete JSON (can be large)
                    - "stats": Statistics only
                    - "functions": List of functions
                    - "edges": List of caller-callee relationships

        Returns:
            Information from the call graph
        """
        called_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        print(f"\n{Fore.CYAN}🔧 TOOL: read_call_graph")
        print(f"{Fore.CYAN}   📥 section: {section}{Style.RESET_ALL}")

        call_graph_path = context_output_path / "call_graph.json"

        if not call_graph_path.exists():
            result = "❌ call_graph.json not found"
            duration = round(time.perf_counter() - t0, 4)
            tool_call_log.append(
                {
                    "index": len(tool_call_log),
                    "tool_name": "read_call_graph",
                    "arguments": {"section": section},
                    "result": result,
                    "result_chars": len(result),
                    "truncated": False,
                    "called_at": called_at,
                    "duration_seconds": duration,
                }
            )
            return result

        try:
            with open(call_graph_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            result = f"❌ Error reading call_graph.json: {e}"
            duration = round(time.perf_counter() - t0, 4)
            tool_call_log.append(
                {
                    "index": len(tool_call_log),
                    "tool_name": "read_call_graph",
                    "arguments": {"section": section},
                    "result": result,
                    "result_chars": len(result),
                    "truncated": False,
                    "called_at": called_at,
                    "duration_seconds": duration,
                }
            )
            return result

        if section == "stats":
            result = json.dumps(data.get("stats", {}), indent=2)

        elif section == "functions":
            funcs = list(data.get("functions", {}).keys())
            result = f"📊 {len(funcs)} functions found:\n" + "\n".join(
                f"  - {f}" for f in funcs[:100]
            )

        elif section == "edges":
            edges = data.get("edges", [])[:100]
            output_lines = [
                f"📊 {len(data.get('edges', []))} relationships (showing first 100):"
            ]
            for edge in edges:
                output_lines.append(f"  {edge['from']} -> {edge['to']}")
            result = "\n".join(output_lines)

        else:
            result = json.dumps(data, indent=2)[:50000]

        duration = round(time.perf_counter() - t0, 4)

        tool_call_log.append(
            {
                "index": len(tool_call_log),
                "tool_name": "read_call_graph",
                "arguments": {"section": section},
                "result": result,
                "result_chars": len(result),
                "truncated": False,
                "called_at": called_at,
                "duration_seconds": duration,
            }
        )

        return result

    return [read_context_file, list_context_files, read_call_graph]


# =============================================================================
# AGENT FACTORY


def create_analysis_agent(
    client: AsyncOpenAI,
    model_name: str,
    summarizer_model_name: str,
    masca_analysis: str,
    base_project_path: Path,
    tool_call_log: list,
    ablation: bool = False,
) -> Agent:
    """
    Create the Analysis Agent.

    This agent:
    1. Receives PR title and body
    2. Has access to MASCA context in the system prompt
    3. Can navigate and read files in base_project
    4. Produces structured output with files and functions to modify

    model_name: model used by this agent.
    summarizer_model_name: model used by read_base_project_file to summarize files.
    tool_call_log: shared mutable list for capturing tool invocations.
    """

    MODEL = OpenAIChatCompletionsModel(model=model_name, openai_client=client)

    if ablation:
        tools = create_base_project_tools_ablation(base_project_path, tool_call_log)
    else:
        tools = create_base_project_tools(
            base_project_path, tool_call_log, client, summarizer_model_name
        )

    instructions = get_analysis_agent_prompt(masca_analysis)

    return Agent(
        name="analysis_agent",
        instructions=instructions,
        tools=tools,
        model=MODEL,
        model_settings=ModelSettings(),
        output_type=AnalysisOutput,
    )


def create_context_planner_agent(
    client: AsyncOpenAI, model_name: str, context_output_path: Path, tool_call_log: list
) -> Agent:
    """
    Create the Context Planner Agent.

    This agent:
    1. Receives the Analysis Agent's output
    2. Uses context files to understand dependencies
    3. Generates detailed step plan for each function

    tool_call_log: shared mutable list for capturing tool invocations.
    """

    MODEL = OpenAIChatCompletionsModel(model=model_name, openai_client=client)

    tools = create_context_files_tools(context_output_path, tool_call_log)

    instructions = CONTEXT_PLANNER_PROMPT

    return Agent(
        name="context_planner_agent",
        instructions=instructions,
        tools=tools,
        model=MODEL,
        model_settings=ModelSettings(),
        output_type=PlannerOutput,
    )


# =============================================================================
# MAIN ORCHESTRATOR


class PRStepPlanner:
    """
    Multi-agent system orchestrator.

    Manages the flow:
    1. Load PR data and MASCA analysis
    2. Run Analysis Agent
    3. Run Context Planner Agent
    4. Generate JSON output compatible with ground_truth.json
    5. Generate session_log.json with full trace for dashboard consumption
    """

    def __init__(
        self,
        pr_dir: str,
        model_name: Optional[str] = None,
        verbose: bool = True,
        ablation: bool = False,
        eval_dir: Optional[Path] = None,
    ):
        """
        Initialize the planner.

        Args:
            pr_dir: Path to the PR directory (e.g., PR4Code/dataset_pr_commits_py/owner_repo/pr_123/)
            model_name: When provided, overrides the model for ALL agents in the
                        pipeline (analysis, context_planner, file_summarizer).
                        When omitted, per-agent models are loaded from
                        GenAI/agents_config.toml.
            verbose: If True, print detailed output
            ablation: If True, use raw file content instead of LLM summaries and
                      strip reason/expected_information from the tool schema.
            eval_dir: Optional consolidated output folder (e.g. Path("gpt_5-2_evals/ablation_turn_2")).
                      When set, save_output() copies results there under
                      <owner_repo>/<pr_NUMBER>/, mirroring the gpt_5-2_evals layout.
                      Only used when ablation=True.
        """
        self.pr_dir = Path(pr_dir).resolve()
        self.verbose = verbose
        self.ablation = ablation
        self.eval_dir = Path(eval_dir).resolve() if eval_dir else None

        # Resolve per-agent models from config, with optional CLI-level override
        cfg = load_config()
        if model_name:
            # Single override applies to every agent
            self.model_analysis = model_name
            self.model_context_planner = model_name
            self.model_file_summarizer = model_name
        else:
            self.model_analysis = cfg.agents.analysis.model
            self.model_context_planner = cfg.agents.context_planner.model
            self.model_file_summarizer = cfg.agents.file_summarizer.model

        # model_name kept for session-level display and backward compat
        self.model_name = model_name or cfg.defaults.model

        # Paths
        self.data_json_path = self.pr_dir / "data.json"
        self.base_project_path = self.pr_dir / "base_project"
        self.context_output_path = self.base_project_path / "context_output"
        self.masca_path = self.context_output_path / "masca_analysis.md"

        # Validate
        self._validate_paths()

        # Load data
        self.pr_data = self._load_pr_data()
        self.masca_analysis = self._load_masca_analysis()

        # OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")
        self.client = AsyncOpenAI(api_key=api_key, timeout=120.0)

    def _validate_paths(self):
        """Validate that all required paths exist."""
        if not self.pr_dir.exists():
            raise FileNotFoundError(f"PR directory not found: {self.pr_dir}")

        if not self.data_json_path.exists():
            raise FileNotFoundError(f"data.json not found: {self.data_json_path}")

        if not self.base_project_path.exists():
            raise FileNotFoundError(f"base_project not found: {self.base_project_path}")

    def _load_pr_data(self) -> dict:
        """Load PR data from data.json."""
        with open(self.data_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_masca_analysis(self) -> str:
        """Load MASCA analysis if available."""
        if self.masca_path.exists():
            return _read_text_file(self.masca_path)

        # Fallback: generate base MASCA from project_tree.txt and README
        tree_path = self.context_output_path / "project_tree.txt"

        masca = "## Project Analysis\n\n"

        if tree_path.exists():
            tree = _read_text_file(tree_path)
            masca += f"### Directory Structure\n```\n{tree[:5000]}\n```\n\n"

        # Search for README in base_project
        readme_paths = [
            self.base_project_path / "README.md",
            self.base_project_path / "README.txt",
            self.base_project_path / "README",
        ]

        for readme_path in readme_paths:
            if readme_path.exists():
                readme = _read_text_file(readme_path)
                masca += f"### README\n{readme[:3000]}\n"
                break

        return (
            masca
            if masca != "## Project Analysis\n\n"
            else "MASCA analysis not available"
        )

    async def _run_analysis_agent(self) -> tuple[AnalysisOutput, AgentSession]:
        """Run the Analysis Agent. Returns (final_output, full AgentSession trace)."""
        if self.verbose:
            print(f"\n{Fore.YELLOW}{'='*80}")
            print(f"{Fore.YELLOW}🔍 PHASE 1: Analysis Agent")
            print(f"{Fore.YELLOW}{'='*80}{Style.RESET_ALL}")

        tool_call_log: list = []

        agent = create_analysis_agent(
            self.client,
            self.model_analysis,
            self.model_file_summarizer,
            self.masca_analysis,
            self.base_project_path,
            tool_call_log,
            ablation=self.ablation,
        )

        pr_title = self.pr_data.get("title", "")
        pr_body = self.pr_data.get("body", "") or ""

        # Sanitize PR data to limit prompt injection surface
        safe_title = (pr_title or "")[:500]
        safe_body = (pr_body or "")[:5000]

        system_prompt = get_analysis_agent_prompt(self.masca_analysis)
        input_prompt = f"""Analyze this Pull Request:

## Title
{safe_title}

## Description
{safe_body}

Explore the source code to identify the files and functions to modify."""

        started_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        retry_events: list[dict] = []
        last_error = None
        for attempt in range(3):
            try:
                result = await Runner.run(agent, input_prompt, max_turns=1000)
                break
            except Exception as e:
                last_error = e
                waited = float(2**attempt)
                retry_events.append(
                    {
                        "attempt": attempt,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "timestamp": datetime.now().isoformat(),
                        "waited_seconds": waited,
                    }
                )
                if attempt < 2:
                    await asyncio.sleep(waited)
        else:
            raise last_error

        duration = round(time.perf_counter() - t0, 4)
        completed_at = datetime.now().isoformat()

        usage = result.context_wrapper.usage
        token_usage = AgentTokenUsage(
            agent_name="analysis_agent",
            requests=usage.requests,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

        if self.verbose:
            print(f"\n{Fore.GREEN}✅ Analysis Agent completed{Style.RESET_ALL}")

        final_output: AnalysisOutput = result.final_output
        output_dict = final_output.model_dump()

        session = AgentSession(
            name="analysis_agent",
            phase=1,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            system_prompt=system_prompt,
            system_prompt_chars=len(system_prompt),
            input_prompt=input_prompt,
            input_prompt_chars=len(input_prompt),
            token_usage=token_usage,
            retry_count=len(retry_events),
            retry_events=[RetryEvent(**e) for e in retry_events],
            tool_calls=[ToolCall(**tc) for tc in tool_call_log],
            output=output_dict,
        )

        return final_output, session

    async def _run_context_planner_agent(
        self, analysis: AnalysisOutput
    ) -> tuple[PlannerOutput, AgentSession]:
        """Run the Context Planner Agent. Returns (final_output, full AgentSession trace)."""
        if self.verbose:
            print(f"\n{Fore.YELLOW}{'='*80}")
            print(f"{Fore.YELLOW}📋 PHASE 2: Context Planner Agent")
            print(f"{Fore.YELLOW}{'='*80}{Style.RESET_ALL}")

        tool_call_log: list = []

        agent = create_context_planner_agent(
            self.client,
            self.model_context_planner,
            self.context_output_path,
            tool_call_log,
        )

        # Prepare prompt with analysis data
        files_list = "\n".join(
            [f"- {f.file_path}: {f.reason}" for f in analysis.files_to_modify]
        )

        functions_list = "\n".join(
            [
                f"- {f.function_name} ({f.file_path}): {f.reason}"
                for f in analysis.functions_to_modify
            ]
        )

        system_prompt = CONTEXT_PLANNER_PROMPT
        input_prompt = f"""Generate an implementation plan for this PR:

## PR Title
{analysis.pr_title}

## PR Body
{analysis.pr_body}

## MASCA Analysis (optimized)
{analysis.masca_optimized}

## Files to Modify
{files_list}

## Functions to Modify
{functions_list}

## Analysis Summary
{analysis.analysis_summary}

Use the context files to understand dependencies and generate a detailed step-by-step plan."""

        started_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        retry_events: list[dict] = []
        last_error = None
        for attempt in range(3):
            try:
                result = await Runner.run(agent, input_prompt, max_turns=1000)
                break
            except Exception as e:
                last_error = e
                waited = float(2**attempt)
                retry_events.append(
                    {
                        "attempt": attempt,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "timestamp": datetime.now().isoformat(),
                        "waited_seconds": waited,
                    }
                )
                if attempt < 2:
                    await asyncio.sleep(waited)
        else:
            raise last_error

        duration = round(time.perf_counter() - t0, 4)
        completed_at = datetime.now().isoformat()

        usage = result.context_wrapper.usage
        token_usage = AgentTokenUsage(
            agent_name="context_planner_agent",
            requests=usage.requests,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

        if self.verbose:
            print(f"\n{Fore.GREEN}✅ Context Planner Agent completed{Style.RESET_ALL}")

        final_output: PlannerOutput = result.final_output
        output_dict = final_output.model_dump()

        session = AgentSession(
            name="context_planner_agent",
            phase=2,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            system_prompt=system_prompt,
            system_prompt_chars=len(system_prompt),
            input_prompt=input_prompt,
            input_prompt_chars=len(input_prompt),
            token_usage=token_usage,
            retry_count=len(retry_events),
            retry_events=[RetryEvent(**e) for e in retry_events],
            tool_calls=[ToolCall(**tc) for tc in tool_call_log],
            output=output_dict,
        )

        return final_output, session

    def _generate_output_json(
        self, analysis: AnalysisOutput, planner: PlannerOutput
    ) -> dict:
        """
        Generate final JSON compatible with ground_truth.json.
        """
        # data.json uses "pull_request_number", ground_truth uses "pr_number"
        pr_num = self.pr_data.get("pull_request_number") or self.pr_data.get(
            "number", 0
        )

        return {
            "pr_number": pr_num,
            "repository": self.pr_data.get("repository", "unknown/unknown"),
            "title": analysis.pr_title,
            "body": analysis.pr_body,
            "extraction_metadata": {
                "extracted_at": datetime.now().isoformat(),
                "extractor_version": "2.0.0-multiagent",
                "success": True,
                "error_message": None,
            },
            "files_modified": [
                {
                    "filename": f.file_path,
                    "status": "modified",
                    "additions": 0,  # Cannot estimate without diff
                    "deletions": 0,
                    "functions_modified": [
                        {
                            "function_name": func.function_name.split(".")[-1],
                            "class_name": (
                                func.function_name.split(".")[0]
                                if "." in func.function_name
                                else None
                            ),
                            "full_name": func.function_name,
                            "start_line": 0,  # Not available without AST
                            "end_line": 0,
                            "lines_changed": [],
                        }
                        for func in analysis.functions_to_modify
                        if func.file_path == f.file_path
                    ],
                }
                for f in analysis.files_to_modify
            ],
            "step_plan": {
                "summary": planner.step_plan.summary,
                "steps": [
                    {
                        "operation": step.operation,
                        "file_to_modify": step.file_to_modify,
                        "function_to_modify": step.function_to_modify,
                        "reason": step.reason,
                        "side_effects": step.side_effects,
                    }
                    for step in planner.step_plan.steps
                ],
            },
        }

    async def run(self) -> tuple[dict, SessionLog]:
        """
        Run the complete pipeline.

        Returns:
            Tuple of (output_dict, session_log)
            - output_dict: JSON output compatible with ground_truth.json
            - session_log: Full session trace including all tool calls, prompts,
                           timings, and token usage — intended for dashboard consumption
        """
        if self.verbose:
            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"{Fore.CYAN}🚀 PR Step Planner - Multi-Agent System")
            print(f"{Fore.CYAN}{'='*80}")
            print(f"{Fore.CYAN}📁 PR Directory: {self.pr_dir}")
            print(f"{Fore.CYAN}🤖 Model: {self.model_name}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

        pr_num = self.pr_data.get("pull_request_number") or self.pr_data.get(
            "number", 0
        )
        pipeline_started_at = datetime.now().isoformat()
        t0_pipeline = time.perf_counter()

        # Phase 1: Analysis Agent
        analysis, agent1_session = await self._run_analysis_agent()

        # Phase 2: Context Planner Agent
        planner, agent2_session = await self._run_context_planner_agent(analysis)

        pipeline_duration = round(time.perf_counter() - t0_pipeline, 4)
        pipeline_completed_at = datetime.now().isoformat()

        # Generate final output
        output = self._generate_output_json(analysis, planner)

        # Token summary
        a1 = agent1_session.token_usage
        a2 = agent2_session.token_usage
        token_summary = {
            "total_requests": a1.requests + a2.requests,
            "total_input_tokens": a1.input_tokens + a2.input_tokens,
            "total_output_tokens": a1.output_tokens + a2.output_tokens,
            "total_tokens": a1.total_tokens + a2.total_tokens,
        }

        # Session ID: pr{number}_{date}_{time}
        compact_ts = (
            pipeline_started_at[:19].replace("-", "").replace("T", "_").replace(":", "")
        )
        session_id = f"pr{pr_num}_{compact_ts}"

        session_log = SessionLog(
            session_id=session_id,
            pr_number=pr_num,
            repository=self.pr_data.get("repository", "unknown/unknown"),
            model=self.model_name,
            extractor_version="2.0.0-multiagent",
            started_at=pipeline_started_at,
            completed_at=pipeline_completed_at,
            duration_seconds=pipeline_duration,
            success=True,
            error=None,
            context=SessionContext(
                pr_title=self.pr_data.get("title", ""),
                pr_body=self.pr_data.get("body", "") or "",
                masca_available=self.masca_path.exists(),
                masca_chars=len(self.masca_analysis),
                call_graph_available=(
                    self.context_output_path / "call_graph.json"
                ).exists(),
                context_files_available=(
                    self.context_output_path / "context_files"
                ).exists(),
                ablation=self.ablation,
            ),
            agents=[agent1_session, agent2_session],
            token_summary=token_summary,
        )

        if self.verbose:
            print(f"\n{Fore.GREEN}{'='*80}")
            print(f"{Fore.GREEN}✅ Pipeline completed!")
            print(f"{Fore.GREEN}{'='*80}")
            print(f"{Fore.GREEN}📊 Results:")
            print(f"{Fore.GREEN}   - Files identified: {len(analysis.files_to_modify)}")
            print(
                f"{Fore.GREEN}   - Functions identified: {len(analysis.functions_to_modify)}"
            )
            print(f"{Fore.GREEN}   - Steps generated: {len(planner.step_plan.steps)}")
            print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}")

            print(f"\n{Fore.BLUE}📊 Token Usage:")
            print(
                f"   Analysis Agent:  {a1.total_tokens} tokens ({a1.requests} requests)"
            )
            print(
                f"   Context Planner: {a2.total_tokens} tokens ({a2.requests} requests)"
            )
            print(f"   Total:           {token_summary['total_tokens']} tokens")
            print(f"   Pipeline time:   {pipeline_duration}s{Style.RESET_ALL}")

        return output, session_log

    def run_sync(self) -> tuple[dict, SessionLog]:
        """Synchronous wrapper for run(). Handles nested event loops."""
        return run_async_safely(self.run())

    def save_output(self, output_path: Optional[str] = None) -> tuple[str, str, str]:
        """
        Run the pipeline and save all outputs.

        Args:
            output_path: Output file path (default: pr_dir/predicted_plan.json)

        Returns:
            Tuple of (predicted_plan_path, token_usage_path, session_log_path)
        """
        output, session_log = self.run_sync()

        # Determine output directory
        if output_path is None:
            out_path = self.pr_dir / "predicted_plan.json"
            out_dir = self.pr_dir
        else:
            out_path = Path(output_path)
            out_dir = out_path.parent

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        # Save token usage report (backward-compatible format)
        token_path = out_dir / "token_usage.json"
        token_report = TokenUsageReport(
            pr_number=session_log.pr_number,
            repository=session_log.repository,
            timestamp=session_log.started_at,
            model_name=session_log.model,
            agents=[s.token_usage for s in session_log.agents],
            total_requests=session_log.token_summary["total_requests"],
            total_input_tokens=session_log.token_summary["total_input_tokens"],
            total_output_tokens=session_log.token_summary["total_output_tokens"],
            total_tokens=session_log.token_summary["total_tokens"],
            duration_seconds=session_log.duration_seconds,
        )
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(token_report.model_dump(), f, indent=2, ensure_ascii=False)

        # Save full session log for the dashboard
        session_path = out_dir / "session_log.json"
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session_log.model_dump(), f, indent=2, ensure_ascii=False)

        # For ablation: copy ground_truth.json so the evaluator can find it
        if self.ablation:
            import shutil

            gt_src = self.pr_dir / "ground_truth.json"
            if gt_src.exists():
                shutil.copy2(gt_src, out_dir / "ground_truth.json")

        if self.verbose:
            print(f"\n{Fore.GREEN}💾 Output saved:      {out_path}")
            print(f"{Fore.GREEN}📊 Token usage saved: {token_path}")
            print(f"{Fore.GREEN}📋 Session log saved: {session_path}{Style.RESET_ALL}")

        return str(out_path), str(token_path), str(session_path)


# =============================================================================
# CLI ENTRY POINT


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PR Step Planner - Generate step plan for Pull Requests"
    )
    parser.add_argument(
        "pr_dir",
        help="PR directory (e.g., PR4Code/dataset_pr_commits_py/owner_repo/pr_123/)",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="gpt-5.2-2025-12-11",
        help="OpenAI model to use (default: gpt-5.2-2025-12-11)",
    )
    parser.add_argument(
        "-o", "--output", help="Output file path (default: pr_dir/predicted_plan.json)"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode")

    args = parser.parse_args()

    try:
        planner = PRStepPlanner(
            pr_dir=args.pr_dir, model_name=args.model, verbose=not args.quiet
        )

        out_path, token_path, session_path = planner.save_output(args.output)
        print(f"\n✅ Completed!")
        print(f"   📄 Plan:         {out_path}")
        print(f"   📊 Token usage:  {token_path}")
        print(f"   📋 Session log:  {session_path}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
