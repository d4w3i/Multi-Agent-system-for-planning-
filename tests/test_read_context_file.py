"""Tests for the _read_file_impl tool."""

from GenAI.tools import _read_file_impl


def test_read_existing_file(tmp_path):
    """Test reading an existing file."""
    test_content = "# CONTEXT FILE FOR: test_function\n\ndef test_function():\n    return 42\n"
    test_file = tmp_path / "test_context.txt"
    test_file.write_text(test_content, encoding="utf-8")

    content = _read_file_impl(str(test_file), verbose=False)
    assert test_content in content


def test_file_not_found():
    """Test handling of non-existent file."""
    result = _read_file_impl("non_existent_file_12345.txt", verbose=False)
    assert "File Not Found" in result or "\u274c" in result


def test_directory_traversal_prevention():
    """Test directory traversal prevention."""
    dangerous_paths = [
        "../../../etc/passwd",
        "output/../../../secret.txt",
        "context_files/../../sensitive_data.txt",
    ]

    for path in dangerous_paths:
        result = _read_file_impl(path, verbose=False)
        assert "Security Error" in result or "directory traversal" in result or "\u274c" in result, (
            f"Directory traversal not prevented for: {path}"
        )


def test_encoding_fallback(tmp_path):
    """Test fallback encoding for non-UTF8 files."""
    test_file = tmp_path / "latin1_context.txt"
    content_bytes = "Test con caratteri speciali: \xe0\xe8\xe9\xec\xf2\xf9".encode("latin-1")
    test_file.write_bytes(content_bytes)

    result = _read_file_impl(str(test_file), verbose=False)
    assert result and "Error" not in result
