"""
=============================================================================
GENAI/__INIT__.PY - AI Agent Tools Package
=============================================================================

This package provides AI-powered tools for code analysis and planning,
built on top of the OpenAI Agents SDK.

PACKAGE PURPOSE:

    The GenAI package enables AI agents to:
    1. Generate implementation plans from Pull Request context
    2. Analyze code using call graphs and context files
    3. Evaluate predictions against ground truth

PACKAGE STRUCTURE:

    GenAI/
    ├── __init__.py              <- This file
    ├── tools.py                 <- Function tools for AI agents
    ├── pr_step_planner.py       <- PR-specific step planning
    ├── batch_predict.py         <- Batch prediction runner
    ├── evaluate_predictions.py  <- Evaluation metrics
    ├── masca_runner.py          <- MASCA integration
    ├── utils.py                 <- Shared utilities (run_async_safely)
    └── prompts/                 <- Centralized LLM system prompts

USAGE:

    # Using the PRStepPlanner
    from GenAI.pr_step_planner import PRStepPlanner

    planner = PRStepPlanner(pr_dir="/path/to/pr_123")
    result = await planner.run()

    # Batch processing
    python -m GenAI.batch_predict PR4Code/dataset/ --limit 10

REQUIREMENTS:
    - OpenAI API key in .env (OPENAI_API_KEY)
    - openai, agents, pydantic packages

=============================================================================
"""

__version__ = "1.0.0"

# Public API exports
__all__ = [
    "__version__",
]
