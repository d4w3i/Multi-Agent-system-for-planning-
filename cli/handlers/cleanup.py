"""
=============================================================================
CLEANUP.PY - Dataset Cleanup Handler
=============================================================================

Handler for removing generated files from the dataset.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Optional

from cli.components.prompts import (
    prompt_directory,
    prompt_multi_choice,
    prompt_confirm,
    prompt_confirm_destructive
)
from cli.components.displays import display_results, display_error
from cli.components.progress import ProgressContext


def handle_dataset_cleanup(console: Console) -> Optional[dict]:
    """
    Handle dataset cleanup operations.

    Options:
    - Target selection (ground_truth, predicted_plan, context_output, all)
    - Directory path
    - Preview mode (dry-run)
    - Confirmation for destructive action
    """
    console.print(Panel(
        "[bold red]Dataset Cleanup[/bold red]\n\n"
        "[yellow]Warning:[/yellow] This operation will permanently delete files.\n"
        "Use preview mode first to see what will be deleted.",
        border_style="red"
    ))

    # Get directory
    base_dir = prompt_directory(
        console,
        "Dataset directory",
        default="PR4Code",
        must_exist=True
    )

    if base_dir is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return None

    # Target selection
    targets = prompt_multi_choice(
        console,
        "Select targets to delete",
        options=[
            ("ground_truth", "ground_truth.json files"),
            ("predicted_plan", "predicted_plan.json files"),
            ("context_output", "context_output/ directories"),
        ],
        defaults=[]
    )

    if not targets:
        console.print("[yellow]No targets selected. Cancelled.[/yellow]")
        return None

    # Preview first
    console.print("\n[cyan]Scanning for files to delete...[/cyan]")

    try:
        from scripts.dataset_cleanup import find_targets, TARGETS, get_size_human

        all_targets = []
        target_counts = {}

        for target_name in targets:
            found = find_targets(str(base_dir), target_name)
            target_counts[target_name] = len(found)
            all_targets.extend([(t, target_name) for t in found])

        if not all_targets:
            console.print("[yellow]No files found to delete.[/yellow]")
            return {"total": 0, "success": 0, "failed": 0}

        # Show preview
        table = Table(title="Files to Delete", show_header=True)
        table.add_column("Target Type", style="cyan")
        table.add_column("Count", justify="right")

        total_count = 0
        for target_name, count in target_counts.items():
            if count > 0:
                table.add_row(
                    TARGETS[target_name].description,
                    str(count)
                )
                total_count += count

        table.add_row("[bold]Total[/bold]", f"[bold]{total_count}[/bold]")
        console.print(table)

        # Show sample files
        console.print("\n[bold]Sample files:[/bold]")
        for path, target_name in all_targets[:5]:
            config = TARGETS[target_name]
            size = get_size_human(path)
            console.print(f"  - {path.name} ({size})")
        if len(all_targets) > 5:
            console.print(f"  ... and {len(all_targets) - 5} more")

        # Ask if just preview
        if prompt_confirm(console, "Preview only? (don't delete)", default=True):
            return {
                "total": total_count,
                "success": 0,
                "failed": 0,
                "preview": True
            }

        # Destructive confirmation
        if not prompt_confirm_destructive(
            console,
            action="Delete files",
            target=", ".join([TARGETS[t].description for t in targets]),
            count=total_count
        ):
            console.print("[yellow]Cancelled.[/yellow]")
            return None

        # Perform deletion
        from scripts.dataset_cleanup import delete_targets as do_delete

        results = {"total": total_count, "success": 0, "failed": 0, "errors": []}

        with ProgressContext(console, "Deleting files", total=total_count) as progress:
            for path, target_name in all_targets:
                try:
                    config = TARGETS[target_name]
                    if config.is_directory:
                        import shutil
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    results["success"] += 1
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "item": str(path),
                        "error": str(e)
                    })
                progress.advance()

        display_results(console, results, "Cleanup Complete")
        return results

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"dataset_cleanup module not available: {e}"
        )
        return None
