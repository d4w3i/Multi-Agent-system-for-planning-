"""
=============================================================================
MODELS.PY - Pydantic Models for Ground Truth Extraction
=============================================================================

This module defines the data structures (models) used to represent
the ground truth extracted from Pull Requests.

HIERARCHICAL MODEL STRUCTURE:

    GroundTruth                      <- Main model
    ├── pr_number: int
    ├── repository: str
    ├── title: str
    ├── body: Optional[str]
    ├── extraction_metadata: ExtractionMetadata
    │   ├── extracted_at: datetime
    │   ├── extractor_version: str
    │   ├── success: bool
    │   └── error_message: Optional[str]
    ├── files_modified: List[FileChange]
    │   ├── filename: str
    │   ├── status: "modified" | "added" | "deleted"
    │   ├── additions: int
    │   ├── deletions: int
    │   ├── patch: Optional[str]
    │   └── functions_modified: List[FunctionChange]
    │       ├── function_name: str
    │       ├── class_name: Optional[str]
    │       ├── full_name: str
    │       ├── start_line: int
    │       ├── end_line: int
    │       └── lines_changed: List[int]
    └── step_plan: Optional[StepPlan]
        ├── summary: Optional[str]
        └── steps: List[Step]
            ├── operation: str
            ├── target: str
            ├── reason: str
            └── side_effects: str

=============================================================================
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


# =============================================================================
# FunctionChange Model - Represents a Modified Function

class FunctionChange(BaseModel):
    """
    Represents a single function/method modified in a PR.

    This model captures information about WHICH functions were
    affected by a change and WHERE in the code the changes are located.

    HOW IT IS POPULATED:
    1. Tree-sitter parses the modified file
    2. Extracts all function definitions with line ranges
    3. Compares with the modified lines from the diff
    4. If there is overlap, the function is considered "modified"

    Attributes:
        function_name: Simple function name (e.g., "parse")
        class_name: Class name if it's a method (e.g., "Parser"), None if standalone
        full_name: Fully qualified name (e.g., "Parser.parse")
        start_line: First line of the function definition (1-based)
        end_line: Last line of the function definition
        lines_changed: Specific list of lines modified within the function

    """

    function_name: str = Field(
        description="Name of the function"
    )

    class_name: Optional[str] = Field(
        default=None,
        description="Parent class name if method"
    )

    full_name: str = Field(
        description="Fully qualified name (e.g., module.Class.method)"
    )

    start_line: int = Field(
        ge=0,
        description="Starting line number in the file"
    )

    end_line: int = Field(
        ge=0,
        description="Ending line number in the file"
    )

    lines_changed: List[int] = Field(
        description="Specific line numbers that were modified"
    )


# =============================================================================
# FileChange Model - Represents a Modified File

class FileChange(BaseModel):
    """
    Represents a single file modified in a PR.

    This model combines:
    - Information from the Git diff (additions, deletions, status)
    - Information from static analysis (functions_modified)

    Attributes:
        filename: Relative path of the file in the repository
        status: Type of change ("modified", "added", "deleted")
        additions: Number of lines added
        deletions: Number of lines removed
        functions_modified: List of modified functions (Python only)
        patch: The unified diff patch content (optional, may be None for binary files)
    """

    filename: str = Field(
        description="Path to the file"
    )

    status: Literal["modified", "added", "deleted", "renamed", "copied", "changed"] = Field(
        description="Change status"
    )

    additions: int = Field(
        description="Number of lines added"
    )

    deletions: int = Field(
        description="Number of lines deleted"
    )

    functions_modified: List[FunctionChange] = Field(
        default=[],
        description="Functions that were modified in this file"
    )

    patch: Optional[str] = Field(
        default=None,
        description="The unified diff patch content for this file"
    )

# =============================================================================
# Step Model - Single Step of the Implementation Plan

class Step(BaseModel):
    """
    Represents a single step in the implementation plan.

    Steps are generated by an LLM that analyzes the PR and produces
    a detailed plan of how the change was implemented.

    Attributes:
        operation: Description of the action performed
        file_to_modify: Relative path of the file to modify
        function_to_modify: Name of the function to modify (None for non-.py files)
        reason: Technical rationale for the change
        side_effects: Potential impacts on other parts of the system
    """

    operation: str = Field(
        description="What operation to perform"
    )

    file_to_modify: str = Field(
        description="Relative path of the file to modify (e.g., 'src/module.py')"
    )

    function_to_modify: Optional[str] = Field(
        default=None,
        description="Name of the function to modify (e.g., 'ClassName.method_name'). Null if the file is not .py."
    )

    reason: str = Field(
        description="Why this change is needed"
    )

    side_effects: str = Field(
        description="Potential impacts on other parts"
    )

# =============================================================================
# StepPlan Model - Complete Implementation Plan

class StepPlan(BaseModel):
    """
    Complete step-by-step plan for the PR implementation.

    Contains an ordered sequence of Steps that describe how
    the PR was (or should be) implemented.

    Attributes:
        steps: Ordered list of Steps (from first to last)
        summary: Optional 1-2 sentence summary
    """

    steps: List[Step] = Field(
        min_length=1,
        description="Ordered list of implementation steps"
    )

    summary: Optional[str] = Field(
        default=None,
        description="High-level summary of what the PR does"
    )

# =============================================================================
# ExtractionMetadata Model - Extraction Process Metadata

class ExtractionMetadata(BaseModel):
    """
    Metadata about the ground truth extraction process.
    """
    extracted_at: datetime = Field(
        description="When the extraction was performed"
    )

    extractor_version: str = Field(
        default="1.0.0",
        description="Version of the extractor used"
    )

    success: bool = Field(
        description="Whether extraction completed successfully"
    )

    error_message: Optional[str] = Field(
        default=None,
        description="Error message if extraction failed"
    )

# =============================================================================
# GroundTruth Model - Main Model (Root)

class GroundTruth(BaseModel):
    """
    Complete ground truth for a single Pull Request.

    This is the MAIN MODEL that contains all information
    extracted from a PR. It is serialized to `ground_truth.json`.

    STRUCTURE:
    ├── PR metadata (pr_number, repository, title, body)
    ├── Extraction metadata (extraction_metadata)
    ├── Modified files (files_modified)
    │   └── Modified functions per file (functions_modified)
    ├── All modified functions, flat (functions_modified)
    │   Deterministic: file order from diff, then sorted by start_line.
    │   Populated by the extractor without LLM involvement.
    └── Implementation plan (step_plan)

    """

    pr_number: int = Field(
        description="Pull request number"
    )

    repository: str = Field(
        description="Repository name (owner/repo)"
    )

    title: str = Field(
        description="PR title"
    )

    body: Optional[str] = Field(
        default=None,
        description="PR description/body"
    )

    extraction_metadata: ExtractionMetadata = Field(
        description="Extraction process metadata"
    )

    files_modified: List[FileChange] = Field(
        description="List of modified files"
    )

    functions_modified: List[FunctionChange] = Field(
        default=[],
        description=(
            "Flat list of all modified functions across all files, "
            "ordered by file appearance in the diff then by start_line. "
            "Populated deterministically by Tree-sitter, no LLM involved."
        )
    )

    step_plan: Optional[StepPlan] = Field(
        default=None,
        description="LLM-generated step-by-step plan (if available)"
    )
