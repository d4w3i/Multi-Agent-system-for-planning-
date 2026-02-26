#!/usr/bin/env python3
"""
=============================================================================
EXTRACT_PYTHON_PR_PATHS.PY - Filter PRs with Python-Only Files
=============================================================================

This script extracts paths of PR folders that contain only Python files
in the modified_files/ and original_files/ subdirectories.

PURPOSE:

    The PR4Code dataset contains PRs with various file types. This script
    filters to find PRs that only modify Python files, useful for:
    - Building Python-specific evaluation subsets
    - Ensuring consistent analysis scope
    - Filtering for language-specific model training

FILTERING LOGIC:

    A PR is included if ALL of the following are true:
    1. Both modified_files/ and original_files/ directories exist
    2. At least one file exists in these directories
    3. ALL files have the .py extension (excluding hidden files like .DS_Store)

OUTPUT:

    Lists of:
    - Unique repository names containing Python-only PRs
    - Absolute paths to all qualifying PR directories

USAGE:

    # Run standalone to see Python-only PRs
    python -m scripts.extract_python_pr_paths

    # Import for use in other scripts
    from scripts.extract_python_pr_paths import get_python_only_pr_paths

    pr_paths = get_python_only_pr_paths("PR4Code/dataset_pr_commits_py")

=============================================================================
"""

from pathlib import Path


def get_python_only_pr_paths(dataset_path: str) -> list[str]:
    """
    Returns absolute paths of PR folders that contain
    only Python files in modified_files and original_files.

    Args:
        dataset_path: Path to the dataset folder (e.g., PR4Code/dataset_pr_commits_py)

    Returns:
        List of absolute paths of PR folders with Python-only files
    """
    python_only_prs = []
    dataset_path = Path(dataset_path).resolve()

    # Iterate over all repositories
    for repo_dir in dataset_path.iterdir():
        if not repo_dir.is_dir():
            continue

        # Iterate over all PRs in the repository
        for pr_dir in repo_dir.iterdir():
            if not pr_dir.is_dir() or not pr_dir.name.startswith("pr_"):
                continue

            modified_files_dir = pr_dir / "modified_files"
            original_files_dir = pr_dir / "original_files"

            # Verify both directories exist
            if not modified_files_dir.exists() or not original_files_dir.exists():
                continue

            # Collect all files (excluding .DS_Store and other hidden files)
            all_files = []

            for files_dir in [modified_files_dir, original_files_dir]:
                for file_path in files_dir.rglob("*"):
                    if file_path.is_file() and not file_path.name.startswith("."):
                        all_files.append(file_path)

            # Verify there are files and they are all .py
            if all_files and all(f.suffix == ".py" for f in all_files):
                python_only_prs.append(str(pr_dir))

    return sorted(python_only_prs)


def get_unique_repos(pr_paths: list[str]) -> list[str]:
    """
    Extracts unique repository names from PR paths.

    Args:
        pr_paths: List of absolute paths of PR folders

    Returns:
        Sorted list of unique repository names
    """
    repos = set()
    for pr_path in pr_paths:
        # The repo name is the parent directory of the pr_XXX folder
        repo_name = Path(pr_path).parent.name
        repos.add(repo_name)
    return sorted(repos)


def main():
    # Default path to the Python dataset (relative to project root)
    default_dataset_path = "PR4Code/dataset_pr_commits_py"

    # Resolve dataset path relative to project root (one level above scripts/)
    project_root = Path(__file__).parent.parent
    dataset_path = project_root / default_dataset_path

    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path}")
        return

    # Extract paths
    pr_paths = get_python_only_pr_paths(dataset_path)

    # Extract unique repository names
    unique_repos = get_unique_repos(pr_paths)

    print("=" * 60)
    print(f"UNIQUE REPOSITORIES ({len(unique_repos)}):")
    print("=" * 60)
    for repo in unique_repos:
        print(repo)

    print("\n" + "=" * 60)
    print(f"PR PATHS WITH PYTHON-ONLY FILES ({len(pr_paths)}):")
    print("=" * 60)
    for path in pr_paths:
        print(path)


if __name__ == "__main__":
    main()
