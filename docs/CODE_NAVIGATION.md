# Code Navigation Guide

This document provides a high-level overview of the codebase structure and explains how to navigate the Python Call Graph Analyzer project.

## Project Overview

The Python Call Graph Analyzer extracts dependency graphs from Python repositories and generates AI-ready context files. It also includes tools for evaluating AI-generated implementation plans against ground truth from real Pull Requests.

## Directory Structure

```
planningtest0/
├── main.py                    # Entry point → cli.app.run()
├── CLAUDE.md                  # Instructions for Claude Code
├── CODE_NAVIGATION.md         # This file
│
├── cli/                       # Interactive CLI layer
│   ├── app.py                 # Application class, startup orchestration
│   ├── banner.py              # Welcome line + system status
│   ├── config.py              # Config, history, express defaults
│   ├── components/            # Reusable UI components
│   │   ├── prompts.py         # All input prompts + Q_STYLE (single source)
│   │   ├── displays.py        # Output tables, panels, messages
│   │   └── progress.py        # Spinners and progress tracking
│   ├── handlers/              # One handler per menu operation
│   │   ├── repository.py      # Clone + analyze repo
│   │   ├── context.py         # Generate context for PRs
│   │   ├── extraction.py      # Extract ground truth
│   │   ├── prediction.py      # AI prediction generation
│   │   ├── verification.py    # Dataset completeness check
│   │   ├── subset.py          # Create subsets + Python filter
│   │   ├── cleanup.py         # Remove generated files
│   │   ├── testing.py         # Run pytest
│   │   └── settings.py        # View/edit configuration
│   └── menus/
│       ├── __init__.py        # BaseMenu with arrow-key navigation
│       └── main_menu.py       # Main menu items and grouping
│
├── context_retrieving/        # Core analysis pipeline
│   ├── call_graph_builder.py  # Tree-sitter AST analysis
│   ├── context_generator.py   # AI-ready context file generation
│   ├── batch_context_retriever.py  # Batch processing wrapper
│   └── generate_tree.py       # ASCII directory tree generation
│
├── evaluation/                # PR ground truth extraction
│   ├── models.py              # Pydantic data structures
│   ├── ground_truth_extractor.py  # Main orchestrator
│   ├── step_planner.py        # LLM-based step planning
│   ├── diff_parser.py         # Git diff parsing
│   ├── function_matcher.py    # Tree-sitter function matching
│   ├── pr_loader.py           # PR data I/O
│   └── utils.py               # Logging utilities
│
├── GenAI/                     # AI agent tools
│   ├── agent.py               # Multi-agent planning system
│   ├── tools.py               # Function tools for AI agents
│   ├── pr_step_planner.py     # PR-specific step planning
│   ├── batch_predict.py       # Batch prediction runner
│   ├── evaluate_predictions.py # Evaluation metrics
│   ├── masca_runner.py        # MASCA integration
│   └── prompts/               # Centralized LLM prompts
│       ├── __init__.py        # Exports all prompts
│       ├── clarification_agent.py  # Clarification agent prompt
│       ├── costanza.py        # Costanza planning prompt
│       ├── analysis_agent.py  # PR analysis agent prompt
│       ├── context_planner.py # Context planner prompt
│       ├── masca.py           # MASCA agent prompt
│       └── step_planner.py    # Step planner prompt
│
├── scripts/                   # Utility scripts
│   ├── dataset_cleanup.py     # Clean generated files
│   ├── generate_context_outputs.py  # Batch context generation
│   ├── verify_pr_completeness.py    # Dataset validation
│   ├── create_pr_subset.py    # Create filtered subsets
│   └── extract_python_pr_paths.py   # Extract Python PR paths
│
├── shared/                    # Shared utilities
│   └── terminal.py            # Terminal UI helpers (Spinner, Colors)
│
├── tests/                     # Test suite
│
└── PR4Code/                   # PR dataset (not in version control)
    ├── dataset_pr_commits_py/ # Python PRs
    └── dataset_pr_commits_java/  # Java PRs
```

## Module Descriptions

### `context_retrieving/` - Core Analysis Pipeline

