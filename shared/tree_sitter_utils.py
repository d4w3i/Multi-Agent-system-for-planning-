"""
Shared Tree-sitter utilities used by call_graph_builder and function_matcher.
"""


def get_node_text(node, code_bytes: bytes) -> str:
    """
    Extract the text corresponding to a Tree-sitter AST node.

    Tree-sitter stores only byte offsets in the source code, not the text
    itself. This extracts the original text using start_byte/end_byte.

    Args:
        node: Tree-sitter AST node
        code_bytes: Source file content as bytes

    Returns:
        The text corresponding to the node, decoded as UTF-8
    """
    return code_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')
