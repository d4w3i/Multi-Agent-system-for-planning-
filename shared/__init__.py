"""
=============================================================================
SHARED - Common Utilities Package
=============================================================================

This package contains shared utilities used across the codebase.

MODULES:
    terminal.py - Terminal UI helpers (Spinner, Colors, print functions)

USAGE:
    from shared.terminal import Spinner, Colors, print_header

    with Spinner("Processing"):
        do_work()

    print_header("My Section")
=============================================================================
"""

from .tree_sitter_utils import get_node_text
from .terminal import (
    Spinner,
    Colors,
    print_header,
    print_step,
    print_success,
    print_error,
)

__all__ = [
    "get_node_text",
    "Spinner",
    "Colors",
    "print_header",
    "print_step",
    "print_success",
    "print_error",
]
