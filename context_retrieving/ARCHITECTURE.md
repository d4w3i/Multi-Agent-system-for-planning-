# Architecture — `context_retrieving`

## 1. Module Overview

The `context_retrieving` package analyses Python repositories to build
function call graphs and generate *AI-ready context files* — text files that
bundle a target function with all its transitive dependencies and usage
examples, ready to be fed directly to an LLM.

It is consumed by:
- The interactive CLI (`cli/handlers/repository.py`, `cli/handlers/context.py`)
- The batch pipeline (`context_retrieving.batch_context_retriever`)
- The evaluation layer (`evaluation/`)

---

## 2. Pipeline Diagram

```
Input: repository path
          │
          ▼
┌─────────────────────┐
│  CallGraphBuilder   │  Stage 1 — AST analysis (Tree-sitter, 4-pass)
│  call_graph_builder │
└────────┬────────────┘
         │  call_graph: dict
         ├──────────────────────────────────────────────┐
         ▼                                              ▼
┌─────────────────────┐                    ┌──────────────────────┐
│  ContextGenerator   │  Stage 2a          │   TreeGenerator      │  Stage 2b
│  context_generator  │  context files     │   generate_tree      │  ASCII tree
└─────────────────────┘                    └──────────────────────┘
         │                                              │
         └──────────────────────┬───────────────────────┘
                                ▼
                  ┌──────────────────────────┐
                  │  BatchContextRetriever   │  Stage 3 — orchestration over
                  │  batch_context_retriever │  entire PR4Code dataset
                  └──────────────────────────┘
                                │
                                ▼
              pr_dir/context_output/
              ├── call_graph.json
              ├── project_tree.txt
              ├── project_info.py
              └── context_files/
```

---

## 3. CallGraphBuilder — 4-Pass Analysis

`call_graph_builder.py` (with helpers in `_ast_visitors.py`)

### Why 4 passes?

A single-pass traversal cannot correctly resolve function call names because
when a call site is encountered, the definition of the called function may not
have been seen yet (it could live in another file, or later in the same file).
The 4-pass design solves this:

| Pass | What it does | Why first |
|------|-------------|-----------|
| 0 | Extract all `import` statements per file → `import_map` | Names like `pd.read_csv` can only be resolved if we know `pd = pandas` |
| 1 | Extract all function/class definitions → `all_functions`, `all_classes` | Call resolution in Pass 2 requires the complete function universe |
| 2 | Extract and resolve call sites → populate `calls` / `called_by` | Now every name can be looked up |
| 3 | Mark `is_leaf` and `is_entry_point` flags | Requires complete `calls` / `called_by` lists |

### Key data structures

```python
call_graph: defaultdict   # {full_name: {file, line, calls, called_by,
                          #              code, is_leaf, is_entry_point,
                          #              class_name, is_method, full_name}}
all_functions: set        # {"module.Class.method", ...}
all_classes: set          # {"module.Class", ...}
import_map: dict          # {filepath: {alias: full_name}}
_suffix_index: dict       # {short_name: [full_names]} — rebuilt lazily
```

---

## 4. Name Resolution Strategy

`_ASTVisitorMixin._resolve_function_call()` applies five strategies in order,
returning on the first match:

| Level | Strategy | Example |
|-------|----------|---------|
| 1 | `import_map` of the current file | `pd` → `pandas`, then look for `pandas.func` |
| 2 | Current class method | Inside `MyClass`, `helper()` → `module.MyClass.helper` |
| 3 | Local module function | In `utils.py`, `helper()` → `utils.helper` |
| 4 | Global exact match | `helper` exists as a top-level name in `all_functions` |
| 5 | Suffix index (partial) | `process` matches the single function `pkg.sub.process` |

Strategy 5 uses `_suffix_index` — a dict mapping the last name component to a
list of fully-qualified names — rebuilt lazily whenever `all_functions` changes.
A partial match is only accepted when there is **exactly one** candidate; ties
are dropped to avoid false edges.

---

## 5. ContextGenerator — Transitive Dependency DFS

`context_generator.py`

For each target function, `get_all_dependencies()` performs an **iterative
depth-first search** over the call graph:

```
stack = [target_func]
while stack:
    current = stack.pop()
    if current in visited or current not in call_graph: continue
    visited.add(current)
    for dep in call_graph[current]['calls']:
        if dep not in visited: stack.append(dep)
return visited  # includes target_func itself
```

