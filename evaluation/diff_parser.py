"""
=============================================================================
DIFF_PARSER.PY - Parser for Git Unified Diff Format
=============================================================================

This module parses Git diffs in "unified diff" format and extracts
information about modified lines. It is used to understand WHICH lines
of a file were changed in a Pull Request.

WHAT IS THE UNIFIED DIFF FORMAT:

The unified diff format is the standard used by Git to show the
differences between two versions of a file. Example:

    @@ -10,8 +10,6 @@
     from pathlib import Path
     import typing as tp

    -#from dora.log import fatal
    -
     import logging
     from dataclasses import dataclass

ANATOMY OF A DIFF:

1. HUNK HEADER (@@ ... @@):
   @@ -10,8 +10,6 @@
   - -10,8 : OLD file, starting at line 10, 8 lines of context
   - +10,6 : NEW file, starting at line 10, 6 lines of context

2. CONTEXT LINES (leading space):
   " from pathlib import Path" - unchanged lines, for context

3. REMOVED LINES (leading -):
   "-#from dora.log import fatal" - line present in OLD file

4. ADDED LINES (leading +):
   "+import logging" - line present in NEW file

TERMINOLOGY:
- Hunk: A "block" of changes with its header
- Patch: The entire diff of a file (can contain multiple hunks)
- Old file: Previous version (before the PR)
- New file: New version (after the PR)

OUTPUT:
The parser produces a DiffResult with:
- added_lines: line numbers of added lines (in NEW file)
- deleted_lines: line numbers of removed lines (in OLD file)
- modified_lines: all changed lines (in NEW file)
- hunks: detailed list of hunks

USAGE:

    from evaluation.diff_parser import parse_unified_diff

    patch = '''@@ -10,5 +10,4 @@
     context line
    -removed line
    +added line
     another context'''

    result = parse_unified_diff(patch, "myfile.py")
    print(result.added_lines)     # [11]
    print(result.deleted_lines)   # [11]
    print(result.modified_lines)  # [11]

=============================================================================
"""

from dataclasses import dataclass
from typing import List, Tuple
import re

# =============================================================================
# DATACLASS DiffHunk - Represents a Single Hunk

@dataclass
class DiffHunk:
    """
    Represents a single "hunk" (block of changes) in a diff.

    A hunk is a contiguous section of changes in a file. A diff
    can contain multiple hunks if the changes are not contiguous.

    HUNK EXAMPLE:

        @@ -10,8 +10,6 @@            ← Header
         from pathlib import Path    ← Context
         import typing as tp         ← Context
                                     ← Context (empty line)
        -#from dora.log import fatal ← Removed
        -                            ← Removed (empty line)
         import logging              ← Context

    The header "@@ -10,8 +10,6 @@" means:
    - In OLD file: starts at line 10, shows 8 lines
    - In NEW file: starts at line 10, shows 6 lines
    - The difference (8-6=2) indicates that 2 lines were removed

    Attributes:
        old_start (int): Starting line in OLD file (1-based)
        old_count (int): Number of lines in OLD file for this hunk
        new_start (int): Starting line in NEW file (1-based)
        new_count (int): Number of lines in NEW file for this hunk
        lines (List[str]): Raw diff lines (including +/-/space prefixes)

    Example:
        DiffHunk(
            old_start=10,
            old_count=8,
            new_start=10,
            new_count=6,
            lines=[" from pathlib...", "-#from dora...", ...]
        )
    """

    # Starting line number in OLD file (before modification)
    old_start: int

    # How many lines of this hunk appear in OLD file
    old_count: int

    # Starting line number in NEW file (after modification)
    new_start: int

    # How many lines of this hunk appear in NEW file
    new_count: int

    # Raw diff lines with their prefixes:
    # - " " (space): context line (unchanged)
    # - "-": removed line
    # - "+": added line
    lines: List[str]

# =============================================================================
# DATACLASS DiffResult - Complete Parsing Result

