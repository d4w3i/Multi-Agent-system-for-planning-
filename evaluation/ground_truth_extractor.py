"""
=============================================================================
GROUND_TRUTH_EXTRACTOR.PY - Main Extraction Orchestrator
=============================================================================

This module is the CORE of the ground truth extraction system.
It coordinates all other modules to extract complete information
from each Pull Request in the PR4Code dataset.

ROLE IN THE SYSTEM:

    ┌─────────────────────────────────────────────────────────────────┐
    │                  ground_truth_extractor.py                      │
    │                  (THIS FILE - ORCHESTRATOR)                     │
    └──────────────────────────┬──────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │ pr_loader   │     │ diff_parser │     │ step_planner│
    │             │     │             │     │             │
    │ Loads       │     │ Parses      │     │ Generates   │
    │ data.json   │     │ Git diffs   │     │ steps w/LLM │
    └─────────────┘     └──────┬──────┘     └─────────────┘
                               │
                               ▼
                        ┌─────────────┐
                        │ function_   │
                        │ matcher     │
                        │             │
                        │ Tree-sitter │
                        │ matching    │
                        └─────────────┘

WHAT THIS MODULE DOES:

For each PR in the dataset:
1. LOADS the data from data.json (using pr_loader)
2. PARSES the diffs to extract modified lines (using diff_parser)
3. MATCHES lines to functions (using function_matcher)
4. GENERATES implementation steps (using step_planner, optional)
5. SAVES the result to ground_truth.json

DIRECTORY STRUCTURE:

    PR4Code/dataset_pr_commits_py/
    └── owner_repo/
        └── pr_123/
            ├── data.json           ← INPUT: Original PR data
            ├── ground_truth.json   ← OUTPUT: Extraction result
            ├── original_files/     ← Files before the PR
            └── modified_files/     ← Files after the PR

=============================================================================
USAGE GUIDE
=============================================================================

BASIC COMMANDS:
---------------

    # Process a single PR
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/owner_repo/pr_123/

    # Process all PRs from a repository
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/owner_repo/

    # Process the entire dataset
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/


AVAILABLE OPTIONS:
------------------

    --no-llm        Disables step plan generation with LLM.
                    Extracts only modified files and functions (much faster).

    --limit N       Process only the first N PRs found.
                    Useful for testing and development.

    --skip-existing Skip PRs that already have a ground_truth.json file.
                    Useful for resuming interrupted processing.


EXAMPLES:
---------

    # 1. Quick test on 10 PRs without LLM
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --no-llm --limit 10

    # 2. Generate ground truth for the first 50 PRs with LLM
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --limit 50

    # 3. Resume interrupted processing (skip already processed)
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --skip-existing

    # 4. Process only a specific repository
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/1Panel-dev_MaxKB/

    # 5. Process a single specific PR
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/1Panel-dev_MaxKB/pr_3556/

    # 6. Combination: first 100 PRs, skip existing, without LLM
    python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/ --limit 100 --skip-existing --no-llm


NUMBER OF GENERATED STEPS:
--------------------------

    The number of steps in the plan is DYNAMIC and depends on the changes:
    - For .py files: 1 step for each MODIFIED FUNCTION
    - For non-.py files: 1 step for each MODIFIED FILE

    Example: PR that modifies 3 functions in main.py + README.md = 4 steps


ERROR HANDLING:

The system is designed to be ROBUST:
- If a PR fails, it still saves a ground_truth.json with success=False
- Errors are logged but don't block processing
- The --skip-existing flag allows resuming interrupted processing

EXAMPLE OUTPUT:

    {
      "pr_number": 123,
      "repository": "owner/repo",
      "title": "Fix bug in parser",
      "extraction_metadata": {
        "extracted_at": "2024-01-15T10:30:00",
        "success": true
      },
      "files_modified": [
        {
          "filename": "parser.py",
          "functions_modified": [
            {"full_name": "Parser.parse", "lines_changed": [45, 46, 47]}
          ]
        }
      ],
      "step_plan": {
        "summary": "This PR fixes...",
        "steps": [...]
      }
    }

=============================================================================
"""
import argparse
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import sys
try:
    from tqdm import tqdm  # Progress bar for terminal
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Warn the user but don't block execution
    print("Warning: tqdm not installed. Install with: pip install tqdm")
