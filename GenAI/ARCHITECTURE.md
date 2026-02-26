# GenAI Package — Architecture Reference

> **Location:** `GenAI/`
> **Purpose:** AI-powered code analysis and implementation-plan generation, built on the OpenAI Agents SDK.

---

## 1. Overview

The GenAI package turns a Pull Request (title + description + source snapshot) into a structured, machine-readable implementation plan that can be evaluated against a human-written ground truth.

```
PR metadata + base_project/
        │
        ▼
┌───────────────────────┐     ┌────────────────────────┐
│   Analysis Agent      │     │  Context Planner Agent │
│  (reads source code)  │────▶│  (reads context files) │
└───────────────────────┘     └───────────┬────────────┘
                                          │
                                          ▼
                               predicted_plan.json
                                          │
                                          ▼
                               evaluate_predictions.py
                                          │
                                          ▼
                               Precision / Recall / F1
                                + Semantic similarity
```

---

## 2. Module Map

```
GenAI/
├── __init__.py              Package entry-point and public API docs
├── utils.py                 Shared utilities (run_async_safely)
├── tools.py                 @function_tool wrappers for agents
├── masca_runner.py          Standalone MASCA context-generation runner
├── pr_step_planner.py       Automated PR-to-plan two-agent pipeline
├── batch_predict.py         CLI batch runner — drives pr_step_planner
├── evaluate_predictions.py  Metrics engine — compares plan vs ground truth
└── prompts/
    ├── __init__.py              Re-exports all prompts and template functions
    ├── analysis_agent.py        ANALYSIS_AGENT_PROMPT + get_analysis_agent_prompt()
    ├── context_planner.py       CONTEXT_PLANNER_PROMPT
    ├── masca.py                 MASCA_PROMPT + get_masca_prompt()
    └── step_planner.py          STEP_PLANNER_PROMPT + get_step_planner_prompt()
```

---

## 3. Module-by-Module Reference

### 3.1 `utils.py` — Shared Utilities

**Single exported symbol:** `run_async_safely(coro)`

Both `masca_runner.py` and `pr_step_planner.run_sync()` need to call async code from a synchronous call site. The tricky part is that the call site may already live inside a running event loop (e.g. a Jupyter notebook or an outer async framework). `run_async_safely` handles both cases:

| Situation | Strategy |
|-----------|----------|
| No running event loop | `asyncio.run(coro)` |
| Running event loop detected | Submit to a `ThreadPoolExecutor` worker that owns its own loop |

All other modules import this function instead of duplicating the detection logic.

---

### 3.2 `tools.py` — Agent Function Tools

Provides the `@function_tool`-decorated callables that the OpenAI Agents SDK exposes to LLMs as callable tools.

**Three-layer architecture:**

```
@function_tool wrappers          ← agents call these
        │
        ▼
_impl functions                  ← core logic, testable without the decorator
        │
        ▼
_read_* / _detect_* helpers      ← format-specific file readers
```

**Public tools:**

| Tool | Purpose |
|------|---------|
| `read_file` | Read any file — source code, PDF, Word, Excel, images — with automatic format detection |
| `list_directory` | List directory contents with glob filtering and optional recursion |
| `find_code_files` | Convenience wrapper: recursively find all files for a given language |

**Security model:**

- Path traversal (`..`) is blocked at the string level before any filesystem access.
- An optional `base_dir` argument restricts all access to a sandboxed subtree; `os.path.realpath` is used to defeat symlink escapes.
- A configurable `max_size_mb` (default 50 MB) prevents memory exhaustion.

**File-type detection priority order:**

1. `SPECIAL_FILES` (exact filename match — `Makefile`, `Dockerfile`, etc.)
2. `CODE_EXTENSIONS` (Python-focused: `.py`, `.pyi`, `.pyx`, shell, config, docs, SQL, basic web)
3. `DOCUMENT_EXTENSIONS` (PDF, DOCX, XLSX, … — binary formats requiring special parsers)
4. `IMAGE_EXTENSIONS` (PNG, JPG, SVG, … — binary formats sent to vision)
5. Fallback → plain text

`DOCUMENT_EXTENSIONS` and `IMAGE_EXTENSIONS` are the functionally significant exclusion lists: they route files to dedicated parsers. `CODE_EXTENSIONS` only provides a language label in the output header and drives `find_code_files` filtering; unknown extensions fall through to plain text anyway.

---

### 3.3 `masca_runner.py` — Standalone MASCA Runner

Runs the **MASCA** (project-context) agent in isolation. Given a project README and a directory tree, it produces a rich free-form analysis used downstream as the `{masca_analysis}` injection point in `ANALYSIS_AGENT_PROMPT`.

