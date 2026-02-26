"""
=============================================================================
DATASET_CLEANUP.PY - Unified Dataset Cleanup Utility
=============================================================================

This script provides a unified interface for cleaning up generated files
and directories in the PR4Code dataset. It replaces three separate scripts:
- delete_context_outputs.py
- delete_ground_truths.py
- delete_predicted_plans.py

SUPPORTED TARGETS:

    Target              Type        Pattern
    ─────────────────────────────────────────────────────
    context_output      directory   context_output/
    ground_truth        file        ground_truth.json
    predicted_plan      file        predicted_plan.json

=============================================================================
USAGE GUIDE
=============================================================================

BASIC COMMANDS:
---------------

    # Show what would be deleted (dry-run, SAFE DEFAULT)
    python -m scripts.dataset_cleanup --target ground_truth

    # Actually delete
    python -m scripts.dataset_cleanup --target ground_truth --delete

    # Clean up all target types at once
    python -m scripts.dataset_cleanup --target all --delete


AVAILABLE OPTIONS:
------------------

    --target TARGET     What to delete: context_output, ground_truth,
                        predicted_plan, or "all" (required)
    --dir DIR           Base directory to search (default: PR4Code)
    --delete            Actually delete (without this flag, dry-run only)


EXAMPLES:
---------

    # 1. Preview ground truth files that would be deleted
    python -m scripts.dataset_cleanup --target ground_truth

    # 2. Delete all context_output directories
    python -m scripts.dataset_cleanup --target context_output --delete

    # 3. Delete all predicted plans in a specific subdirectory
    python -m scripts.dataset_cleanup --target predicted_plan --dir PR4Code/dataset_pr_commits_py --delete

    # 4. Clean everything (context + ground truth + predictions)
    python -m scripts.dataset_cleanup --target all --delete


NOTES:
------
    - By default the script operates in DRY-RUN mode (deletes nothing)
    - Always run without --delete first to verify what will be deleted
    - Deleted files/directories CANNOT be recovered

=============================================================================
"""

import argparse
import shutil
from pathlib import Path
from typing import NamedTuple


# =============================================================================
# TARGET DEFINITIONS
# =============================================================================

class TargetConfig(NamedTuple):
    """Configuration for a cleanup target."""
    pattern: str        # Glob pattern to search for
    is_directory: bool  # True if target is a directory, False if file
    description: str    # Human-readable description


