# Quick Guide

## How to Use

```bash
python main.py
```

Navigate with arrow keys, press Enter to select. Each operation offers **Express mode** (run with defaults) or **Configure** (customize options). Tab-completes directory paths.

## Main Menu

| # | Operation | Description |
|---|-----------|-------------|
| 1 | Repository Analysis | Clone + analyze a GitHub repo |
| 2 | Context Generation | Generate context files for PRs |
| 3 | Ground Truth | Extract truth from PR data |
| 4 | AI Predictions | Generate implementation plans |
| 5 | Verify Dataset | Check PR completeness |
| 6 | Create Subset | Fixed PR evaluation subset |
| 7 | Python PR Filter | Find Python-only PRs |
| 8 | Cleanup | Remove generated files |
| 9 | Run Tests | Execute pytest suite |
| 0 | Settings | Configuration and status |

## Repository Analysis (6 steps)

1. **Input Repository** — Enter URL (autocompletes from recent repos)
2. **Clone Repository** — Downloads to `repos/REPO_NAME/`
3. **Code Analysis** — 4-pass pipeline (imports → functions → calls → finalize)
4. **Output Generation** — Creates JSON, DOT, context files
5. **Project Info** — Creates project_info.py with README and directory tree
6. **Masca AI Analysis** — AI project analysis (if API key configured)

### Output
Everything saved in `output/REPO_NAME/`:
```
output/REPO_NAME/
├── project_info.py           # README and directory tree as Python variables
├── call_graph.json           # Complete machine-readable graph
├── call_graph.dot            # Graphviz diagram (generates PNG/SVG/PDF)
└── context_files/            # Hierarchical structure mirroring the repo
    └── src/
        └── module/
            ├── file1/                    ← file1.py becomes directory
            │   ├── function1_context.txt
            │   ├── function1_metadata.json
            │   ├── function2_context.txt
            │   └── function2_metadata.json
            └── file2/                    ← file2.py becomes directory
                ├── MyClass.__init___context.txt
                ├── MyClass.__init___metadata.json
                └── ...
```

After analysis, you're asked whether to remove the cloned repo.

## Supported URLs

```
https://github.com/user/repo
https://github.com/user/repo.git
git@github.com:user/repo.git
```

## Hierarchical Context Files

Context files maintain exactly the structure of the original repository:

### Original Repository
```
my_project/
├── src/
│   ├── core/
│   │   └── engine.py        # contains: init_engine(), run_engine()
│   ├── utils/
│   │   └── helpers.py       # contains: validate(), process()
│   └── models/
│       └── user.py          # contains: User.__init__(), User.save()
└── tests/
    └── test_core.py         # contains: test_engine()
```

### Generated Context Files
```
context_files/
├── src/
│   ├── core/
│   │   └── engine/                    ← engine.py becomes directory
│   │       ├── init_engine_context.txt
│   │       ├── init_engine_metadata.json
│   │       ├── run_engine_context.txt
│   │       └── run_engine_metadata.json
│   ├── utils/
│   │   └── helpers/                   ← helpers.py becomes directory
│   │       ├── validate_context.txt
│   │       ├── validate_metadata.json
│   │       ├── process_context.txt
│   │       └── process_metadata.json
│   └── models/
│       └── user/                      ← user.py becomes directory
│           ├── User.__init___context.txt
│           ├── User.__init___metadata.json
│           ├── User.save_context.txt
│           └── User.save_metadata.json
└── tests/
    └── test_core/                     ← test_core.py becomes directory
        ├── test_engine_context.txt
        └── test_engine_metadata.json
```

## Output Files

**project_info.py**:
- Importable Python module
- `DIRECTORY_TREE` variable: Complete ASCII tree of the repository
- `README` variable: Content of README.md (if present)
- Usage example:
  ```python
  from output.repo_name.project_info import DIRECTORY_TREE, README
  print(DIRECTORY_TREE)
  print(README)
  ```

**call_graph.json**:
- All functions/methods found
- Complete dependencies (who calls whom)
- Metadata (file, line, code, class_name, is_method)
- Statistics (total_functions, entry_points, leaf_functions)

**call_graph.dot**:
- Graphviz diagram with ALL nodes (scales better than Mermaid)
- Colors: Green (entry points), Blue (leaf functions), White (regular)
- Generate visualizations:
  ```bash
  dot -Tpng call_graph.dot -o graph.png
  dot -Tsvg call_graph.dot -o graph.svg
  dot -Tpdf call_graph.dot -o graph.pdf
  ```

**context_files/**:
- **Hierarchical structure** that exactly mirrors the repository
- Each `.py` file becomes a **subdirectory**
- For each function:
  - `*_context.txt`: Dependencies + target function + callers
  - `*_metadata.json`: Structured metadata (file, line, dependencies, callers, flags)
- Ready for AI/LLM and intuitive navigation

## Requirements

- Python 3.13+
- Git installed
- `pip install -r requirements.txt`
- Optional: `OPENAI_API_KEY` in `.env` for AI features
- Optional: Graphviz for DOT visualization (`brew install graphviz` on macOS)

## Programmatic Usage

```python
# Use project_info.py with AI
from output.my_repo.project_info import README, DIRECTORY_TREE

# Analyze call graph
import json
with open('output/repo_name/call_graph.json') as f:
    data = json.load(f)
entry_points = [n for n, i in data['functions'].items() if i['is_entry_point']]
```

```bash
# Visualize DOT graph
dot -Tpng output/repo_name/call_graph.dot -o graph.png
```
