"""
=============================================================================
FUNCTION_MATCHER.PY - Matching Functions with Modified Lines
=============================================================================

This module identifies WHICH FUNCTIONS were modified in a PR by analyzing
the source code with Tree-sitter and comparing with the modified lines
extracted from the diff.

PROBLEM SOLVED:

Git diff tells us WHICH LINES changed, but not WHICH FUNCTIONS.
To know if a modification impacts a function, we need to:

1. Parse the Python file and find all function definitions
2. Get the line range [start, end] of each function
3. Check if modified lines fall within these ranges
4. If there's overlap → the function was modified

VISUAL EXAMPLE:

    File parser.py:
    1   def helper():        ←┐
    2       return "ok"       │ Function helper (lines 1-2)
    3                        ←┘
    4   def parse():         ←┐
    5       x = 1             │
    6       y = helper()      │ Function parse (lines 4-7)
    7       return x + y     ←┘

    Diff says: lines 5-6 modified

    Result: parse() was modified (5-6 inside 4-7)
            helper() was NOT modified

COMPONENTS:

- SimpleFunctionExtractor: Extracts function definitions with Tree-sitter
- match_functions_to_changes(): Compares functions with modified lines

USAGE:

    from evaluation.function_matcher import match_functions_to_changes
    from evaluation.diff_parser import parse_unified_diff

    # Parse the diff
    diff_result = parse_unified_diff(patch, "parser.py")

    # Find modified functions
    functions = match_functions_to_changes(
        "modified_files/parser.py",
        diff_result
    )

    for func in functions:
        print(f"{func.full_name}: lines {func.lines_changed}")

=============================================================================
"""

import logging
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
from pathlib import Path
from typing import List, Dict, Optional
from .diff_parser import DiffResult
from .models import FunctionChange

logger = logging.getLogger('ground_truth_extractor')

# =============================================================================
# CLASS SimpleFunctionExtractor - Lightweight Function Extractor

class SimpleFunctionExtractor:
    """
    Lightweight extractor for function definitions using Tree-sitter.

    Unlike CallGraphBuilder (which builds the entire call graph), this class
    extracts ONLY function definitions with their line ranges. It's faster
    and sufficient for matching purposes.

    WHAT IT EXTRACTS FOR EACH FUNCTION:
    - function_name: Function name (e.g., "parse")
    - class_name: Class name if it's a method (e.g., "Parser")
    - full_name: Full qualified name (e.g., "Parser.parse")
    - start_line: First line of the function (1-based)
    - end_line: Last line of the function (1-based)
    - code: Function source code

    CLASS HANDLING:
    Tracks class context during recursion, so methods are correctly
    identified as "Class.method".

    Attributes:
        parser: Tree-sitter parser configured for Python

    Example:
        extractor = SimpleFunctionExtractor()
        functions = extractor.extract_functions("parser.py")

        for func in functions:
            print(f"{func['full_name']}: {func['start_line']}-{func['end_line']}")
    """

    def __init__(self):
        """
        Initialize the extractor with the Tree-sitter parser for Python.

        Configures Tree-sitter with the Python grammar from the
        tree_sitter_python library.
        """

        # Load Python grammar
        PY_LANGUAGE = Language(tspython.language())

        # Create parser and assign grammar
        self.parser = Parser(PY_LANGUAGE)

    def extract_functions(self, file_path: str) -> List[Dict]:
        """
        Extract all function definitions from a Python file.

        Reads the file, parses it with Tree-sitter, and traverses the AST
        looking for 'function_definition' nodes.

        ERROR HANDLING:
        If the file doesn't exist or isn't readable, returns an empty list
        with a warning (doesn't raise an exception).

        Args:
            file_path (str): Path to the Python file to analyze

        Returns:
            List[Dict]: List of dictionaries, one for each function found.
                       Each dictionary contains:
                       - 'function_name': str
                       - 'class_name': Optional[str]
                       - 'full_name': str
                       - 'start_line': int (1-based)
                       - 'end_line': int (1-based)
                       - 'code': str

        Example:
            extractor = SimpleFunctionExtractor()
            functions = extractor.extract_functions("src/parser.py")

            >> Example output:
            >> [
            >>   {'function_name': '__init__', 'class_name': 'Parser',
            >>    'full_name': 'Parser.__init__', 'start_line': 10, ...},
            >>   {'function_name': 'parse', 'class_name': 'Parser',
            >>    'full_name': 'Parser.parse', 'start_line': 15, ...}
            >> ]
        """

        # ---------------------------------------------------------------------
        # File reading
        try:
            # Tree-sitter works with bytes, not strings
            with open(file_path, 'rb') as f:
                code_bytes = f.read()
        except (FileNotFoundError, IOError) as e:
            # Don't raise exception - return empty list
            # This allows the process to continue with other files
            logger.warning(f"Could not read file {file_path}: {e}")
            return []

        # ---------------------------------------------------------------------
        # Parsing with Tree-sitter
        # parse() returns a Tree, from which we get the root node
        tree = self.parser.parse(code_bytes)

        # List to collect found functions
        functions = []

        # ---------------------------------------------------------------------
        # Recursive extraction
        # Start from AST root without class context
        self._extract_functions_recursive(
            tree.root_node,
            code_bytes,
            file_path,
            functions,
            current_class=None
        )

        return functions

    # NOTE: Similar to context_retrieving/call_graph_builder.py:_extract_functions,
    # but builds a flat list for diff matching. Not merged intentionally.
    def _extract_functions_recursive(
        self,
        node,
        code_bytes: bytes,
        filepath: str,
        functions: List[Dict],
        current_class: Optional[str] = None
    ):
        """
        Recursively traverse the AST extracting function definitions.

        This method implements a depth-first traversal of the AST:
        1. If it finds a class_definition, extracts the name and recurses into children
           passing the class name as context
        2. If it finds a function_definition, extracts metadata and adds it
        3. Otherwise, recurses on all children

        AST STRUCTURE (simplified):

            module
            ├── class_definition (name="Parser")
            │   └── block
            │       ├── function_definition (name="__init__")
            │       └── function_definition (name="parse")
            └── function_definition (name="helper")

        Args:
            node: Current Tree-sitter AST node
            code_bytes (bytes): File content as bytes
            filepath (str): File path (for logging)
            functions (List[Dict]): List where found functions are added
            current_class (Optional[str]): Current class name (if inside a class)
        """

        # ---------------------------------------------------------------------
        # Case 1: Class definition
        if node.type == 'class_definition':
            # Extract class name
            class_name_node = node.child_by_field_name('name')

            if class_name_node:
                # Get the name text
                class_name = self._get_node_text(class_name_node, code_bytes)

                # Recurse on class children, passing the name
                # This allows methods to know which class they belong to
                for child in node.children:
                    self._extract_functions_recursive(
                        child, code_bytes, filepath, functions,
                        current_class=class_name
                    )

                return

        # ---------------------------------------------------------------------
        # Case 2: Function definition
        if node.type == 'function_definition':
            # Extract function name
            func_name_node = node.child_by_field_name('name')

            if func_name_node:
                func_name = self._get_node_text(func_name_node, code_bytes)

                # Build full qualified name
                if current_class:
                    # It's a method: Class.method
                    full_name = f"{current_class}.{func_name}"
                else:
                    # Standalone function
                    full_name = func_name

                # Create dictionary with all metadata
                functions.append({
                    'function_name': func_name,
                    'class_name': current_class,
                    'full_name': full_name,
                    # Tree-sitter uses 0-based indices, convert to 1-based
                    'start_line': node.start_point[0] + 1,
                    'end_line': node.end_point[0] + 1,
                    # Full function source code
                    'code': self._get_node_text(node, code_bytes)
                })

        # ---------------------------------------------------------------------
        # Recurse on children (if not inside a class)
        if node.type != 'class_definition':
            for child in node.children:
                self._extract_functions_recursive(
                    child, code_bytes, filepath, functions, current_class
                )

    def _get_node_text(self, node, code_bytes: bytes) -> str:
        """Extract text from a Tree-sitter AST node. See shared.tree_sitter_utils."""
        from shared.tree_sitter_utils import get_node_text
        return get_node_text(node, code_bytes)

