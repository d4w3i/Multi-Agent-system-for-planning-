"""
Single Agent Prompt

Used by: GenAI/single_agent_runner.py
Purpose: Minimal user message for the single-agent ablation.
         No system instructions. The agent receives only the PR title and body.
"""


def get_single_agent_prompt(pr_title: str, pr_body: str) -> str:
    """
    Build the single agent user message.

    The agent receives only the PR title and body -- no system instructions,
    no MASCA context, no task guidelines. All understanding must come from
    tool use alone.

    Args:
        pr_title: PR title (truncated to 500 chars by the caller).
        pr_body: PR body (truncated to 5000 chars by the caller).

    Returns:
        Formatted user message string.
    """
    return f"Title: {pr_title}\n\nBody:\n{pr_body}"
