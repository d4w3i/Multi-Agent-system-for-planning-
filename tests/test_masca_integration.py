"""Tests for MASCA agent integration."""

import os
from pathlib import Path

from GenAI.masca_runner import run_masca_analysis, save_masca_output


def test_masca_import():
    """Test that masca_runner module is importable."""
    assert callable(run_masca_analysis)
    assert callable(save_masca_output)


def test_masca_no_api_key(monkeypatch):
    """Test that MASCA handles missing API key correctly."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = run_masca_analysis("# Test README", "test/\n  file.py")
    assert isinstance(result, dict)
    assert "OPENAI_API_KEY" in result["output"] and ("not found" in result["output"] or "non trovata" in result["output"])
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["total_tokens"] == 0


def test_save_output(tmp_path):
    """Test that saving output works correctly."""
    output_file = tmp_path / "masca_output.md"
    test_output = "# Test Analysis\n\nThis is a test."

    success = save_masca_output(test_output, str(output_file))

    assert success
    assert output_file.exists()
    content = output_file.read_text()
    assert "# Analisi del Progetto - Masca Agent" in content
    assert "This is a test" in content


def test_save_output_with_tree(tmp_path):
    """Test that saving output with directory tree works correctly."""
    output_file = tmp_path / "masca_output.md"
    test_output = "# Test Analysis\n\nThis is a test."
    test_tree = "src/\n  main.py\n  utils/\n    helper.py"

    success = save_masca_output(test_output, str(output_file), test_tree)

    assert success
    assert output_file.exists()
    content = output_file.read_text()
    assert "# Analisi del Progetto - Masca Agent" in content
    assert "This is a test" in content
    assert "main.py" in content
    assert "helper.py" in content
