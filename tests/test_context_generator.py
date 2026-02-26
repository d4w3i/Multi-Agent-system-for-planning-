"""Unit tests for ContextGenerator."""

import pytest
import json
from pathlib import Path
from context_retrieving.call_graph_builder import CallGraphBuilder
from context_retrieving.context_generator import ContextGenerator


class TestContextGenerator:
    """Test suite for ContextGenerator class."""

    @pytest.fixture
    def sample_graph(self):
        """Create a call graph from simple_functions.py fixture."""
        builder = CallGraphBuilder()
        builder.parse_file("tests/fixtures/simple_functions.py")
        builder._mark_special_nodes()
        return builder.call_graph

    @pytest.fixture
    def generator(self, sample_graph):
        """Create a ContextGenerator with sample graph."""
        return ContextGenerator(sample_graph)

    @pytest.fixture
    def recursive_graph(self):
        """Create a call graph from recursive.py fixture."""
        builder = CallGraphBuilder()
        builder.parse_file("tests/fixtures/recursive.py")
        builder._mark_special_nodes()
        return builder.call_graph

    @pytest.fixture
    def class_graph(self):
        """Create a call graph from class_methods.py fixture."""
        builder = CallGraphBuilder()
        builder.parse_file("tests/fixtures/class_methods.py")
        builder._mark_special_nodes()
        return builder.call_graph

    # ========== Unit Tests - Dependency Collection ==========

    def test_get_all_dependencies(self, generator):
        """Test recursive dependency collection."""
        # main_function -> process_data -> helper_function
        deps = generator.get_all_dependencies("main_function")

        # Should include all functions in the chain
        assert "main_function" in deps
        assert "process_data" in deps
        assert "helper_function" in deps

        # Should have exactly 3 functions
        assert len(deps) == 3

    def test_get_dependencies_leaf_function(self, generator):
        """Test dependency collection for leaf function (no dependencies)."""
        # helper_function doesn't call anyone
        deps = generator.get_all_dependencies("helper_function")

        # Should only contain itself
        assert deps == {"helper_function"}

    def test_get_dependencies_middle_function(self, generator):
        """Test dependency collection for middle function in chain."""
        # process_data -> helper_function
        deps = generator.get_all_dependencies("process_data")

        # Should include itself and helper_function
        assert "process_data" in deps
        assert "helper_function" in deps
        assert len(deps) == 2

        # Should NOT include main_function (it calls process_data, not vice versa)
        assert "main_function" not in deps

    def test_get_dependencies_nonexistent_function(self, generator):
        """Test dependency collection for non-existent function."""
        deps = generator.get_all_dependencies("nonexistent_function")

        # Should return empty set
        assert deps == set()

    # ========== Edge Cases - Circular Dependencies ==========

    def test_circular_dependency(self, recursive_graph):
        """Test handling of circular dependencies (recursive functions)."""
        generator = ContextGenerator(recursive_graph)

        # fibonacci calls itself - circular dependency
        deps = generator.get_all_dependencies("fibonacci")

        # Should handle gracefully without infinite loop
        assert "fibonacci" in deps

        # Should only appear once (no duplicates)
        assert len(deps) == 1

    def test_deep_dependency_chain(self):
        """Test deep dependency chain with class methods."""
        builder = CallGraphBuilder()
        builder.parse_file("tests/fixtures/class_methods.py")
        builder._mark_special_nodes()
        generator = ContextGenerator(builder.call_graph)

        # get_result -> process -> _validate and _compute
        deps = generator.get_all_dependencies("DataProcessor.get_result")

        # Should include all functions in the chain
        assert "DataProcessor.get_result" in deps
        assert "DataProcessor.process" in deps
        assert "DataProcessor._validate" in deps
        assert "DataProcessor._compute" in deps

    # ========== Context File Generation ==========

    def test_generate_context_file(self, generator, tmp_path):
        """Test context file generation."""
        output_dir = tmp_path / "context_files"

        # Generate context for process_data
        result_path = generator.generate_context_file("process_data", str(output_dir))

        # Verify file was created
        assert result_path is not None
        assert Path(result_path).exists()

        # Read and verify content
        with open(result_path) as f:
            content = f.read()

            # Should have header
            assert "CONTEXT FILE FOR: process_data" in content
            assert "File:" in content
            assert "Line:" in content

            # Should have sections
            assert "DEPENDENCIES" in content
            assert "TARGET FUNCTION" in content
            assert "USAGE CONTEXT" in content

            # Should include dependency code (helper_function)
            assert "def helper_function" in content

            # Should include target function code
            assert "def process_data" in content

            # Should include caller info (main_function)
            assert "main_function" in content

    def test_generate_context_file_without_callers(self, generator, tmp_path):
        """Test context file generation without caller section."""
        output_dir = tmp_path / "context_files"

        # Generate without callers
        result_path = generator.generate_context_file(
            "process_data",
            str(output_dir),
            include_callers=False
        )

        # Read content
        with open(result_path) as f:
            content = f.read()

            # Should NOT have usage context section
            assert "USAGE CONTEXT" not in content

    def test_generate_context_file_for_leaf(self, generator, tmp_path):
        """Test context file generation for leaf function."""
        output_dir = tmp_path / "context_files"

        # Generate for helper_function (leaf)
        result_path = generator.generate_context_file("helper_function", str(output_dir))

        # Verify file was created
        assert Path(result_path).exists()

        # Read content
        with open(result_path) as f:
            content = f.read()

            # Should have target function
            assert "def helper_function" in content

            # Dependencies section should be minimal or absent
            # (leaf functions have no dependencies except themselves)
            assert "TARGET FUNCTION" in content

    def test_generate_context_file_nonexistent(self, generator, tmp_path):
        """Test context file generation for non-existent function."""
        output_dir = tmp_path / "context_files"

        # Try to generate for non-existent function
        result = generator.generate_context_file("nonexistent", str(output_dir))

        # Should return None or not create file
        assert result is None

    # ========== Metadata JSON Generation ==========

    def test_generate_metadata_json(self, generator, tmp_path):
        """Test metadata JSON file generation."""
        output_dir = tmp_path / "context_files"

        # Generate context (also generates metadata)
        generator.generate_context_file("process_data", str(output_dir))

        # Verify metadata file exists
        metadata_path = output_dir / "process_data_metadata.json"
        assert metadata_path.exists()

        # Read and verify metadata
        with open(metadata_path) as f:
            metadata = json.load(f)

            # Verify structure
            assert "target_function" in metadata
            assert "file" in metadata
            assert "line" in metadata
            assert "dependencies" in metadata
            assert "called_by" in metadata
            assert "is_leaf" in metadata
            assert "is_entry_point" in metadata

            # Verify values
            assert metadata["target_function"] == "process_data"
            assert metadata["is_leaf"] == False
            assert metadata["is_entry_point"] == False

            # Verify dependencies list
            assert "helper_function" in metadata["dependencies"]

            # Verify called_by list
            assert "main_function" in metadata["called_by"]

    # ========== Generate All Context Files ==========

    def test_generate_all_context_files(self, generator, tmp_path):
        """Test generating context files for all functions."""
        output_dir = tmp_path / "context_files"

        # Generate all
        generator.generate_all_context_files(str(output_dir))

        # Verify output directory exists
        assert output_dir.exists()

        # Verify context files were created for all functions
        expected_files = [
            "helper_function_context.txt",
            "process_data_context.txt",
            "main_function_context.txt"
        ]

        for filename in expected_files:
            file_path = output_dir / filename
            assert file_path.exists(), f"Missing: {filename}"

        # Verify metadata files were also created
        expected_metadata = [
            "helper_function_metadata.json",
            "process_data_metadata.json",
            "main_function_metadata.json"
        ]

        for filename in expected_metadata:
            file_path = output_dir / filename
            assert file_path.exists(), f"Missing: {filename}"

    def test_context_file_directory_creation(self, generator, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        # Use a nested path that doesn't exist
        output_dir = tmp_path / "level1" / "level2" / "context_files"
        assert not output_dir.exists()

        # Generate context file
        generator.generate_context_file("helper_function", str(output_dir))

        # Verify directory was created
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_context_content_quality(self, class_graph, tmp_path):
        """Test that generated context has high quality content."""
        generator = ContextGenerator(class_graph)
        output_dir = tmp_path / "context_files"

        # Generate context for a method
        result_path = generator.generate_context_file(
            "DataProcessor.process",
            str(output_dir)
        )

        # Read content
        with open(result_path) as f:
            content = f.read()

            # Should include class context
            assert "DataProcessor" in content

            # Should include dependencies (methods it calls)
            assert "_validate" in content or "DataProcessor._validate" in content
            assert "_compute" in content or "DataProcessor._compute" in content

            # Should be well-formatted
            assert "def process" in content
            assert "=" * 80 in content  # Header separator

    def test_no_duplicate_dependencies(self, recursive_graph):
        """Test that dependencies are not duplicated."""
        generator = ContextGenerator(recursive_graph)

        deps = generator.get_all_dependencies("fibonacci")

        # Convert to list and verify no duplicates
        deps_list = list(deps)
        assert len(deps_list) == len(set(deps_list))
