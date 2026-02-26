"""
=============================================================================
PROGRESS.PY - Progress Tracking Components
=============================================================================

Provides progress bars and spinners for long-running operations.
"""

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from contextlib import contextmanager
from typing import Optional, Generator


def create_progress(console: Console, transient: bool = False) -> Progress:
    """
    Create a standard progress bar with common columns.

    Args:
        console: Rich console instance
        transient: Whether to remove progress bar after completion

    Returns:
        Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=transient
    )


def create_simple_progress(console: Console) -> Progress:
    """
    Create a simple progress bar without time estimates.

    Args:
        console: Rich console instance

    Returns:
        Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    )


def create_spinner_progress(console: Console) -> Progress:
    """
    Create a spinner-only progress indicator.

    Args:
        console: Rich console instance

    Returns:
        Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    )


class ProgressContext:
    """
    Context manager for progress tracking with automatic cleanup.

    Usage:
        with ProgressContext(console, "Processing...", total=100) as progress:
            for item in items:
                process(item)
                progress.advance()
    """

    def __init__(
        self,
        console: Console,
        description: str,
        total: Optional[int] = None,
        transient: bool = False
    ):
        """
        Initialize progress context.

        Args:
            console: Rich console instance
            description: Task description
            total: Total number of items (None for indeterminate)
            transient: Whether to remove progress after completion
        """
        self.console = console
        self.description = description
        self.total = total
        self.transient = transient
        self.progress: Optional[Progress] = None
        self.task_id = None

    def __enter__(self) -> "ProgressContext":
        """Enter context and start progress."""
        self.progress = create_progress(self.console, self.transient)
        self.progress.start()
        self.task_id = self.progress.add_task(
            f"[cyan]{self.description}[/cyan]",
            total=self.total
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and stop progress."""
        if self.progress:
            self.progress.stop()
        return False

    def advance(self, amount: int = 1) -> None:
        """Advance progress by amount."""
        if self.progress and self.task_id is not None:
            self.progress.advance(self.task_id, amount)

    def update(self, **kwargs) -> None:
        """Update task properties."""
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, **kwargs)

    def set_description(self, description: str) -> None:
        """Update task description."""
        self.update(description=f"[cyan]{description}[/cyan]")


@contextmanager
def spinner(console: Console, message: str) -> Generator[None, None, None]:
    """
    Simple spinner context manager for indeterminate operations.

    Usage:
        with spinner(console, "Loading..."):
            do_something()

    Args:
        console: Rich console instance
        message: Spinner message

    Yields:
        None
    """
    with console.status(f"[bold cyan]{message}[/bold cyan]"):
        yield
