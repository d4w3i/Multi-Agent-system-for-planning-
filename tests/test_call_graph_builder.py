"""Unit tests for CallGraphBuilder."""

import pytest
import json
from pathlib import Path
from context_retrieving.call_graph_builder import CallGraphBuilder


class TestCallGraphBuilder:
    """Test suite for CallGraphBuilder class."""

    @pytest.fixture
    def builder(self):
        """Create a fresh CallGraphBuilder instance for each test."""
        return CallGraphBuilder()

    # ========== Unit Tests - Parsing Base ==========

    def test_parse_simple_functions(self, builder):
        """Test parsing of simple standalone functions."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)

        # Verify all functions were extracted
        assert "helper_function" in builder.call_graph
        assert "process_data" in builder.call_graph
        assert "main_function" in builder.call_graph

        # Verify function properties
        assert builder.call_graph["helper_function"]["is_method"] == False
        assert builder.call_graph["process_data"]["is_method"] == False

        # Verify call relationships
        assert "helper_function" in builder.call_graph["process_data"]["calls"]
        assert "process_data" in builder.call_graph["main_function"]["calls"]

        # Verify reverse relationships
        assert "process_data" in builder.call_graph["helper_function"]["called_by"]
        assert "main_function" in builder.call_graph["process_data"]["called_by"]

    def test_parse_class_methods(self, builder):
        """Test parsing of class methods."""
        test_file = "tests/fixtures/class_methods.py"
        builder.parse_file(test_file)

        # Verify methods have correct full names
        assert "DataProcessor.__init__" in builder.call_graph
        assert "DataProcessor._validate" in builder.call_graph
        assert "DataProcessor.process" in builder.call_graph
        assert "DataProcessor._compute" in builder.call_graph
        assert "DataProcessor.get_result" in builder.call_graph

        # Verify they are marked as methods
        assert builder.call_graph["DataProcessor.__init__"]["is_method"] == True
        assert builder.call_graph["DataProcessor.process"]["is_method"] == True

        # Verify class_name is set
        assert builder.call_graph["DataProcessor.process"]["class_name"] == "DataProcessor"

        # Verify self.method() calls are resolved correctly
        assert "DataProcessor._validate" in builder.call_graph["DataProcessor.process"]["calls"]
        assert "DataProcessor._compute" in builder.call_graph["DataProcessor.process"]["calls"]
        assert "DataProcessor.process" in builder.call_graph["DataProcessor.get_result"]["calls"]

    def test_parse_recursive_function(self, builder):
        """Test detection of recursive function calls."""
        test_file = "tests/fixtures/recursive.py"
        builder.parse_file(test_file)

        # Verify recursive functions exist
        assert "fibonacci" in builder.call_graph
        assert "factorial" in builder.call_graph

        # Verify recursion is detected (function calls itself)
        assert "fibonacci" in builder.call_graph["fibonacci"]["calls"]
        assert "factorial" in builder.call_graph["factorial"]["calls"]

        # Verify it's in its own called_by list
        assert "fibonacci" in builder.call_graph["fibonacci"]["called_by"]
        assert "factorial" in builder.call_graph["factorial"]["called_by"]

    # ========== Edge Cases ==========

    def test_empty_file(self, builder):
        """Test parsing an empty file doesn't crash."""
        test_file = "tests/fixtures/empty_file.py"
        builder.parse_file(test_file)

        # Should not crash, and call_graph should be empty
        assert len(builder.call_graph) == 0

    def test_builtin_calls_not_tracked(self, builder):
        """Test that built-in function calls are not tracked."""
        test_file = "tests/fixtures/edge_cases.py"
        builder.parse_file(test_file)

        # Function should exist
        assert "function_with_builtins" in builder.call_graph

        # But built-ins (print, len, max) should NOT be in calls
        calls = builder.call_graph["function_with_builtins"]["calls"]
        assert "print" not in calls
        assert "len" not in calls
        assert "max" not in calls

        # Should be marked as leaf since it doesn't call custom functions
        builder._mark_special_nodes()
        assert builder.call_graph["function_with_builtins"]["is_leaf"] == True

    def test_empty_function(self, builder):
        """Test function with only 'pass' is parsed correctly."""
        test_file = "tests/fixtures/edge_cases.py"
        builder.parse_file(test_file)

        assert "empty_function" in builder.call_graph
        assert builder.call_graph["empty_function"]["calls"] == []

    def test_single_line_function(self, builder):
        """Test single-line function definition."""
        test_file = "tests/fixtures/edge_cases.py"
        builder.parse_file(test_file)

        assert "single_line_function" in builder.call_graph
        assert builder.call_graph["single_line_function"]["is_method"] == False

    # ========== Marking Special Nodes ==========

    def test_mark_leaf_functions(self, builder):
        """Test that leaf functions are correctly identified."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)
        builder._mark_special_nodes()

        # helper_function doesn't call anyone - should be leaf
        assert builder.call_graph["helper_function"]["is_leaf"] == True

        # process_data calls helper_function - NOT a leaf
        assert builder.call_graph["process_data"]["is_leaf"] == False

        # main_function calls process_data - NOT a leaf
        assert builder.call_graph["main_function"]["is_leaf"] == False

    def test_mark_entry_points(self, builder):
        """Test that entry points are correctly identified."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)
        builder._mark_special_nodes()

        # main_function is not called by anyone - entry point
        assert builder.call_graph["main_function"]["is_entry_point"] == True

        # process_data is called by main_function - NOT entry point
        assert builder.call_graph["process_data"]["is_entry_point"] == False

        # helper_function is called by process_data - NOT entry point
        assert builder.call_graph["helper_function"]["is_entry_point"] == False

    # ========== Output Methods ==========

    def test_to_json(self, builder, tmp_path):
        """Test JSON output generation."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)
        builder._mark_special_nodes()

        # Generate JSON to temporary file
        output_file = tmp_path / "test_output.json"
        result = builder.to_json(str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Verify structure
        assert "functions" in result
        assert "edges" in result
        assert "stats" in result

        # Verify stats
        assert result["stats"]["total_functions"] == 3
        assert result["stats"]["entry_points"] == 1
        assert result["stats"]["leaf_functions"] == 1

        # Verify edges
        edges = result["edges"]
        assert {"from": "process_data", "to": "helper_function"} in edges
        assert {"from": "main_function", "to": "process_data"} in edges

        # Verify JSON is valid by reading it back
        with open(output_file) as f:
            loaded = json.load(f)
            assert loaded == result

    def test_to_mermaid(self, builder, tmp_path):
        """Test Mermaid diagram generation."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)
        builder._mark_special_nodes()

        # Generate Mermaid to temporary file
        output_file = tmp_path / "test_output.mmd"
        diagram = builder.to_mermaid(str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Verify diagram contains expected elements
        assert "graph TD" in diagram
        assert "main_function" in diagram
        assert "process_data" in diagram
        assert "helper_function" in diagram

        # Verify entry point styling
        assert ":::entry" in diagram

        # Verify leaf function styling
        assert ":::leaf" in diagram

        # Verify arrows exist
        assert "-->" in diagram

        # Read file and verify it matches
        with open(output_file) as f:
            file_content = f.read()
            assert file_content == diagram

    def test_analyze_repository(self, builder, tmp_path):
        """Test analyzing entire repository."""
        # Use the fixtures directory as a mini repository
        result = builder.analyze_repository("tests/fixtures")

        # Should have found functions from multiple files
        assert len(result) > 0

        # Should have functions from different files
        assert "helper_function" in result  # from simple_functions.py
        assert "DataProcessor.__init__" in result  # from class_methods.py
        assert "fibonacci" in result  # from recursive.py

        # Verify special nodes were marked
        assert "is_leaf" in result["helper_function"]
        assert "is_entry_point" in result["helper_function"]

    def test_file_and_line_tracking(self, builder):
        """Test that file paths and line numbers are tracked."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)

        # Verify file path is stored
        assert builder.call_graph["helper_function"]["file"] == test_file

        # Verify line numbers are positive integers
        assert builder.call_graph["helper_function"]["line"] > 0
        assert builder.call_graph["process_data"]["line"] > 0

        # Verify lines are in order (helper comes before process_data in file)
        assert builder.call_graph["helper_function"]["line"] < builder.call_graph["process_data"]["line"]

    def test_code_extraction(self, builder):
        """Test that function code is extracted correctly."""
        test_file = "tests/fixtures/simple_functions.py"
        builder.parse_file(test_file)

        # Verify code was extracted
        code = builder.call_graph["helper_function"]["code"]
        assert code is not None
        assert len(code) > 0

        # Verify code contains function definition
        assert "def helper_function" in code
        assert "return 42" in code