The heart of the project. Uses a 4-pass pipeline to analyze Python code:

| Pass | Purpose | Output |
|------|---------|--------|
| 0 | Extract Imports | `import_map` for each file |
| 1 | Extract Functions | All functions/classes/methods |
| 2 | Extract Calls | Resolve calls using import_map |
| 3 | Finalize | Identify entry points and leaf functions |

**Key Classes:**
- `CallGraphBuilder` - Tree-sitter based AST analyzer
- `ContextGenerator` - Generates hierarchical context files

**Entry Point:**
```python
from context_retrieving.call_graph_builder import CallGraphBuilder
from context_retrieving.context_generator import ContextGenerator

builder = CallGraphBuilder()
call_graph = builder.analyze_repository("/path/to/repo")

generator = ContextGenerator(call_graph)
generator.generate_all_context_files("output/context_files")
```

### `evaluation/` - Ground Truth Extraction

Extracts ground truth from GitHub Pull Requests for evaluation:

- **`models.py`** - Pydantic models: `GroundTruth`, `FileChange`, `Step`, `StepPlan`
- **`ground_truth_extractor.py`** - Orchestrates: loads PR -> parses diffs -> matches functions -> generates steps
- **`step_planner.py`** - Uses OpenAI to generate implementation plans

**Entry Point:**
```bash
python -m evaluation.ground_truth_extractor PR4Code/dataset/ --limit 10
```

### `GenAI/` - AI Agent Tools

Provides tools for AI agents to analyze and plan code modifications:

- **`agent.py`** - Multi-agent system (Clarification Agent -> Costanza)
- **`tools.py`** - Function tools: `get_function_context`, `read_file`, `list_directory`
- **`pr_step_planner.py`** - Multi-agent PR analysis (Analysis Agent -> Context Planner)
- **`batch_predict.py`** - Batch generate predictions for evaluation
- **`masca_runner.py`** - Standalone MASCA project analysis

**Centralized Prompts (`prompts/`):**

All LLM system prompts are defined in `GenAI/prompts/` as constants and template functions. Agent files import from here — they never define prompts inline.

| Prompt | Variable | Template Function | Used By |
|--------|----------|-------------------|---------|
| Clarification Agent | `CLARIFICATION_AGENT_PROMPT` | — | `agent.py` |
| Costanza | `COSTANZA_PROMPT` | — | `agent.py` |
| Analysis Agent | `ANALYSIS_AGENT_PROMPT` | `get_analysis_agent_prompt(masca)` | `pr_step_planner.py` |
| Context Planner | `CONTEXT_PLANNER_PROMPT` | — | `pr_step_planner.py` |
| MASCA | `MASCA_PROMPT` | `get_masca_prompt(readme, tree)` | `masca_runner.py` |
| Step Planner | `STEP_PLANNER_PROMPT` | `get_step_planner_prompt(num_steps)` | `evaluation/step_planner.py` |

**Entry Point:**
```bash
python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10
```

### `scripts/` - Utility Scripts

Dataset management and batch operations:

| Script | Purpose |
|--------|---------|
| `dataset_cleanup.py` | Remove generated files (context, ground truth, predictions) |
| `generate_context_outputs.py` | Batch generate context files for PRs |
| `verify_pr_completeness.py` | Check dataset completeness |
| `create_pr_subset.py` | Create filtered evaluation subsets |
| `extract_python_pr_paths.py` | Find Python-only PRs |

**Examples:**
```bash
# Clean up all predicted plans
python -m scripts.dataset_cleanup --target predicted_plan --delete

# Generate context for 10 PRs
python -m scripts.generate_context_outputs --limit 10

# Verify dataset completeness
python -m scripts.verify_pr_completeness
```

### `cli/` - Interactive CLI

Arrow-key menus, Tab-completion, and express mode. Built on Rich (output) and questionary (input).