from .models import (
    GroundTruth, FileChange, StepPlan,
    ExtractionMetadata
)
from .diff_parser import parse_unified_diff

# function_matcher: Function matching with Tree-sitter
# - match_functions_to_changes(): Finds modified functions
from .function_matcher import match_functions_to_changes

# step_planner: Step generation with LLM
# - StepPlannerWithRetry: Planner with automatic retries
from .step_planner import StepPlannerWithRetry

# pr_loader: PR data loading/saving
# - load_pr_data(): Loads data.json
# - save_ground_truth(): Saves ground_truth.json
from .pr_loader import load_pr_data, save_ground_truth

# utils: Logging utilities
# - setup_logging(): Configures the logger
# - log_error(), log_success(): Colored helpers
from .utils import setup_logging, log_error, log_success

# -----------------------------------------------------------------------------
# Logger Initialization
logger = setup_logging()

_EXTRACTOR_VERSION = "1.0.0"


# =============================================================================
# GroundTruthExtractor CLASS - Main Extractor

class GroundTruthExtractor:
    """
    Main class for extracting ground truth from PRs.

    This class coordinates the entire extraction process:
    1. Loading PR data
    2. Parsing diffs
    3. Function matching
    4. Step plan generation (optional)
    5. Saving results

    OPERATING MODES:

    1. WITH LLM (default):
       - Extracts modified files and functions
       - Generates step plan using GPT
       - Slower but more complete output

    2. WITHOUT LLM (--no-llm):
       - Extracts only modified files and functions
       - No step plan
       - Much faster (useful for testing)

    ERROR HANDLING:

    The class is designed to be fault-tolerant:
    - If diff parsing fails, it continues with the others
    - If function matching fails, it saves the file without functions
    - If the entire extraction fails, it still saves with success=False

    Attributes:
        use_llm (bool): If True, generates step plan with LLM
        step_planner (Optional[StepPlannerWithRetry]): LLM Planner (None if use_llm=False)

    Example:
        # Extraction with LLM
        extractor = GroundTruthExtractor(use_llm=True)
        result = extractor.extract_pr(Path("PR4Code/.../pr_123"))

        # Extraction without LLM (faster)
        extractor = GroundTruthExtractor(use_llm=False)
        result = extractor.extract_pr(Path("PR4Code/.../pr_123"))

        # Verify result
        if result:
            print(f"Extracted {len(result.files_modified)} files")
        else:
            print("Extraction failed")
    """

    def __init__(self, use_llm: bool = True):
        """
        Initialize the extractor.

        LAZY INITIALIZATION:
        The step_planner is created only if use_llm=True.
        This avoids loading the OpenAI client when not needed.

        Args:
            use_llm (bool): If True, enables step plan generation
                           via LLM. Default: True.
                           If False, step_plan will always be None.

        Example:
            # With LLM (requires OPENAI_API_KEY)
            extractor = GroundTruthExtractor(use_llm=True)

            # Without LLM (no API dependency)
            extractor = GroundTruthExtractor(use_llm=False)
        """

        # Save the configuration
        self.use_llm = use_llm

        # Initialize the planner only if necessary
        # This avoids errors if OPENAI_API_KEY is not configured
        # when the LLM is not needed
        self.step_planner = StepPlannerWithRetry() if use_llm else None

    def extract_pr(self, pr_dir: Path) -> Optional[GroundTruth]:
        """
        Extract ground truth for a single PR.

        This is the main function that orchestrates the extraction.
        It handles all errors internally and ensures that
        a ground_truth.json is always saved (even in case of error).

        EXECUTION FLOW:

            pr_dir
               │
               ▼
            load_pr_data()
               │
               ├── Error → return None
               │
               ▼
            _extract_files_modified()
               │
               ▼
            _extract_step_plan() [if use_llm]
               │
               ▼
            GroundTruth()
               │
               ▼
            save_ground_truth()
               │
               ├── Success → return GroundTruth
               │
               └── Error → return None

        ERROR HANDLING:

        If an exception occurs during extraction:
        1. Logs the error
        2. Creates a GroundTruth with success=False and error_message
        3. Still saves the file (for traceability)
        4. Returns None

        Args:
            pr_dir (Path): Path to the PR directory.
                          Must contain data.json and modified_files/.

        Returns:
            Optional[GroundTruth]: The extracted object if successful, None if failed.
                                  Even when returning None, ground_truth.json
                                  is saved with error details.

        Example:
            extractor = GroundTruthExtractor()

            result = extractor.extract_pr(Path("PR4Code/repo/pr_123"))

            if result:
                print(f"PR #{result.pr_number}: {len(result.files_modified)} files")
                if result.step_plan:
                    print(f"Step plan: {result.step_plan.summary}")
            else:
                print("Extraction failed - see ground_truth.json for details")
        """

        # Log the start of processing
        logger.info(f"Processing {pr_dir.name}")

        # ---------------------------------------------------------------------
        # Step 1: Load PR data
        # load_pr_data handles errors internally and returns None if it fails
        pr_data = load_pr_data(pr_dir)
        if not pr_data:
            return None

        try:
            # -----------------------------------------------------------------
            # Step 2: Extract modified files and functions
            files_modified = self._extract_files_modified(pr_data)

            # -----------------------------------------------------------------
            # Step 3: Generate step plan (optional)
            step_plan = None
            if self.use_llm and self.step_planner:
                step_plan = self._extract_step_plan(pr_data, files_modified)

            # -----------------------------------------------------------------
            # Step 4: Build the GroundTruth object

            # Flat, deterministic list of all modified functions:
            # iterate files in diff order, sort each file's functions by start_line.
            all_functions_modified = [
                func
                for file_change in files_modified
                for func in sorted(file_change.functions_modified, key=lambda f: f.start_line)
            ]

            ground_truth = GroundTruth(
                pr_number=pr_data.pr_number,
                repository=pr_data.repository,
                title=pr_data.title,
                body=pr_data.body,
                extraction_metadata=ExtractionMetadata(
                    extracted_at=datetime.now(),
                    extractor_version=_EXTRACTOR_VERSION,
                    success=True  # Extraction successful
                ),
                files_modified=files_modified,
                functions_modified=all_functions_modified,
                step_plan=step_plan
            )

            # -----------------------------------------------------------------
            # Step 5: Save the result
            if save_ground_truth(ground_truth, pr_dir):
                log_success(f"Saved ground truth for PR {pr_data.pr_number}")
                return ground_truth
            else:
                log_error(f"Failed to save ground truth for PR {pr_data.pr_number}")
                return None

        except Exception as e:
            # -----------------------------------------------------------------
            # Error handling: save partial result
            log_error(f"Error extracting PR {pr_data.pr_number}: {e}")

            # Create a "fallback" GroundTruth with the error recorded
            # This allows tracking which PRs had problems
            ground_truth = GroundTruth(
                pr_number=pr_data.pr_number,
                repository=pr_data.repository,
                title=pr_data.title,
                body=pr_data.body,
                extraction_metadata=ExtractionMetadata(
                    extracted_at=datetime.now(),
                    extractor_version=_EXTRACTOR_VERSION,
                    success=False,
                    error_message=str(e)
                ),
                files_modified=[],
                step_plan=None
            )

            # Save anyway for traceability
            save_ground_truth(ground_truth, pr_dir)
            return None

    def _extract_files_modified(self, pr_data) -> List[FileChange]:
        """
        Extract the list of modified files with their functions.

        For each file in the PR diff:
        1. Check if it's a Python file
        2. Parse the diff to get the modified lines
        3. Use Tree-sitter to find the functions in those lines

        NON-PYTHON FILE HANDLING:

        Non-Python files (e.g., .md, .json, .yml) are included
        in the output but without function matching.
        This maintains complete information about all modified files.

        ERROR HANDLING:

        If parsing a diff fails, the file is still
        added to the output but with functions_modified=[].
        This ensures the output is always complete.

        FLOW FOR EACH FILE:

            diff
             │
             ├── Non-Python? → FileChange without functions
             │
             ├── Empty patch? → FileChange without functions
             │
             ▼
            parse_unified_diff()
             │
             ├── Error? → FileChange without functions
             │
             ▼
            match_functions_to_changes()
             │
             └── FileChange with functions

        Args:
            pr_data: PRData object with PR data
                    (access to diffs, get_modified_file_path, etc.)

        Returns:
            List[FileChange]: List of modified files with functions.
                             Each element contains:
                             - filename: file path
                             - status: "modified", "added", "deleted"
                             - additions/deletions: line counts
                             - functions_modified: list of FunctionChange

        Example:
            files = self._extract_files_modified(pr_data)

            for f in files:
                print(f"{f.filename}: {len(f.functions_modified)} functions")
        """

        # Result list
        files_modified = []

        # Iterate over all PR diffs
        for diff in pr_data.diffs:
            if not isinstance(diff, dict) or 'filename' not in diff:
                logger.warning(f"Skipping invalid diff entry: {type(diff)}")
                continue
            filename = diff['filename']

            # -----------------------------------------------------------------
            # Case 1: Non-Python file
            if not filename.endswith('.py'):
                # Add the file without functions
                files_modified.append(
                    FileChange(
                        filename=filename,
                        status=diff.get('status', 'modified'),
                        additions=diff.get('additions', 0),
                        deletions=diff.get('deletions', 0),
                        functions_modified=[],  # No matching possible
                        patch=diff.get('patch', '')
                    )
                )
                continue

            # -----------------------------------------------------------------
            # Case 2: Empty or missing patch
            # Some files may have empty diffs (e.g., binary files, renames)
            patch = diff.get('patch', '')
            if not patch:
                files_modified.append(
                    FileChange(
                        filename=filename,
                        status=diff.get('status', 'modified'),
                        additions=diff.get('additions', 0),
                        deletions=diff.get('deletions', 0),
                        functions_modified=[],  # No analyzable changes
                        patch=None
                    )
                )
                continue

            # -----------------------------------------------------------------
            # Case 3: Diff parsing
            try:
                # Extract modified lines from the patch
                diff_result = parse_unified_diff(patch, filename)
            except Exception as e:
                # Parsing failed - log and continue without functions
                logger.warning(f"Failed to parse diff for {filename}: {e}")
                files_modified.append(
                    FileChange(
                        filename=filename,
                        status=diff.get('status', 'modified'),
                        additions=diff.get('additions', 0),
                        deletions=diff.get('deletions', 0),
                        functions_modified=[],
                        patch=patch
                    )
                )
                continue

            # -----------------------------------------------------------------
            # Case 4: Function matching
            functions_modified = []

            # Find the file in the modified_files/ folder
            modified_file_path = pr_data.get_modified_file_path(filename)

            if modified_file_path and modified_file_path.exists():
                try:
                    # Use Tree-sitter to find modified functions
                    functions_modified = match_functions_to_changes(
                        str(modified_file_path),
                        diff_result
                    )
                except Exception as e:
                    # Matching failed - log but continue
                    logger.warning(f"Failed to match functions in {filename}: {e}")
                    # functions_modified remains an empty list

            # -----------------------------------------------------------------
            # Add the file to the result
            files_modified.append(
                FileChange(
                    filename=filename,
                    status=diff.get('status', 'modified'),
                    additions=diff.get('additions', 0),
                    deletions=diff.get('deletions', 0),
                    functions_modified=functions_modified,
                    patch=patch
                )
            )

        return files_modified

    def _extract_step_plan(
        self,
        pr_data,
        files_modified: List[FileChange]
    ) -> Optional[StepPlan]:
        """
        Generate the step plan using the LLM.

        Builds context from the PR and passes it to the StepPlanner
        to generate a detailed implementation plan.

        CONTEXT PASSED TO THE LLM:

        - PR title
        - Description (body)
        - Commit messages
        - List of modified files with additions/deletions
        - Patch content (unified diff) for each file

        STEP COUNT CALCULATION:

        The number of steps is automatically determined based on the changes:
        - For .py files WITH modified functions: 1 step for each function
        - For .py files WITHOUT modified functions: 1 step for the file
        - For non-.py files: 1 step for each file

        Example:
        - main.py with 2 modified functions → 2 steps
        - config.json modified → 1 step
        - README.md modified → 1 step
        - utils.py without identified functions → 1 step
        Total: 5 steps

        Args:
            pr_data: PRData object with PR data
            files_modified (List[FileChange]): Already extracted files
                                              (used to build diff_summaries)

        Returns:
            Optional[StepPlan]: Plan with num_steps steps if successful, None if failed.
                              num_steps = modified functions (.py files) + non-.py files

        Example:
            # Called internally by extract_pr()
            step_plan = self._extract_step_plan(pr_data, files_modified)

            if step_plan:
                print(f"Summary: {step_plan.summary}")
                for step in step_plan.steps:
                    print(f"  - {step.operation}: {step.target}")
        """

        # ---------------------------------------------------------------------
        # Calculate the number of steps based on changes
        # Logic:
        # - .py files WITH modified functions: count the functions
        # - .py files WITHOUT functions (or non-.py files): count 1 per file
        num_steps = 0
        for f in files_modified:
            if f.filename.endswith('.py') and f.functions_modified:
                # Python file with identified functions: 1 step per function
                num_steps += len(f.functions_modified)
            else:
                # Non-Python file or Python file without functions: 1 step per file
                num_steps += 1

        # Ensure there's at least 1 step (edge case: no files)
        if num_steps < 1:
            logger.warning("No changes detected, defaulting to 1 step")
            num_steps = 1

        logger.info(f"Generating step plan with {num_steps} steps")

        # ---------------------------------------------------------------------
        # Build diff summaries
        # Extract essential information for the LLM including patch content
        diff_summaries = [
            {
                'filename': f.filename,
                'additions': f.additions,
                'deletions': f.deletions,
                'patch': f.patch
            }
            for f in files_modified
        ]

        # ---------------------------------------------------------------------
        # Generate the plan
        try:
            # The planner handles retries and errors internally
            return self.step_planner.generate_step_plan(
                pr_title=pr_data.title,
                pr_body=pr_data.body,
                commit_messages=pr_data.commit_messages,
                diff_summaries=diff_summaries,
                num_steps=num_steps  # Pass the calculated number of steps
            )
        except Exception as e:
            # Log the error but don't raise an exception
            # Allows extraction to continue without step plan
            logger.error(f"LLM step planning failed: {e}")
            return None

