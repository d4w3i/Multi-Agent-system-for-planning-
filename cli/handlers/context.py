"""
=============================================================================
CONTEXT.PY - Context Generation Handler
=============================================================================

Handler for generating context files for PRs in the dataset.
"""

from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from typing import Optional
import json
import os

from cli.components.prompts import (
    prompt_directory, prompt_limit, prompt_confirm, prompt_express_or_configure,
    validate_express_directory,
)
from cli.components.displays import display_results, display_error
from cli.components.progress import ProgressContext, spinner
from cli.config import config


def handle_context_generation(console: Console) -> Optional[dict]:
    """
    Handle context file generation for PRs.

    Options:
    - Directory path
    - Limit (number of PRs)
    - Enable MASCA analysis
    - Skip existing
    - Dry-run preview
    """
    console.print(Panel(
        "[bold]Context Generation[/bold]\n\n"
        "Generate call graphs and context files for PRs\n"
        "that have a base_project/ directory.",
        border_style="blue"
    ))

    defaults = config.express_defaults["context"]

    express = prompt_express_or_configure(console, "Context Generation", {
        "Directory": defaults["directory"],
        "Limit": defaults["limit"],
        "MASCA analysis": "No",
        "Skip existing": "Yes",
        "Dry-run": "No",
    })

    if express:
        base_dir = validate_express_directory(console, defaults["directory"])
        if base_dir is None:
            return None
        limit = defaults["limit"]
        with_masca = defaults["masca"]
        skip_existing = defaults["skip_existing"]
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

        # Get limit
        limit = prompt_limit(console, default=defaults["limit"], allow_all=True)

        # Options
        with_masca = False
        if os.getenv("OPENAI_API_KEY"):
            with_masca = prompt_confirm(console, "Enable MASCA AI analysis?", default=True)
        else:
            console.print("[dim]MASCA disabled (no API key)[/dim]")

        skip_existing = prompt_confirm(console, "Skip PRs with existing context_output?", default=True)
        dry_run = prompt_confirm(console, "Preview only (dry-run)?", default=False)

    # Find PRs with base_project
    console.print("\n[cyan]Scanning for PRs with base_project/...[/cyan]")

    pr_dirs = []
    for repo_dir in base_dir.iterdir():
        if not repo_dir.is_dir():
            continue
        for pr_dir in repo_dir.iterdir():
            if not pr_dir.is_dir() or not pr_dir.name.startswith("pr_"):
                continue
            if (pr_dir / "base_project").exists():
                if skip_existing and (pr_dir / "context_output").exists():
                    continue
                pr_dirs.append(pr_dir)

    pr_dirs = sorted(pr_dirs)

    if limit:
        pr_dirs = pr_dirs[:limit]

    if not pr_dirs:
        console.print("[yellow]No PRs found to process.[/yellow]")
        return {"total": 0, "success": 0, "failed": 0}

    console.print(f"Found [bold]{len(pr_dirs)}[/bold] PRs to process")

    if dry_run:
        console.print("\n[bold]Dry-run preview:[/bold]")
        for pr_dir in pr_dirs[:10]:
            console.print(f"  - {pr_dir.parent.name}/{pr_dir.name}")
        if len(pr_dirs) > 10:
            console.print(f"  ... and {len(pr_dirs) - 10} more")
        return {"total": len(pr_dirs), "success": 0, "failed": 0, "dry_run": True}

    # Process PRs
    try:
        from context_retrieving.batch_context_retriever import BatchContextRetriever

        retriever = BatchContextRetriever(with_masca=with_masca)
        results = {"total": len(pr_dirs), "success": 0, "failed": 0, "errors": []}
        masca_results = []

        with ProgressContext(console, "Generating context files", total=len(pr_dirs)) as progress:
            for pr_dir in pr_dirs:
                try:
                    success, masca_data = retriever.process_pr(pr_dir)

                    if success:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

                    if masca_data is not None:
                        pr_id = f"{pr_dir.parent.name}/{pr_dir.name}"
                        masca_results.append({
                            "pr_id": pr_id,
                            "system_prompt": masca_data["system_prompt"],
                            "prompt": masca_data["prompt"],
                            "output": masca_data["output"],
                            "input_tokens": masca_data["input_tokens"],
                            "output_tokens": masca_data["output_tokens"],
                            "total_tokens": masca_data["total_tokens"],
                        })

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "pr": str(pr_dir),
                        "error": str(e)
                    })

                progress.advance()

        # Write MASCA token usage JSON if any results were collected
        if masca_results:
            token_json_path = base_dir / "masca_output_token.json"
            with open(token_json_path, "w", encoding="utf-8") as f:
                json.dump(masca_results, f, indent=2, ensure_ascii=False)
            console.print(f"[green]MASCA token usage saved to {token_json_path}[/green]")

        display_results(console, results, "Context Generation Complete")
        return results

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"BatchContextRetriever not available: {e}"
        )
        return None
