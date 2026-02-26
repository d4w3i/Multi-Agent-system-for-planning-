"""Edge cases fixture for testing call graph builder."""

def empty_function():
    """Function that does nothing."""
    pass


def function_with_builtins():
    """Function that calls only built-in functions."""
    print("Hello")
    result = len([1, 2, 3])
    value = max(5, 10)
    return result + value


def function_with_external_lib():
    """Function that calls external library functions."""
    import os
    return os.path.exists("/tmp")


def single_line_function(): return 42
