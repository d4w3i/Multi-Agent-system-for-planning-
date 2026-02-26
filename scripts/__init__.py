"""
=============================================================================
SCRIPTS - Dataset Utility Scripts Package
=============================================================================

This package contains utility scripts for managing the PR4Code dataset
and related operations.

MODULES:
    extract_python_pr_paths.py  - Filter PRs with Python-only files (low-level)
    create_pr_subset.py         - Create reproducible subsets of the dataset
    generate_context_outputs.py - Batch-generate context files for PRs
    verify_pr_completeness.py   - Validate dataset completeness
    dataset_cleanup.py          - Clean up generated files (context, ground truth, predictions)

DEPENDENCY ORDER:
    extract_python_pr_paths  ←  create_pr_subset  ←  generate_context_outputs
    dataset_cleanup          (standalone)
    verify_pr_completeness   (standalone)

USAGE:
    # Run as module
    python -m scripts.dataset_cleanup --target ground_truth --delete

    # Import functions
    from scripts.dataset_cleanup import find_targets, delete_targets
    from scripts.create_pr_subset import load_pr_subset, load_pr_subset_data
    from scripts.extract_python_pr_paths import get_python_only_pr_paths
=============================================================================
"""

__version__ = "1.0.0"
