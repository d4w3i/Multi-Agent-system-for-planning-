#!/usr/bin/env python3
"""
=============================================================================
GENERATE_CONTEXT_OUTPUTS.PY - Generate context_output for dataset PRs
=============================================================================

This script generates context files (call graph, context files, project_info)
for Pull Requests in the PR4Code dataset that have a base_project/ folder.

GENERATED OUTPUT:

    pr_123/
    └── context_output/
        ├── call_graph.json         # Complete call graph
        ├── project_tree.txt        # ASCII directory tree
        ├── project_info.py         # DIRECTORY_TREE + README + MASCA
        ├── masca_analysis.md       # Only if --with-masca
        └── context_files/          # Context files for each function
            └── [hierarchical structure]

=============================================================================
USAGE GUIDE
=============================================================================

BASIC COMMANDS:
---------------

    # Generate context_output for all PRs (MASCA enabled by default)
    python generate_context_outputs.py

    # Generate without MASCA analysis
    python generate_context_outputs.py --no-masca


AVAILABLE OPTIONS:
------------------

    --dir DIR         Dataset directory (default: PR4Code/dataset_pr_commits_py)
    --limit N         Process only the first N PRs (for testing)
    --skip-existing   Skip PRs that already have context_output/
    --no-masca        Disable AI analysis with Masca (enabled by default;
                      requires OPENAI_API_KEY in .env file)


EXAMPLES:
---------

    # 1. Preview: show how many PRs would be processed (dry-run)
    python generate_context_outputs.py --dry-run

    # 2. Quick test on 5 PRs (MASCA enabled by default)
    python generate_context_outputs.py --limit 5

    # 3. Quick test on 10 PRs without MASCA
    python generate_context_outputs.py --no-masca --limit 10

    # 4. Resume interrupted processing (skip existing)
    python generate_context_outputs.py --skip-existing

    # 5. Process all without MASCA, skipping existing
    python generate_context_outputs.py --no-masca --skip-existing

    # 6. Process a specific repository
    python generate_context_outputs.py --dir PR4Code/dataset_pr_commits_py/1Panel-dev_MaxKB

    # 7. Process PRs from a subset file (created by create_pr_subset.py)
    python generate_context_outputs.py --subset PR4Code/pr_subset_100.json


NOTES:
------
    - Requires PRs to have the base_project/ folder
    - MASCA is enabled by default; use --no-masca to skip it
    - MASCA requires OPENAI_API_KEY and makes one API call per PR (~$0.001/PR)
    - Use --dry-run to see what would be processed without doing it
    - Use --subset to process only PRs from a subset file (created by create_pr_subset.py)

=============================================================================
"""

import argparse
import sys
from pathlib import Path

from scripts.create_pr_subset import load_pr_subset_data

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    from context_retrieving.batch_context_retriever import (
        BatchContextRetriever,
        find_prs_with_base_project
    )
    HAS_RETRIEVER = True
except ImportError as e:
    HAS_RETRIEVER = False
    IMPORT_ERROR = str(e)


def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def print_stats(with_base: int, to_process: int, skipped: int = 0):
    """Print PR statistics."""
    print(f"  📦 PRs with base_project/:       {with_base}")
    if skipped > 0:
        print(f"  ⏭️  PRs skipped (already exist):  {skipped}")
    print(f"  🎯 PRs to process:               {to_process}")
    print()

