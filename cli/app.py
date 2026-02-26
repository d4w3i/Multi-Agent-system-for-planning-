"""
=============================================================================
APP.PY - Main CLI Application
=============================================================================

The main application class that orchestrates the CLI interface.
"""

from rich.console import Console
from rich.theme import Theme
import sys

from cli.banner import show_banner, show_quick_help
from cli.menus import MainMenu
from cli.config import config


class EvaluationCLI:
    """
    Main CLI application for the AI Planning Module Evaluation System.

    This class manages:
    - Application lifecycle
    - Console instance (rich)
    - Menu navigation
    - Error handling
    """

    def __init__(self):
        """Initialize the CLI application."""
        # Create themed console
        self.theme = Theme({
            "info": "cyan",
            "success": "green bold",
            "warning": "yellow",
            "error": "red bold",
            "heading": "magenta bold",
            "option": "blue",
        })
        self.console = Console(theme=self.theme)
        self.config = config

    def run(self) -> int:
        """
        Run the main application loop.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            # Show welcome
            self.show_welcome()

            # Run main menu
            menu = MainMenu(self.console)
            menu.run()

            return 0

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Goodbye![/yellow]")
            return 0
        except Exception as e:
            self.console.print(f"\n[red]Fatal error:[/red] {e}")
            return 1

    def show_welcome(self) -> None:
        """Display compact welcome header."""
        show_banner(self.console)
        show_quick_help(self.console)


def main() -> int:
    """
    Entry point for the CLI application.

    Returns:
        Exit code
    """
    app = EvaluationCLI()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
