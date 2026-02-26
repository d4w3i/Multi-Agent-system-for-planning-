"""
=============================================================================
CALL_GRAPH_BUILDER.PY - Call Graph Builder for Python Code
=============================================================================

This module analyzes Python repositories to build a complete "call graph",
i.e., a graph showing which functions call which other functions.

WHAT IS A CALL GRAPH:
A call graph is a representation of calling relationships between functions.
If function A() calls function B(), there is an edge A → B in the graph.

    main() ──────► process_data() ──────► validate()
       │                  │
       │                  └──────────────► transform()
       │
       └──────────────────────────────────► cleanup()

TECHNOLOGY USED - TREE-SITTER:
Tree-sitter is an incremental parser that builds an AST (Abstract Syntax Tree)
of source code. Unlike Python's ast.parse():
- It's faster for large files
- It can parse partial or syntactically incorrect code
- It supports many languages with the same API

ANALYSIS PIPELINE (4 passes):
1. PASS 0 - Imports: Extracts all imports to resolve names
2. PASS 1 - Functions: Extracts all function/method definitions
3. PASS 2 - Calls: Extracts calls (now all names are known)
4. PASS 3 - Finalization: Marks leaf functions and entry points

OUTPUT STRUCTURE:
For each function, the following information is collected:
- file: source file path
- line: line number of the definition
- calls: list of called functions
- called_by: list of functions that call this one
- code: complete source code of the function
- is_leaf: True if it doesn't call other custom functions
- is_entry_point: True if not called by anyone
- class_name: class name (if it's a method)
- is_method: True if it's a class method
- full_name: fully qualified name (e.g., "module.Class.method")

USAGE:
    builder = CallGraphBuilder(verbose=True)
    call_graph = builder.analyze_repository("/path/to/repo")
    builder.to_json("call_graph.json")

REQUIREMENTS:
    - tree-sitter
    - tree-sitter-python

=============================================================================
"""
import json
import logging
from collections import defaultdict
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from ._ast_visitors import _ASTVisitorMixin

logger = logging.getLogger(__name__)


# =============================================================================
# CLASS CallGraphBuilder - The Call Graph Builder

