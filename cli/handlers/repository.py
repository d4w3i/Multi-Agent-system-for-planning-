"""
=============================================================================
REPOSITORY.PY - Repository Analysis Handler
=============================================================================

Handler for analyzing GitHub repositories (migrated from original main.py).
"""

from rich.console import Console
from rich.panel import Panel
from pathlib import Path
import subprocess
import shutil
import time
from typing import Optional

from cli.components.prompts import prompt_confirm, prompt_text
from cli.components.progress import spinner
from cli.components.displays import display_success, display_error
from cli.config import config


def is_valid_git_url(url: str) -> bool:
    """Validate Git URL."""
    if not url or not isinstance(url, str):
        return False

    # SSH format
    if url.startswith("git@"):
        return ":" in url

    # HTTP/HTTPS format
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def clone_repository(console: Console, repo_url: str, target_dir: str) -> bool:
    """Clone Git repository."""
    try:
        with spinner(console, "Cloning repository from GitHub"):
            subprocess.run(
                ["git", "clone", "--", repo_url, target_dir],
                check=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for large repos
            )
        return True
    except subprocess.CalledProcessError as e:
        display_error(console, "Clone failed", e.stderr)
        return False
    except FileNotFoundError:
        display_error(console, "Git not installed", "Please install Git to use this feature.")
        return False


def sanitize_for_triple_quotes(content: str, delimiter: str = "'''") -> str:
    """Sanitize content to prevent conflicts with string delimiters.

    Note: canonical implementation is in context_retrieving.batch_context_retriever.
    Kept here to avoid adding a dependency on that module for the CLI handler.
    """
    if delimiter == "'''":
        return content.replace("'''", r"\'\'\'")
    elif delimiter == '"""':
        return content.replace('"""', r'\"\"\"')
    return content


