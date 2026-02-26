"""
=============================================================================
PROMPTS.PY - Interactive Input Prompts
=============================================================================

Provides reusable prompt functions for user input with validation.
Uses questionary for arrow-key navigation and prompt_toolkit for path completion.
Falls back to basic input if not running in a TTY.
"""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional, List, Tuple

import questionary
from prompt_toolkit.completion import PathCompleter, WordCompleter, merge_completers
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style as PTStyle

from cli.config import config

# Shared style: selected item bright, others dimmed
Q_STYLE = PTStyle([
    ("qmark", "fg:#5f87ff bold"),
    ("question", "fg:#ffffff bold"),
    ("pointer", "fg:#5fffff bold"),
    ("highlighted", "fg:#ffffff bold"),
    ("selected", "fg:#5fffff"),
    ("text", "fg:#888888"),
    ("separator", "fg:#555555"),
    ("instruction", "fg:#555555"),
    ("answer", "fg:#5fffff bold"),
])


def _is_tty() -> bool:
    """Check if stdin is a TTY (interactive terminal)."""
    return sys.stdin.isatty()


def prompt_directory(
    console: Console,
    message: str = "Enter directory path",
    default: str = "PR4Code/dataset_pr_commits_py",
    must_exist: bool = True
) -> Optional[Path]:
    """
    Prompt for a directory path with Tab completion and recent directory suggestions.

    Returns:
        Path object or None if cancelled
    """
    if not _is_tty():
        path_str = input(f"{message} [{default}]: ").strip() or default
        path = Path(path_str).resolve()
        if must_exist and (not path.exists() or not path.is_dir()):
            return None
        return path

    recent_completer = WordCompleter(config.recent_directories, sentence=True)
    path_completer = PathCompleter(only_directories=True)
    merged = merge_completers([recent_completer, path_completer])

    while True:
        try:
            path_str = pt_prompt(
                f"{message} [{default}]: ",
                completer=merged,
                default=default,
            )
        except (KeyboardInterrupt, EOFError):
            return None

        if not path_str or path_str.lower() in ("q", "quit", "cancel"):
            return None

        path = Path(path_str).resolve()

        if must_exist and not path.exists():
            console.print(f"[red]Directory not found:[/red] {path}")
            continue

        if must_exist and not path.is_dir():
            console.print(f"[red]Not a directory:[/red] {path}")
            continue

        config.add_recent_directory(str(path))
        return path


def prompt_limit(
    console: Console,
    default: int = 10,
    allow_all: bool = True
) -> Optional[int]:
    """
    Prompt for a processing limit with arrow-key selection.

    Returns:
        Integer limit or None for all items
    """
    choices = [
        questionary.Choice("5   - Quick test", value=5),
        questionary.Choice("10  - Small batch", value=10),
        questionary.Choice("50  - Medium batch", value=50),
        questionary.Choice("100 - Large batch", value=100),
    ]

    if allow_all:
        choices.append(questionary.Choice("All - Process everything", value=None))

    choices.append(questionary.Choice("Custom...", value="custom"))

    # Find the default choice index
    default_choice = None
    for c in choices:
        if c.value == default:
            default_choice = c
            break
    if default_choice is None:
        default_choice = choices[1]  # 10

    if not _is_tty():
        return default

    result = questionary.select(
        "Select limit:",
        choices=choices,
        default=default_choice,
        instruction="(arrow keys to move, Enter to select)",
        style=Q_STYLE,
    ).ask()

    if result is None:
        return default  # Ctrl+C -> use default
    if result == "custom":
        custom = questionary.text(
            "Enter custom limit:",
            default=str(default),
            validate=lambda v: v.isdigit() and int(v) > 0,
            style=Q_STYLE,
        ).ask()
        if custom is None:
            return default
        return int(custom)
    return result


def prompt_model(console: Console, default: str = "gpt-4o-mini") -> str:
    """
    Prompt for AI model selection with arrow-key navigation.

    Returns:
        Selected model name
    """
    choices = [
        questionary.Choice("gpt-4o-mini  - Fast, economical (recommended)", value="gpt-4o-mini"),
        questionary.Choice("gpt-4o       - Best quality, slower", value="gpt-4o"),
        questionary.Choice("gpt-4-turbo  - High performance", value="gpt-4-turbo"),
    ]

    default_choice = None
    for c in choices:
        if c.value == default:
            default_choice = c
            break

    if not _is_tty():
        return default

    result = questionary.select(
        "Select model:",
        choices=choices,
        default=default_choice,
        instruction="(arrow keys to move, Enter to select)",
        style=Q_STYLE,
    ).ask()

    return result if result is not None else default


def prompt_confirm(
    console: Console,
    message: str,
    default: bool = False
) -> bool:
    """
    Simple yes/no confirmation prompt.

    Returns:
        Boolean confirmation
    """
    if not _is_tty():
        return default

    result = questionary.confirm(message, default=default, style=Q_STYLE).ask()
    return result if result is not None else default


