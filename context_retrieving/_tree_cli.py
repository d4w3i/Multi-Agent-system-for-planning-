"""
=============================================================================
_TREE_CLI.PY - Interactive CLI Entry Point for generate_tree
=============================================================================

This module contains the Colors class and the interactive main() function
that were extracted from generate_tree.py.

It is the CLI entry point when generate_tree.py is run directly:

    python -m context_retrieving.generate_tree

or from the project root:

    python context_retrieving/generate_tree.py

The library class TreeGenerator and the format_size helper remain in
generate_tree.py so that programmatic imports are unaffected.

=============================================================================
"""

import sys
import time
from pathlib import Path

from .generate_tree import TreeGenerator, format_size


# =============================================================================
# Colors Class - ANSI Codes for Colored Output

class Colors:
    """
    ANSI escape codes for coloring terminal output.

    """

    CYAN = '\033[96m'      # Bright cyan - titles and headers
    GREEN = '\033[92m'     # Bright green - success and confirmations
    RED = '\033[91m'       # Bright red - errors
    YELLOW = '\033[93m'    # Bright yellow - warnings and prompts
    BLUE = '\033[94m'      # Bright blue - information

    BOLD = '\033[1m'       # Bold - emphasis

    RESET = '\033[0m'      # Reset - ESSENTIAL to return to normal


# =============================================================================
# main Function - Interactive Entry Point

def main():
    """
    Script entry point with interactive interface.

    This function:
    1. Shows a decorative header
    2. Asks for the directory path
    3. Asks for maximum depth
    4. Asks whether to show hidden files
    5. Generates the tree
    6. Shows a preview (first 20 lines)
    7. Shows statistics
    8. Asks whether to save to file

    The interface uses ANSI colors for better readability.

    ERROR HANDLING:
    - Non-existent path: error message and exit
    - Path is not a directory: error message and exit
    - Ctrl+C: terminates gracefully
    - Other errors: shows message and exit

    OUTPUT FILE:
    If the user chooses to save, creates 'tree_output.txt' with:
    - The complete tree
    - A statistics section at the end
    """

    try:
        # ---------------------------------------------------------------------
        # Decorative header

        print()
        print(f"{Colors.CYAN}{Colors.BOLD}╔════════════════════════════════════════════════╗{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}║     Directory Tree Generator - ASCII Art       ║{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}╚════════════════════════════════════════════════╝{Colors.RESET}")
        print()

        # ---------------------------------------------------------------------
        # Input: directory path
        path_input = input(f"{Colors.YELLOW}Directory path (press ENTER for current directory): {Colors.RESET}").strip()

        # Default: current directory
        root_path = path_input if path_input else '.'

        # Check existence
        if not Path(root_path).exists():
            print(f"{Colors.RED}Error: Path '{root_path}' does not exist{Colors.RESET}")
            sys.exit(1)

        # Check that it's a directory
        if not Path(root_path).is_dir():
            print(f"{Colors.RED}Error: '{root_path}' is not a directory{Colors.RESET}")
            sys.exit(1)

        # ---------------------------------------------------------------------
        # Input: maximum depth
        depth_input = input(f"{Colors.YELLOW}Maximum depth (press ENTER for unlimited): {Colors.RESET}").strip()

        max_depth = None
        if depth_input:
            try:
                max_depth = int(depth_input)
                if max_depth < 1:
                    print(f"{Colors.YELLOW}Warning: using minimum depth 1{Colors.RESET}")
                    max_depth = 1
            except ValueError:
                print(f"{Colors.YELLOW}Invalid value, using unlimited depth{Colors.RESET}")

        # ---------------------------------------------------------------------
        # Input: hidden files
        hidden_input = input(f"{Colors.YELLOW}Show hidden files? (y/N): {Colors.RESET}").strip().lower()
        show_hidden = hidden_input in ['s', 'si', 'y', 'yes']

        # ---------------------------------------------------------------------
        # Tree generation
        print()
        print(f"{Colors.BLUE}Generating tree...{Colors.RESET}")

        start_time = time.time()

        # Create the generator and generate the tree
        generator = TreeGenerator(
            root_path=root_path,
            max_depth=max_depth,
            show_hidden=show_hidden
        )
        tree_lines, stats = generator.generate()

        elapsed_time = time.time() - start_time

        # ---------------------------------------------------------------------
        # Preview (first 20 lines)
        print()
        print(f"{Colors.CYAN}{Colors.BOLD}Preview (first 20 lines):{Colors.RESET}")
        print(f"{Colors.CYAN}{'─' * 50}{Colors.RESET}")

        for line in tree_lines[:20]:
            print(line)

        # Indicate if there are more lines
        if len(tree_lines) > 20:
            print(f"{Colors.BLUE}... ({len(tree_lines) - 20} lines remaining){Colors.RESET}")

        print(f"{Colors.CYAN}{'─' * 50}{Colors.RESET}")
        print()

        # ---------------------------------------------------------------------
        # Statistics
        print(f"{Colors.BLUE}{Colors.BOLD}Statistics:{Colors.RESET}")
        print(f"{Colors.BLUE}  Directories: {Colors.RESET}{stats['directories']}")
        print(f"{Colors.BLUE}  Files: {Colors.RESET}{stats['files']}")
        print(f"{Colors.BLUE}  Total size: {Colors.RESET}{format_size(stats['total_size'])}")

        if stats['skipped'] > 0:
            print(f"{Colors.YELLOW}  Skipped elements (permissions): {Colors.RESET}{stats['skipped']}")

        print(f"{Colors.BLUE}  Execution time: {Colors.RESET}{elapsed_time:.2f}s")
        print(f"{Colors.BLUE}  Total lines: {Colors.RESET}{len(tree_lines)}")
        print()

        # ---------------------------------------------------------------------
        # Save to file
        save_input = input(f"{Colors.YELLOW}Save to 'tree_output.txt'? (Y/n): {Colors.RESET}").strip().lower()

        if save_input not in ['n', 'no']:
            output_file = Path('tree_output.txt')

            # Write the tree and statistics
            with open(output_file, 'w', encoding='utf-8') as f:
                # Tree
                f.write('\n'.join(tree_lines))
                f.write('\n\n')

                # Separator
                f.write('=' * 50 + '\n')
                f.write('STATISTICS\n')
                f.write('=' * 50 + '\n')

                # Statistics
                f.write(f"Directories: {stats['directories']}\n")
                f.write(f"Files: {stats['files']}\n")
                f.write(f"Total size: {format_size(stats['total_size'])}\n")

                if stats['skipped'] > 0:
                    f.write(f"Skipped elements: {stats['skipped']}\n")

                f.write(f"Generation time: {elapsed_time:.2f}s\n")

            print()
            print(f"{Colors.GREEN}{Colors.BOLD}File saved successfully!{Colors.RESET}")
            print(f"{Colors.GREEN}Path: {Colors.RESET}{output_file.resolve()}")

        else:
            print()
            print(f"{Colors.YELLOW}Save cancelled{Colors.RESET}")

    # -------------------------------------------------------------------------

    except Exception as e:
        # Generic error
        print(f"\n{Colors.RED}{Colors.BOLD}Error: {str(e)}{Colors.RESET}")
        sys.exit(1)
