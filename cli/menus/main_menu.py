"""
=============================================================================
MAIN_MENU.PY - Main Application Menu
=============================================================================

The primary menu with logically grouped operations.
"""

from rich.console import Console
from . import BaseMenu, MenuItem


class MainMenu(BaseMenu):
    """Main menu with grouped evaluation system operations."""

    def get_title(self) -> str:
        return "What would you like to do?"

    def setup_items(self) -> None:
        """Configure all menu items with logical grouping."""

        # Import handlers lazily to avoid circular imports
        from cli.handlers import (
            handle_repository_analysis,
            handle_context_generation,
            handle_ground_truth_extraction,
            handle_ai_predictions,
            handle_dataset_cleanup,
            handle_dataset_verification,
            handle_subset_creation,
            handle_python_filter,
            handle_run_tests,
            handle_settings,
            handle_help,
        )

        # --- Analysis & Generation ---
        self.add_item(MenuItem(
            key="1",
            icon="\U0001f4e6",
            label="Repository Analysis",
            description="Clone and analyze a repo",
            handler=lambda: handle_repository_analysis(self.console)
        ))

        self.add_item(MenuItem(
            key="2",
            icon="\U0001f4c4",
            label="Context Generation",
            description="Generate context for PRs",
            handler=lambda: handle_context_generation(self.console),
        ))

        self.add_item(MenuItem(
            key="3",
            icon="\U0001f50d",
            label="Ground Truth",
            description="Extract truth from PR data",
            handler=lambda: handle_ground_truth_extraction(self.console),
        ))

        self.add_item(MenuItem(
            key="4",
            icon="\U0001f916",
            label="AI Predictions",
            description="Generate implementation plans",
            handler=lambda: handle_ai_predictions(self.console),
            requires_api_key=True
        ))

        # --- Dataset Tools ---
        self.add_item(MenuItem(
            key="5",
            icon="\u2705",
            label="Verify Dataset",
            description="Check PR completeness",
            handler=lambda: handle_dataset_verification(self.console)
        ))

        self.add_item(MenuItem(
            key="6",
            icon="\u2702\ufe0f",
            label=" Create Subset",
            description=" Fixed PR evaluation subset",
            handler=lambda: handle_subset_creation(self.console)
        ))

        self.add_item(MenuItem(
            key="7",
            icon="\U0001f40d",
            label="Python PR Filter",
            description="Find Python-only PRs",
            handler=lambda: handle_python_filter(self.console)
        ))

        self.add_item(MenuItem(
            key="8",
            icon="\U0001f9f9",
            label="Cleanup",
            description="Remove generated files",
            handler=lambda: handle_dataset_cleanup(self.console),
            is_destructive=True
        ))

        # --- Utility ---
        self.add_item(MenuItem(
            key="9",
            icon="\U0001f9ea",
            label="Run Tests",
            description="Execute pytest suite",
            handler=lambda: handle_run_tests(self.console)
        ))

        self.add_item(MenuItem(
            key="0",
            icon="\u2699\ufe0f",
            label=" Settings",
            description=" Configuration & status",
            handler=lambda: handle_settings(self.console),
        ))

        self.add_item(MenuItem(
            key="h",
            icon="\u2753",
            label="Help",
            description="Docs & keyboard shortcuts",
            handler=lambda: handle_help(self.console)
        ))

        self.add_item(MenuItem(
            key="q",
            icon="\U0001f6aa",
            label="Exit",
            description="",
            handler=self._exit
        ))

    def _exit(self) -> None:
        """Exit the menu."""
        self.running = False
        self.console.print("[dim]Goodbye![/dim]")
