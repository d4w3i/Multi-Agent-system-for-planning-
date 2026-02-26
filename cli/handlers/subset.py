"""
=============================================================================
SUBSET.PY - Subset Creation and Python Filter Handlers
=============================================================================

Handlers for creating PR subsets and filtering Python-only PRs.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional

from cli.components.prompts import (
    prompt_directory, prompt_confirm, prompt_text, prompt_express_or_configure,
    validate_express_directory,
)
from cli.components.displays import display_success, display_error
from cli.components.progress import spinner
from cli.config import config


def handle_subset_creation(console: Console) -> Optional[dict]:
    """
    Handle subset creation.

    Options:
    - Dataset path
    - Subset size
    - Random seed
    - Output filename
    - Dry-run preview
    """
    console.print(Panel(
        "[bold]Subset Creation[/bold]\n\n"
        "Create a fixed subset of PRs for evaluation.\n"
        "Selects one PR per repository from Python-only PRs.",
        border_style="blue"
    ))

    defaults = config.express_defaults["subset"]

    express = prompt_express_or_configure(console, "Subset Creation", {
        "Directory": defaults["directory"],
        "Size": defaults["size"],
        "Seed": defaults["seed"],
        "Output file": defaults["output_file"],
        "Dry-run": "No",
    })

    if express:
        base_dir = validate_express_directory(console, defaults["directory"])
        if base_dir is None:
            return None
        size = defaults["size"]
        seed = defaults["seed"]
        output_file = defaults["output_file"]
        dry_run = defaults["dry_run"]
    else:
        # Get directory
        base_dir = prompt_directory(
            console,
            "Dataset directory",
            default=defaults["directory"],
            must_exist=True
        )

        if base_dir is None:
            console.print("[yellow]Cancelled.[/yellow]")
            return None

        # Options
        size_str = prompt_text(
            console,
            "Subset size:",
            default=str(defaults["size"]),
            validate=lambda v: v.isdigit() and int(v) > 0,
        )
        size = int(size_str) if size_str else defaults["size"]

        seed_str = prompt_text(
            console,
            "Random seed (for reproducibility):",
            default=str(defaults["seed"]),
            validate=lambda v: v.isdigit(),
        )
        seed = int(seed_str) if seed_str else defaults["seed"]

        output_file = prompt_text(
            console,
            "Output filename:",
            default=defaults["output_file"],
        )
        if output_file is None:
            output_file = defaults["output_file"]

        dry_run = prompt_confirm(console, "Preview only (dry-run)?", default=False)

    # Create subset
    console.print("\n[cyan]Creating subset...[/cyan]")

    try:
        from scripts.create_pr_subset import create_pr_subset

        with spinner(console, "Scanning Python-only PRs"):
            result = create_pr_subset(
                dataset_path=str(base_dir),
                size=size,
                seed=seed,
                output_file=None if dry_run else output_file
            )

        if not result:
            display_error(console, "Subset Creation Failed", "No PRs found matching criteria.")
            return None

        # Display results
        metadata = result.get("metadata", {})
        prs = result.get("prs", [])

        table = Table(title="Subset Statistics", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold")

        table.add_row("Total Python-only PRs", str(metadata.get("total_python_only_prs", 0)))
        table.add_row("Total repositories", str(metadata.get("total_repos", 0)))
        table.add_row("Subset size", str(len(prs)))
        table.add_row("Random seed", str(metadata.get("random_seed", seed)))

        console.print(table)

        # Show sample PRs
        console.print("\n[bold]Sample PRs in subset:[/bold]")
        for pr in prs[:5]:
            console.print(f"  - {pr['repo']}/{pr['pr']}")
        if len(prs) > 5:
            console.print(f"  ... and {len(prs) - 5} more")

        if dry_run:
            console.print("\n[yellow]Dry-run mode: no file saved.[/yellow]")
        else:
            console.print(f"\n[green]OK[/green] Subset saved to: {output_file}")

        return {
            "total_prs": metadata.get("total_python_only_prs", 0),
            "subset_size": len(prs),
            "output_file": output_file if not dry_run else None
        }

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"create_pr_subset module not available: {e}"
        )
        return None


def handle_python_filter(console: Console) -> Optional[dict]:
    """
    Handle Python PR path extraction.

    Lists all PRs that contain only Python files.
    """
    console.print(Panel(
        "[bold]Python PR Filter[/bold]\n\n"
        "Find all PRs that contain only Python files\n"
        "in their modified_files/ and original_files/.",
        border_style="blue"
    ))

    # Get directory
    base_dir = prompt_directory(
        console,
        "Dataset directory",
        default="PR4Code/dataset_pr_commits_py",
        must_exist=True
    )

    if base_dir is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return None

    # Find Python-only PRs
    console.print("\n[cyan]Scanning for Python-only PRs...[/cyan]")

    try:
        from scripts.extract_python_pr_paths import get_python_only_pr_paths, get_unique_repos

        with spinner(console, "Scanning PRs"):
            pr_paths = get_python_only_pr_paths(str(base_dir))
            repos = get_unique_repos(pr_paths)

        # Display results
        table = Table(title="Python-Only PRs", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold")

        table.add_row("Python-only PRs", str(len(pr_paths)))
        table.add_row("Unique repositories", str(len(repos)))

        console.print(table)

        # Show repositories
        console.print("\n[bold]Repositories:[/bold]")
        for repo in repos[:10]:
            console.print(f"  - {repo}")
        if len(repos) > 10:
            console.print(f"  ... and {len(repos) - 10} more")

        # Option to export
        if prompt_confirm(console, "Export PR paths to file?", default=False):
            output_file = prompt_text(
                console,
                "Output filename:",
                default="python_pr_paths.txt",
            )
            if output_file is None:
                output_file = "python_pr_paths.txt"

            with open(output_file, "w") as f:
                for path in pr_paths:
                    f.write(f"{path}\n")

            console.print(f"[green]OK[/green] Paths saved to: {output_file}")

        return {
            "total_prs": len(pr_paths),
            "total_repos": len(repos)
        }

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"extract_python_pr_paths module not available: {e}"
        )
        return None
