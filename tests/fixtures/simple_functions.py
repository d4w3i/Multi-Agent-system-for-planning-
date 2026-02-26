"""Simple functions fixture for testing call graph builder."""

def helper_function():
    """A simple helper that does nothing."""
    return 42


def process_data(value):
    """Process data using helper function."""
    result = helper_function()
    return result + value


def main_function():
    """Entry point that calls process_data."""
    data = 10
    return process_data(data)
