#!/usr/bin/env python3
"""
=============================================================================
CREATE_PR_SUBSET.PY - Create a fixed subset of PRs for evaluation
=============================================================================

This script creates a fixed subset of PRs from the PR4Code dataset.
The subset is saved to a JSON file for reproducibility across:
- Context generation
- Ground truth extraction
- Predicted plan generation

CONSTRAINTS:
- Only PRs with Python-only files in modified_files/ and original_files/
- One PR per repository (100 different repos)
- Random selection with fixed seed for reproducibility

=============================================================================
USAGE
=============================================================================

    # Create subset with default settings (100 PRs, seed=42)
    python create_pr_subset.py

    # Create subset with custom size
    python create_pr_subset.py --size 50

    # Create subset with different seed
    python create_pr_subset.py --seed 123

    # Specify output file
    python create_pr_subset.py --output my_subset.json

    # Show subset without saving (dry-run)
    python create_pr_subset.py --dry-run

=============================================================================
"""

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scripts.extract_python_pr_paths import get_python_only_pr_paths


def create_pr_subset(
    dataset_path: str,
    size: int = 100,
    seed: int = 42,
    output_file: str = None
) -> dict:
    """
    Create a fixed subset of PRs from different repositories.

    Args:
        dataset_path: Path to the dataset directory
        size: Number of PRs to select (one per repo)
        seed: Random seed for reproducibility
        output_file: Path to save the subset JSON (None = don't save)

    Returns:
        Dictionary with subset metadata and PR paths
    """
    # Get all Python-only PRs
    all_pr_paths = get_python_only_pr_paths(dataset_path)

    # Group PRs by repository
    prs_by_repo = defaultdict(list)
    for pr_path in all_pr_paths:
        repo_name = Path(pr_path).parent.name
        prs_by_repo[repo_name].append(pr_path)

    print(f"Found {len(all_pr_paths)} Python-only PRs from {len(prs_by_repo)} repositories")

    # Check if we have enough repos
    if len(prs_by_repo) < size:
        print(f"Warning: Only {len(prs_by_repo)} repositories available, requested {size}")
        size = len(prs_by_repo)

    # Set random seed for reproducibility
    random.seed(seed)

    # Randomly select repos
    selected_repos = random.sample(list(prs_by_repo.keys()), size)

    # For each selected repo, randomly select one PR
    selected_prs = []
    for repo in sorted(selected_repos):
        pr_path = random.choice(prs_by_repo[repo])
        pr_name = Path(pr_path).name
        selected_prs.append({
            "repo": repo,
            "pr": pr_name,
            "path": pr_path
        })

    # Create subset metadata
    subset = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "dataset_path": str(Path(dataset_path).resolve()),
            "total_python_only_prs": len(all_pr_paths),
            "total_repos": len(prs_by_repo),
            "subset_size": len(selected_prs),
            "random_seed": seed,
            "constraints": [
                "Python-only files in modified_files/ and original_files/",
                "One PR per repository"
            ]
        },
        "prs": selected_prs
    }

    # Save to file if specified
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(subset, f, indent=2, ensure_ascii=False)
        print(f"\nSubset saved to: {output_path}")

    return subset


def load_pr_subset_data(subset_file: str) -> dict:
    """
    Load the full data from a subset JSON file.

    Args:
        subset_file: Path to the subset JSON file

    Returns:
        Full subset dictionary with 'metadata' and 'prs' keys
    """
    with open(subset_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_pr_subset(subset_file: str) -> list[str]:
    """
    Load PR paths from a subset JSON file.

    Args:
        subset_file: Path to the subset JSON file

    Returns:
        List of PR paths
    """
    return [pr["path"] for pr in load_pr_subset_data(subset_file)["prs"]]


def main():
    parser = argparse.ArgumentParser(
        description="Create a fixed subset of PRs for evaluation"
    )

    parser.add_argument(
        "--dir",
        default="PR4Code/dataset_pr_commits_py",
        help="Dataset directory (default: PR4Code/dataset_pr_commits_py)"
    )

    parser.add_argument(
        "--size",
        type=int,
        default=100,
        help="Number of PRs to select (default: 100)"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )

    parser.add_argument(
        "--output",
        default="PR4Code/pr_subset_100.json",
        help="Output file path (default: PR4Code/pr_subset_100.json)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show subset without saving"
    )

    args = parser.parse_args()

    # Validate dataset path
    dataset_path = Path(args.dir)
    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path}")
        return

    print("=" * 70)
    print("  CREATE PR SUBSET")
    print("=" * 70)
    print(f"\n  Dataset:     {dataset_path}")
    print(f"  Size:        {args.size}")
    print(f"  Seed:        {args.seed}")
    print(f"  Output:      {args.output if not args.dry_run else '(dry-run)'}")
    print()

    # Create subset
    output_file = None if args.dry_run else args.output
    subset = create_pr_subset(
        dataset_path=str(dataset_path),
        size=args.size,
        seed=args.seed,
        output_file=output_file
    )

    # Print summary
    print("\n" + "=" * 70)
    print("  SELECTED PRs")
    print("=" * 70)

    for i, pr in enumerate(subset["prs"], 1):
        print(f"  {i:3}. {pr['repo']}/{pr['pr']}")

    print("\n" + "=" * 70)
    print(f"  Total: {len(subset['prs'])} PRs from {len(subset['prs'])} different repositories")
    print("=" * 70)

    if args.dry_run:
        print("\n  DRY-RUN: No file saved. Remove --dry-run to save.")


if __name__ == "__main__":
    main()
