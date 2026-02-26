"""
=============================================================================
VERIFY_PR_COMPLETENESS.PY - Verify PR directory completeness
=============================================================================

This script verifies that PR directories containing ground_truth.json also
include the other files/directories required for complete analysis:
- base_project/    (base project source code)
- context_output/  (generated context files)

It identifies and categorizes separately:
- Complete PRs (all files present)
- PRs missing only base_project/
- PRs missing only context_output/
- PRs missing both

=============================================================================
USAGE GUIDE
=============================================================================

BASIC COMMANDS:
---------------

    # Verify all PRs and show complete summary
    python verify_pr_completeness.py

    # Show only incomplete PRs (hide complete ones)
    python verify_pr_completeness.py --only-incomplete

    # Output in JSON format (for automated processing)
    python verify_pr_completeness.py --json


AVAILABLE OPTIONS:
------------------

    --dir DIR           Base directory to search from (default: PR4Code)
    --only-incomplete   Show only PRs with missing files
    --json              Output in JSON format instead of table


EXAMPLES:
---------

    # 1. Complete dataset verification
    python verify_pr_completeness.py

    # 2. Show only incomplete PRs
    python verify_pr_completeness.py --only-incomplete

    # 3. Verify a specific subdirectory
    python verify_pr_completeness.py --dir PR4Code/dataset_pr_commits_py/1Panel-dev_MaxKB

    # 4. Export results to JSON for external scripts
    python verify_pr_completeness.py --json > pr_status.json

    # 5. Count incomplete PRs with jq
    python verify_pr_completeness.py --json | jq '.summary.missing_context_output_only'


OUTPUT:
-------
    The script produces a table with:
    - Count of complete PRs
    - Count of PRs with missing base_project/
    - Count of PRs with missing context_output/
    - Count of PRs with both missing
    - Detailed list of PRs by category

=============================================================================
"""
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass
class PRStatus:
    """Completeness status of a PR."""
    pr_path: str
    has_ground_truth: bool = False
    has_base_project: bool = False
    has_context_output: bool = False

    @property
    def is_complete(self) -> bool:
        """Returns True if the PR has all required files."""
        return (
            self.has_ground_truth and
            self.has_base_project and
            self.has_context_output
        )

    @property
    def missing(self) -> list[str]:
        """Returns list of missing files/directories."""
        missing = []
        if not self.has_ground_truth:
            missing.append("ground_truth.json")
        if not self.has_base_project:
            missing.append("base_project/")
        if not self.has_context_output:
            missing.append("context_output/")
        return missing

    def get_short_path(self) -> str:
        """Returns abbreviated path (repo/pr_xxx)."""
        path = Path(self.pr_path)
        # Take the last 2 components: repo/pr_xxx
        return str(Path(path.parent.name) / path.name)

def check_pr_directory(pr_dir: Path) -> PRStatus:
    """
    Verify the completeness of a PR directory.

    Args:
        pr_dir: Path to the PR directory

    Returns:
        PRStatus with the status of each component
    """
    return PRStatus(
        pr_path=str(pr_dir),
        has_ground_truth=(pr_dir / "ground_truth.json").exists(),
        has_base_project=(pr_dir / "base_project").is_dir(),
        has_context_output=(pr_dir / "context_output").is_dir()
    )


def find_prs_with_ground_truth(base_dir: str = "PR4Code") -> list[Path]:
    """
    Find all PR directories that have ground_truth.json.

    Args:
        base_dir: Base directory to search from

    Returns:
        List of Paths to PR directories with ground_truth.json
    """
    base_path = Path(base_dir)

    if not base_path.exists():
        print(f"❌ Directory not found: {base_dir}")
        return []

    # Find all ground_truth.json files and return their parent directories
    gt_files = base_path.rglob("ground_truth.json")
    pr_dirs = [f.parent for f in gt_files]

    return sorted(pr_dirs)


def categorize_statuses(statuses: list[PRStatus]) -> dict:
    """
    Categorize PRs by type of missing files.

    Returns:
        Dict with categorized lists
    """
    return {
        "complete": [s for s in statuses if s.is_complete],
        "missing_both": [s for s in statuses
                        if not s.has_base_project and not s.has_context_output],
        "missing_base_project_only": [s for s in statuses
                                      if not s.has_base_project and s.has_context_output],
        "missing_context_output_only": [s for s in statuses
                                        if s.has_base_project and not s.has_context_output],
    }


