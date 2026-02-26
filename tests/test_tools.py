"""Unit tests for tools.py utility functions."""

import pytest
from GenAI.tools import get_function_context


class TestGetFunctionContext:
    """Test suite for get_function_context function."""

    def test_get_function_context_returns_string(self):
        """Test that function returns a string for valid function."""
        context = get_function_context("helper_function", repo_path="tests/fixtures")

        # Should return a string
        assert context is not None
        assert isinstance(context, str)
        assert len(context) > 0

    def test_get_function_context_nonexistent(self):
        """Test that function returns None for non-existent function."""
        context = get_function_context("nonexistent_function", repo_path="tests/fixtures")

        # Should return None
        assert context is None

    def test_context_has_header(self):
        """Test that context string has correct header."""
        context = get_function_context("helper_function", repo_path="tests/fixtures")

        # Verify header elements
        assert "CONTEXT FILE FOR: helper_function" in context
        assert "Generated from call graph analysis" in context
        assert "File:" in context
        assert "Line:" in context
        assert "Dependencies:" in context
        assert "Called by:" in context

    def test_context_has_sections(self):
        """Test that context has all required sections."""
        context = get_function_context("process_data", repo_path="tests/fixtures")

        # Should have all three sections
        assert "DEPENDENCIES" in context
        assert "TARGET FUNCTION" in context
        assert "USAGE CONTEXT" in context

        # Should contain separator
        assert "=" * 80 in context

    def test_context_contains_dependency_code(self):
        """Test that dependencies section contains actual code."""
        context = get_function_context("process_data", repo_path="tests/fixtures")

        # process_data calls helper_function, so helper should be in dependencies
        assert "def helper_function" in context

    def test_context_contains_target_code(self):
        """Test that target function code is included."""
        context = get_function_context("process_data", repo_path="tests/fixtures")

        # Should contain the target function definition
        assert "def process_data" in context
        assert "result = helper_function()" in context

    def test_context_contains_caller_info(self):
        """Test that caller information is included."""
        context = get_function_context("process_data", repo_path="tests/fixtures")

        # main_function calls process_data, so should be in USAGE CONTEXT
        assert "main_function" in context

    def test_context_without_callers(self):
        """Test include_callers=False flag."""
        context = get_function_context("process_data", repo_path="tests/fixtures", include_callers=False)

        # Should NOT have usage context section
        assert "USAGE CONTEXT" not in context

        # Should still have other sections
        assert "TARGET FUNCTION" in context
        assert "def process_data" in context

    def test_context_for_leaf_function(self):
        """Test context for a leaf function (no dependencies)."""
        context = get_function_context("helper_function", repo_path="tests/fixtures")

        # Should have target function
        assert "def helper_function" in context

        # Dependencies section should be minimal or show 0 dependencies
        assert "Dependencies: 0" in context

    def test_context_for_class_method(self):
        """Test context for a class method."""
        context = get_function_context("DataProcessor.process", repo_path="tests/fixtures")

        # Should return context
        assert context is not None

        # Should contain the method
        assert "def process" in context

        # Should contain dependencies (methods it calls)
        assert "_validate" in context or "DataProcessor._validate" in context
        assert "_compute" in context or "DataProcessor._compute" in context

    def test_context_for_recursive_function(self):
        """Test context for a recursive function."""
        context = get_function_context("fibonacci", repo_path="tests/fixtures")

        # Should return context
        assert context is not None

        # Should contain the function
        assert "def fibonacci" in context

        # Should handle recursion without infinite loop
        # (fibonacci appears in its own dependencies)
        assert "fibonacci" in context

    def test_context_format_consistency(self):
        """Test that format matches context_files output."""
        context = get_function_context("process_data", repo_path="tests/fixtures")

        # Check for consistent formatting
        lines = context.split('\n')

        # First line should be header comment
        assert lines[0].startswith("# CONTEXT FILE FOR:")

        # Should have comment lines
        comment_lines = [l for l in lines if l.startswith("#")]
        assert len(comment_lines) > 0

        # Should have code lines (not comments)
        code_lines = [l for l in lines if not l.startswith("#") and l.strip()]
        assert len(code_lines) > 0

    def test_different_repo_path(self):
        """Test analyzing a different repository path."""
        # Analyze the main codebase instead of fixtures
        context = get_function_context("CallGraphBuilder.__init__", repo_path=".")

        # Should find it
        assert context is not None
        assert "CallGraphBuilder.__init__" in context
        assert "def __init__" in context

    def test_context_metadata_accuracy(self):
        """Test that metadata in header is accurate."""
        context = get_function_context("process_data", repo_path="tests/fixtures")

        # Should have file path
        assert "simple_functions.py" in context

        # Should have line number (positive integer)
        import re
        line_match = re.search(r"# Line: (\d+)", context)
        assert line_match is not None
        line_num = int(line_match.group(1))
        assert line_num > 0

        # Should have dependency count
        deps_match = re.search(r"# Dependencies: (\d+)", context)
        assert deps_match is not None
        deps_count = int(deps_match.group(1))
        # process_data calls helper_function, so should have 1 dependency
        assert deps_count == 1

        # Should have caller count
        called_match = re.search(r"# Called by: (\d+)", context)
        assert called_match is not None
        called_count = int(called_match.group(1))
        # process_data is called by main_function, so should have 1 caller
        assert called_count == 1
