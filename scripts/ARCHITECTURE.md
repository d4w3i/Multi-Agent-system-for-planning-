# scripts/ — Architecture Reference

## Overview

This package provides five utility scripts for managing the **PR4Code dataset**: filtering PRs by language, creating reproducible evaluation subsets, generating context files, verifying dataset completeness, and cleaning up generated artifacts.

Three modules form a linear pipeline; two are fully standalone:

```
extract_python_pr_paths  ←  create_pr_subset  ←  generate_context_outputs

dataset_cleanup          (standalone)
verify_pr_completeness   (standalone)
```

---

## Module Reference

### `extract_python_pr_paths.py` — PR Language Filter

**Role:** Foundation layer. Scans the dataset and returns only those PRs where every file in `modified_files/` and `original_files/` is a `.py` file.

**Public API:**

```python
get_python_only_pr_paths(dataset_path: str) -> list[str]
get_unique_repos(pr_paths: list[str]) -> list[str]
```

**Filtering logic (all conditions required):**

1. Both `modified_files/` and `original_files/` directories must exist.
2. At least one non-hidden file must exist across both directories.
3. Every non-hidden file must carry a `.py` extension.

**Output:** Sorted list of absolute paths for deterministic downstream consumption.

---

### `create_pr_subset.py` — Reproducible Subset Creator

**Role:** Middle layer. Selects at most one PR per repository using seeded randomness, producing a JSON file that pins the exact subset for all downstream scripts.

**Public API:**

```python
create_pr_subset(dataset_path, size=100, seed=42, output_file=None) -> dict
load_pr_subset_data(subset_file: str) -> dict   # full JSON with metadata + prs
load_pr_subset(subset_file: str) -> list[str]   # convenience wrapper: paths only
```

**Subset JSON schema:**

```json
{
  "metadata": {
    "created_at": "<ISO-8601>",
    "dataset_path": "<absolute path>",
    "total_python_only_prs": 423,
    "total_repos": 312,
    "subset_size": 100,
    "random_seed": 42,
    "constraints": ["Python-only files in modified_files/ and original_files/",
                    "One PR per repository"]
  },
  "prs": [
    { "repo": "owner_repo", "pr": "pr_42", "path": "<absolute path>" }
  ]
}
```

**Reproducibility guarantee:** `random.seed(seed)` is set before every sampling call. The repo key list fed to `random.sample` has a deterministic insertion order (derived from the sorted `all_pr_paths` input), and selected repos are then iterated in sorted order for stable output.

---

### `generate_context_outputs.py` — Batch Context Generator

**Role:** Top of the pipeline. For each PR, runs the full context-generation workflow (call graph, project tree, project info, optional MASCA analysis).

**PR source modes:**

- **Subset mode** (`--subset <file>`): reads the exact PR list from a JSON file produced by `create_pr_subset.py` and prints its metadata (creation date, seed, count).
- **Scan mode** (default): discovers all PRs that contain a `base_project/` directory under `--dir`.

**Filter chain (applied in order):**

1. `--skip-existing` — removes PRs that already have `context_output/call_graph.json`.
2. `--limit N` — caps the working list at N entries.

**Output per PR:**

```
pr_123/context_output/
├── call_graph.json
├── project_tree.txt
├── project_info.py
├── masca_analysis.md   (only when MASCA is enabled)
└── context_files/      (hierarchical per-function structure)
```

**Optional dependencies:** `tqdm` for progress bars; `context_retrieving` for the actual generation. Both are imported with `try/except` and degrade gracefully — `tqdm` falls back to a plain iterator; a missing `context_retrieving` exits early with a clear error.

---

### `dataset_cleanup.py` — Artifact Cleanup Utility

**Role:** Standalone, safe-by-default tool for removing generated artifacts. Defaults to dry-run mode; deletion requires an explicit `--delete` flag.

**Public API:**

```python
find_targets(base_dir: str, target_name: str) -> list[Path]           # pure — no side effects
delete_targets(targets, is_directory, dry_run=True) -> tuple[int, int]
cleanup_target(base_dir, target_name, delete=False) -> tuple[int, int]
```

