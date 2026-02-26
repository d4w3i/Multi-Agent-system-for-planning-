"""
=============================================================================
MASCA_RUNNER.PY - Standalone MASCA Agent Runner
=============================================================================

Runs the MASCA agent in isolation: given a project README and directory
tree it produces a structured context summary used by downstream agents.

USAGE:

    from GenAI.masca_runner import run_masca_analysis, save_masca_output

    result = run_masca_analysis(readme_content, directory_tree)
    save_masca_output(result["output"], "output/masca_analysis.md")

=============================================================================
"""

import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner
from typing import Optional

from GenAI.prompts import get_masca_prompt
from GenAI.utils import run_async_safely
from GenAI.config_loader import load_config

# Load environment variables
load_dotenv()

def run_masca_analysis(readme_content: str, directory_tree: str, user_request: Optional[str] = None) -> dict:
    """
    Run Masca analysis on a project.

    Args:
        readme_content: Content of the project's README
        directory_tree: Tree structure of the project files
        user_request: Specific user request (optional)

    Returns:
        Dict with keys: system_prompt, prompt, output, input_tokens, output_tokens, total_tokens
    """
    def _make_result(system_prompt: str, prompt: str, output: str,
                     input_tokens: int = 0, output_tokens: int = 0, total_tokens: int = 0) -> dict:
        return {
            "system_prompt": system_prompt,
            "prompt": prompt,
            "output": output,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    # Check that the API key is available
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return _make_result("", "", "❌ ERROR: OPENAI_API_KEY not found in the .env file To use the Masca agent, add your OpenAI API key to the .env file: OPENAI_API_KEY=sk-...")

    instructions = ""
    input_prompt = ""

    try:
        model_name = load_config().agents.masca.model
        client = AsyncOpenAI(api_key=api_key, timeout=120.0)
        MODEL = OpenAIChatCompletionsModel(
            model=model_name,
            openai_client=client
        )

        # Build the instructions for Masca
        instructions = get_masca_prompt(readme_content, directory_tree)

        # Create the Masca agent
        masca = Agent(
            name="masca",
            instructions=instructions,
            model=MODEL,
            model_settings=ModelSettings(reasoning={"effort": "medium"})
        )

        # Prepare the input prompt
        if user_request:
            # Sanitize user_request to prevent prompt injection
            sanitized_request = user_request.replace('\n', ' ').strip()[:500]
            input_prompt = f"Analyze this project to support the following request: {sanitized_request}"
        else:
            input_prompt = "Analyze this project and provide comprehensive context to support future changes."

        # Print prompts to terminal for visibility
        print("\n" + "=" * 70)
        print("MASCA — SYSTEM PROMPT")
        print("=" * 70)
        print(instructions)
        print("\n" + "-" * 70)
        print("MASCA — INPUT PROMPT")
        print("-" * 70)
        print(input_prompt)
        print("=" * 70 + "\n")

        # Run MASCA — delegates event-loop management to run_async_safely
        async def _run():
            return await Runner.run(masca, input_prompt, max_turns=1000)

        runner_result = run_async_safely(_run())

        # Extract token usage from raw_responses
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        if hasattr(runner_result, 'raw_responses'):
            for resp in runner_result.raw_responses:
                if hasattr(resp, 'usage') and resp.usage:
                    input_tokens += getattr(resp.usage, 'input_tokens', 0) or 0
                    output_tokens += getattr(resp.usage, 'output_tokens', 0) or 0
                    total_tokens += getattr(resp.usage, 'total_tokens', 0) or 0

        # Extract the response content
        output_text = runner_result.final_output

        if hasattr(output_text, 'messages'):
            # Get the last message from the agent
            for msg in reversed(output_text.messages):
                if hasattr(msg, 'role') and msg.role == 'assistant':
                    if hasattr(msg, 'content'):
                        output_text = msg.content
                        break
                    elif hasattr(msg, 'text'):
                        output_text = msg.text
                        break

        return _make_result(instructions, input_prompt, str(output_text),
                            input_tokens, output_tokens, total_tokens)

    except Exception as e:
        error_msg = f"""
❌ ERROR during the execution:
{str(e)}

Possible errors:
1. OPENAI_API_KEY not valid
2. LLM not available
3. API connection problem

Technical issues:
{type(e).__name__}: {str(e)}
"""
        return _make_result(instructions, input_prompt, error_msg)

def save_masca_output(output: str, output_path: str, directory_tree: str = None) -> bool:
    """
    Save Masca output to a markdown file.

    Args:
        output: Content of the Masca analysis
        output_path: Full path of the output file
        directory_tree: Directory tree to include (optional)

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Project Analysis - MASCA Agent\n\n")
            f.write(output)

            # Add directory tree if provided
            if directory_tree:
                f.write("\n\n---\n\n")
                f.write("## 📁 Project Directory Structure\n\n")
                f.write("```\n")
                f.write(directory_tree)
                f.write("\n```\n")
        return True
    except Exception as e:
        print(f"Error saving MASCA output: {e}")
        return False
    