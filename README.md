# Python Call Graph Analyzer & AI Planning System

A research system for analyzing Python repositories and Pull Requests using static call graph analysis and multi-agent AI. Given a PR from the [PR4Code](https://github.com/coderamp-labs/pr4code) dataset, the system generates a structured implementation plan and evaluates it against ground truth using Precision/Recall/F1 and semantic similarity.

---

## Overview

The pipeline has three independent stages that can be run separately or end-to-end:

```
Python Repo / PR Dataset
        │
        ▼
┌─────────────────────┐
│ Call Graph Analysis │  Tree-sitter 4-pass AST → call_graph.json + context files
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Ground Truth       │  PR diff → modified functions → LLM step plan
│  Extraction         │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  AI Prediction      │  Two-agent pipeline → predicted_plan.json
│  & Evaluation       │  Evaluated against ground truth (P/R/F1 + semantic score)
└─────────────────────┘
```

---

## Requirements

- Python 3.13+
- `.env` file with `OPENAI_API_KEY=sk-...`

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Call Graph Analysis

Analyze any local Python repository and generate context files:

```bash
python -m context_retrieving.call_graph_builder <repo_path>
python -m context_retrieving.context_generator <repo_path>
```

Output is written to `output/REPO_NAME/`:

```
output/REPO_NAME/
├── call_graph.json          # Machine-readable dependency graph
├── project_info.py          # README + directory tree as Python variables
└── context_files/           # Per-function context, mirroring source structure
    └── module/Class/
        ├── method_context.txt
        └── method_metadata.json
```

### Ground Truth Extraction

Extract structured ground truth (which files/functions were modified) from PR diffs:

```bash
python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/

# Skip LLM step plan generation (faster, no API key needed)
python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --no-llm --limit 10
```

Produces `ground_truth.json` inside each `pr_NUMBER/` directory.

### Context Generation for PRs

Pre-generate call graph context for all PRs in the dataset:

```bash
python -m scripts.generate_context_outputs --limit 10
```

Omit `--limit` to process the full dataset.

### AI Prediction

Run the two-agent system to generate predicted implementation plans:

```bash
# Batch mode
python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10

# Override model for all agents in this run
python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10 --model gpt-4o

# Single PR
python -m GenAI.pr_step_planner <pr_directory>
```

Output per PR: `predicted_plan.json`, `token_usage.json`.

### Evaluation

Score predicted plans against ground truth:

```bash
python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py/
```

Writes `evaluation_score.json` into each PR directory with file-level and function-level Precision/Recall/F1 and a semantic similarity score.

### MASCA Standalone Analysis

Generate a project-level context summary using the MASCA agent:

```bash
python -m GenAI.masca_runner PR4Code/dataset_pr_commits_py/ --limit 10
```

---

## Architecture

### Call Graph Analysis — 4-Pass Pipeline

`CallGraphBuilder` (`context_retrieving/call_graph_builder.py`) uses Tree-sitter for AST analysis:

```
Pass 0: Extract Imports    → build import_map  (pd → pandas)
Pass 1: Extract Functions  → full symbol table (all functions/classes/methods)
Pass 2: Extract Calls      → resolve call targets using import_map + symbol table
Pass 3: Finalize           → mark is_leaf and is_entry_point
```

The multi-pass design is necessary: import aliases (Pass 0) must be resolved before call targets (Pass 2), and the complete symbol table (Pass 1) must exist before any call can be matched.

### Ground Truth Extraction — 5-Stage Pipeline

`GroundTruthExtractor` (`evaluation/ground_truth_extractor.py`) orchestrates:

```
data.json → pr_loader → diff_parser → function_matcher → step_planner → ground_truth.json
```

Each stage is fault-tolerant; a failure in step planning does not block structural extraction.

### AI Prediction — Two-Agent Pipeline

`PRStepPlanner` (`GenAI/pr_step_planner.py`) runs two sequential agents:

| Agent | Input | Output |
|-------|-------|--------|
| **Analysis Agent** | PR title/body, `base_project/` source | `files_to_modify`, `functions_to_modify` |
| **Context Planner** | Analysis output, `context_files/`, `call_graph.json` | `predicted_plan.json` (ordered steps) |

Each agent has sandboxed file-system tools restricted to its designated directories.

### Shared Data Models

All output schemas are defined in `evaluation/models.py` (Pydantic). Ground truth and predictions share the same `Step` schema, enabling direct comparison during evaluation.

```python
Step(operation, file_to_modify, function_to_modify, reason, side_effects)
StepPlan(summary, steps: List[Step])
GroundTruth(pr_number, repository, files_modified, step_plan)
```

### Model Configuration

Agent models are declared in `GenAI/agents_config.toml`. The `--model` CLI flag overrides all agents for a single run without modifying the config:

```toml
[agents.analysis]
model = "gpt-4o"

[agents.context_planner]
model = "gpt-4o"
```

### Prompts

`GenAI/prompts/` is the single source of truth for all LLM system prompts. Agent files import from here — prompts are never defined inline.

---

## Dataset Utilities

```bash
# Check which PRs have ground truth, predictions, and evaluation scores
python -m scripts.verify_pr_completeness

# Create a filtered subset
python -m scripts.create_subset PR4Code/dataset_pr_commits_py/ --output PR4Code/subset_py/

# Remove all generated files (ground_truth.json, predicted_plan.json, evaluation_score.json)
python -m scripts.cleanup PR4Code/dataset_pr_commits_py/
```

---

## Tests

```bash
pytest
pytest tests/test_call_graph_builder.py -v
pytest --cov
```

---

## Project Structure

```
├── context_retrieving/      # Call graph analysis and context generation
├── evaluation/              # Ground truth extraction and data models
├── GenAI/                   # Multi-agent prediction, evaluation, prompts
│   ├── prompts/             # Centralized LLM system prompts
│   └── agents_config.toml   # Per-agent model selection
├── scripts/                 # Dataset utilities
├── cli/                     # Interactive terminal UI
├── tests/                   # Test suite
└── PR4Code/                 # PR dataset (not included in repo)
    └── dataset_pr_commits_py/
        └── owner_repo/pr_NUMBER/
            ├── data.json
            ├── base_project/
            ├── original_files/
            ├── modified_files/
            ├── ground_truth.json      # generated
            ├── predicted_plan.json    # generated
            └── evaluation_score.json  # generated
```
