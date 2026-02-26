"""
=============================================================================
GENERATE_TREE.PY - ASCII Directory Tree Generator
=============================================================================

This script generates an ASCII text representation of a directory structure,
similar to the Unix 'tree' command but with additional features like
.gitignore filters and statistics.

EXAMPLE OUTPUT:

    my_project/
    ├── src/
    │   ├── main.py
    │   ├── utils/
    │   │   ├── helpers.py
    │   │   └── validators.py
    │   └── models/
    │       └── user.py
    ├── tests/
    │   └── test_main.py
    ├── README.md
    └── requirements.txt

FEATURES:
- ASCII tree generation with box-drawing characters (├── └── │)
- Automatic .gitignore pattern support
- Default exclusion patterns (node_modules, __pycache__, .venv, etc.)
- Scan depth limitation
- Option to show/hide hidden files
- Statistics: file count, directory count, total size
- Save to file with statistics

INTERACTIVE USAGE:
    python generate_tree.py

    The script will ask for:
    1. Directory path (ENTER = current directory)
    2. Maximum depth (ENTER = unlimited)
    3. Whether to show hidden files (default: No)
    4. Whether to save to file (default: Yes)

PROGRAMMATIC USAGE:
    from generate_tree import TreeGenerator

    generator = TreeGenerator(
        root_path="/path/to/project",
        max_depth=3,
        show_hidden=False
    )
    lines, stats = generator.generate()

    # lines is a list of strings (one per line)
    # stats contains: files, directories, total_size, skipped

ASCII CHARACTERS USED:
    ├── : BRANCH (intermediate branch)
    └── : LAST (last element)
    │   : VERTICAL (vertical continuation)
        : SPACE (4 spaces for indentation)

=============================================================================
"""

from pathlib import Path

# =============================================================================
# TreeGenerator Class - The ASCII Tree Generator