def print_pr_list(prs: list[PRStatus], max_show: int = 20):
    """Print list of PRs (with limit)."""
    for status in prs[:max_show]:
        print(f"     • {status.get_short_path()}")

    if len(prs) > max_show:
        print(f"     ... and {len(prs) - max_show} more")


def print_summary(categories: dict, total: int, only_incomplete: bool = False):
    """Print a summary of PR status."""

    print(f"\n{'='*70}")
    print(f"📊 PR VERIFICATION SUMMARY")
    print(f"{'='*70}\n")

    # General statistics
    print(f"  📁 PRs with ground_truth.json: {total}")
    print()

    # Summary table
    print(f"  {'─'*50}")
    print(f"  {'Status':<35} {'Count':>10}")
    print(f"  {'─'*50}")
    print(f"  ✅ Complete (all files)             {len(categories['complete']):>10}")
    print(f"  ❌ Missing only base_project/       {len(categories['missing_base_project_only']):>10}")
    print(f"  ❌ Missing only context_output/     {len(categories['missing_context_output_only']):>10}")
    print(f"  ❌ Missing both                     {len(categories['missing_both']):>10}")
    print(f"  {'─'*50}")
    print()

    # Incomplete PR details
    if categories['missing_base_project_only']:
        print(f"{'─'*70}")
        print(f"❌ MISSING ONLY base_project/ ({len(categories['missing_base_project_only'])} PRs):\n")
        print_pr_list(categories['missing_base_project_only'])
        print()

    if categories['missing_context_output_only']:
        print(f"{'─'*70}")
        print(f"❌ MISSING ONLY context_output/ ({len(categories['missing_context_output_only'])} PRs):\n")
        print_pr_list(categories['missing_context_output_only'])
        print()

    if categories['missing_both']:
        print(f"{'─'*70}")
        print(f"❌ MISSING BOTH (base_project/ and context_output/) ({len(categories['missing_both'])} PRs):\n")
        print_pr_list(categories['missing_both'])
        print()

    # Complete PRs (optional)
    if not only_incomplete and categories['complete']:
        print(f"{'─'*70}")
        print(f"✅ COMPLETE ({len(categories['complete'])} PRs):\n")
        print_pr_list(categories['complete'], max_show=10)
        print()

    print(f"{'='*70}\n")


def print_json(categories: dict, statuses: list[PRStatus]):
    """Print status in JSON format."""
    output = {
        "total": len(statuses),
        "summary": {
            "complete": len(categories['complete']),
            "missing_base_project_only": len(categories['missing_base_project_only']),
            "missing_context_output_only": len(categories['missing_context_output_only']),
            "missing_both": len(categories['missing_both']),
        },
        "details": {
            "complete": [s.get_short_path() for s in categories['complete']],
            "missing_base_project_only": [s.get_short_path() for s in categories['missing_base_project_only']],
            "missing_context_output_only": [s.get_short_path() for s in categories['missing_context_output_only']],
            "missing_both": [s.get_short_path() for s in categories['missing_both']],
        },
        "all_statuses": [asdict(s) for s in statuses]
    }
    print(json.dumps(output, indent=2))

def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(
        description="Verify PR directory completeness"
    )
    parser.add_argument(
        "--dir",
        default="PR4Code",
        help="Base directory to search from (default: PR4Code)"
    )
    parser.add_argument(
        "--only-incomplete",
        action="store_true",
        help="Show only incomplete PRs"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    args = parser.parse_args()

    # Find PRs with ground_truth.json
    if not args.json:
        print(f"\n🔍 Searching for PRs with ground_truth.json in: {args.dir}/")

    pr_dirs = find_prs_with_ground_truth(args.dir)

    if not pr_dirs:
        if not args.json:
            print("❌ No PRs with ground_truth.json found.\n")
        else:
            print('{"total": 0, "summary": {}, "details": {}, "all_statuses": []}')
        return

    # Verify each PR
    if not args.json:
        print(f"📋 Verifying {len(pr_dirs)} PRs...")

    statuses = [check_pr_directory(pr_dir) for pr_dir in pr_dirs]

    # Categorise once; pass the result to whichever formatter is active
    categories = categorize_statuses(statuses)

    if args.json:
        print_json(categories, statuses)
    else:
        print_summary(categories, len(statuses), only_incomplete=args.only_incomplete)

if __name__ == "__main__":
    main()
