# Folder Dependency Map

This document maps every inter-folder import dependency in the project, folder by folder.
Only **internal** imports are listed (stdlib and third-party packages are excluded).

---

## Dependency Hierarchy (top-level overview)

```
GenAI/prompts/          ← leaf: no internal deps, pure string constants
       ↓
context_retrieving/     ← leaf: no internal deps, pure analysis engine
       ↓
scripts/                ← only depends on other scripts/ files (create_pr_subset → extract_python_pr_paths)
       ↓
evaluation/             ← depends on GenAI/prompts/
GenAI/                  ← depends on GenAI/prompts/ + context_retrieving/
       ↓
cli/components/         ← depends on cli/config (local)
       ↓
cli/handlers/           ← depends on cli/components/, cli/config, context_retrieving/, scripts/
       ↓
cli/menus/              ← depends on cli/handlers/ + cli/components/
       ↓
cli/app.py              ← depends on cli/menus/, cli/banner, cli/config
       ↓
tests/                  ← depends on context_retrieving/ + GenAI/
```

No circular dependencies exist in the project.

---

## `cli/`

The top-level CLI orchestrator. Wires together the banner, configuration, and the menu system.

| File | Imports from |
|------|-------------|
| `cli/__init__.py` | `cli.app` |
| `cli/app.py` | `cli.banner`, `cli.menus`, `cli.config` |
| `cli/banner.py` | *(none — only `rich`)* |
| `cli/config.py` | *(none — only stdlib/third-party)* |

**What depends on `cli/`:**
Nothing outside of `cli/` imports from `cli/app.py` or `cli/config.py` directly, except `cli/components/prompts.py` which imports `config` from `cli.config`.

---

## `cli/components/`

Reusable UI primitives. Single source of truth for all user-facing input (`prompts.py`) and output (`displays.py`).

| File | Imports from |
|------|-------------|
| `cli/components/__init__.py` | `cli/components/prompts`, `cli/components/displays`, `cli/components/progress` |
| `cli/components/prompts.py` | `cli.config` (for defaults/history), `cli.components.displays` (for `display_error`) |
| `cli/components/displays.py` | *(none)* |
| `cli/components/progress.py` | *(none)* |

**Key design rule enforced here:** `prompts.py` is the **only** file that imports `questionary` and `prompt_toolkit`. All handlers must go through this module to interact with the user.

**What depends on `cli/components/`:**
- `cli/handlers/` (every handler imports from here)
- `cli/menus/__init__.py` (imports `Q_STYLE`)

---

## `cli/handlers/`

One handler per menu operation. Each handler imports UI primitives from `cli/components/` and delegates to domain modules (`context_retrieving/`, `scripts/`).

| File | Imports from |
|------|-------------|
| `cli/handlers/__init__.py` | All sibling handler files (re-exports) |
| `cli/handlers/repository.py` | `cli/components/` · `cli/config` · **`context_retrieving/generate_tree`** |
| `cli/handlers/context.py` | `cli/components/` · `cli/config` |
| `cli/handlers/extraction.py` | `cli/components/` · `cli/config` |
| `cli/handlers/prediction.py` | `cli/components/` · `cli/config` |
| `cli/handlers/cleanup.py` | `cli/components/` · **`scripts/dataset_cleanup`** |
| `cli/handlers/verification.py` | `cli/components/` · `cli/config` · **`scripts/verify_pr_completeness`** |
| `cli/handlers/subset.py` | `cli/components/` · `cli/config` · **`scripts/create_pr_subset`** · **`scripts/extract_python_pr_paths`** |
| `cli/handlers/testing.py` | `cli/components/` · `cli/config` |
| `cli/handlers/settings.py` | *(none)* |

**Cross-folder dependencies introduced here:**
- `repository.py` → `context_retrieving/` (the only CLI→analysis bridge for the tree generator)
- `cleanup.py`, `verification.py`, `subset.py` → `scripts/` (delegate file-system operations to script utilities)

