"""
=============================================================================
BATCH_PREDICT.PY - Batch PR Step Plan Generation
=============================================================================

This script batch processes multiple Pull Requests to generate predicted
implementation plans that can be compared with ground_truth.json.

WORKFLOW:

    PR4Code/dataset/
    └── repo_name/
        └── pr_123/
            ├── data.json           # PR metadata
            ├── base_project/       # Source code snapshot
            └── predicted_plan.json # <-- GENERATED OUTPUT

FEATURES:

    - Batch processing with progress tracking
    - Parallel execution support (--parallel N)
    - Skip already-processed PRs (--skip-existing)
    - Configurable model selection
    - JSON report generation

=============================================================================
USAGE GUIDE
=============================================================================

BASIC COMMANDS:
---------------

    # Process 10 PRs from the dataset
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10

    # Process all PRs from a specific repository
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/3b1b_manim/ --all

    # Resume processing (skip existing)
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 50 --skip-existing


AVAILABLE OPTIONS:
------------------

    base_path           Directory containing the PRs (required)
    -n, --limit N       Maximum number of PRs to process
    --all               Process all found PRs
    -m, --model         OpenAI model to use (default: gpt-5.2-2025-12-11)
    --skip-existing     Skip PRs with existing predicted_plan.json
    -v, --verbose       Detailed output for each PR
    -p, --parallel N    Number of parallel workers (default: 1)
    --report PATH       Save batch report to JSON file


EXAMPLES:
---------

    # Process 10 PRs with verbose output
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ -n 10 -v

    # Parallel processing with 4 workers
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ -n 20 -p 4

    # Use gpt-5.2-2025-12-11 model
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ -n 5 -m gpt-5.2-2025-12-11

    # Save batch report
    python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ -n 10 --report batch_report.json

=============================================================================
"""

import os
import sys
import json
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from colorama import Fore, Style, init

# Initialize
init(autoreset=True)
load_dotenv()

# Local import after path setup
from GenAI.pr_step_planner import PRStepPlanner


def find_pr_directories(base_path: Path, limit: Optional[int] = None, skip_existing: bool = False) -> List[Path]:
    """
    Find all valid PR directories under the specified path.

    A valid PR directory contains:
    - data.json
    - base_project/

    Args:
        base_path: Base directory to explore
        limit: Maximum number of PRs to process (None = all)
        skip_existing: If True, skip PRs that already have predicted_plan.json

    Returns:
        List of Paths to PR directories, sorted alphabetically.
        With --limit 1 returns the first PR in alphabetical order.
    """
    pr_dirs = []

    # Search for pr_* pattern directories
    for item in base_path.rglob("pr_*"):
        if not item.is_dir():
            continue

        # Verify it's a valid PR
        data_json = item / "data.json"
        base_project = item / "base_project"

        if not data_json.exists() or not base_project.exists():
            continue

        # Skip if predicted_plan.json already exists
        if skip_existing and (item / "predicted_plan.json").exists():
            continue

        pr_dirs.append(item)

    # Sort BEFORE applying the limit (alphabetical order by repo/pr)
    pr_dirs = sorted(pr_dirs)

    # Apply limit AFTER sorting
    if limit:
        pr_dirs = pr_dirs[:limit]

    return pr_dirs

def process_single_pr(
    pr_dir: Path,
    model_name: str,
    verbose: bool = False
) -> Tuple[Path, bool, str]:
    """
    Process a single PR.

    Returns:
        Tuple (pr_dir, success, message)
    """
    try:
        planner = PRStepPlanner(
            pr_dir=str(pr_dir),
            model_name=model_name,
            verbose=verbose
        )

        output_path = planner.save_output()
        return (pr_dir, True, f"Saved: {output_path}")

    except FileNotFoundError as e:
        return (pr_dir, False, f"File not found: {e}")
    except ValueError as e:
        return (pr_dir, False, f"Value error: {e}")
    except Exception as e:
        return (pr_dir, False, f"Error: {type(e).__name__}: {e}")