`find_targets` is intentionally side-effect-free: all user-facing messages (including "Directory not found") live in `cleanup_target`, which orchestrates the scan-then-delete flow.

**Supported targets (`TARGETS` dict, keyed by CLI name):**

| Key | Pattern | Type | Description |
|-----|---------|------|-------------|
| `context_output` | `context_output` | directory | generated context directories |
| `ground_truth` | `ground_truth.json` | file | ground truth extraction results |
| `predicted_plan` | `predicted_plan.json` | file | AI-generated implementation plans |

`TargetConfig` is a `NamedTuple` that centralises every target's pattern, type, and description, making it trivial to add new artifact types.

**Size helpers:** `get_size_human(path)` and `count_files_in_dir(path)` both catch `OSError`/`PermissionError` and return safe fallbacks, so a permissions issue on a single item never aborts the scan.

---

### `verify_pr_completeness.py` — Dataset Validator

**Role:** Standalone. Checks which PRs (those that have `ground_truth.json`) also have `base_project/` and `context_output/`.

**Data model:**

```python
@dataclass
class PRStatus:
    pr_path: str
    has_ground_truth: bool
    has_base_project: bool
    has_context_output: bool

    @property
    def is_complete(self) -> bool: ...      # all three present

    @property
    def missing(self) -> list[str]: ...     # names of absent items

    def get_short_path(self) -> str: ...    # returns "repo/pr_xxx"
```

**Public API:**

```python
find_prs_with_ground_truth(base_dir="PR4Code") -> list[Path]
check_pr_directory(pr_dir: Path) -> PRStatus
categorize_statuses(statuses: list[PRStatus]) -> dict
```

`categorize_statuses` is called exactly once in `main()` and its result is passed to whichever formatter is active — eliminating redundant computation when output mode switches between table and JSON.

**Output categories:**

- `complete` — all three artifacts present
- `missing_base_project_only`
- `missing_context_output_only`
- `missing_both`

**Output modes:**

- **Default (table):** human-readable summary with per-category PR lists capped at 20 entries.
- **`--json`:** machine-readable; same four categories plus a full `asdict()` dump of every `PRStatus`.

---

## Shared Conventions

| Convention | Detail |
|---|---|
| **Safe defaults** | Destructive operations require an explicit opt-in flag (`--delete`) |
| **`argparse` + `main()`** | Every script has a `main()` function and an `if __name__ == "__main__": main()` guard |
| **Sorted output** | All collections returned to callers are sorted for determinism |
| **`pathlib.Path`** | Used internally throughout; plain `str` only at serialisation boundaries |
| **Error resilience** | I/O helpers catch `OSError`/`PermissionError` and return safe fallbacks |
| **Optional dependencies** | `tqdm` and `context_retrieving` use `try/except` with graceful degradation |
| **Pure core functions** | Functions meant to be imported (e.g., `find_targets`, `get_python_only_pr_paths`) have no print side-effects; all user-facing output lives in orchestration functions (`cleanup_target`, `main`) |

---

## Running the Scripts

```bash
# Filter Python-only PRs
python -m scripts.extract_python_pr_paths

# Create 100-PR reproducible subset (seed=42)
python -m scripts.create_pr_subset --size 100 --output PR4Code/pr_subset_100.json

# Dry-run: preview what would be generated
python -m scripts.generate_context_outputs --subset PR4Code/pr_subset_100.json --dry-run

# Generate context for subset (MASCA enabled, skip already-done)
python -m scripts.generate_context_outputs --subset PR4Code/pr_subset_100.json --skip-existing

# Generate without MASCA
python -m scripts.generate_context_outputs --subset PR4Code/pr_subset_100.json --no-masca

# Verify dataset completeness
python -m scripts.verify_pr_completeness
python -m scripts.verify_pr_completeness --only-incomplete
python -m scripts.verify_pr_completeness --json > status.json

# Preview what would be deleted (safe — dry-run is the default)
python -m scripts.dataset_cleanup --target all

# Delete a specific artifact type
python -m scripts.dataset_cleanup --target context_output --delete
python -m scripts.dataset_cleanup --target all --delete
```
