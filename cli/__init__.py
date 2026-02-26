"""
=============================================================================
CLI - Interactive Command Line Interface
=============================================================================

Interactive CLI for the AI Planning Module Evaluation System.

USAGE:
    python main.py                 # Run interactive CLI
    python -m cli                  # Alternative entry point

PACKAGE STRUCTURE:

    cli/
    ├── __init__.py               # This file - package entry point
    ├── app.py                    # Main application class
    ├── banner.py                 # ASCII banner and welcome
    ├── config.py                 # Configuration management
    ├── menus/                    # Menu system
    │   ├── __init__.py           # Menu base classes
    │   └── main_menu.py          # Main menu implementation
    ├── handlers/                 # Operation handlers
    │   ├── repository.py         # Repository analysis
    │   ├── context.py            # Context generation
    │   ├── extraction.py         # Ground truth extraction
    │   ├── prediction.py         # AI predictions
    │   ├── cleanup.py            # Dataset cleanup
    │   ├── verification.py       # Dataset verification
    │   ├── subset.py             # Subset creation
    │   └── testing.py            # Test execution
    └── components/               # Reusable UI components
        ├── prompts.py            # Input prompts
        ├── displays.py           # Output displays
        └── progress.py           # Progress tracking

FEATURES:
    - Beautiful terminal UI using rich library
    - Interactive menus with keyboard navigation
    - Progress bars and spinners
    - Colored output and styled panels
    - All existing functionality accessible through menus

=============================================================================
"""

__version__ = "1.0.0"

from cli.app import main, EvaluationCLI

__all__ = ["main", "EvaluationCLI", "__version__"]