def run_batch(
    base_path: str,
    limit: Optional[int] = None,
    model_name: str = "gpt-5.2-2025-12-11",
    skip_existing: bool = False,
    verbose: bool = False,
    parallel: int = 1,
    pr_dirs_override: Optional[List[Path]] = None
) -> dict:
    """
    Execute batch processing of PRs.

    Args:
        base_path: Base path containing the PRs (used for the report location)
        limit: Maximum number of PRs to process
        model_name: OpenAI model to use
        skip_existing: Skip PRs with existing predicted_plan.json
        verbose: Detailed output for each PR
        parallel: Number of PRs to process in parallel (1 = sequential)
        pr_dirs_override: When set, use these paths directly and skip discovery

    Returns:
        Dict with batch statistics
    """
    base = Path(base_path).resolve()

    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {base}")

    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}🚀 Batch Predict - PR Step Planner")
    print(f"{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}Base path: {base}")
    print(f"{Fore.CYAN}Model: {model_name}")
    print(f"{Fore.CYAN}Limit: {limit if limit else 'None'}")
    print(f"{Fore.CYAN}Skip existing: {skip_existing}")
    print(f"{Fore.CYAN}Parallel: {parallel}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    # Find PR directories (or use the provided override list)
    if pr_dirs_override is not None:
        pr_dirs = pr_dirs_override
        if skip_existing:
            pr_dirs = [d for d in pr_dirs if not (d / "predicted_plan.json").exists()]
        print(f"{Fore.YELLOW}Using {len(pr_dirs)} PRs from subset{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}Searching for PR directories...{Style.RESET_ALL}")
        pr_dirs = find_pr_directories(base, limit, skip_existing)

    if not pr_dirs:
        print(f"{Fore.RED}No PRs found to process{Style.RESET_ALL}")
        return {"total": 0, "success": 0, "failed": 0, "errors": []}

    print(f"{Fore.GREEN}Found {len(pr_dirs)} PRs to process{Style.RESET_ALL}\n")

    # Statistics
    results = {
        "total": len(pr_dirs),
        "success": 0,
        "failed": 0,
        "errors": [],
        "processed": []
    }

    start_time = datetime.now()

    # Process PRs
    if parallel > 1:
        # Parallel execution
        print(f"{Fore.YELLOW}⚡ Parallel execution with {parallel} workers...{Style.RESET_ALL}\n")

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(process_single_pr, pr_dir, model_name, verbose): pr_dir
                for pr_dir in pr_dirs
            }

            for i, future in enumerate(as_completed(futures), 1):
                pr_dir, success, message = future.result()
                pr_name = f"{pr_dir.parent.name}/{pr_dir.name}"

                if success:
                    results["success"] += 1
                    results["processed"].append(str(pr_dir))
                    print(f"{Fore.GREEN}[{i}/{len(pr_dirs)}] {pr_name}{Style.RESET_ALL}")
                else:
                    results["failed"] += 1
                    results["errors"].append({"pr": str(pr_dir), "error": message})
                    print(f"{Fore.RED}[{i}/{len(pr_dirs)}] {pr_name}: {message}{Style.RESET_ALL}")
    else:
        # Sequential execution
        for i, pr_dir in enumerate(pr_dirs, 1):
            pr_name = f"{pr_dir.parent.name}/{pr_dir.name}"

            print(f"\n{Fore.YELLOW}[{i}/{len(pr_dirs)}] Processing: {pr_name}{Style.RESET_ALL}")

            pr_dir, success, message = process_single_pr(pr_dir, model_name, verbose)

            if success:
                results["success"] += 1
                results["processed"].append(str(pr_dir))
                print(f"{Fore.GREEN}   {message}{Style.RESET_ALL}")
            else:
                results["failed"] += 1
                results["errors"].append({"pr": str(pr_dir), "error": message})
                print(f"{Fore.RED}   {message}{Style.RESET_ALL}")

    # Calculate total time
    elapsed = datetime.now() - start_time
    results["elapsed_seconds"] = elapsed.total_seconds()

    # Final report
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}FINAL REPORT")
    print(f"{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}   Total PRs: {results['total']}")
    print(f"{Fore.GREEN}   Success: {results['success']}")
    print(f"{Fore.RED}   Failed: {results['failed']}")
    print(f"{Fore.CYAN}   Time: {elapsed}")
    if results['total'] > 0:
        avg_time = elapsed.total_seconds() / results['total']
        print(f"{Fore.CYAN}   Average per PR: {avg_time:.1f}s")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    # Show errors if any
    if results["errors"]:
        print(f"{Fore.RED}Errors:{Style.RESET_ALL}")
        for err in results["errors"][:10]:  # Max 10 errors
            print(f"   - {Path(err['pr']).name}: {err['error']}")
        if len(results["errors"]) > 10:
            print(f"   ... and {len(results['errors']) - 10} more errors")

    return results

def save_batch_report(results: dict, output_path: str):
    """Save the batch report to a JSON file."""
    report = {
        "timestamp": datetime.now().isoformat(),
        **results
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"{Fore.GREEN}💾 Report saved: {output_path}{Style.RESET_ALL}")

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate predicted_plan.json for multiple PRs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process 10 PRs from any repository
  python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10

  # Process all PRs from a specific repository
  python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/3b1b_manim/ --all

  # Process only PRs without existing predicted_plan.json
  python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 20 --skip-existing

  # Process in parallel with 3 workers
  python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 10 --parallel 3

  # Use a different model
  python -m GenAI.batch_predict PR4Code/dataset_pr_commits_py/ --limit 5 -m gpt-5.2-2025-12-11
        """
    )

    parser.add_argument(
        "base_path",
        help="Base directory containing the PRs (e.g., PR4Code/dataset_pr_commits_py/)"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-n", "--limit",
        type=int,
        help="Maximum number of PRs to process"
    )

    group.add_argument(
        "--all",
        action="store_true",
        help="Process all found PRs"
    )

    group.add_argument(
        "--subset",
        metavar='FILE',
        help='Subset JSON file (from create_pr_subset.py); bypasses base_path discovery'
    )

    parser.add_argument(
        "-m", "--model",
        default="gpt-5.2-2025-12-11",
        help="OpenAI model to use (default: gpt-5.2-2025-12-11)"
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PRs that already have predicted_plan.json"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Detailed output for each PR"
    )

    parser.add_argument(
        "-p", "--parallel",
        type=int,
        default=1,
        choices=range(1, 17),
        metavar="N",
        help="Number of PRs to process in parallel (1-16, default: 1)"
    )

    parser.add_argument(
        "--report",
        help="Path to save the batch JSON report"
    )

    args = parser.parse_args()

    # Verify API key
    if not os.getenv('OPENAI_API_KEY'):
        print(f"{Fore.RED}OPENAI_API_KEY not found in .env file{Style.RESET_ALL}")
        sys.exit(1)

    try:
        limit = None if (args.all or args.subset) else args.limit

        pr_dirs_override = None
        if args.subset:
            from scripts.create_pr_subset import load_pr_subset
            pr_dirs_override = [Path(p) for p in load_pr_subset(args.subset)]

        results = run_batch(
            base_path=args.base_path,
            limit=limit,
            model_name=args.model,
            skip_existing=args.skip_existing,
            verbose=args.verbose,
            parallel=args.parallel,
            pr_dirs_override=pr_dirs_override
        )

        # Save report if requested
        if args.report:
            save_batch_report(results, args.report)

        # Exit code based on success
        if results["failed"] > 0 and results["success"] == 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
