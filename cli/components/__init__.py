"""
=============================================================================
COMPONENTS - Reusable UI Components
=============================================================================

Provides reusable UI components for the CLI:
- prompts: Input prompts and selections
- displays: Output tables and panels
- progress: Progress tracking
"""

from .prompts import (
    Q_STYLE,
    prompt_directory,
    prompt_limit,
    prompt_model,
    prompt_confirm,
    prompt_confirm_destructive,
    prompt_choice,
    prompt_multi_choice,
    prompt_text,
    prompt_express_or_configure,
)

from .displays import (
    display_results,
    display_error,
    display_success,
    display_warning,
    display_table,
    display_stats_panel,
)

from .progress import create_progress, ProgressContext

__all__ = [
    # Prompts
    "Q_STYLE",
    "prompt_directory",
    "prompt_limit",
    "prompt_model",
    "prompt_confirm",
    "prompt_confirm_destructive",
    "prompt_choice",
    "prompt_multi_choice",
    "prompt_text",
    "prompt_express_or_configure",
    # Displays
    "display_results",
    "display_error",
    "display_success",
    "display_warning",
    "display_table",
    "display_stats_panel",
    # Progress
    "create_progress",
    "ProgressContext",
]