def main():
    """
    Entry point for command line execution.

    This function:
    1. Parses CLI arguments
    2. Collects PR directories to process
    3. Applies filters (--limit, --skip-existing)
    4. Runs extraction on all PRs
    5. Prints a final summary

    CLI USAGE:

        # Process a single PR
        python -m evaluation.ground_truth_extractor path/to/pr_123/

        # Process a parent directory (automatically finds pr_*)
        python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/

        # Options:
        --no-llm        Disable step plan generation (faster)
        --limit N       Process only the first N PRs
        --skip-existing Skip PRs that already have ground_truth.json

    PRACTICAL EXAMPLES:

        # Quick test on 10 PRs without LLM
        python -m evaluation.ground_truth_extractor PR4Code/... --no-llm --limit 10

        # Resume interrupted processing
        python -m evaluation.ground_truth_extractor PR4Code/... --skip-existing

        # Process the entire dataset
        python -m evaluation.ground_truth_extractor PR4Code/dataset_pr_commits_py/

    EXIT CODES:
        0: Success (at least some PRs processed)
        1: Error (no PRs found)
    """

    # -------------------------------------------------------------------------
    # ArgumentParser Configuration
    parser = argparse.ArgumentParser(
        description="Extract ground truth from PR4Code dataset"
    )

    # Positional argument: PR directories (optional when --subset is provided)
    parser.add_argument(
        'pr_dirs',
        nargs='*',
        help='PR directory paths or parent directory containing PRs'
    )

    # Option: load PR paths from a subset JSON file
    parser.add_argument(
        '--subset',
        metavar='FILE',
        help='Subset JSON file (from create_pr_subset.py); overrides positional pr_dirs'
    )

    # Flag: disable LLM
    # action='store_true' means it's a boolean (present = True)
    parser.add_argument(
        '--no-llm',
        action='store_true',
        help='Skip LLM-based step plan generation'
    )

    # Option: limit number of PRs
    # Useful for testing and debugging
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of PRs to process (for testing)'
    )

    # Flag: skip already processed PRs
    # Allows resuming interrupted processing
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip PRs that already have ground_truth.json'
    )

    # Parse arguments
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Collect PR directories
    # --subset overrides positional pr_dirs
    pr_dirs = []

    if args.subset:
        from scripts.create_pr_subset import load_pr_subset
        pr_dirs = [Path(p) for p in load_pr_subset(args.subset)]
        logger.info(f"Loaded {len(pr_dirs)} PRs from subset: {args.subset}")
    else:
        if not args.pr_dirs:
            logger.error("Provide at least one PR directory or use --subset")
            sys.exit(1)

        for path_str in args.pr_dirs:
            path = Path(path_str)

            if path.is_dir():
                # Check if it's a PR directory (contains data.json)
                # or a parent directory (contains pr_* subdirectories)
                if (path / 'data.json').exists():
                    # It's a single PR
                    pr_dirs.append(path)
                else:
                    # It's a parent directory - find all PRs
                    # Pattern: */pr_*/ finds all subdirectories starting with "pr_"
                    # sorted() for deterministic order
                    pr_dirs.extend(sorted(path.glob('*/pr_*/')))
            else:
                # Not a directory - warn but continue
                logger.warning(f"Not a directory: {path}")

    # Verify there are PRs to process
    if not pr_dirs:
        logger.error("No PR directories found")
        sys.exit(1)  # Exit with error code

    # -------------------------------------------------------------------------
    # Apply filters
    # Apply --limit if specified
    if args.limit:
        pr_dirs = pr_dirs[:args.limit]

    # Filter already processed PRs if --skip-existing
    if args.skip_existing:
        pr_dirs = [
            d for d in pr_dirs
            if not (d / 'ground_truth.json').exists()
        ]

    # -------------------------------------------------------------------------
    # Informative log
    logger.info(f"Processing {len(pr_dirs)} PRs...")
    if args.no_llm:
        logger.info("LLM step planning disabled (--no-llm)")

    # -------------------------------------------------------------------------
    # Run extraction
    # Create the extractor with the correct configuration
    extractor = GroundTruthExtractor(use_llm=not args.no_llm)

    # Counters for the summary
    success_count = 0
    failed_count = 0

    # Use tqdm for progress bar if available
    # Otherwise simple iteration
    iterator = tqdm(pr_dirs, desc="Extracting ground truth") if HAS_TQDM else pr_dirs

    for pr_dir in iterator:
        # Extract the single PR
        result = extractor.extract_pr(pr_dir)

        # Update counters
        if result:
            success_count += 1
        else:
            failed_count += 1

    # -------------------------------------------------------------------------
    # Final summary
    # Print statistics at the end of processing
    logger.info(f"\n{'='*60}")
    logger.info(f"Extraction complete!")
    logger.info(f"Success: {success_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"{'='*60}")

if __name__ == '__main__':
    main()
