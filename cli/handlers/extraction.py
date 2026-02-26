"""
=============================================================================
EXTRACTION.PY - Ground Truth Extraction Handler
=============================================================================

Handler for extracting ground truth from PR data.
"""

from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from typing import Optional
import os

from cli.components.prompts import (
    prompt_directory, prompt_limit, prompt_confirm, prompt_express_or_configure,
    validate_express_directory,
)
from cli.components.displays import display_results, display_error
from cli.components.progress import ProgressContext
from cli.config import config


def handle_ground_truth_extraction(console: Console) -> Optional[dict]:
    """
    Handle ground truth extraction from PRs.

    Options:
    - Directory path
    - Limit (number of PRs)
    - Use LLM for step plans
    - Skip existing
    """
    console.print(Panel(
        "[bold]Ground Truth Extraction[/bold]\n\n"
        "Extract ground truth (modified files, functions, step plans)\n"
        "from Pull Request data.",
        border_style="blue"
    ))

    defaults = config.express_defaults["extraction"]

    express = prompt_express_or_configure(console, "Ground Truth Extraction", {
        "Directory": defaults["directory"],
        "Limit": defaults["limit"],
        "Use LLM": "No",
        "Skip existing": "Yes",
    })

    if express:
        base_dir = validate_express_directory(console, defaults["directory"])
        if base_dir is None:
            return None
        limit = defaults["limit"]
        use_llm = defaults["use_llm"]
        skip_existing = defaults["skip_existing"]
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
        use_llm = False
        if os.getenv("OPENAI_API_KEY"):
            use_llm = prompt_confirm(
                console,
                "Use LLM to generate step plans? (slower but more detailed)",
                default=False
            )
        else:
            console.print("[dim]LLM disabled (no API key)[/dim]")

        skip_existing = prompt_confirm(console, "Skip PRs with existing ground_truth.json?", default=True)

    # Find valid PRs
    console.print("\n[cyan]Scanning for valid PRs...[/cyan]")

    pr_dirs = []
    for repo_dir in base_dir.iterdir():
        if not repo_dir.is_dir():
            continue
        for pr_dir in repo_dir.iterdir():
            if not pr_dir.is_dir() or not pr_dir.name.startswith("pr_"):
                continue
            # Must have data.json and modified_files
            if (pr_dir / "data.json").exists() and (pr_dir / "modified_files").exists():
                if skip_existing and (pr_dir / "ground_truth.json").exists():
                    continue
                pr_dirs.append(pr_dir)

    pr_dirs = sorted(pr_dirs)

    if limit:
        pr_dirs = pr_dirs[:limit]

    if not pr_dirs:
        console.print("[yellow]No PRs found to process.[/yellow]")
        return {"total": 0, "success": 0, "failed": 0}

    console.print(f"Found [bold]{len(pr_dirs)}[/bold] PRs to process")

    # Process PRs
    try:
        from evaluation.ground_truth_extractor import GroundTruthExtractor

        extractor = GroundTruthExtractor(use_llm=use_llm)
        results = {"total": len(pr_dirs), "success": 0, "failed": 0, "errors": []}

        with ProgressContext(console, "Extracting ground truth", total=len(pr_dirs)) as progress:
            for pr_dir in pr_dirs:
                try:
                    result = extractor.extract_pr(pr_dir)

                    if result and result.extraction_metadata.success:
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                        if result:
                            results["errors"].append({
                                "pr": str(pr_dir),
                                "error": result.extraction_metadata.error_message or "Unknown error"
                            })

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "pr": str(pr_dir),
                        "error": str(e)
                    })

                progress.advance()

        display_results(console, results, "Ground Truth Extraction Complete")
        return results

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"GroundTruthExtractor not available: {e}"
        )
        return None
