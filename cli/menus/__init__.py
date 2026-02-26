"""
=============================================================================
MENUS - Menu System Components
=============================================================================

Provides the menu base classes and main menu implementation.
"""

import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any
from abc import ABC, abstractmethod
from rich.console import Console

import questionary
from cli.components.prompts import Q_STYLE


def _strip_rich_markup(text: str) -> str:
    """Remove rich markup tags like [bold], [red], etc."""
    return re.sub(r"\[/?[^\]]+\]", "", text)


@dataclass
class MenuItem:
    """Represents a single menu option."""

    key: str
    icon: str
    label: str
    description: str
    handler: Callable
    requires_confirmation: bool = False
    is_destructive: bool = False
    requires_api_key: bool = False


class BaseMenu(ABC):
    """Abstract base class for menus."""

    def __init__(self, console: Console, parent: Optional["BaseMenu"] = None):
        """
        Initialize menu.

        Args:
            console: Rich console instance
            parent: Parent menu for back navigation
        """
        self.console = console
        self.parent = parent
        self.items: Dict[str, MenuItem] = {}
        self.running = True
        self.setup_items()

    @abstractmethod
    def get_title(self) -> str:
        """Return menu title."""
        pass

    @abstractmethod
    def setup_items(self) -> None:
        """Configure menu items. Override in subclass."""
        pass

    def add_item(self, item: MenuItem) -> None:
        """Add a menu item."""
        self.items[item.key] = item

    def handle_input(self, choice: str) -> Optional[Any]:
        """
        Process user selection.

        Args:
            choice: User's input (menu item key)

        Returns:
            Result from handler or None
        """
        choice = choice.strip().lower()

        if choice in ("q", "quit", "exit"):
            self.running = False
            return None

        if choice in self.items:
            item = self.items[choice]

            # Check if API key required
            if item.requires_api_key:
                if not os.getenv("OPENAI_API_KEY"):
                    self.console.print(
                        "[red]Error:[/red] This operation requires an OpenAI API key.\n"
                        "[dim]Set OPENAI_API_KEY in your .env file.[/dim]"
                    )
                    return None

            # Handle the selection
            try:
                return item.handler()
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Operation cancelled.[/yellow]")
                return None
            except Exception as e:
                self.console.print(f"\n[red]Error:[/red] {e}")
                return None
        else:
            self.console.print(f"[yellow]Invalid option:[/yellow] {choice}")
            return None

    def run(self) -> None:
        """Interactive menu loop with arrow-key navigation."""
        self.running = True

        # Section separators: keys that start a new group
        section_starts = {
            "5": "Dataset Tools",
            "9": "Utility",
            "q": "",
        }

        while self.running:
            self.console.print()

            if not sys.stdin.isatty():
                # Fallback for non-TTY
                for item in self.items.values():
                    print(f"  [{item.key}] {_strip_rich_markup(item.icon)}  {_strip_rich_markup(item.label)}")
                try:
                    choice = self.console.input("[bold cyan]Select option:[/bold cyan] ")
                    self.handle_input(choice)
                except (KeyboardInterrupt, EOFError):
                    self.console.print("\n[yellow]Goodbye![/yellow]")
                    self.running = False
                continue

            # Build questionary choices from menu items
            choices = []
            for item in self.items.values():
                # Add section separator if this key starts a new group
                if item.key in section_starts:
                    label = section_starts[item.key]
                    if label:
                        choices.append(questionary.Separator(f"  ── {label} ──"))
                    else:
                        choices.append(questionary.Separator("  ──────────"))

                icon = _strip_rich_markup(item.icon)
                name = _strip_rich_markup(item.label)
                desc = _strip_rich_markup(item.description)
                if desc:
                    display = f"{icon}  {name:<20s} {desc}"
                else:
                    display = f"{icon}  {name}"
                choices.append(questionary.Choice(display, value=item.key))

            try:
                result = questionary.select(
                    self.get_title(),
                    choices=choices,
                    instruction="(use arrow keys)",
                    use_shortcuts=False,
                    style=Q_STYLE,
                ).ask()

                if result is None:
                    self.console.print("\n[yellow]Goodbye![/yellow]")
                    self.running = False
                else:
                    self.handle_input(result)
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Goodbye![/yellow]")
                self.running = False
            except EOFError:
                self.running = False


from .main_menu import MainMenu

__all__ = ["MenuItem", "BaseMenu", "MainMenu"]
