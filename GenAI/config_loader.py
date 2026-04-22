"""
GenAI Agent Configuration Loader
=================================

Loads and validates `agents_config.toml` (located in the same directory as
this module). Provides a typed `AgentModels` helper used by `PRStepPlanner`
to select the right OpenAI model for each agent in the pipeline.

Usage
-----
    from GenAI.config_loader import load_config

    cfg = load_config()
    print(cfg.agents.analysis.model)       # "gpt-4o-mini"
    print(cfg.agents.context_planner.model)
    print(cfg.agents.file_summarizer.model)
    print(cfg.defaults.model)              # fallback / display model

The result is cached after the first call (module-level singleton).

CLI Override Pattern
--------------------
`PRStepPlanner.__init__` accepts an optional `model_name` argument. When
provided it overrides all three agents for that run:

    planner = PRStepPlanner(pr_dir, model_name="gpt-4o")   # overrides all
    planner = PRStepPlanner(pr_dir)                         # uses config

This file is intentionally read-only — to change models, edit agents_config.toml.
"""

import tomllib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

# Path to the sibling config file
_CONFIG_PATH = Path(__file__).parent / "agents_config.toml"

# Module-level cache — loaded once per process
_cached_config: Optional["Config"] = None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """Settings for a single agent."""
    model: str

    @field_validator("model")
    @classmethod
    def model_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent model name must not be empty")
        return v.strip()


class AgentsSection(BaseModel):
    """Per-agent model configuration."""
    analysis: AgentConfig
    context_planner: AgentConfig
    file_summarizer: AgentConfig
    masca: AgentConfig
    single_agent: Optional[AgentConfig] = None


class Config(BaseModel):
    """Root configuration object parsed from agents_config.toml."""
    defaults: AgentConfig
    agents: AgentsSection


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(path: Optional[Path] = None) -> Config:
    """
    Load and return the agent configuration.

    Results are cached after the first successful load. Pass a custom `path`
    to load from a different file (useful in tests).

    Args:
        path: Override the default config file path. Defaults to
              `GenAI/agents_config.toml` (sibling of this module).

    Returns:
        Validated `Config` instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        tomllib.TOMLDecodeError: If the file is not valid TOML.
        pydantic.ValidationError: If required fields are missing or invalid.
    """
    global _cached_config

    if _cached_config is not None and path is None:
        return _cached_config

    config_path = path or _CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"Agent config not found: {config_path}\n"
            f"Expected file: GenAI/agents_config.toml"
        )

    with open(config_path, "rb") as fh:
        raw = tomllib.load(fh)

    config = Config.model_validate(raw)

    if path is None:
        _cached_config = config

    return config


def reset_cache() -> None:
    """Clear the cached config (useful in tests or after hot-reload)."""
    global _cached_config
    _cached_config = None
