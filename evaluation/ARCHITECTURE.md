# evaluation/ — Architecture Overview

## Purpose

Extracts ground truth from GitHub Pull Requests to create datasets for evaluating
AI-generated implementation plans. Identifies modified files and functions, then
optionally generates step-by-step implementation plans via LLM.

## Pipeline

```
data.json → pr_loader.py → diff_parser.py → function_matcher.py → step_planner.py → ground_truth.json
```

| Stage | Module | Responsibility |
|-------|--------|----------------|
| 1 | `pr_loader.py` | Load and validate `data.json`; typed `PRData` wrapper with path-traversal protection |
| 2 | `diff_parser.py` | Parse unified diff patches into `DiffResult` (added/modified lines per file) |
| 3 | `function_matcher.py` | Tree-sitter AST matching of modified line ranges to `FunctionChange` objects |
| 4 | `step_planner.py` | OpenAI agent call (via `openai-agents`) that produces a `StepPlan` |
| 5 | `ground_truth_extractor.py` | Orchestrator; fault-tolerant, always writes `ground_truth.json` |

## Data Models (`models.py`)

```
GroundTruth
├── ExtractionMetadata  (timestamp, extractor_version, success, error_message)
├── FileChange[]
│   └── FunctionChange[]  (function_name, class_name, full_name, line ranges)
└── StepPlan (optional)
    └── Step[]  (operation, target, reason, side_effects)
```

## Key Design Rules

- **Prompts live in `GenAI/prompts/`** — `step_planner.py` imports `get_step_planner_prompt`,
  never defines prompts inline.
- **Central logger** — all modules use `logging.getLogger('ground_truth_extractor')`;
  configured once in `utils.setup_logging()`.
- **LLM is optional** — core extraction (files + functions) works without an API key;
  pass `use_llm=False` or use `--no-llm` on the CLI.
- **Error resilience** — each pipeline stage is wrapped; a failure in one file does not
  block processing of others. `ground_truth.json` is always written (with `success=False`
  on failure).

## Entry Points

```bash
# Single PR
python -m evaluation.ground_truth_extractor PR4Code/.../pr_123/

# Batch (all PRs under a directory)
python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --no-llm --limit 10

# Resume interrupted run
python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --skip-existing
```

## Step Count Heuristic

The number of LLM-generated steps is computed dynamically by `_extract_step_plan`:

- `.py` files **with** identified functions → 1 step per modified function
- `.py` files **without** identified functions → 1 step per file
- Non-`.py` files → 1 step per file
