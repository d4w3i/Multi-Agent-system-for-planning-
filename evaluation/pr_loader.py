"""
=============================================================================
PR_LOADER.PY - Pull Request Data Loading and Saving
=============================================================================

This module handles loading PR data from the data.json file
and saving results (ground_truth.json).

PR DIRECTORY STRUCTURE:

    PR4Code/dataset_pr_commits_py/
    └── owner_repo/                    # Repository directory
        └── pr_123/                    # Single PR directory
            ├── data.json              # ← Original data (INPUT)
            ├── ground_truth.json      # ← Extraction result (OUTPUT)
            ├── original_files/        # Files before the PR
            │   └── file.py
            └── modified_files/        # Files after the PR
                └── file.py

DATA.JSON CONTENTS:

    {
        "repository": "owner/repo",
        "pull_request_number": 123,
        "title": "Fix bug in parser",
        "body": "Description of the PR...",
        "diff_between_base_and_last": [
            {
                "filename": "src/parser.py",
                "status": "modified",
                "additions": 10,
                "deletions": 5,
                "patch": "@@ -10,5 +10,6 @@..."
            }
        ],
        "commits": [
            {"message": "Fix parsing bug", "sha": "abc123..."}
        ]
    }

CLASSES AND FUNCTIONS:

- PRData: Wrapper that provides typed access to JSON data
- load_pr_data(): Loads and validates data.json
- save_ground_truth(): Saves GroundTruth as JSON

USAGE:

    from evaluation.pr_loader import load_pr_data, save_ground_truth

    # Load PR data
    pr_data = load_pr_data(Path("PR4Code/.../pr_123/"))

    # Access data
    print(pr_data.title)
    print(pr_data.diffs)

    # Find modified files
    path = pr_data.get_modified_file_path("src/parser.py")

    # Save results
    save_ground_truth(ground_truth, Path("PR4Code/.../pr_123/"))

=============================================================================
"""

import json
import logging

# Path: Cross-platform path handling
# - Path.exists(): Check if file exists
# - Path / "subpath": Path concatenation
from pathlib import Path

# Type hints
# - Optional: Can be None
# - Dict: Dictionary
# - Any: Any type
# - List: List
from typing import Optional, Dict, Any, List

# Import GroundTruth model for type hint
from .models import GroundTruth

logger = logging.getLogger('ground_truth_extractor')

# =============================================================================
# PRData CLASS - Pull Request Data Wrapper

class PRData:
    """
    Wrapper that provides structured access to data.json contents.

    Instead of accessing the dictionary directly with data['field'],
    this class provides typed properties that:
    - Document available fields
    - Provide default values for optional fields
    - Centralize access logic

    MAIN FIELDS:
    - pr_number: PR number
    - repository: Repository name (owner/repo)
    - title: PR title
    - body: Description (optional)
    - diffs: List of diffs for each modified file
    - commits: List of commits in the PR

    HELPER METHODS:
    - get_modified_file_path(): Find file in modified_files/ folder
    - get_original_file_path(): Find file in original_files/ folder

    Attributes:
        data (Dict): Raw dictionary from data.json
        pr_dir (Path): Path to the PR directory

    Example:
        pr_data = PRData(json_data, Path("/path/to/pr_123"))
        print(pr_data.title)
        print(pr_data.pr_number)
        for diff in pr_data.diffs:
            print(diff['filename'])
    """

    def __init__(self, data: Dict[str, Any], pr_dir: Path):
        """
        Initialize the PRData wrapper.

        Args:
            data (Dict[str, Any]): Dictionary loaded from data.json
            pr_dir (Path): Path to the directory containing data.json
                          Used to locate modified_files/ and original_files/

        """

        # Store raw dictionary for direct access if needed
        self.data = data

        # Store PR directory path
        # Required for get_*_file_path() methods
        self.pr_dir = pr_dir

    # =========================================================================
    # PROPERTIES - Typed Field Access

    @property
    def pr_number(self) -> int:
        """
        Pull Request identifier number.

        Returns:
            int: The PR number (e.g., 123, 4567)

        """
        return self.data['pull_request_number']

    @property
    def repository(self) -> str:
        """
        Full repository name in owner/repo format.

        Returns:
            str: Repository name (e.g., "facebook/react")
        """
        return self.data['repository']

    @property
    def title(self) -> str:
        """
        Pull Request title.

        Returns:
            str: The title (e.g., "Fix memory leak in useEffect")
        """
        return self.data['title']

    @property
    def body(self) -> Optional[str]:
        """
        Pull Request description/body.

        Some PRs don't have a description, so this field is optional.
        Returns empty string if not present (not None, for safety).

        Returns:
            Optional[str]: The description or empty string

        """
        # Use .get() with default '' to handle missing fields
        return self.data.get('body', '')

    @property
    def diffs(self) -> List[Dict]:
        """
        List of diffs for each modified file in the PR.

        Each element is a dictionary with:
        - filename: file path
        - status: "modified", "added", "deleted"
        - additions: number of lines added
        - deletions: number of lines removed
        - patch: the diff in unified format (optional)
        """
        return self.data.get('diff_between_base_and_last', [])

    @property
    def commits(self) -> List[Dict]:
        """
        List of commits included in the PR.

        Each commit is a dictionary with at least:
        - message: commit message
        - sha: commit hash

        Returns:
            List[Dict]: List of commits, or empty list if not present
        """
        return self.data.get('commits', [])

    @property
    def commit_messages(self) -> List[str]:
        """
        List of commit messages only (convenient helper).

        Extracts only the 'message' field from each commit for
        simpler usage (e.g., passing to LLM).

        Returns:
            List[str]: List of commit messages
        """
        # List comprehension with .get() for robustness
        return [c.get('message', '') for c in self.commits]

    # =========================================================================
    # HELPER METHODS - File Location

    def _resolve_file_path(self, filename: str, subdir: str) -> Optional[Path]:
        """
        Resolve a filename within a given subdirectory of the PR folder.

        Handles two cases:
        1. Full path preserved: <subdir>/src/parser.py
        2. Basename only: <subdir>/parser.py
           (some datasets strip directory structure when saving files)

        Also guards against path-traversal attacks from untrusted filenames.

        Args:
            filename (str): Relative path or basename to locate.
            subdir (str): Subdirectory name (e.g., "modified_files").

        Returns:
            Optional[Path]: Resolved path if the file exists and is safe, else None.
        """
        # Guard against path traversal from untrusted filenames
        if '..' in Path(filename).parts:
            logger.warning(f"Skipping path with traversal: {filename}")
            return None

        base_dir = (self.pr_dir / subdir).resolve()

        # Attempt 1: Try with full path
        path = (self.pr_dir / subdir / filename).resolve()
        if path.exists() and str(path).startswith(str(base_dir)):
            return path

        # Attempt 2: Try with basename only ("src/utils/parser.py" → "parser.py")
        basename = Path(filename).name
        path = (self.pr_dir / subdir / basename).resolve()
        if path.exists() and str(path).startswith(str(base_dir)):
            return path

        return None

    def get_modified_file_path(self, filename: str) -> Optional[Path]:
        """
        Find the path of a file in the modified_files/ folder.

        The modified_files/ folder contains files AFTER the PR changes.

        Args:
            filename (str): Name of the file to find.
                           Can be relative path (e.g., "src/parser.py")
                           or just filename (e.g., "parser.py")

        Returns:
            Optional[Path]: Full path to the file if found, None otherwise
        """
        return self._resolve_file_path(filename, 'modified_files')

    def get_original_file_path(self, filename: str) -> Optional[Path]:
        """
        Find the path of a file in the original_files/ folder.

        The original_files/ folder contains files BEFORE the PR changes
        (base version). Uses the same logic as get_modified_file_path.

        Args:
            filename (str): Name of the file to find

        Returns:
            Optional[Path]: Full path to the file if found, None otherwise
        """
        return self._resolve_file_path(filename, 'original_files')