@dataclass
class DiffResult:
    """
    Result of parsing a complete diff for a file.

    Contains all information extracted from the diff, organized
    to facilitate subsequent use (e.g., matching with functions).

    CONTENTS:
    - filename: which file was modified
    - added_lines: added lines (referring to NEW file)
    - deleted_lines: removed lines (referring to OLD file)
    - modified_lines: union of added_lines (for ease of use)
    - hunks: detailed list of hunks

    NOTE ON added_lines vs deleted_lines:
    Line numbers refer to DIFFERENT files:
    - added_lines → numbers in NEW file
    - deleted_lines → numbers in OLD file

    This is important because numbers may not correspond
    if there are changes that alter the line count.

    Attributes:
        filename (str): File name/path
        added_lines (List[int]): Added lines (numbers in NEW file)
        deleted_lines (List[int]): Removed lines (numbers in OLD file)
        modified_lines (List[int]): Modified lines in NEW file
        hunks (List[DiffHunk]): List of parsed hunks

    Example:
        DiffResult(
            filename="parser.py",
            added_lines=[15, 16, 17],
            deleted_lines=[15, 16],
            modified_lines=[15, 16, 17],
            hunks=[DiffHunk(...), DiffHunk(...)]
        )
    """

    # Name of the file this diff refers to
    filename: str

    # List of ADDED line numbers
    added_lines: List[int]

    # List of REMOVED line numbers
    deleted_lines: List[int]

    # List of "modified" lines in NEW file
    modified_lines: List[int]

    # Complete list of parsed hunks
    hunks: List[DiffHunk]

# =============================================================================
# FUNCTION parse_hunk_header - Parsing the Hunk Header

def parse_hunk_header(header: str) -> Tuple[int, int, int, int]:
    """
    Parses a hunk header and extracts line numbers.

    HEADER FORMAT:
    @@ -OLD_START,OLD_COUNT +NEW_START,NEW_COUNT @@

    VARIANTS:
    - @@ -10,8 +10,6 @@ : complete format
    - @@ -10 +10 @@ : count omitted (means 1)
    - @@ -10,8 +10,6 @@ function_name : can have context after @@

    REGEX USED:
    @@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@

    - (\d+) : captures one or more digits (the number)
    - (?:,(\d+))? : optionally captures ,number
    - \+ : escape of + (literal)

    Args:
        header (str): The header line (e.g., "@@ -10,8 +10,6 @@")

    Returns:
        Tuple[int, int, int, int]: (old_start, old_count, new_start, new_count)

    Raises:
        ValueError: If the header format is invalid

    Examples:
        >>> parse_hunk_header("@@ -10,8 +10,6 @@")
        (10, 8, 10, 6)

        >>> parse_hunk_header("@@ -5 +5 @@")
        (5, 1, 5, 1)  # count defaults to 1

        >>> parse_hunk_header("@@ -10,5 +12,7 @@ def my_func():")
        (10, 5, 12, 7)  # ignores text after @@
    """

    # Regex pattern for the header
    pattern = r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@'

    # Search for the pattern in the header
    match = re.match(pattern, header)

    if not match:
        # The header doesn't match the expected format
        raise ValueError(f"Invalid hunk header: {header}")

    # Extract values from capture groups
    # If an optional group doesn't match, match.group() returns None
    # In that case, we use 1 as default (a single line)
    old_start = int(match.group(1))
    old_count = int(match.group(2) or 1)  # Default to 1 if not specified
    new_start = int(match.group(3))
    new_count = int(match.group(4) or 1)  # Default to 1 if not specified

    return old_start, old_count, new_start, new_count

# =============================================================================
# FUNCTION parse_unified_diff - Complete Diff Parsing

