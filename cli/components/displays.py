"""
=============================================================================
DISPLAYS.PY - Output Display Components
=============================================================================

Provides reusable display functions for results, errors, and statistics.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Dict, List, Any, Optional, Tuple


def display_results(
    console: Console,
    results: Dict[str, Any],
    title: str = "Operation Complete"
) -> None:
    """
    Display operation results in a styled panel.

    Args:
        console: Rich console instance
        results: Results dict with 'success', 'failed', 'errors', etc.
        title: Panel title
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Icon", width=3)
    table.add_column("Label", width=15)
    table.add_column("Value", style="bold")

    # Success count
    success = results.get("success", 0)
    table.add_row("[green]OK[/green]", "Successful", f"[green]{success}[/green]")

    # Failed count
    failed = results.get("failed", 0)
    if failed > 0:
        table.add_row("[red]X[/red]", "Failed", f"[red]{failed}[/red]")

    # Skipped count
    skipped = results.get("skipped", 0)
    if skipped > 0:
        table.add_row("[yellow]--[/yellow]", "Skipped", f"[yellow]{skipped}[/yellow]")

    # Total count
    total = results.get("total", success + failed + skipped)
    table.add_row("[blue]#[/blue]", "Total", str(total))

    # Elapsed time
    elapsed = results.get("elapsed_seconds")
    if elapsed is not None:
        table.add_row("[cyan]T[/cyan]", "Time", f"{elapsed:.1f}s")

    # Determine border color
    if failed == 0:
        border_style = "green"
    elif success > 0:
        border_style = "yellow"
    else:
        border_style = "red"

    console.print(Panel(
        table,
        title=f"[bold]{title}[/bold]",
        border_style=border_style
    ))

    # Show errors if any
    errors = results.get("errors", [])
    if errors:
        display_errors(console, errors)


def display_errors(
    console: Console,
    errors: List[Dict[str, str]],
    max_display: int = 5
) -> None:
    """
    Display error list with truncation.

    Args:
        console: Rich console instance
        errors: List of error dicts with 'pr' or 'item' and 'error' keys
        max_display: Maximum number of errors to display
    """
    console.print()
    console.print("[bold red]Errors:[/bold red]")

    for i, err in enumerate(errors[:max_display]):
        item = err.get("pr") or err.get("item") or "Unknown"
        error = err.get("error", "Unknown error")
        console.print(f"  [red]x[/red] {item}: {error}")

    if len(errors) > max_display:
        console.print(f"  [dim]... and {len(errors) - max_display} more errors[/dim]")


def display_error(console: Console, message: str, details: str = "") -> None:
    """
    Display an error message in a panel.

    Args:
        console: Rich console instance
        message: Main error message
        details: Additional details
    """
    content = f"[bold red]{message}[/bold red]"
    if details:
        content += f"\n\n[dim]{details}[/dim]"

    console.print(Panel(
        content,
        title="[bold red]Error[/bold red]",
        border_style="red"
    ))


def display_success(console: Console, message: str) -> None:
    """
    Display a success message.

    Args:
        console: Rich console instance
        message: Success message
    """
    console.print(f"[green]OK[/green] {message}")


def display_warning(console: Console, message: str) -> None:
    """
    Display a warning message.

    Args:
        console: Rich console instance
        message: Warning message
    """
    console.print(f"[yellow]Warning:[/yellow] {message}")


def display_table(
    console: Console,
    data: List[Dict[str, Any]],
    columns: List[Tuple[str, str, Optional[str]]],  # (key, header, style)
    title: str = ""
) -> None:
    """
    Display data in a formatted table.

    Args:
        console: Rich console instance
        data: List of row dicts
        columns: List of (key, header, style) tuples
        title: Optional table title
    """
    table = Table(title=title if title else None, show_header=True)

    for key, header, style in columns:
        table.add_column(header, style=style)

    for row in data:
        table.add_row(*[str(row.get(col[0], "")) for col in columns])

    console.print(table)


def display_stats_panel(
    console: Console,
    stats: Dict[str, Any],
    title: str = "Statistics"
) -> None:
    """
    Display statistics in a panel.

    Args:
        console: Rich console instance
        stats: Statistics dict
        title: Panel title
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan")

    for key, value in stats.items():
        # Format key from snake_case to Title Case
        label = key.replace("_", " ").title()
        table.add_row(label, str(value))

    console.print(Panel(
        table,
        title=f"[bold]{title}[/bold]",
        border_style="blue"
    ))


def display_verification_table(
    console: Console,
    categories: Dict[str, List],
    title: str = "PR Verification Results"
) -> None:
    """
    Display PR verification results in a formatted table.

    Args:
        console: Rich console instance
        categories: Dict with 'complete', 'missing_base_project_only', etc.
        title: Table title
    """
    table = Table(title=title, show_header=True)
    table.add_column("Status", width=10)
    table.add_column("Category", width=30)
    table.add_column("Count", justify="right", width=10)

    # Complete
    complete = len(categories.get("complete", []))
    table.add_row("[green]OK[/green]", "Complete PRs", f"[green]{complete}[/green]")

    # Missing base_project only
    missing_base = len(categories.get("missing_base_project_only", []))
    if missing_base > 0:
        table.add_row("[yellow]--[/yellow]", "Missing base_project/", f"[yellow]{missing_base}[/yellow]")

    # Missing context_output only
    missing_context = len(categories.get("missing_context_output_only", []))
    if missing_context > 0:
        table.add_row("[yellow]--[/yellow]", "Missing context_output/", f"[yellow]{missing_context}[/yellow]")

    # Missing both
    missing_both = len(categories.get("missing_both", []))
    if missing_both > 0:
        table.add_row("[red]X[/red]", "Missing both", f"[red]{missing_both}[/red]")

    # Total
    total = complete + missing_base + missing_context + missing_both
    table.add_row("[blue]#[/blue]", "[bold]Total[/bold]", f"[bold]{total}[/bold]")

    console.print(table)