# =============================================================================
# load_pr_data FUNCTION - Loading and Validation

def load_pr_data(pr_dir: Path) -> Optional[PRData]:
    """
    Load PR data from data.json with validation.

    This function:
    1. Verifies that data.json exists
    2. Parses the JSON
    3. Validates required fields
    4. Returns a PRData wrapper object

    REQUIRED FIELDS:
    - pull_request_number
    - repository
    - title

    ERROR HANDLING:
    - File not found: prints error and returns None
    - Invalid JSON: prints error and returns None
    - Missing fields: prints error and returns None

    Args:
        pr_dir (Path): Path to the PR directory (containing data.json)

    Returns:
        Optional[PRData]: PRData object if loading succeeds, None otherwise
    """

    # Build full path to data.json
    data_json = pr_dir / 'data.json'

    # -------------------------------------------------------------------------
    # Check file existence
    if not data_json.exists():
        logger.error(f"{data_json} not found")
        return None

    try:
        # ---------------------------------------------------------------------
        # Load JSON
        # Handle special characters
        with open(data_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # ---------------------------------------------------------------------
        # Validate required fields and types
        required_fields = {
            'pull_request_number': int,
            'repository': str,
            'title': str,
        }

        for field, expected_type in required_fields.items():
            if field not in data:
                logger.error(f"Missing required field '{field}' in {data_json}")
                return None
            if not isinstance(data[field], expected_type):
                logger.error(f"Field '{field}' should be {expected_type.__name__}, got {type(data[field]).__name__} in {data_json}")
                return None

        # ---------------------------------------------------------------------
        # Create wrapper
        return PRData(data, pr_dir)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {data_json}: {e}")
        return None

    except Exception as e:
        logger.error(f"Error loading {data_json}: {e}")
        return None

# =============================================================================
# save_ground_truth FUNCTION - Saving Results

def save_ground_truth(ground_truth: GroundTruth, pr_dir: Path) -> bool:
    """
    Save the GroundTruth object as ground_truth.json in the PR directory.

    Uses Pydantic serialization to ensure the JSON is
    properly formatted with all fields.

    OUTPUT FORMAT:
    The file is saved with 2-space indentation for readability.
    Datetime fields are serialized in ISO 8601 format.

    Args:
        ground_truth (GroundTruth): The object to save
        pr_dir (Path): PR directory where to save the file

    Returns:
        bool: True if saved successfully, False otherwise
    """

    # Build output path
    output_path = pr_dir / 'ground_truth.json'

    try:
        # Open file for writing with UTF-8 encoding
        with open(output_path, 'w', encoding='utf-8') as f:
            # Use Pydantic's model_dump_json() for serialization
            f.write(ground_truth.model_dump_json(indent=2))

        return True

    except Exception as e:
        logger.error(f"Error saving ground truth to {output_path}: {e}")
        return False