def parse_unified_diff(patch: str, filename: str) -> DiffResult:
    """
    Parses a diff in unified format and extracts information about changes.

    This is the main function of the module. It takes the raw content
    of a diff (like the one in the "patch" field of data.json) and produces
    a structured DiffResult.

    ALGORITHM:

    1. Split the patch into lines
    2. For each line:
       a. If it starts with "@@": new hunk, parse the header
       b. If it starts with "+": added line (increment new_line_num)
       c. If it starts with "-": removed line (increment old_line_num)
       d. If it starts with " ": context (increment both)
    3. Collect line numbers in separate lists
    4. Return DiffResult with all information

    LINE NUMBER HANDLING:

    The new_line_num and old_line_num counters track the current
    position in their respective files as we scan the diff.

    Example:
        @@ -10,4 +10,4 @@
         context        # old=10, new=10, then both +1
        -removed        # old=11, then old +1
        +added          # new=11, then new +1
         context        # old=12, new=12

    Args:
        patch (str): The diff content ("patch" field from GitHub API)
        filename (str): Name of the file this diff refers to

    Returns:
        DiffResult: Object with all extracted information

    Example:
        patch = '''@@ -10,8 +10,6 @@
         from pathlib import Path
         import typing as tp

        -#from dora.log import fatal
        -
         import logging
        '''

        result = parse_unified_diff(patch, "module.py")
        print(result.deleted_lines)  # [12, 13]
        print(result.added_lines)    # []
    """

    # -------------------------------------------------------------------------
    # Initialization

    # Split the patch into individual lines
    lines = patch.split('\n')

    # List to collect parsed hunks
    hunks = []

    # Lists for line numbers
    added_lines = []      # Added lines (in NEW file)
    deleted_lines = []    # Removed lines (in OLD file)
    modified_lines = []   # All modified lines (in NEW file)

    # State variables for parsing
    current_hunk = None   # Current hunk (None if not inside a hunk)
    new_line_num = 0      # Position counter in NEW file
    old_line_num = 0      # Position counter in OLD file

    # -------------------------------------------------------------------------
    # Line-by-line parsing

    for line in lines:

        # ---------------------------------------------------------------------
        # Case 1: Header of a new hunk (@@ ... @@)
        if line.startswith('@@'):

            # Save the previous hunk (if exists)
            if current_hunk:
                hunks.append(current_hunk)

            # Parse the new header
            try:
                old_start, old_count, new_start, new_count = parse_hunk_header(line)
            except ValueError:
                # Invalid header - skip this hunk
                continue

            # Create a new DiffHunk object
            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=[]  # Lines will be added later
            )

            # Initialize position counters
            new_line_num = new_start
            old_line_num = old_start

        # ---------------------------------------------------------------------
        # Case 2: Inside a hunk - process the lines
        elif current_hunk:

            # Add the raw line to the current hunk
            current_hunk.lines.append(line)

            # -----------------------------------------------------------------
            # ADDED line (starts with +, but not +++)
            # +++ is the new file header, not an added line
            if line.startswith('+') and not line.startswith('+++'):
                # Record the line number (in NEW file)
                added_lines.append(new_line_num)
                modified_lines.append(new_line_num)

                # Increment only the NEW counter
                # (the line doesn't exist in OLD file)
                new_line_num += 1

            # -----------------------------------------------------------------
            # REMOVED line (starts with -, but not ---)
            elif line.startswith('-') and not line.startswith('---'):
                deleted_lines.append(old_line_num)

                # Increment only the OLD counter
                old_line_num += 1

            # -----------------------------------------------------------------
            # "No newline at end of file" marker - skip without advancing counters
            elif line.startswith('\\'):
                pass

            # -----------------------------------------------------------------
            # CONTEXT line (starts with space)
            elif line.startswith(' '):
                new_line_num += 1
                old_line_num += 1

    # -------------------------------------------------------------------------
    # Finalization

    # Save the last hunk (if exists)
    if current_hunk:
        hunks.append(current_hunk)

    # Create and return the result
    return DiffResult(
        filename=filename,
        added_lines=sorted(added_lines),
        deleted_lines=sorted(deleted_lines),
        modified_lines=sorted(modified_lines),
        hunks=hunks
    )
