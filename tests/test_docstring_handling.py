"""Tests for docstring handling in generated project_info.py files."""

import importlib.util

from context_retrieving.batch_context_retriever import sanitize_for_triple_quotes


def test_docstring_handling(tmp_path):
    """Test that generated project_info.py with docstrings compiles and imports correctly."""
    tree_content = '''
src/
  module.py:
    def example():
        """
        Multi-line docstring
        with multiple lines
        """
        pass
'''

    readme_content = '''
# My Project

Example code:
```python
def hello():
    """Greet the user"""
    print("Hello")
```

Note: Use ''' + "'" + ''' for string literals.
'''

    output = '"""Project Information - Auto-generated file"""\n\n'
    output += "DIRECTORY_TREE = '''"
    output += sanitize_for_triple_quotes(tree_content, "'''")
    output += "'''\n\n"
    output += "README = '''"
    output += sanitize_for_triple_quotes(readme_content, "'''")
    output += "'''\n"

    # Verify syntax is valid
    compile(output, "<test>", "exec")

    # Write and import the module
    temp_file = tmp_path / "project_info.py"
    temp_file.write_text(output, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("project_info", str(temp_file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert '"""' in module.DIRECTORY_TREE, "Docstring should be preserved"
    assert "def example():" in module.DIRECTORY_TREE, "Code should be present"
    assert "# My Project" in module.README, "README title should be present"