**What depends on `cli/handlers/`:**
- `cli/menus/main_menu.py` (maps menu items to handler functions)

---

## `cli/menus/`

Arrow-key navigation loop. Knows about handlers (to call them) and components (for the questionary style token).

| File | Imports from |
|------|-------------|
| `cli/menus/__init__.py` | `cli/components/prompts` (for `Q_STYLE`) |
| `cli/menus/main_menu.py` | `cli/menus/__init__` · `cli/handlers/` (all public handlers) |

**What depends on `cli/menus/`:**
- `cli/app.py` (instantiates `MainMenu` and starts the loop)

---

## `context_retrieving/`

Pure analysis engine. No dependencies on any other internal folder — it only uses `tree-sitter` and stdlib.

| File | Imports from |
|------|-------------|
| `context_retrieving/__init__.py` | `call_graph_builder`, `context_generator`, `generate_tree`, `batch_context_retriever` (all internal siblings) |
| `context_retrieving/call_graph_builder.py` | *(none)* |
| `context_retrieving/context_generator.py` | *(none)* |
| `context_retrieving/generate_tree.py` | *(none)* |
| `context_retrieving/batch_context_retriever.py` | Sibling modules within `context_retrieving/` |

**What depends on `context_retrieving/`:**
- `cli/handlers/repository.py` → `generate_tree`
- `GenAI/tools.py` → `call_graph_builder`, `context_generator`
- `tests/test_call_graph_builder.py`, `tests/test_context_generator.py`

---

## `evaluation/`

PR analysis pipeline. Internally self-contained except for one upward dependency on `GenAI/prompts/` (for the step planner prompt).

| File | Imports from |
|------|-------------|
| `evaluation/__init__.py` | `evaluation/models` |
| `evaluation/models.py` | *(none — Pydantic only)* |
| `evaluation/pr_loader.py` | *(none)* |
| `evaluation/diff_parser.py` | *(none)* |
| `evaluation/function_matcher.py` | *(none — tree-sitter only)* |
| `evaluation/utils.py` | *(none)* |
| `evaluation/step_planner.py` | **`GenAI/prompts`** (for `get_step_planner_prompt`) · `evaluation/models` |
| `evaluation/ground_truth_extractor.py` | `evaluation/pr_loader` · `evaluation/diff_parser` · `evaluation/function_matcher` · `evaluation/models` · `evaluation/step_planner` · `evaluation/utils` |

**Cross-folder dependency introduced here:**
- `evaluation/step_planner.py` → `GenAI/prompts/` — the only place where the evaluation pipeline reaches into the AI layer to retrieve a prompt template.

**What depends on `evaluation/`:**
- `GenAI/batch_predict.py` → `GenAI/pr_step_planner` (which in turn uses evaluation models)

---

## `GenAI/`

Multi-agent AI system. Depends on `GenAI/prompts/` for all LLM system prompts and on `context_retrieving/` for code analysis tools.

| File | Imports from |
|------|-------------|
| `GenAI/__init__.py` | *(none)* |
| `GenAI/agent.py` | **`GenAI/tools`** · **`GenAI/prompts`** (`COSTANZA_PROMPT`, `CLARIFICATION_AGENT_PROMPT`) |
| `GenAI/tools.py` | **`context_retrieving/call_graph_builder`** · **`context_retrieving/context_generator`** |
| `GenAI/batch_predict.py` | **`GenAI/pr_step_planner`** |
| `GenAI/pr_step_planner.py` | **`GenAI/prompts`** (`get_analysis_agent_prompt`, `CONTEXT_PLANNER_PROMPT`) · **`GenAI/tools`** |
| `GenAI/masca_runner.py` | **`GenAI/prompts`** (`get_masca_prompt`) |
| `GenAI/evaluate_predictions.py` | *(none)* |