def generate_directory_tree(console: Console, repo_path: str, output_file: str) -> bool:
    """Generate ASCII directory tree."""
    try:
        result = subprocess.run(
            ["tree", "-I", ".git|.venv|venv|__pycache__|*.pyc|.pytest_cache",
             "-L", "4", repo_path],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            with open(output_file, "w") as f:
                f.write(result.stdout)
            return True
        else:
            return generate_tree_python(console, repo_path, output_file)

    except FileNotFoundError:
        return generate_tree_python(console, repo_path, output_file)


def generate_tree_python(console: Console, repo_path: str, output_file: str) -> bool:
    """Fallback to generate tree without tree command."""
    try:
        from context_retrieving.generate_tree import TreeGenerator

        generator = TreeGenerator(root_path=repo_path, max_depth=4)
        lines, stats = generator.generate()

        with open(output_file, "w") as f:
            f.write("\n".join(lines))
            f.write("\n\n")
            f.write("=" * 50 + "\n")
            f.write("STATISTICS\n")
            f.write("=" * 50 + "\n")
            f.write(f"Directory: {stats['directories']}\n")
            f.write(f"File: {stats['files']}\n")

        return True
    except Exception as e:
        console.print(f"[yellow]Tree generation warning:[/yellow] {e}")
        return False


def handle_repository_analysis(console: Console) -> Optional[dict]:
    """
    Handle repository analysis workflow.

    Steps:
    1. Input repository URL
    2. Clone repository
    3. Analyze code and build call graph
    4. Generate outputs (JSON, DOT, context files)
    5. Generate directory tree
    6. Run Masca AI analysis (optional)
    """
    console.print(Panel(
        "[bold]Repository Analysis[/bold]\n\n"
        "This will clone a GitHub repository, analyze its code,\n"
        "and generate call graphs and context files.",
        border_style="blue"
    ))

    # Step 1: Input URL with autocomplete from recent repos
    console.print("\n[bold cyan]Step 1/6:[/bold cyan] Input Repository URL")

    recent = config.recent_repos or None
    repo_url = prompt_text(
        console,
        "GitHub repository URL:",
        validate=lambda v: len(v.strip()) > 0,
        suggestions=recent,
    )

    if not repo_url or repo_url.lower() in ("q", "quit", "cancel"):
        console.print("[yellow]Cancelled.[/yellow]")
        return None

    if not is_valid_git_url(repo_url):
        display_error(console, "Invalid URL", "Please enter a valid Git URL.")
        return None

    config.add_recent_repo(repo_url)

    # Extract repo name
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    clone_dir = f"repos/{repo_name}"
    output_dir = f"output/{repo_name}"

    console.print(f"[green]OK[/green] Repository: [bold]{repo_name}[/bold]")

    # Step 2: Clone repository
    console.print("\n[bold cyan]Step 2/6:[/bold cyan] Cloning Repository")

    # Clean up if already exists
    if Path(clone_dir).exists():
        if prompt_confirm(console, f"Directory {clone_dir} exists. Remove and re-clone?", default=True):
            shutil.rmtree(clone_dir)
        else:
            console.print("[yellow]Using existing directory.[/yellow]")

    if not Path(clone_dir).exists():
        Path(clone_dir).parent.mkdir(parents=True, exist_ok=True)
        if not clone_repository(console, repo_url, clone_dir):
            return None

    console.print(f"[green]OK[/green] Repository cloned to {clone_dir}")

    # Step 3: Code analysis
    console.print("\n[bold cyan]Step 3/6:[/bold cyan] Code Analysis")

    from context_retrieving.call_graph_builder import CallGraphBuilder

    with spinner(console, "Analyzing repository"):
        start_time = time.time()
        builder = CallGraphBuilder(verbose=False)
        call_graph = builder.analyze_repository(clone_dir)
        elapsed = time.time() - start_time

    console.print(f"[green]OK[/green] Found [bold]{len(call_graph)}[/bold] functions in {elapsed:.2f}s")

    # Step 4: Output generation
    console.print("\n[bold cyan]Step 4/6:[/bold cyan] Generating Output")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Read README.md if exists
    readme_content = ""
    readme_path = Path(clone_dir) / "README.md"
    if readme_path.exists():
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()
        except UnicodeDecodeError:
            try:
                with open(readme_path, "r", encoding="latin-1") as f:
                    readme_content = f.read()
            except Exception:
                readme_content = ""

    # Save call graph JSON
    with spinner(console, "Generating call_graph.json"):
        json_file = f"{output_dir}/call_graph.json"
        builder.to_json(json_file)
    console.print(f"[green]OK[/green] Call graph JSON: {json_file}")

    # Generate context files
    from context_retrieving.context_generator import ContextGenerator

    with spinner(console, f"Generating {len(call_graph)} context files"):
        context_dir = f"{output_dir}/context_files"
        generator = ContextGenerator(call_graph, repo_root=clone_dir, verbose=False)
        generator.generate_all_context_files(context_dir)
    console.print(f"[green]OK[/green] Context files: {context_dir}/")

    # Step 5: Directory tree
    console.print("\n[bold cyan]Step 5/6:[/bold cyan] Generating Directory Tree")

    temp_tree_file = f"{output_dir}/.temp_tree.txt"
    tree_content = ""
    if generate_directory_tree(console, clone_dir, temp_tree_file):
        with open(temp_tree_file, "r", encoding="utf-8") as f:
            tree_content = f.read()
        Path(temp_tree_file).unlink()
        console.print("[green]OK[/green] Directory tree generated")

    # Create project_info.py
    project_info_path = f"{output_dir}/project_info.py"
    with open(project_info_path, "w", encoding="utf-8") as f:
        f.write('"""Project Information - Auto-generated file"""\n\n')
        f.write("DIRECTORY_TREE = '''")
        f.write(sanitize_for_triple_quotes(tree_content, "'''"))
        f.write("'''\n\n")
        f.write("README = '''")
        f.write(sanitize_for_triple_quotes(readme_content, "'''"))
        f.write("'''\n")

    console.print(f"[green]OK[/green] Project info: {project_info_path}")

    # Step 6: Masca AI analysis (optional)
    console.print("\n[bold cyan]Step 6/6:[/bold cyan] AI Analysis")

    import os
    if os.getenv("OPENAI_API_KEY"):
        try:
            from GenAI.masca_runner import run_masca_analysis, save_masca_output

            with spinner(console, "Running AI analysis"):
                masca_output = run_masca_analysis(readme_content, tree_content)

            masca_file = f"{output_dir}/masca_analysis.md"
            if save_masca_output(masca_output, masca_file, tree_content):
                console.print(f"[green]OK[/green] Masca analysis: {masca_file}")
            else:
                console.print("[yellow]Warning:[/yellow] Error saving Masca analysis")

        except ImportError:
            console.print("[yellow]Skipped:[/yellow] Masca agent not available")
        except Exception as e:
            console.print(f"[yellow]Skipped:[/yellow] {e}")
    else:
        console.print("[yellow]Skipped:[/yellow] No API key (set OPENAI_API_KEY to enable)")

    # Summary
    console.print(Panel(
        f"[bold green]Analysis Complete![/bold green]\n\n"
        f"Repository: [bold]{repo_name}[/bold]\n"
        f"Functions: [bold]{len(call_graph)}[/bold]\n"
        f"Output: [bold]{output_dir}/[/bold]\n\n"
        f"Files generated:\n"
        f"  - project_info.py\n"
        f"  - call_graph.json\n"
        f"  - context_files/ ({len(call_graph)} files)",
        title="[bold]Summary[/bold]",
        border_style="green"
    ))

    # Optional cleanup
    if prompt_confirm(console, "Remove cloned repository?", default=False):
        shutil.rmtree(clone_dir)
        console.print(f"[green]OK[/green] Repository {clone_dir} removed")

    return {
        "repo_name": repo_name,
        "functions": len(call_graph),
        "output_dir": output_dir
    }
