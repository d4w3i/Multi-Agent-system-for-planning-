"""
=============================================================================
VERIFICATION.PY - Dataset Verification Handler
=============================================================================

Handler for verifying PR directory completeness.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional
import json

from cli.components.prompts import (
    prompt_directory, prompt_confirm, prompt_text, prompt_express_or_configure,
    validate_express_directory,
)
from cli.components.displays import display_verification_table, display_error
from cli.components.progress import spinner
from cli.config import config


def handle_dataset_verification(console: Console) -> Optional[dict]:
    """
    Handle dataset verification.

    Options:
    - Directory path
    - Show only incomplete
    - Export to JSON
    """
    console.print(Panel(
        "[bold]Dataset Verification[/bold]\n\n"
        "Check PR directories for required files:\n"
        "- ground_truth.json\n"
        "- base_project/\n"
        "- context_output/",
        border_style="blue"
    ))

    defaults = config.express_defaults["verification"]

    express = prompt_express_or_configure(console, "Dataset Verification", {
        "Directory": defaults["directory"],
        "Show only incomplete": "No",
        "Export to JSON": "No",
    })

    if express:
        base_dir = validate_express_directory(console, defaults["directory"])
        if base_dir is None:
            return None
        only_incomplete = defaults["only_incomplete"]
        export_json = defaults["export_json"]
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
        only_incomplete = prompt_confirm(console, "Show only incomplete PRs?", default=False)
        export_json = prompt_confirm(console, "Export results to JSON?", default=False)

    # Run verification
    console.print("\n[cyan]Verifying PR directories...[/cyan]")

    try:
        from scripts.verify_pr_completeness import (
            find_prs_with_ground_truth,
            check_pr_directory,
            categorize_statuses
        )

        with spinner(console, "Scanning PRs"):
            pr_dirs = find_prs_with_ground_truth(str(base_dir))
            statuses = [check_pr_directory(d) for d in pr_dirs]
            categories = categorize_statuses(statuses)

        # Display results
        display_verification_table(console, categories)

        # Show details if requested
        if only_incomplete:
            incomplete_categories = [
                ("missing_base_project_only", "Missing base_project/"),
                ("missing_context_output_only", "Missing context_output/"),
                ("missing_both", "Missing both"),
            ]

            for cat_key, cat_name in incomplete_categories:
                items = categories.get(cat_key, [])
                if items:
                    console.print(f"\n[bold yellow]{cat_name}:[/bold yellow]")
                    for status in items[:10]:
                        console.print(f"  - {status.get_short_path()}")
                    if len(items) > 10:
                        console.print(f"  ... and {len(items) - 10} more")

        # Export to JSON
        if export_json:
            output_file = prompt_text(
                console,
                "Output filename:",
                default="verification_results.json",
            )
            if output_file is None:
                output_file = "verification_results.json"

            results_dict = {
                "summary": {
                    "complete": len(categories.get("complete", [])),
                    "missing_base_project_only": len(categories.get("missing_base_project_only", [])),
                    "missing_context_output_only": len(categories.get("missing_context_output_only", [])),
                    "missing_both": len(categories.get("missing_both", [])),
                    "total": len(statuses)
                },
                "incomplete_prs": [
                    {
                        "path": s.pr_path,
                        "missing": s.missing
                    }
                    for s in statuses if not s.is_complete
                ]
            }

            with open(output_file, "w") as f:
                json.dump(results_dict, f, indent=2)

            console.print(f"[green]OK[/green] Results saved to {output_file}")

        return {
            "total": len(statuses),
            "complete": len(categories.get("complete", [])),
            "incomplete": len(statuses) - len(categories.get("complete", []))
        }

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"verify_pr_completeness module not available: {e}"
        )
        return None