**Public API:**

```python
result = run_masca_analysis(readme_content, directory_tree, user_request=None)
# → {"system_prompt", "prompt", "output", "input_tokens", "output_tokens", "total_tokens"}

saved = save_masca_output(output_text, output_path, directory_tree=None)
# → True on success, False on I/O error
```

**Event-loop handling:** delegates entirely to `run_async_safely` from `utils.py`.

**Token accounting:** token counts are extracted from `runner_result.raw_responses[*].usage` and aggregated before being returned in the result dict.

---

### 3.4 `pr_step_planner.py` — Automated PR Pipeline

The core production pipeline. Takes a PR directory and produces a `predicted_plan.json` compatible with `ground_truth.json`.

**Two-agent pipeline:**

```
PR title + body
      │
      ▼
┌─────────────────────────────────────────────────────┐
│ Agent 1 — Analysis Agent                            │
│  System prompt: MASCA context (project-wide)        │
│  Tools:                                             │
│    read_base_project_file(path)                     │
│    list_base_project_directory(dir, pattern, recur) │
│  Output: AnalysisOutput                             │
│    • files_to_modify  List[FileToModify]            │
│    • functions_to_modify  List[FunctionToModify]    │
│    • masca_optimized  (PR-focused MASCA slice)      │
└──────────────────────────┬──────────────────────────┘
                           │ structured handoff (prompt)
                           ▼
┌─────────────────────────────────────────────────────┐
│ Agent 2 — Context Planner Agent                     │
│  System prompt: CONTEXT_PLANNER_PROMPT              │
│  Tools:                                             │
│    read_context_file(path)                          │
│    list_context_files(dir, pattern)                 │
│    read_call_graph(section)                         │
│  Output: PlannerOutput                              │
│    • step_plan  StepPlan         (evaluation.models)│
│      ├── summary  str                               │
│      └── steps   List[Step]      (evaluation.models)│
│          ├── file_to_modify  str                    │
│          └── function_to_modify  Optional[str]      │
└─────────────────────────────────────────────────────┘
```

**Sandboxed tool factories:**

`create_base_project_tools(base_project_path)` and `create_context_files_tools(context_output_path)` are closure factories. Each call returns a fresh pair of `@function_tool` functions whose file-system access is restricted to a single directory. Internally they reuse `_read_file_impl` and `_list_directory_impl` from `tools.py` to avoid duplicating security and encoding logic.

**`MAX_FILE_CHARS` constant (module level, `60_000`):**

Files larger than this threshold are truncated before being returned to the agent. The constant is defined once at module level and referenced by both tool factories — previously it was duplicated inside each factory closure.

**Retry logic:** Each agent call is retried up to 3 times with exponential back-off (`2^attempt` seconds) to handle transient API errors (rate limits, timeouts).

**`PRStepPlanner` class:**

| Method | Description |
|--------|-------------|
| `__init__(pr_dir, model_name, verbose)` | Validates paths, loads `data.json` and MASCA, creates the `AsyncOpenAI` client |
| `run()` | `async` — runs the full two-agent pipeline, returns `(output_dict, TokenUsageReport)` |
| `run_sync()` | Thin sync wrapper: calls `run_async_safely(self.run())` |
| `save_output(output_path)` | Calls `run_sync()` and writes `predicted_plan.json` + `token_usage.json` |

**MASCA fallback:** if `masca_analysis.md` is absent, a minimal context is synthesised from `project_tree.txt` and the project README (up to 5 000 and 3 000 characters respectively).

---

### 3.5 `batch_predict.py` — Batch CLI Runner

Drives `PRStepPlanner` over an arbitrary number of PR directories found under a base path.

**PR discovery (`find_pr_directories`):** recursively scans for `pr_*` directories that contain both `data.json` and `base_project/`. Results are sorted alphabetically before the limit is applied, so `--limit N` always returns the first N PRs in a deterministic order.

**Execution modes:**

| Flag | Behaviour |
|------|-----------|
| *(default)* | Sequential, one PR at a time |
| `-p N` | Parallel with `N` `ThreadPoolExecutor` workers (1–16) |
| `--skip-existing` | Skips any PR that already has `predicted_plan.json` |

**Entry point:** `python -m GenAI.batch_predict <base_path> --limit N`

---

### 3.6 `evaluate_predictions.py` — Metrics Engine

Compares every `predicted_plan.json` with the corresponding `ground_truth.json` and computes four classes of metrics.

**Metric classes:**

