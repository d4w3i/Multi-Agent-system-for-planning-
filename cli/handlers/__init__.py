"""
=============================================================================
HANDLERS - Operation Handlers
=============================================================================

Provides handler functions for each menu operation.
"""

from .repository import handle_repository_analysis
from .context import handle_context_generation
from .extraction import handle_ground_truth_extraction
from .prediction import handle_ai_predictions
from .cleanup import handle_dataset_cleanup
from .verification import handle_dataset_verification
from .subset import handle_subset_creation, handle_python_filter
from .testing import handle_run_tests
from .settings import handle_settings, handle_help

__all__ = [
    "handle_repository_analysis",
    "handle_context_generation",
    "handle_ground_truth_extraction",
    "handle_ai_predictions",
    "handle_dataset_cleanup",
    "handle_dataset_verification",
    "handle_subset_creation",
    "handle_python_filter",
    "handle_run_tests",
    "handle_settings",
    "handle_help",
]