Using an explicit stack instead of recursion avoids `RecursionError` on deep
or cyclic call chains. The caller discards the target from the returned set
before writing the context file.

### Output layout

Each `.py` source file becomes a **directory** in the output tree, mirroring
the repository structure:

```
repo/src/utils/helpers.py
  → context_files/src/utils/helpers/
        module.utils.helpers.validate_context.txt
        module.utils.helpers.validate_metadata.json
```

---

## 6. TreeGenerator

`generate_tree.py`

Generates a Unix-`tree`-style ASCII representation.

### Ignore patterns

Two layers of exclusion:

1. **Default patterns** (`DEFAULT_IGNORE_PATTERNS`) — hardcoded set covering
   `.git`, `__pycache__`, `node_modules`, `.venv`, build artefacts, etc.
2. **`.gitignore` patterns** — loaded from `<root>/.gitignore` on construction
   (simple patterns only; negation `!` and `**` globs are not supported).

### Prefix construction algorithm

The tree is built by `_generate_tree(directory, prefix, depth)`:

- Entries are sorted: directories first, then files, both alphabetically.
- For each entry, the connector is `LAST` (`└── `) if it is the final entry,
  else `BRANCH` (`├── `).
- The child prefix is accumulated: `prefix + (SPACE if last else VERTICAL)`.
- Recursion stops when `depth >= max_depth`.

### CLI entry point

The interactive `main()` and the `Colors` class live in `_tree_cli.py` so that
importing `generate_tree` in library mode does not pull in `sys` or `time`.
When run directly (`python generate_tree.py`), the `__main__` block imports
`main` from `_tree_cli` and calls it.

---

## 7. BatchContextRetriever

`batch_context_retriever.py`

Orchestrates Stages 1–3 over an entire PR4Code dataset directory.

### Orchestration sequence (per PR)

```
1.  Verify base_project/ exists
2.  Create context_output/ and context_output/context_files/
3.  CallGraphBuilder.analyze_repository(base_project/)
4.  Export call_graph.json
5.  TreeGenerator → project_tree.txt
6.  Load README (tries README.md, .rst, .txt, bare README)
7.  [Optional] run_masca_analysis() → masca_analysis.md
8.  Write project_info.py  (DIRECTORY_TREE, README, MASCA variables)
9.  ContextGenerator.generate_all_context_files(context_files/)
```

### Output

All artefacts land in `pr_dir/context_output/`. A single
`masca_output_token.json` is written at the dataset root to aggregate LLM
token usage across all processed PRs.

---

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Tree-sitter instead of `ast.parse` | Handles syntax errors in partial/malformed files; faster on large repos; language-agnostic API |
| 4-pass pipeline | Guarantees all function names are known before any call site is resolved |
| Iterative DFS in `ContextGenerator` | Prevents `RecursionError` on deeply nested or mutually recursive call chains |
| `_ASTVisitorMixin` split | Keeps `call_graph_builder.py` focused on orchestration; mixin owns Tree-sitter traversal details; both remain testable independently |
| `_tree_cli.py` split | Library import of `generate_tree` does not pull in interactive-CLI dependencies (`sys`, `time`, ANSI colours) |
| `with_masca` flag | Masca LLM analysis is entirely opt-in; the pipeline runs fully offline without an OpenAI key |
| `logging` module | Replaces scattered `print()` calls; callers control verbosity via standard `logging.basicConfig` or by configuring handlers |

---

## 9. Extension Guide

### Adding a new exporter (e.g. CSV)

1. Add a `to_csv(self, output_file: str)` method to `CallGraphBuilder`
   following the same pattern as `to_json`.
2. No changes needed to `_ast_visitors.py` or other files.

### Adding a new analysis pass

1. Add the traversal logic as a method on `_ASTVisitorMixin` in
   `_ast_visitors.py`.
2. Call it from `CallGraphBuilder.analyze_repository()` at the appropriate
   point in the pipeline — typically after Pass 1 (functions are known) or
   after Pass 2 (calls are known).
3. If the pass populates new fields on `call_graph` nodes, document them in
   the `__init__` defaultdict factory.

### Adding a new output format to `ContextGenerator`

1. Add a helper method, e.g. `generate_markdown_file(target_func, output_dir)`.
2. Call it from `generate_context_file` or expose it as a standalone method.
3. `get_all_dependencies` is reusable as-is for any new format.