def prompt_confirm_destructive(
    console: Console,
    action: str,
    target: str,
    count: int
) -> bool:
    """
    Confirmation for destructive operations requiring explicit text input.

    Returns:
        Boolean confirmation
    """
    # Show warning panel (rich for output)
    warning = Table(show_header=False, box=None)
    warning.add_row("[bold red]WARNING[/bold red]", "This action cannot be undone!")
    warning.add_row("Action:", action)
    warning.add_row("Target:", target)
    warning.add_row("Affected:", f"[bold]{count}[/bold] items")

    console.print(Panel(
        warning,
        title="[bold red]Destructive Operation[/bold red]",
        border_style="red"
    ))

    # Use questionary for the DELETE confirmation input
    if not _is_tty():
        return False

    confirmation = questionary.text(
        "Type 'DELETE' to confirm:",
        style=Q_STYLE,
    ).ask()

    if confirmation is None:
        return False
    return confirmation.strip().upper() == "DELETE"


def prompt_choice(
    console: Console,
    title: str,
    options: List[Tuple[str, str, str]],  # (key, label, description)
    default: str = "1"
) -> str:
    """
    Generic choice prompt with arrow-key selection.

    Returns:
        Selected key
    """
    choices = []
    key_map = {}
    default_choice = None
    for key, label, desc in options:
        display = f"{label} - {desc}" if desc else label
        choice = questionary.Choice(display, value=key)
        choices.append(choice)
        key_map[key] = choice
        if key == default:
            default_choice = choice

    if not _is_tty():
        return default

    result = questionary.select(
        f"{title}:",
        choices=choices,
        default=default_choice,
        instruction="(arrow keys to move, Enter to select)",
        style=Q_STYLE,
    ).ask()

    return result if result is not None else default


def prompt_multi_choice(
    console: Console,
    title: str,
    options: List[Tuple[str, str]],  # (value, label)
    defaults: Optional[List[str]] = None
) -> List[str]:
    """
    Multi-select prompt with space-to-toggle and arrow keys.

    Returns:
        List of selected values
    """
    defaults = defaults or []

    choices = []
    for value, label in options:
        choices.append(questionary.Choice(
            label,
            value=value,
            checked=value in defaults,
        ))

    if not _is_tty():
        return defaults

    result = questionary.checkbox(
        f"{title}:",
        choices=choices,
        instruction="(Space to toggle, Enter to confirm)",
        style=Q_STYLE,
    ).ask()

    return result if result is not None else defaults


def prompt_text(
    console: Console,
    message: str,
    default: str = "",
    validate: Optional[callable] = None,
    suggestions: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Generic text input prompt.

    Supports optional validation, default value, and autocomplete suggestions.

    Args:
        console: Rich console instance
        message: Prompt message
        default: Default value
        validate: Optional validation function (str -> bool)
        suggestions: Optional list of autocomplete suggestions

    Returns:
        User input string or None if cancelled
    """
    if not _is_tty():
        raw = input(f"{message} [{default}]: ").strip()
        return raw if raw else default

    if suggestions:
        result = questionary.autocomplete(
            message,
            choices=suggestions,
            default=default,
            validate=validate,
            style=Q_STYLE,
        ).ask()
    else:
        result = questionary.text(
            message,
            default=default,
            validate=validate,
            style=Q_STYLE,
        ).ask()

    return result


def prompt_express_or_configure(
    console: Console,
    operation_name: str,
    defaults_summary: dict,
) -> bool:
    """
    Ask whether to run with express defaults or configure manually.

    Shows a table of current defaults, then asks Express vs Configure.

    Args:
        console: Rich console instance
        operation_name: Name of the operation (e.g., "Context Generation")
        defaults_summary: Dict of {param_name: display_value} for the defaults table

    Returns:
        True for express mode, False for configure mode
    """
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Parameter", style="cyan")
    table.add_column("Default", style="bold")

    for param, value in defaults_summary.items():
        table.add_row(param, str(value))

    console.print(Panel(
        table,
        title=f"[bold]{operation_name} - Express Defaults[/bold]",
        border_style="blue"
    ))

    if not _is_tty():
        return True

    result = questionary.select(
        "How would you like to proceed?",
        choices=[
            questionary.Choice("\u26a1 Express  - Run with defaults shown above", value=True),
            questionary.Choice("\U0001f527 Configure - Customize all options", value=False),
        ],
        default=None,
        instruction="(Enter to select)",
        style=Q_STYLE,
    ).ask()

    return result if result is not None else True


def validate_express_directory(console: Console, directory: str) -> Optional[Path]:
    """
    Resolve and validate a directory path for express mode.

    Returns:
        Resolved Path if valid, or None (after displaying error) if not found.
    """
    from cli.components.displays import display_error

    base_dir = Path(directory).resolve()
    if not base_dir.exists() or not base_dir.is_dir():
        display_error(console, "Directory not found", str(base_dir))
        return None
    return base_dir