def main():
    """Main entry point."""

    # -------------------------------------------------------------------------
    # Check dependencies
    if not HAS_RETRIEVER:
        print(f"❌ Error: unable to import context_retrieving module")
        print(f"   Details: {IMPORT_ERROR}")
        print(f"\n   Make sure you are in the correct project directory.")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # CLI argument parser
    parser = argparse.ArgumentParser(
        description="Generate context_output for PRs in the PR4Code dataset"
    )

    parser.add_argument(
        "--dir",
        default="PR4Code/dataset_pr_commits_py",
        help="Dataset directory (default: PR4Code/dataset_pr_commits_py)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N PRs (for testing)"
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PRs that already have context_output/"
    )

    parser.add_argument(
        "--no-masca",
        action="store_true",
        help="Disable MASCA AI analysis (enabled by default; requires OPENAI_API_KEY)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without doing it"
    )

    parser.add_argument(
        "--subset",
        type=str,
        default=None,
        help="Path to subset JSON file (created by create_pr_subset.py)"
    )

    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Input validation
    dataset_dir = Path(args.dir)

    # -------------------------------------------------------------------------
    # Find PRs - either from subset file or by scanning for base_project/
    if args.subset:
        # Load PRs from subset file
        print_header("📋 LOADING SUBSET")

        subset_path = Path(args.subset)
        if not subset_path.exists():
            print(f"❌ Subset file not found: {subset_path}")
            sys.exit(1)

        subset_data = load_pr_subset_data(str(subset_path))

        print(f"  Subset file: {subset_path}")
        print(f"  Created:     {subset_data['metadata']['created_at']}")
        print(f"  Seed:        {subset_data['metadata']['random_seed']}")
        print(f"  PRs:         {len(subset_data['prs'])}")
        print()

        # Convert to Path objects
        pr_dirs = [Path(pr['path']) for pr in subset_data['prs']]

        # Verify PRs exist
        missing = [d for d in pr_dirs if not d.exists()]
        if missing:
            print(f"⚠️  {len(missing)} PRs in subset do not exist:")
            for m in missing[:5]:
                print(f"     - {m}")
            if len(missing) > 5:
                print(f"     ... and {len(missing) - 5} more")
            pr_dirs = [d for d in pr_dirs if d.exists()]

    else:
        # Find PRs with base_project/
        if not dataset_dir.exists():
            print(f"❌ Directory not found: {dataset_dir}")
            sys.exit(1)

        print_header("🔍 SEARCHING FOR PRs WITH BASE_PROJECT")

        print(f"  Searching in: {dataset_dir}/")
        pr_dirs = find_prs_with_base_project(dataset_dir)

    if not pr_dirs:
        print(f"\n❌ No PRs found")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Apply filters
    original_count = len(pr_dirs)
    skipped_count = 0

    # Filter already processed PRs
    if args.skip_existing:
        pr_dirs_filtered = [
            d for d in pr_dirs
            if not (d / 'context_output' / 'call_graph.json').exists()
        ]
        skipped_count = original_count - len(pr_dirs_filtered)
        pr_dirs = pr_dirs_filtered

    # Apply limit
    if args.limit:
        pr_dirs = pr_dirs[:args.limit]

    # -------------------------------------------------------------------------
    # Print statistics
    print_stats(
        with_base=original_count,
        to_process=len(pr_dirs),
        skipped=skipped_count
    )

    if not pr_dirs:
        print("✅ No PRs to process.")
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Dry-run: only show what would be done
    if args.dry_run:
        print_header("📋 DRY-RUN: PRs THAT WOULD BE PROCESSED")

        for i, pr_dir in enumerate(pr_dirs[:20], 1):
            repo_name = pr_dir.parent.name
            pr_name = pr_dir.name
            print(f"  {i:3}. {repo_name}/{pr_name}")

        if len(pr_dirs) > 20:
            print(f"  ... and {len(pr_dirs) - 20} more PRs")

        print(f"\n{'='*70}")
        print(f"⚠️  DRY-RUN mode: no operations performed.")
        print(f"   Remove --dry-run to actually process the PRs.")
        if not args.no_masca:
            print(f"   NOTE: MASCA is active by default (requires OPENAI_API_KEY)")
        print(f"{'='*70}\n")
        sys.exit(0)

    # -------------------------------------------------------------------------
    # Execution
    print_header("🚀 GENERATING CONTEXT_OUTPUT")

    if args.no_masca:
        print("  📊 MASCA analysis: DISABLED (--no-masca)")
    else:
        print("  📊 MASCA analysis: ENABLED (requires OpenAI API)")
    print()

    # Create the retriever
    retriever = BatchContextRetriever(with_masca=not args.no_masca)

    # Counters
    success_count = 0
    failed_count = 0

    # Progress bar
    iterator = tqdm(pr_dirs, desc="Generating context") if HAS_TQDM else pr_dirs

    for pr_dir in iterator:
        result = retriever.process_pr(pr_dir)

        if result:
            success_count += 1
        else:
            failed_count += 1

    # -------------------------------------------------------------------------
    # Final summary
    # -------------------------------------------------------------------------
    print_header("📊 SUMMARY")

    print(f"  ✅ Success:   {success_count}")
    print(f"  ❌ Failed:    {failed_count}")
    print(f"  📁 Total:     {success_count + failed_count}")
    print()

    if failed_count > 0:
        print(f"  ⚠️  Some PRs failed. Check logs for details.")
    else:
        print(f"  🎉 All PRs processed successfully!")

    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    main()
