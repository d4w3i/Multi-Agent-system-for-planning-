"""
=============================================================================
PREDICTION.PY - AI Predictions Handler
=============================================================================

Handler for generating AI implementation plans.
"""

from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from typing import Optional
import os

from cli.components.prompts import (
    prompt_directory, prompt_limit, prompt_model, prompt_confirm,
    prompt_text, prompt_express_or_configure, validate_express_directory,
)
from cli.components.displays import display_results, display_error
from cli.config import config


def handle_ai_predictions(console: Console) -> Optional[dict]:
    """
    Handle AI prediction generation for PRs.

    Options:
    - Directory path
    - Limit or process all
    - Model selection
    - Skip existing
    - Parallel workers
    - Save report
    """
    # Check API key first
    if not os.getenv("OPENAI_API_KEY"):
        display_error(
            console,
            "API Key Required",
            "This operation requires OPENAI_API_KEY to be set in your .env file."
        )
        return None

    console.print(Panel(
        "[bold]AI Predictions Generation[/bold]\n\n"
        "Generate predicted implementation plans using AI\n"
        "for PRs in the dataset.",
        border_style="blue"
    ))

    defaults = config.express_defaults["prediction"]

    express = prompt_express_or_configure(console, "AI Predictions", {
        "Directory": defaults["directory"],
        "Limit": defaults["limit"],
        "Model": defaults["model"],
        "Skip existing": "Yes",
        "Parallel workers": defaults["parallel"],
        "Save report": "No",
    })

    if express:
        base_dir = validate_express_directory(console, defaults["directory"])
        if base_dir is None:
            return None
        limit = defaults["limit"]
        model = defaults["model"]
        skip_existing = defaults["skip_existing"]
        parallel = defaults["parallel"]
        save_report = defaults["save_report"]
        report_path = None
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

        # Model selection
        model = prompt_model(console, default=defaults["model"])
        console.print(f"Selected model: [bold]{model}[/bold]")

        # Options
        skip_existing = prompt_confirm(console, "Skip PRs with existing predicted_plan.json?", default=True)

        # Parallel processing
        parallel = 1
        if prompt_confirm(console, "Enable parallel processing?", default=False):
            result = prompt_text(
                console,
                "Number of parallel workers:",
                default="2",
                validate=lambda v: v.isdigit() and 1 <= int(v) <= 8,
            )
            if result is not None:
                parallel = max(1, min(int(result), 8))

        # Save report
        save_report = prompt_confirm(console, "Save batch report to JSON?", default=False)
        report_path = None
        if save_report:
            report_path = prompt_text(
                console,
                "Report filename:",
                default="batch_report.json",
            )
            if report_path is None:
                report_path = "batch_report.json"

    # Run batch prediction
    console.print("\n[cyan]Starting AI prediction generation...[/cyan]")
    console.print(f"Model: [bold]{model}[/bold]")
    console.print(f"Parallel workers: [bold]{parallel}[/bold]")

    try:
        from GenAI.batch_predict import run_batch, save_batch_report

        results = run_batch(
            base_path=str(base_dir),
            limit=limit,
            model_name=model,
            skip_existing=skip_existing,
            verbose=True,
            parallel=parallel
        )

        # Save report if requested
        if save_report and report_path:
            save_batch_report(results, report_path)
            console.print(f"\n[green]OK[/green] Report saved: {report_path}")

        display_results(console, results, "AI Prediction Complete")
        return results

    except ImportError as e:
        display_error(
            console,
            "Missing dependency",
            f"GenAI.batch_predict not available: {e}"
        )
        return None
    except Exception as e:
        display_error(console, "Prediction Error", str(e))
        return None