# Supported cleanup targets
TARGETS = {
    "context_output": TargetConfig(
        pattern="context_output",
        is_directory=True,
        description="context output directories"
    ),
    "ground_truth": TargetConfig(
        pattern="ground_truth.json",
        is_directory=False,
        description="ground truth files"
    ),
    "predicted_plan": TargetConfig(
        pattern="predicted_plan.json",
        is_directory=False,
        description="predicted plan files"
    ),
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_size_human(path: Path) -> str:
    """
    Calculate the size of a file or directory in human-readable format.

    Args:
        path: Path to file or directory

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    try:
        if path.is_file():
            total = path.stat().st_size
        else:
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

        if total < 1024:
            return f"{total} B"
        elif total < 1024 * 1024:
            return f"{total / 1024:.1f} KB"
        elif total < 1024 * 1024 * 1024:
            return f"{total / (1024 * 1024):.1f} MB"
        else:
            return f"{total / (1024 * 1024 * 1024):.1f} GB"
    except (OSError, PermissionError):
        return "? KB"


def count_files_in_dir(path: Path) -> int:
    """
    Count the number of files in a directory.

    Args:
        path: Path to directory

    Returns:
        Number of files (0 if path is a file or on error)
    """
    try:
        return sum(1 for f in path.rglob("*") if f.is_file())
    except (OSError, PermissionError):
        return 0


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def find_targets(base_dir: str, target_name: str) -> list[Path]:
    """
    Find all targets matching the specified type in the directory.

    Callers are responsible for verifying that base_dir exists before calling
    this function — it is intentionally side-effect-free.

    Args:
        base_dir: Base directory to search in
        target_name: Target type (context_output, ground_truth, predicted_plan)

    Returns:
        Sorted list of Paths to found targets
    """
    base_path = Path(base_dir)
    config = TARGETS[target_name]

    # Recursively search for all matching targets
    if config.is_directory:
        results = [p for p in base_path.rglob(config.pattern) if p.is_dir()]
    else:
        results = list(base_path.rglob(config.pattern))

    return sorted(results)


def delete_targets(
    targets: list[Path],
    is_directory: bool,
    dry_run: bool = True
) -> tuple[int, int]:
    """
    Delete the specified targets (files or directories).

    Args:
        targets: List of paths to delete
        is_directory: True if targets are directories
        dry_run: If True, only shows what would be deleted

    Returns:
        Tuple (deleted_count, error_count)
    """
    deleted = 0
    errors = 0

    for path in targets:
        try:
            size = get_size_human(path)

            if is_directory:
                file_count = count_files_in_dir(path)
                info = f"({file_count} files, {size})"
            else:
                info = f"({size})"

            if dry_run:
                print(f"  > {path} {info}")
            else:
                if is_directory:
                    shutil.rmtree(path)
                else:
                    path.unlink()
                print(f"  [OK] Deleted: {path} {info}")
                deleted += 1

        except Exception as e:
            print(f"  [ERROR] {path} - {e}")
            errors += 1

    return deleted, errors


def cleanup_target(base_dir: str, target_name: str, delete: bool = False) -> tuple[int, int]:
    """
    Find and optionally delete all instances of a target type.

    Args:
        base_dir: Base directory to search in
        target_name: Target type to clean up
        delete: If True, actually delete; if False, dry-run only

    Returns:
        Tuple (deleted_count, error_count)
    """
    config = TARGETS[target_name]

    print(f"\nSearching for {config.description} in: {base_dir}/\n")

    if not Path(base_dir).exists():
        print(f"Directory not found: {base_dir}\n")
        return 0, 0

    targets = find_targets(base_dir, target_name)

    if not targets:
        print(f"No {config.description} found.\n")
        return 0, 0

    if delete:
        print(f"Deleting {len(targets)} {config.description}...\n")
        deleted, errors = delete_targets(targets, config.is_directory, dry_run=False)
        print(f"\n{'='*60}")
        print(f"Deleted: {deleted}")
        if errors:
            print(f"Errors: {errors}")
        print(f"{'='*60}\n")
        return deleted, errors
    else:
        print(f"Found {len(targets)} {config.description}:\n")
        delete_targets(targets, config.is_directory, dry_run=True)
        print(f"\n{'='*60}")
        print(f"DRY-RUN mode: nothing deleted.")
        print(f"Use --delete to actually delete.")
        print(f"{'='*60}\n")
        return 0, 0


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point for CLI usage."""

    parser = argparse.ArgumentParser(
        description="Clean up generated files and directories from the PR4Code dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.dataset_cleanup --target ground_truth
  python -m scripts.dataset_cleanup --target context_output --delete
  python -m scripts.dataset_cleanup --target all --dir PR4Code/subset --delete
        """
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=list(TARGETS.keys()) + ["all"],
        help="What to delete: context_output, ground_truth, predicted_plan, or 'all'"
    )
    parser.add_argument(
        "--dir",
        default="PR4Code",
        help="Base directory to search in (default: PR4Code)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete (default: dry-run mode)"
    )

    args = parser.parse_args()

    # Determine which targets to process
    if args.target == "all":
        target_names = list(TARGETS.keys())
    else:
        target_names = [args.target]

    # Process each target
    total_deleted = 0
    total_errors = 0

    for target_name in target_names:
        deleted, errors = cleanup_target(args.dir, target_name, args.delete)
        total_deleted += deleted
        total_errors += errors

    # Summary for "all" mode
    if args.target == "all" and args.delete:
        print(f"\n{'='*60}")
        print(f"TOTAL DELETED: {total_deleted}")
        if total_errors:
            print(f"TOTAL ERRORS: {total_errors}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