# Module-level shared extractor to avoid recreating Tree-sitter parser per call
_shared_extractor = SimpleFunctionExtractor()

# =============================================================================
# FUNCTION match_functions_to_changes - Main Matching Function

def match_functions_to_changes(
    modified_file_path: str,
    diff_result: DiffResult
) -> List[FunctionChange]:
    """
    Find which functions were modified based on changed lines.

    This is the main function of the module. It combines:
    1. Function extraction from the modified file
    2. Modified lines from the diff
    3. Matching logic (range overlap)

    ALGORITHM:

    For each extracted function:
    1. Create a set of function lines: {start, start+1, ..., end}
    2. Create a set of modified lines from the diff
    3. Calculate the intersection
    4. If the intersection is not empty → the function was modified

    NOTE ON FILE PATH:
    We use the file from modified_files/ folder because:
    - The diff lines (added_lines) refer to the NEW file
    - Function line numbers must match with diff line numbers

    Args:
        modified_file_path (str): Path to the modified file
                                 (from modified_files/ folder)
        diff_result (DiffResult): Result from diff parsing

    Returns:
        List[FunctionChange]: List of functions that have modifications.
                             Each FunctionChange includes:
                             - function_name, class_name, full_name
                             - start_line, end_line
                             - lines_changed (specific modified lines)

    Example:
        from evaluation.diff_parser import parse_unified_diff

        Parse the diff
        diff = parse_unified_diff(patch, "parser.py")

        Find modified functions
        functions = match_functions_to_changes(
            "modified_files/parser.py",
            diff
        )

        for f in functions:
            print(f"{f.full_name}: modified lines {f.lines_changed}")
            # Output: Parser.parse: modified lines [45, 47, 52]
    """

    # -------------------------------------------------------------------------
    # Step 1: Extract all functions from the file
    # Reuse a module-level extractor to avoid recreating the Tree-sitter parser each call
    functions = _shared_extractor.extract_functions(modified_file_path)

    # -------------------------------------------------------------------------
    # Step 2: Prepare the set of modified lines
    # modified_lines contains added/changed lines in the NEW file
    changed_lines_set = set(diff_result.modified_lines)

    # -------------------------------------------------------------------------
    # Step 3: Find functions with overlap
    matched_functions = []

    for func in functions:
        # Create the set of function lines
        func_lines = set(range(func['start_line'], func['end_line'] + 1))

        # Calculate the intersection
        lines_in_function = changed_lines_set.intersection(func_lines)

        # If there's overlap, the function was modified
        if lines_in_function:
            # Create the FunctionChange object
            matched_functions.append(
                FunctionChange(
                    function_name=func['function_name'],
                    class_name=func['class_name'],
                    full_name=func['full_name'],
                    start_line=func['start_line'],
                    end_line=func['end_line'],
                    lines_changed=sorted(lines_in_function)  # sorted() for ordered and deterministic output
                )
            )

    return matched_functions