class CallGraphBuilder(_ASTVisitorMixin):
    """
    Analyzes Python code and builds a graph of function calls.

    INTERNAL ARCHITECTURE:

    The builder maintains several data structures:

    1. call_graph (defaultdict): The main graph
       Key: fully qualified function name (e.g., "module.Class.method")
       Value: dictionary with function metadata

    2. all_functions (set): Set of all function names found
       Used to quickly verify if a function exists

    3. all_classes (set): Set of all class names found
       Used to resolve constructor calls (ClassName() → __init__)

    4. import_map (dict): Import map for each file
       Structure: {filepath: {local_name: full_name}}
       E.g.: {"main.py": {"pd": "pandas", "np": "numpy"}}

    5. repo_root (Path): Repository root
       Used to calculate relative paths in function names

    NAME RESOLUTION ALGORITHM:

    When we find a call like "process()", we need to understand WHICH
    function "process" is being called. The algorithm tries in order:

    1. Check import_map of the current file
    2. If we're in a class, try ClassName.process
    3. Try as local function: current_module.process
    4. Search globally among all functions

    Attributes:
        parser: The Tree-sitter parser configured for Python
        call_graph: The call graph (defaultdict)
        all_functions: Set of all function names
        all_classes: Set of all class names
        import_map: Import map per file
        repo_root: Repository root path
        verbose: If True, prints debug information
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the call graph builder.

        Configures the Tree-sitter parser with Python grammar and
        initializes all necessary data structures.

        Args:
            verbose (bool): If True, prints details during analysis.
                           Useful for debugging or seeing progress.

        Example:
            # Silent builder (default)
            builder = CallGraphBuilder()

            # Verbose builder for debugging
            builder = CallGraphBuilder(verbose=True)
        """

        # Tree-sitter Parser Configuration
        PY_LANGUAGE = Language(tspython.language())
        self.parser = Parser(PY_LANGUAGE)

        # Call Graph Initialization (Main Data Structure)
        self.call_graph = defaultdict(lambda: {
            'file': '',                 # Source file path
            'line': 0,                  # Line number (1-based)
            'calls': [],                # List of functions called by this one
            'called_by': [],            # List of functions that call this one
            'code': '',                 # Complete source code of the function
            'is_leaf': False,           # True if doesn't call other custom functions
            'is_entry_point': False,    # True if not called by anyone
            'class_name': None,         # Container class name (if method)
            'is_method': False,         # True if it's a class method
            'full_name': ''             # Fully-qualified name (module.class.function)
        })

        # Support Structures
        self.all_functions = set()
        self.all_classes = set()
        self.import_map = {}
        self.repo_root = None
        self.verbose = verbose
        self._suffix_index = {}  # {short_name: [full_names]}
        self._suffix_index_stale = True

        if self.verbose:
            logger.debug("CallGraphBuilder initialised (verbose=True)")

    # =========================================================================
    # METHOD parse_file - Parsing a Single File

    def parse_file(self, filepath: str, extract_calls: bool = True):
        """
        Parse a single Python file and extract functions (and optionally calls).

        This method is the core of parsing. It reads a Python file,
        parses it with Tree-sitter, and extracts the required information.

        PROCESS:
        1. Read the file as bytes
        2. Parse the content creating an AST
        3. Extract function definitions from the AST
        4. (Optional) Extract function calls

        NOTE ON extract_calls PARAMETER:
        In the 4-pass pipeline, the first pass extracts ONLY functions
        (extract_calls=False) because we cannot resolve the names of
        called functions until we know them all.

        Args:
            filepath (str): Path of the Python file to parse
            extract_calls (bool): If True, also extracts calls.
                                 Default True for backward compatibility.

        Example:
            # Complete parsing
            builder.parse_file("main.py")

            # Function extraction only (used in first pass)
            builder.parse_file("main.py", extract_calls=False)
        """

        # Read file as bytes
        # Tree-sitter requires bytes because it works at byte offset level,
        # this allows correct handling of files with different encodings
        try:
            with open(filepath, 'rb') as f:
                code_bytes = f.read()
        except (FileNotFoundError, IOError, PermissionError) as e:
            logger.warning("Could not read file %s: %s", filepath, e)
            return

        # Parse code and get AST (Abstract Syntax Tree)
        tree = self.parser.parse(code_bytes)
        # Extract function definitions from AST
        self._extract_functions(tree.root_node, code_bytes, filepath)
        # Extract calls only if requested
        if extract_calls:
            self._extract_calls(tree.root_node, code_bytes, filepath)

    # =========================================================================
    # HELPER METHOD _get_module_path - File Path → Module Path

    def _get_module_path(self, filepath: str) -> str:
        """
        Convert a file path to a Python module path.

        In Python, modules are identified with dot notation:
        - File: src/utils/helpers.py
        - Module: src.utils.helpers

        This method does the conversion, using repo_root as base.

        LOGIC:
        1. If there's no repo_root, use only the file name (without .py)
        2. Otherwise:
           a. Calculate the relative path from repo_root
           b. Remove the .py extension
           c. Replace / (or \\) with .

        Args:
            filepath (str): Python file path

        Returns:
            str: The corresponding module path

        Examples:
            # With repo_root = "/project"
            _get_module_path("/project/src/utils/helpers.py")
            # Returns: "src.utils.helpers"

            # Without repo_root
            _get_module_path("/any/path/helpers.py")
            # Returns: "helpers"
        """

        # Case without repo_root: use only the file name
        if not self.repo_root:
            return Path(filepath).stem  # stem = name without extension

        try:
            # Calculate relative path from repo_root
            rel_path = Path(filepath).relative_to(self.repo_root)

            # Remove extension and convert separators to dots
            module = str(rel_path.with_suffix('')).replace('/', '.').replace('\\', '.')

            return module

        except ValueError:
            return Path(filepath).stem

    # =========================================================================
    # METHOD analyze_repository - Complete Repository Analysis

    def analyze_repository(self, repo_path: str):
        """
        Analyze all Python files in a repository.

        This is the main method that orchestrates the entire analysis.
        It uses a 4-pass pipeline to ensure all names are resolved correctly.

        4-PASS PIPELINE:

        PASS 0 - IMPORT EXTRACTION:
        For each file, extract import statements and build import_map.
        This is needed to resolve names like "pd.read_csv" → "pandas.read_csv"

        PASS 1 - FUNCTION EXTRACTION:
        For each file, extract all function definitions.
        Does NOT extract calls because names are not yet all known.

        PASS 2 - CALL EXTRACTION:
        For each file, extract function calls.
        Now all names are known, so we can resolve correctly.

        PASS 3 - FINALIZATION:
        Mark special functions:
        - Leaf functions: don't call other functions
        - Entry points: not called by anyone

        EXCLUSIONS:
        - .venv and venv directories (virtual environments)
        - Files that are not .py

        Args:
            repo_path (str): Path of the repository to analyze

        Returns:
            dict: The complete call graph as a dictionary

        Example:
            builder = CallGraphBuilder(verbose=True)
            graph = builder.analyze_repository("/path/to/my-project")

            # Access data
            print(graph['my_module.my_func']['calls'])
        """

        # Convert and save the root path
        repo = Path(repo_path).resolve()
        self.repo_root = repo

        # ---------------------------------------------------------------------
        # Collect Python files
        py_files = []

        # rglob recursively searches for all *.py files
        for py_file in repo.rglob('*.py'):
            # Exclude virtual environments and other non-source directories
            # by checking path components (not substrings) to avoid false positives
            # e.g., a module named "conventioner" won't be excluded
            _excluded_dirs = {'.venv', 'venv', 'node_modules', 'site-packages', '.tox', '__pycache__'}
            if not _excluded_dirs.intersection(py_file.relative_to(repo).parts):
                py_files.append(py_file)

        logger.info("Found %d Python files", len(py_files))

        # ---------------------------------------------------------------------
        # Read all files once and cache parsed trees
        file_cache = {}  # {filepath_str: (code_bytes, tree)}
        for py_file in py_files:
            try:
                with open(py_file, 'rb') as f:
                    code_bytes = f.read()
                tree = self.parser.parse(code_bytes)
                file_cache[str(py_file)] = (code_bytes, tree)
            except (FileNotFoundError, IOError, PermissionError) as e:
                logger.warning("Could not read file %s: %s", py_file, e)

        # ---------------------------------------------------------------------
        # PASS 0: Import Extraction
        logger.info("Pass 0: Extracting imports...")

        for py_file_str, (code_bytes, tree) in file_cache.items():
            try:
                self.import_map[py_file_str] = self._extract_imports(
                    tree.root_node,
                    code_bytes,
                    py_file_str
                )
            except Exception as e:
                logger.error("Error extracting imports from %s: %s", py_file_str, e)

        # ---------------------------------------------------------------------
        # PASS 1: Function Extraction (WITHOUT calls!)
        logger.info("Pass 1: Extracting functions...")

        for py_file_str, (code_bytes, tree) in file_cache.items():
            try:
                self._extract_functions(tree.root_node, code_bytes, py_file_str)
            except Exception as e:
                logger.error("Error extracting functions from %s: %s", py_file_str, e)

        # ---------------------------------------------------------------------
        # PASS 2: Call Extraction
        logger.info("Pass 2: Extracting calls...")

        for py_file_str, (code_bytes, tree) in file_cache.items():
            try:
                self._extract_calls(tree.root_node, code_bytes, py_file_str)
            except Exception as e:
                logger.error("Error extracting calls from %s: %s", py_file_str, e)

        # ---------------------------------------------------------------------
        # PASS 3: Finalization
        logger.info("Finalizing analysis...")

        self._mark_special_nodes()

        # Return the graph as a normal dictionary
        return dict(self.call_graph)

    # =========================================================================
    # METHOD _mark_special_nodes - Special Node Identification

    def _mark_special_nodes(self):
        """
        Identify leaf functions and entry points in the call graph.

        DEFINITIONS:

        LEAF FUNCTION:
        A function that doesn't call any other custom function.
        These are the "leaves" of the call tree.
        E.g.: A function that only does mathematical calculations

        ENTRY POINT:
        A function not called by any other function.
        These are possible execution starting points.
        E.g.: main(), Flask route handlers, test functions

        Note:
            Modifies self.call_graph in place
        """

        for func_name, data in self.call_graph.items():
            # A function is "leaf" if it doesn't call any other function
            data['is_leaf'] = len(data['calls']) == 0

            # A function is "entry point" if not called by anyone
            data['is_entry_point'] = len(data['called_by']) == 0

    # =========================================================================
    # METHOD to_json - Export to JSON Format

    def to_json(self, output_file: str):
        """
        Save the call graph in JSON format.

        The generated JSON has this structure:

        {
            "functions": {
                "module.function": {
                    "file": "/path/to/file.py",
                    "line": 42,
                    "calls": ["module.other_function"],
                    "called_by": [],
                    ...
                },
                ...
            },
            "edges": [
                {"from": "module.function", "to": "module.other_function"},
                ...
            ],
            "stats": {
                "total_functions": 150,
                "entry_points": 10,
                "leaf_functions": 45
            }
        }

        Args:
            output_file (str): Path of the JSON file to create

        Returns:
            dict: The JSON output as a Python dictionary

        Example:
            builder.to_json("call_graph.json")
        """

        # Build the edge list
        edges = []
        for func, data in self.call_graph.items():
            for called in data['calls']:
                edges.append({'from': func, 'to': called})

        # Build the complete output
        output = {
            'functions': dict(self.call_graph),
            'edges': edges,
            'stats': {
                'total_functions': len(self.call_graph),
                'entry_points': sum(1 for d in self.call_graph.values() if d['is_entry_point']),
                'leaf_functions': sum(1 for d in self.call_graph.values() if d['is_leaf'])
            }
        }

        # Write to file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2)
        except (OSError, IOError) as e:
            logger.error("Error saving call graph to %s: %s", output_file, e)
            return output

        logger.info("Call graph saved to %s", output_file)

        return output
