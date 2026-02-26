"""
The `evaluation` package extracts ground truth from GitHub Pull Requests to
create datasets for evaluating AI-generated implementation plans. It identifies
which files and functions were modified, then optionally generates implementation
step plans via LLM.

Usage::

    from evaluation import GroundTruth, FileChange, Step
    from evaluation.models import GroundTruth

Run as module::

    python -m evaluation.ground_truth_extractor PR4Code/dataset/ --limit 10
"""

# =============================================================================
# PACKAGE VERSION
# =============================================================================

# __version__ is a Python convention for tracking package version
# Can be read programmatically: from evaluation import __version__
# Follows Semantic Versioning: MAJOR.MINOR.PATCH
#   - MAJOR: incompatible changes
#   - MINOR: backwards-compatible new features
#   - PATCH: backwards-compatible bug fixes
__version__ = "1.0.0"


# =============================================================================
# IMPORT AND RE-EXPORT OF PUBLIC MODELS
# =============================================================================

# Import Pydantic models from the models.py module
# These are the main data structures used throughout the package
#
# The syntax "from .models import ..." uses relative import:
# - The dot (.) means "same package"
# - So .models = evaluation.models

from .models import (
    # Represents a single modified function
    FunctionChange,

    # Represents a modified file (contains FunctionChange)
    FileChange,

    # Single step of the implementation plan
    Step,

    # Complete plan (list of Steps + summary)
    StepPlan,

    # Extraction metadata (timestamp, version, success/error)
    ExtractionMetadata,

    # Complete ground truth object for a PR
    GroundTruth
)


# =============================================================================
# __all__ - EXPORT CONTROL
# =============================================================================

# __all__ defines what is exported when using:
#     from evaluation import *
#
# Without __all__, Python would export everything not starting with _
# With __all__, it exports ONLY what is listed
#
# BEST PRACTICE: Explicitly list only the public APIs
# This makes clear to package users what is "official" and supported

__all__ = [
    "FunctionChange",      # Model for modified functions
    "FileChange",          # Model for modified files
    "Step",                # Model for single step
    "StepPlan",            # Model for complete plan
    "ExtractionMetadata",  # Extraction metadata
    "GroundTruth"          # Main model (contains everything)
]