| Class | What it measures |
|-------|-----------------|
| **File identification** | Precision / Recall / F1 on the set of files predicted to be modified |
| **Function identification** | Precision / Recall / F1 on the set of function names |
| **Step plan analysis** | Absolute step-count difference; target coverage (fraction of predicted steps that match an actual file or function) |
| **Semantic similarity** *(optional, `--semantic`)* | Cosine similarity of OpenAI embeddings for summaries and step descriptions; overall score = 30 % summary + 70 % steps |

**Data classes:**

```
PRScore
├── files       MetricScore   (precision, recall, f1, counts)
├── functions   MetricScore
├── steps       StepAnalysis  (predicted/actual count, target coverage)
└── semantic    SemanticScore (summary_sim, avg_step_sim, overall, step_matches)

BatchReport
├── avg_file_precision / recall / f1
├── avg_function_precision / recall / f1
├── avg_step_diff / avg_target_coverage
└── avg_semantic_score / avg_summary_similarity / avg_step_similarity
```

**Embedding efficiency:** all step texts for a PR are sent to the API in a single batch call (`get_embeddings_batch`), then split into predicted and ground-truth halves.

**OpenAI client:** lazily initialised via `get_openai_client()` so the module is safely importable without an API key.

**Entry point:** `python -m GenAI.evaluate_predictions <path> [--batch] [--semantic] [--report file.json]`

---

### 3.7 `prompts/` — Centralized Prompt Registry

**Design rule:** every LLM system prompt in the codebase lives here and *nowhere else*. Agent files import from `GenAI.prompts`; they never embed prompt strings inline.

| File | Export(s) | Consumer |
|------|-----------|---------|
| `analysis_agent.py` | `ANALYSIS_AGENT_PROMPT`, `get_analysis_agent_prompt(masca_analysis)` | `pr_step_planner.py` |
| `context_planner.py` | `CONTEXT_PLANNER_PROMPT` | `pr_step_planner.py` |
| `masca.py` | `MASCA_PROMPT`, `get_masca_prompt(readme, tree)` | `masca_runner.py` |
| `step_planner.py` | `STEP_PLANNER_PROMPT`, `get_step_planner_prompt(num_steps)` | `evaluation/step_planner.py` |

Prompts with dynamic content use `get_*_prompt()` template functions (simple `.format()` calls on the constant string) so the static `*_PROMPT` constant remains inspectable and testable independently.

---

## 4. Data Flow — End-to-End

```
PR directory
  ├── data.json                      → pr_title, pr_body
  ├── base_project/                  → source code snapshot
  │   └── context_output/
  │       ├── masca_analysis.md      → MASCA context for Analysis Agent
  │       ├── call_graph.json        → tool: read_call_graph()
  │       └── context_files/         → tool: read_context_file()
  └── [predicted_plan.json]          ← OUTPUT of PRStepPlanner
      [token_usage.json]             ← side-output

Evaluation:
  predicted_plan.json  ┐
                       ├─▶ evaluate_predictions.py ─▶ PRScore / BatchReport
  ground_truth.json    ┘
```

---

## 5. Dependency Graph (internal)

```
batch_predict ──▶ pr_step_planner
                      │
              ┌───────┼──────────────────────┐
              ▼       ▼                      ▼
           tools   prompts                 utils
                                             │
                                    evaluation.models
                                    (Step, StepPlan)

masca_runner ──▶ prompts
             ──▶ utils

evaluate_predictions  (standalone, only openai + numpy)
```

No circular imports. `utils.py` has zero intra-package dependencies.

---

## 6. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **`_impl` / `@function_tool` split in `tools.py`** | The `@function_tool` decorator hides the function signature from Python; having a plain `_impl` counterpart keeps the logic unit-testable and reusable (e.g. `pr_step_planner.py` imports `_read_file_impl` directly). |
| **Sandboxed tool factories (closures)** | Agents receive tools bound to a specific directory. This prevents one agent from accidentally reading outside its allowed scope without any runtime path-checking overhead per call. |
| **Prompts as constants, templates via `get_*_prompt()`** | Static constants are trivially inspectable and diffable. Template injection is explicit and localised. |
| **`MAX_FILE_CHARS` at module level** | A single authoritative value avoids the per-function duplication that existed previously; changing the threshold is a one-line edit. |
| **`run_async_safely` in `utils.py`** | Centralises the "am I inside a running loop?" detection that both `masca_runner` and `pr_step_planner` require, eliminating the duplicated ~10-line block. |
| **`Step` / `StepPlan` shared from `evaluation.models`** | Both the predicted plan (`pr_step_planner.py`) and the ground truth (`evaluation/step_planner.py`) use the same Pydantic models, guaranteeing the two JSON outputs have identical schemas and are directly comparable. |
| **Token usage tracked per agent** | `TokenUsageReport` gives fine-grained visibility into which agent consumed the most tokens, useful for cost profiling and prompt tuning. |
