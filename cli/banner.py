"""
=============================================================================
BANNER.PY - Welcome Display
=============================================================================

Compact welcome screen with inline status indicators.
"""

from rich.console import Console


def show_banner(console: Console) -> None:
    """Display a compact welcome line."""
    console.print()
    console.print(
        "[bold cyan]AI Planning Module[/bold cyan] "
    )


def show_quick_help(console: Console) -> None:
    """Display minimal help hint."""
    console.print()
    console.print("[dim]  Arrow keys to navigate · Enter to select · Ctrl+C to cancel[/dim]")
    console.print()