class TreeGenerator:
    """
    Generates an ASCII representation of a directory structure.

    ASCII CHARACTERS USED:

    The tree uses box-drawing characters to create visual lines:

        project/              ← Root directory
        ├── src/              ← BRANCH + name + "/" (it's a directory)
        │   ├── main.py       ← VERTICAL + BRANCH + name (intermediate file)
        │   └── utils.py      ← VERTICAL + LAST + name (last file)
        └── README.md         ← LAST + name (last element)

    PREFIX LOGIC:

    Each level adds a prefix:
    - If NOT the last element: "│   " (VERTICAL + spaces)
    - If IS the last element: "    " (spaces only)

    This creates the visual effect of vertical continuity.

    EXCLUSION PATTERNS:

    By default, the following are ignored:
    - .git, __pycache__, node_modules (large and not useful)
    - .venv, venv (virtual environments)
    - .DS_Store (macOS file)
    - .idea, .vscode (IDE configurations)
    - *.pyc, *.egg-info (compiled files)
    - dist, build (build directories)

    Additionally, patterns from .gitignore are read if present.

    ALGORITHM:

    1. Reads the directory with iterdir()
    2. Sorts: directories first, then files, alphabetically
    3. Filters elements to ignore
    4. For each element:
       a. Determines if it's the last (to choose ├── or └──)
       b. Builds the line with the correct prefix
       c. If it's a directory, recurses with new prefix
    5. Collects statistics during the scan

    Attributes:
        root_path (Path): Root directory to scan
        max_depth (int): Maximum depth (None = unlimited)
        show_hidden (bool): Whether to show hidden files (.files)
        ignore_patterns (set[str]): Patterns to ignore
        gitignore_patterns (set[str]): Patterns from .gitignore

        file_count (int): Counter for files found
        dir_count (int): Counter for directories found
        total_size (int): Total size in bytes
        skipped_count (int): Elements skipped (permission denied)
    """

    # -------------------------------------------------------------------------
    # ASCII characters for the tree (class constants)

    BRANCH = "├── "    # Intermediate branch (not the last element)
    LAST = "└── "      # Last element of the level
    VERTICAL = "│   "  # Vertical continuation from upper level
    SPACE = "    "     # Space (4 characters) for indentation without line

    # -------------------------------------------------------------------------
    # Default patterns to ignore (class constant)

    DEFAULT_IGNORE_PATTERNS = {
        '.git',           # Git repository (very large)
        '__pycache__',    # Python bytecode cache
        'node_modules',   # Node.js dependencies (huge)
        '.DS_Store',      # macOS metadata file
        '.venv',          # Python virtual environment
        'venv',           # Python virtual environment (alternative)
        '.idea',          # IntelliJ/PyCharm configuration
        '.vscode',        # VS Code configuration
        '*.pyc',          # Python compiled files
        '.pytest_cache',  # pytest cache
        '.coverage',      # Coverage report
        'dist',           # Distribution directory
        'build',          # Build directory
        '*.egg-info'      # Python package metadata
    }

    def __init__(self, root_path: str = '.', max_depth: int = None,
                 show_hidden: bool = False, custom_ignore: set[str] = None):
        """
        Initialize the tree generator.

        Args:
            root_path (str): Path of the directory to scan.
                            Default: '.' (current directory)

            max_depth (int, optional): Maximum scan depth.
                                      None = no limit.
                                      1 = first level only.
                                      2 = first and second level, etc.

            show_hidden (bool): If True, includes files/directories that
                               start with '.' (normally hidden).
                               Default: False.

            custom_ignore (set[str] | None): Additional patterns to ignore.
                                               These are added to the defaults.

        Example:
            # Basic scan
            gen = TreeGenerator("/my/project")

            # With depth limit
            gen = TreeGenerator("/my/project", max_depth=3)

            # Show hidden files
            gen = TreeGenerator("/my/project", show_hidden=True)

            # Ignore custom patterns
            gen = TreeGenerator("/my/project", custom_ignore={"*.log", "temp/"})
        """

        # Convert and resolve the path to absolute Path
        self.root_path = Path(root_path).resolve()

        # Save the maximum depth
        self.max_depth = max_depth

        # Flag for hidden files
        self.show_hidden = show_hidden

        # Initialize ignore patterns with defaults
        self.ignore_patterns = self.DEFAULT_IGNORE_PATTERNS.copy()

        # Add any custom patterns
        if custom_ignore:
            self.ignore_patterns.update(custom_ignore)

        # ---------------------------------------------------------------------
        # Statistics initialization
        # These counters are updated during generation

        self.file_count = 0      # Number of files found
        self.dir_count = 0       # Number of directories found
        self.total_size = 0      # Total size in bytes
        self.skipped_count = 0   # Inaccessible elements

        # ---------------------------------------------------------------------
        # Load .gitignore patterns
        self.gitignore_patterns = self._load_gitignore()

    def _load_gitignore(self) -> set[str]:
        """
        Load patterns from .gitignore file if present.

        The .gitignore file contains patterns of files/directories that Git
        should ignore. This method loads them for use in tree generation
        as well.

        .gitignore FORMAT:
        - One pattern per line
        - Lines starting with # are comments
        - Empty lines are ignored
        - Patterns ending with / indicate directories

        LIMITATIONS:
        This implementation only handles simple patterns.
        Advanced patterns like negation (!) or ** are not supported.

        Returns:
            set[str]: Set of patterns found

        Note:
            If the file doesn't exist or isn't readable, returns empty set.
        """

        gitignore_path = self.root_path / '.gitignore'
        patterns = set()

        # Check if file exists
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r') as f:
                    for line in f:
                        line = line.strip()

                        # Ignore comments and empty lines
                        if line and not line.startswith('#'):
                            patterns.add(line)

            except Exception:
                # .gitignore may be unreadable (permissions, encoding); safe to skip
                pass

        return patterns

    def _should_ignore(self, path: Path) -> bool:
        """
        Check if a path should be ignored.

        This function checks:
        1. If the file is hidden (starts with .)
        2. If it matches default patterns
        3. If it matches .gitignore patterns

        SUPPORTED PATTERN TYPES:

        1. Exact name: "node_modules" matches only "node_modules"

        2. Trailing wildcard: "*.pyc" matches "file.pyc", "test.pyc", etc.

        3. Leading wildcard: "*-info" matches "package-info", etc.

        4. Directory pattern (gitignore): "cache/" matches only directory "cache"

        Args:
            path (Path): The path to check

        Returns:
            bool: True if the path should be ignored, False otherwise
        """

        name = path.name

        # ---------------------------------------------------------------------
        # Hidden files check
        if not self.show_hidden and name.startswith('.'):
            return True

        # ---------------------------------------------------------------------
        # Default patterns check
        for pattern in self.ignore_patterns:

            # Trailing wildcard pattern: *.ext
            if pattern.endswith('*'):
                if name.endswith(pattern[1:]):
                    return True

            # Leading wildcard pattern: *suffix
            elif pattern.startswith('*'):
                if name.endswith(pattern[1:]):
                    return True

            # Exact match
            elif name == pattern:
                return True

        # ---------------------------------------------------------------------
        # .gitignore patterns check
        for pattern in self.gitignore_patterns:

            # Directory pattern (ends with /)
            if pattern.endswith('/'):
                if path.is_dir() and name == pattern[:-1]:
                    return True

            # Wildcard pattern
            elif pattern.endswith('*'):
                if name.startswith(pattern[:-1]):
                    return True

            # Exact match
            elif name == pattern:
                return True

        # No pattern matched - don't ignore
        return False

    def _generate_tree(self, directory: Path, prefix: str = "",
                       depth: int = 0) -> list[str]:
        """
        Recursively generate the ASCII tree for a directory.

        This is the main method that builds the output.
        It is called recursively for each subdirectory.

        ALGORITHM:

        1. Check if we've reached the maximum depth
        2. List the directory contents
        3. Sort: directories first, then files, alphabetically
        4. Filter elements to ignore
        5. For each element:
           a. Determine if it's the last (for ├── vs └──)
           b. Build the prefix (prefix + connector)
           c. Add the line to the list
           d. Update statistics
           e. If it's a directory, recurse

        PREFIX CONSTRUCTION:

        The prefix is built cumulatively:
        - Level 0: "" (nothing)
        - Level 1: "│   " or "    " (depends if there are more elements after)
        - Level 2: "│   │   " or "│       " etc.

        Args:
            directory (Path): Directory to scan
            prefix (str): Prefix accumulated from upper levels
            depth (int): Current depth (0 = root)

        Returns:
            list[str]: List of tree lines

        Note:
            Also updates statistics: file_count, dir_count,
            total_size, skipped_count
        """

        lines = []

        # ---------------------------------------------------------------------
        # Maximum depth check
        if self.max_depth is not None and depth >= self.max_depth:
            return lines

        try:
            # -----------------------------------------------------------------
            # Read and sort directory contents
            entries = sorted(directory.iterdir(),
                           key=lambda x: (not x.is_dir(), x.name.lower()))

            # -----------------------------------------------------------------
            # Filter elements to ignore
            entries = [e for e in entries if not self._should_ignore(e)]

            # -----------------------------------------------------------------
            # Generate lines for each element
            for i, entry in enumerate(entries):

                # Determine if this is the last element of the level
                is_last = (i == len(entries) - 1)

                # Choose the appropriate connector
                connector = self.LAST if is_last else self.BRANCH

                # Determine the prefix extension for children
                extension = self.SPACE if is_last else self.VERTICAL

                # ---------------------------------------------------------
                # Directory handling
                if entry.is_dir():
                    lines.append(f"{prefix}{connector}{entry.name}/")

                    # Increment directory counter
                    self.dir_count += 1

                    # Recurse for directory contents
                    # The new prefix is: current prefix + extension
                    subdir_lines = self._generate_tree(
                        entry,
                        prefix + extension,
                        depth + 1
                    )
                    lines.extend(subdir_lines)

                # ---------------------------------------------------------
                # File handling
                else:
                    # Add the line without "/" (it's a file)
                    lines.append(f"{prefix}{connector}{entry.name}")

                    self.file_count += 1

                    # Calculate file size
                    try:
                        self.total_size += entry.stat().st_size
                    except Exception:
                        # stat() can fail on broken symlinks or permission issues; size is optional
                        pass

        # -----------------------------------------------------------------
        # Access error handling
        except PermissionError:
            lines.append(f"{prefix}[Permission denied]")
            self.skipped_count += 1

        except Exception as e:
            lines.append(f"{prefix}[Error: {str(e)}]")
            self.skipped_count += 1

        return lines

    def generate(self) -> tuple[list[str], dict]:
        """
        Generate the complete directory tree.

        This is the public method to call to get the tree.
        Resets statistics and starts recursive generation.

        Returns:
            tuple[list[str], dict]: A tuple containing:

                1. list[str]: The tree lines, one string per line.
                   The first line is the root directory name.

                2. dict: Scan statistics with keys:
                   - 'files': number of files found
                   - 'directories': number of directories found
                   - 'total_size': total size in bytes
                   - 'skipped': elements skipped due to permission errors

        Example:
            generator = TreeGenerator("/my/project")
            lines, stats = generator.generate()

            # Print the tree
            for line in lines:
                print(line)

            # Show statistics
            print(f"Files: {stats['files']}")
            print(f"Directories: {stats['directories']}")
            print(f"Size: {stats['total_size']} bytes")
        """

        # Reset statistics (to allow multiple calls)
        self.file_count = 0
        self.dir_count = 0
        self.total_size = 0
        self.skipped_count = 0

        # The first line is the root directory name
        lines = [f"{self.root_path.name}/"]

        # Generate the tree recursively
        tree_lines = self._generate_tree(self.root_path)
        lines.extend(tree_lines)

        # Prepare the statistics dictionary
        stats = {
            'files': self.file_count,
            'directories': self.dir_count,
            'total_size': self.total_size,
            'skipped': self.skipped_count
        }

        return lines, stats


# =============================================================================
# format_size Function - Human-Readable Size Formatting

def format_size(size_bytes: int) -> str:
    """
    Format a size in bytes to human-readable format.

    Args:
        size_bytes (int): Size in bytes

    Returns:
        str: Formatted string with appropriate unit
    """

    # Iterate over units, dividing by 1024 at each step
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0

    # If we get here, we're in terabytes
    return f"{size_bytes:.1f} TB"

if __name__ == '__main__':
    from ._tree_cli import main
    main()
