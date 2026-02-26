"""Class with methods fixture for testing call graph builder."""

class DataProcessor:
    """A simple class with methods that call each other."""

    def __init__(self, value):
        """Initialize the processor."""
        self.value = value
        self.result = None

    def _validate(self):
        """Private method to validate data."""
        return self.value > 0

    def process(self):
        """Process the data using validation."""
        if self._validate():
            self.result = self._compute()
        return self.result

    def _compute(self):
        """Private method to compute result."""
        return self.value * 2

    def get_result(self):
        """Get the processed result."""
        if self.result is None:
            self.process()
        return self.result
