"""
=============================================================================
CONFIG.PY - Configuration Management
=============================================================================

Manages application configuration and default settings.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os
import json


HISTORY_FILE = Path.home() / ".ai_planning_cli_history.json"
MAX_RECENT = 10


@dataclass
class Config:
    """Application configuration."""

    # Default paths
    dataset_path: str = "PR4Code/dataset_pr_commits_py"
    output_path: str = "output"

    # Processing defaults
    default_limit: int = 10
    default_parallel: int = 1
    default_model: str = "gpt-4o-mini"

    # Subset defaults
    default_subset_size: int = 100
    default_seed: int = 42

    # Available models
    available_models: list = field(default_factory=lambda: [
        ("gpt-4o-mini", "Fast, economical"),
        ("gpt-4o", "Best quality"),
        ("gpt-4-turbo", "High performance"),
    ])

    # History
    recent_directories: list = field(default_factory=list)
    recent_repos: list = field(default_factory=list)

    @property
    def has_api_key(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(os.getenv("OPENAI_API_KEY"))

    @property
    def dataset_exists(self) -> bool:
        """Check if dataset directory exists."""
        return Path(self.dataset_path).exists()

    @property
    def express_defaults(self) -> dict:
        """Return default parameters for each handler in express mode."""
        return {
            "context": {
                "directory": self.dataset_path,
                "limit": 10,
                "masca": False,
                "skip_existing": True,
                "dry_run": False,
            },
            "extraction": {
                "directory": self.dataset_path,
                "limit": 10,
                "use_llm": False,
                "skip_existing": True,
            },
            "prediction": {
                "directory": self.dataset_path,
                "limit": 10,
                "model": self.default_model,
                "skip_existing": True,
                "parallel": 1,
                "save_report": False,
            },
            "verification": {
                "directory": "PR4Code",
                "only_incomplete": False,
                "export_json": False,
            },
            "subset": {
                "directory": self.dataset_path,
                "size": self.default_subset_size,
                "seed": self.default_seed,
                "output_file": "PR4Code/pr_subset.json",
                "dry_run": False,
            },
            "testing": {
                "run_all": True,
                "verbose": True,
                "coverage": False,
            },
        }

    def validate_path(self, path: str, must_exist: bool = True) -> Optional[Path]:
        """
        Validate a path and return Path object.

        Returns None if invalid.
        """
        try:
            p = Path(path).resolve()
            if must_exist and not p.exists():
                return None
            return p
        except Exception:
            return None

    def get_pr_count(self, path: Optional[str] = None) -> int:
        """Count PR directories in the dataset."""
        dataset = Path(path or self.dataset_path)
        if not dataset.exists():
            return 0

        count = 0
        for repo_dir in dataset.iterdir():
            if repo_dir.is_dir():
                for pr_dir in repo_dir.iterdir():
                    if pr_dir.is_dir() and pr_dir.name.startswith("pr_"):
                        count += 1
        return count

    def load_history(self) -> None:
        """Load history from JSON file."""
        try:
            if HISTORY_FILE.exists():
                data = json.loads(HISTORY_FILE.read_text())
                self.recent_directories = data.get("recent_directories", [])
                self.recent_repos = data.get("recent_repos", [])
        except (json.JSONDecodeError, OSError):
            pass

    def save_history(self) -> None:
        """Save history to JSON file using atomic write to avoid corruption."""
        try:
            import tempfile
            data = {
                "recent_directories": self.recent_directories,
                "recent_repos": self.recent_repos,
            }
            # Write to temp file first, then rename (atomic on most filesystems)
            fd, tmp_path = tempfile.mkstemp(
                dir=HISTORY_FILE.parent, suffix=".tmp"
            )
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2)
                Path(tmp_path).replace(HISTORY_FILE)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError:
            pass

    def add_recent_directory(self, path: str) -> None:
        """Add a directory to recent list (dedup, cap at MAX_RECENT, auto-save)."""
        path = str(Path(path).resolve())
        if path in self.recent_directories:
            self.recent_directories.remove(path)
        self.recent_directories.insert(0, path)
        self.recent_directories = self.recent_directories[:MAX_RECENT]
        self.save_history()

    def add_recent_repo(self, url: str) -> None:
        """Add a repo URL to recent list (dedup, cap at MAX_RECENT, auto-save)."""
        if url in self.recent_repos:
            self.recent_repos.remove(url)
        self.recent_repos.insert(0, url)
        self.recent_repos = self.recent_repos[:MAX_RECENT]
        self.save_history()


# Global config instance
config = Config()
config.load_history()
