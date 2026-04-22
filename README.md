# PR4Code Planning Evaluation Toolkit

This project is a file-oriented toolkit for the PR4Code dataset. It preprocesses repository snapshots, extracts ground truth from PR diffs, generates LLM-based implementation plans, scores the predictions, and serves the results through a CLI and a Flask dashboard.

Core workflows:
- `context_retrieving/`: builds call graphs, project trees, MASCA summaries, and per-function context files.
- `evaluation/`: extracts `ground_truth.json` from PR metadata and diffs.
- `GenAI/`: runs the two-agent planner, the single-agent ablation baseline, and prediction evaluation.
- `dashboard/`: reads generated JSON artifacts and exposes summary/detail APIs plus a static UI.

Main technologies:
- Tree-sitter for Python parsing and call-graph/function matching
- OpenAI Agents SDK + `AsyncOpenAI` for MASCA and plan generation
- Pydantic for structured outputs
- Rich for the CLI
- Flask for the dashboard

Quick start:

```bash
pip install -r requirements.txt
cp .env.example .env  # add OPENAI_API_KEY for LLM-backed steps

python -m context_retrieving.batch_context_retriever PR4Code/dataset_pr_commits_py --limit 10
python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py --limit 10
python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py --limit 10
python -m GenAI.evaluate_predictions PR4Code/dataset_pr_commits_py --batch
python dashboard/server.py
```

Important directories:
- `GenAI/`: agent orchestration, prompts, model config, prediction/evaluation runners
- `context_retrieving/`: static analysis and context generation
- `evaluation/`: diff parsing, function matching, ground-truth extraction
- `cli/`: Rich-based interactive entry point
- `dashboard/`: Flask server and static frontend

Architecture details and state diagrams are in [architecture.md](/Users/davidecroatto/code/planningtest0/architecture.md).
