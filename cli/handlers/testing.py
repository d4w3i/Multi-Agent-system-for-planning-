"""
=============================================================================
TESTING.PY - Test Execution Handler
=============================================================================

Handler for running pytest test suite.
"""

from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from typing import Optional
import subprocess

from cli.components.prompts import prompt_confirm, prompt_choice, prompt_express_or_configure
from cli.components.displays import display_results, display_error
from cli.components.progress import spinner
from cli.config import config


def handle_run_tests(console: Console) -> Optional[dict]:
    """
    Handle pytest test execution.

    Options:
    - Run all tests
    - Run specific test file
    - Enable coverage
    - Verbose output
    """
    console.print(Panel(
        "[bold]Test Suite[/bold]\n\n"
        "Run pytest tests for the project.",
        border_style="blue"
    ))

    # Check if tests directory exists
    tests_dir = Path("tests")
    if not tests_dir.exists():
        display_error(console, "Tests not found", "No tests/ directory found.")
        return None

    # Options
    test_files = list(tests_dir.glob("test_*.py"))

    if not test_files:
        display_error(console, "No test files", "No test_*.py files found in tests/")
        return None

    console.print(f"Found [bold]{len(test_files)}[/bold] test files")

    defaults = config.express_defaults["testing"]

    express = prompt_express_or_configure(console, "Test Suite", {
        "Run": "All tests",
        "Verbose": "Yes",
        "Coverage": "No",
    })

    if express:
        test_path = None
        verbose = defaults["verbose"]
        coverage = defaults["coverage"]
    else:
        # Select what to run
        choice = prompt_choice(
            console,
            "What to run",
            options=[
                ("1", "All tests", "Run all test files"),
                ("2", "Specific file", "Choose a test file"),
            ],
            default="1"
        )

        test_path = None
        if choice == "2":
            file_options = [
                (str(tf), tf.name, "") for tf in test_files
            ]
            selected = prompt_choice(
                console,
                "Select test file",
                options=file_options,
                default=str(test_files[0]),
            )
            if selected is not None:
                test_path = selected

        verbose = prompt_confirm(console, "Verbose output?", default=True)
        coverage = prompt_confirm(console, "Enable coverage report?", default=False)

    # Build command
    cmd = ["pytest"]

    if test_path:
        cmd.append(test_path)

    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(["--cov", "--cov-report=term-missing"])

    # Add color output
    cmd.append("--color=yes")
    cmd.append("--tb=short")

    console.print(f"\n[cyan]Running:[/cyan] {' '.join(cmd)}")

    # Run tests
    try:
        with spinner(console, "Running tests"):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(Path.cwd())
            )

        # Display output
        output = result.stdout + result.stderr

        # Determine status
        if result.returncode == 0:
            border_style = "green"
            title = "[bold green]Tests Passed[/bold green]"
        else:
            border_style = "red"
            title = "[bold red]Tests Failed[/bold red]"

        console.print(Panel(
            output,
            title=title,
            border_style=border_style
        ))

        # Parse results (rough extraction)
        passed = 0
        failed = 0
        for line in output.split("\n"):
            if " passed" in line and "=" in line:
                try:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "passed":
                            passed = int(parts[i-1])
                        elif p == "failed":
                            failed = int(parts[i-1])
                except (ValueError, IndexError):
                    pass

        return {
            "exit_code": result.returncode,
            "passed": passed,
            "failed": failed,
            "success": result.returncode == 0
        }

    except FileNotFoundError:
        display_error(
            console,
            "pytest not found",
            "Install pytest: pip install pytest"
        )
        return None
    except Exception as e:
        display_error(console, "Test Execution Error", str(e))
        return None