**Architecture:**
- `components/prompts.py` — Single source of truth for all user input. Defines `Q_STYLE` and all `prompt_*` functions. Only file that imports `questionary`/`prompt_toolkit` (besides `menus/__init__.py`).
- `components/displays.py` — All output rendering (tables, panels, error/success).
- `handlers/` — One handler per menu operation. Each receives a `Console` and returns an optional result dict.
- `menus/` — `BaseMenu` provides the arrow-key navigation loop. `MainMenu` defines items grouped into Analysis, Dataset Tools, and Utility.
- `config.py` — Persistent history (`~/.ai_planning_cli_history.json`), recent directories/repos, express defaults per handler.

**Express mode:** Every handler (except destructive `cleanup.py`) offers "Express" (run with defaults) or "Configure" (customize all options).

### `shared/` - Shared Utilities

Common utilities used across the codebase:

- **`terminal.py`** - Terminal UI: `Spinner`, `Colors`, `print_header`, `print_success`, etc.

```python
from shared.terminal import Spinner, Colors, print_header

spinner = Spinner("Processing")
spinner.start()
# ... do work ...
spinner.stop("Done!")
```

## Common Workflows

### 1. Analyze a Repository

```bash
python main.py
# Arrow-key menu → Repository Analysis
# Tab-complete paths, choose Express or Configure
```

### 2. Generate Context for PR Dataset

```bash
# Generate context files for PRs
python -m scripts.generate_context_outputs --limit 10

# Or with MASCA analysis
python -m scripts.generate_context_outputs --with-masca --limit 10
```

### 3. Extract Ground Truth

```bash
python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --limit 10
```

### 4. Generate Predictions

```bash
python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10
```

### 5. Clean Up Generated Files

```bash
# Preview what would be deleted
python -m scripts.dataset_cleanup --target all

# Actually delete
python -m scripts.dataset_cleanup --target all --delete
```

## Output Structure

### Repository Analysis Output

```
output/REPO_NAME/
├── project_info.py      # README + directory tree as Python variables
├── call_graph.json      # Machine-readable graph
└── context_files/       # Hierarchical structure mirroring source
    └── module/file/     # Each .py becomes a directory
        ├── func_context.txt
        └── func_metadata.json
```

### PR Dataset Structure

```
PR4Code/dataset_pr_commits_py/owner_repo/pr_NUMBER/
├── data.json            # PR metadata
├── original_files/      # Before changes
├── modified_files/      # After changes
├── base_project/        # Full base repo snapshot
├── context_output/      # Generated context (optional)
├── ground_truth.json    # Extracted ground truth (optional)
└── predicted_plan.json  # AI-generated plan (optional)
```

## Code Style Guide

The codebase follows the documentation style established in `context_retrieving/`:

### Module Header Format

```python
"""
=============================================================================
MODULE_NAME.PY - Brief Description
=============================================================================

This module [what it does].

WHAT IS [CONCEPT]:
[Visual explanation with ASCII diagrams]

    main() ──────► process_data() ──────► validate()

USAGE:
    from module import Class
    instance = Class()
    result = instance.method()

REQUIREMENTS:
    - Dependency 1
    - Dependency 2
=============================================================================
"""
```

### Section Markers

```python
# =============================================================================
# SECTION NAME
# =============================================================================
```

### Function Documentation

```python
def function_name(param1: str, param2: int = 10) -> Optional[str]:
    """
    Brief description of what the function does.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)

    Returns:
        Description of return value, or None if not found

    Example:
        >>> result = function_name("test", 20)
        >>> print(result)
    """
```

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_call_graph_builder.py -v

# Run with coverage
pytest --cov
```

## Requirements

- Python 3.13+
- Dependencies in `requirements.txt`
- Optional: `OPENAI_API_KEY` in `.env` for LLM features

## Quick Reference

| Task | Command |
|------|---------|
| Analyze repo | `python main.py` |
| Run tests | `pytest` |
| Generate context | `python -m scripts.generate_context_outputs --limit N` |
| Extract ground truth | `python -m evaluation.ground_truth_extractor PATH --limit N` |
| Generate predictions | `python -m GenAI.batch_predict PATH --limit N` |
| Clean up files | `python -m scripts.dataset_cleanup --target TARGET --delete` |
| Verify dataset | `python -m scripts.verify_pr_completeness` |
