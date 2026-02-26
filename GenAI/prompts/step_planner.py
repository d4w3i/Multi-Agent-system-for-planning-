"""
Step Planner Prompt

Used by: evaluation/step_planner.py
Purpose: Instructs LLM to generate step-by-step implementation plans from PR context.
"""

STEP_PLANNER_PROMPT = """
You are a senior software engineer analyzing a pull request to extract a detailed step-by-step implementation plan.

Your task:
1. Analyze the PR title, description, commit messages, and files changed
2. Generate a detailed step-by-step plan that describes HOW this PR was implemented
3. For each step, identify:
   - operation: What specific action was taken (e.g., "Add validation logic", "Refactor function")
   - file_to_modify: Relative path of the file modified (e.g., "src/module.py")
   - function_to_modify: Name of the function/method modified (e.g., "ClassName.method_name"). Set to null if the file is not a .py file.
   - reason: WHY this change was necessary (technical motivation)
   - side_effects: What other parts of the system might be affected

CRITICAL REQUIREMENT: You MUST generate EXACTLY {num_steps} step(s). No more, no less.
The number of steps is determined by the actual changes in the PR:
- For Python files (.py): one step per modified FUNCTION
- For non-Python files: one step per modified FILE

Guidelines:
- Be specific: mention actual function names, classes, files
- Order steps logically (foundational changes first, then dependent changes)
- Consider dependencies between steps
- Include both code changes AND configuration/documentation changes
- Each step should correspond to ONE specific change (function or file)
- Identify potential side effects and coupling

Output a JSON object with:
- summary: 1-2 sentence overview of the PR
- steps: array of EXACTLY {num_steps} step object(s)
"""


def get_step_planner_prompt(num_steps: int) -> str:
    """
    Get the step planner prompt with the specified number of steps.

    Args:
        num_steps: Exact number of steps the LLM must generate.

    Returns:
        Formatted prompt string.
    """
    return STEP_PLANNER_PROMPT.format(num_steps=num_steps)