**Cross-folder dependency introduced here:**
- `GenAI/tools.py` → `context_retrieving/` — this is the bridge that lets AI agents query the call graph and generate context files.

**What depends on `GenAI/`:**
- `evaluation/step_planner.py` → `GenAI/prompts/`
- `tests/test_tools.py` → `GenAI/tools`

---

## `GenAI/prompts/`

**Leaf node.** Pure string constants and template functions. No internal imports whatsoever. This is the single source of truth for every LLM system prompt in the project.

| File | Imports from |
|------|-------------|
| `GenAI/prompts/__init__.py` | All sibling prompt files (re-exports everything) |
| `GenAI/prompts/step_planner.py` | *(none)* |
| `GenAI/prompts/analysis_agent.py` | *(none)* |
| `GenAI/prompts/context_planner.py` | *(none)* |
| `GenAI/prompts/costanza.py` | *(none)* |
| `GenAI/prompts/clarification_agent.py` | *(none)* |
| `GenAI/prompts/masca.py` | *(none)* |

**What depends on `GenAI/prompts/`:**
- `GenAI/agent.py`
- `GenAI/pr_step_planner.py`
- `GenAI/masca_runner.py`
- `evaluation/step_planner.py`

---

## `scripts/`

Standalone utility scripts for file-system operations on the PR dataset. Mostly self-contained; one internal dependency between scripts.

| File | Imports from |
|------|-------------|
| `scripts/__init__.py` | *(none)* |
| `scripts/dataset_cleanup.py` | *(none)* |
| `scripts/verify_pr_completeness.py` | *(none)* |
| `scripts/extract_python_pr_paths.py` | *(none)* |
| `scripts/create_pr_subset.py` | **`scripts/extract_python_pr_paths`** |
| `scripts/generate_context_outputs.py` | *(none — runs as __main__)* |

**What depends on `scripts/`:**
- `cli/handlers/cleanup.py` → `scripts/dataset_cleanup`
- `cli/handlers/verification.py` → `scripts/verify_pr_completeness`
- `cli/handlers/subset.py` → `scripts/create_pr_subset`, `scripts/extract_python_pr_paths`

---

## `tests/`

Test suite. Depends only on the public APIs of the analysis and AI layers, never on the CLI.

| File | Imports from |
|------|-------------|
| `tests/conftest.py` | *(none)* |
| `tests/test_call_graph_builder.py` | **`context_retrieving/call_graph_builder`** |
| `tests/test_context_generator.py` | **`context_retrieving/call_graph_builder`** · **`context_retrieving/context_generator`** |
| `tests/test_tools.py` | **`GenAI/tools`** |
| `tests/test_docstring_handling.py` | `context_retrieving/` (likely `call_graph_builder`) |
| `tests/test_masca_integration.py` | `GenAI/` (likely `masca_runner`) |
| `tests/test_read_context_file.py` | `context_retrieving/` (likely `context_generator`) |

**What depends on `tests/`:** Nothing. Tests are a terminal node.

---

## Cross-Folder Dependency Matrix

The table below shows which folders import from which. A ✓ means "row folder imports from column folder."

|                    | `GenAI/prompts` | `context_retrieving` | `evaluation` | `GenAI` | `scripts` | `cli/config` | `cli/components` | `cli/handlers` | `cli/menus` |
|--------------------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **`GenAI/prompts`** | — | | | | | | | | |
| **`context_retrieving`** | | — | | | | | | | |
| **`scripts`** | | | | | — | | | | |
| **`evaluation`** | ✓ | | — | | | | | | |
| **`GenAI`** | ✓ | ✓ | | — | | | | | |
| **`cli/components`** | | | | | | ✓ | — | | |
| **`cli/handlers`** | | ✓ | | | ✓ | ✓ | ✓ | — | |
| **`cli/menus`** | | | | | | | ✓ | ✓ | — |
| **`cli/app`** | | | | | | ✓ | | | ✓ |
| **`tests`** | | ✓ | | ✓ | | | | | |
