#!/usr/bin/env python3
"""
=============================================================================
AI Planning Module - Evaluation System
=============================================================================

Interactive CLI for multi-agent code generation research.

USAGE:
    python main.py          # Launch interactive CLI

FEATURES:
    - Repository analysis (clone, analyze, generate call graphs)
    - Context file generation for PR datasets
    - Ground truth extraction from Pull Requests
    - AI-powered implementation plan generation
    - Dataset verification and cleanup
    - Test suite execution

For more information, see CODE_NAVIGATION.md

=============================================================================
"""

import sys

# Check Python version
if sys.version_info < (3, 10):
    print("Error: Python 3.10+ is required")
    sys.exit(1)

# Check for rich library
try:
    from rich.console import Console
except ImportError:
    print("Error: 'rich' library not installed")
    print("Install with: pip install rich")
    sys.exit(1)


def main():
    """Main entry point."""
    from cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
