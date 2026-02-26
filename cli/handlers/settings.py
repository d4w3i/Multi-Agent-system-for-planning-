"""
=============================================================================
SETTINGS.PY - Settings and Help Handlers
=============================================================================

Handlers for viewing configuration and displaying help.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from typing import Optional
import os


def handle_settings(console: Console) -> Optional[dict]:
    """
    Display current configuration and system status.
    """
    console.print(Panel(
        "[bold]Settings & Configuration[/bold]",
        border_style="blue"
    ))

    # System status
    status_table = Table(title="System Status", show_header=True)
    status_table.add_column("Item", style="cyan")
    status_table.add_column("Status")
    status_table.add_column("Details", style="dim")

    # API Key
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        masked = api_key[:8] + "..." + api_key[-4:]
        status_table.add_row("OpenAI API Key", "[green]OK[/green]", masked)
    else:
        status_table.add_row("OpenAI API Key", "[yellow]Not set[/yellow]", "Set in .env file")

    # Dataset
    from pathlib import Path
    dataset_path = Path("PR4Code/dataset_pr_commits_py")
    if dataset_path.exists():
        # Count PRs
        pr_count = 0
        for repo in dataset_path.iterdir():
            if repo.is_dir():
                for pr in repo.iterdir():
                    if pr.is_dir() and pr.name.startswith("pr_"):
                        pr_count += 1
        status_table.add_row("Dataset", "[green]OK[/green]", f"{pr_count} PRs found")
    else:
        status_table.add_row("Dataset", "[yellow]Not found[/yellow]", "PR4Code/ directory missing")

    # Python version
    import sys
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    status_table.add_row("Python", "[green]OK[/green]", py_version)

    console.print(status_table)

    # Default paths
    console.print("\n")
    paths_table = Table(title="Default Paths", show_header=True)
    paths_table.add_column("Setting", style="cyan")
    paths_table.add_column("Value")

    paths_table.add_row("Dataset", "PR4Code/dataset_pr_commits_py")
    paths_table.add_row("Output", "output/")
    paths_table.add_row("Repos (clone)", "repos/")

    console.print(paths_table)

    # Dependencies
    console.print("\n")
    deps_table = Table(title="Optional Dependencies", show_header=True)
    deps_table.add_column("Package", style="cyan")
    deps_table.add_column("Status")
    deps_table.add_column("Used for", style="dim")

    # Check rich (always available if we're here)
    deps_table.add_row("rich", "[green]OK[/green]", "CLI interface")

    # Check tree-sitter
    try:
        import tree_sitter
        deps_table.add_row("tree-sitter", "[green]OK[/green]", "Code analysis")
    except ImportError:
        deps_table.add_row("tree-sitter", "[yellow]Missing[/yellow]", "Code analysis")

    # Check openai
    try:
        import openai
        deps_table.add_row("openai", "[green]OK[/green]", "AI features")
    except ImportError:
        deps_table.add_row("openai", "[yellow]Missing[/yellow]", "AI features")

    # Check tiktoken
    try:
        import tiktoken
        deps_table.add_row("tiktoken", "[green]OK[/green]", "Token counting")
    except ImportError:
        deps_table.add_row("tiktoken", "[yellow]Missing[/yellow]", "Token counting")

    console.print(deps_table)

    return {"status": "ok"}


def handle_help(console: Console) -> Optional[dict]:
    """
    Display help and documentation.
    """
    help_text = """
# AI Planning Module - Evaluation System

## Quick Start

1. **Verify Dataset**: Check PR completeness
2. **Generate Context**: Create call graphs and context files
3. **Extract Ground Truth**: Get modification patterns from PRs
4. **Generate Predictions**: Use AI to predict implementation plans
5. **Evaluate**: Compare predictions against ground truth

## Menu Options

| Option | Description |
|--------|-------------|
| 1. Repository Analysis | Clone and analyze a GitHub repo |
| 2. Context Generation | Generate context files for PRs |
| 3. Ground Truth | Extract ground truth from PR data |
| 4. AI Predictions | Generate AI implementation plans |
| 5. Cleanup | Remove generated files |
| 6. Verification | Check PR directory completeness |
| 7. Subset Creation | Create fixed evaluation subset |
| 8. Python Filter | Find Python-only PRs |
| 9. Tests | Run pytest test suite |

## Keyboard Shortcuts

- **q**: Quit / Cancel
- **Ctrl+C**: Cancel current operation

## Configuration

Set `OPENAI_API_KEY` in `.env` file to enable AI features:
```
OPENAI_API_KEY=sk-your-key-here
```

## More Information

See `CODE_NAVIGATION.md` for detailed codebase documentation.
"""

    console.print(Panel(
        Markdown(help_text),
        title="[bold]Help & Documentation[/bold]",
        border_style="blue"
    ))

    return None
