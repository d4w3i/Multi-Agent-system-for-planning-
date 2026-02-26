"""
=============================================================================
TERMINAL.PY - Terminal UI Helpers
=============================================================================

This module provides utilities for creating interactive terminal interfaces
with colored output and animated spinners.

COMPONENTS:

    Colors          ANSI color codes for terminal output
    Spinner         Animated spinner for long-running operations
    print_header    Print a styled section header
    print_step      Print a numbered step indicator
    print_success   Print a success message with checkmark
    print_error     Print an error message with X mark

USAGE:

    from shared.terminal import Spinner, Colors, print_header

    # Using colors directly
    print(f"{Colors.GREEN}Success!{Colors.RESET}")

    # Using the spinner as a context manager
    spinner = Spinner("Processing data")
    spinner.start()
    try:
        do_work()
    finally:
        spinner.stop("Done!")

    # Using print helpers
    print_header("Analysis Results")
    print_step(1, "Loading data")
    print_success("Data loaded successfully")
    print_error("Failed to connect")

=============================================================================
"""

import sys
import time
import threading


# =============================================================================
# CLASS Colors - ANSI Terminal Color Codes
# =============================================================================

class Colors:
    """
    ANSI escape codes for colored terminal output.

    USAGE:
        print(f"{Colors.GREEN}Success{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}Header{Colors.RESET}")

    AVAILABLE COLORS:
        CYAN, GREEN, RED, YELLOW, BLUE

    MODIFIERS:
        BOLD - Make text bold
        RESET - Reset all formatting
    """
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


# =============================================================================
# CLASS Spinner - Animated Progress Indicator
# =============================================================================

class Spinner:
    """
    Animated spinner for long-running operations.

    Displays a bouncing dot animation in the terminal while a task runs
    in the background. Thread-safe and non-blocking.

    USAGE:
        spinner = Spinner("Processing")
        spinner.start()
        try:
            do_long_task()
        finally:
            spinner.stop("Complete!")

    ANIMATION:
        ( *    ) → (  *   ) → (   *  ) → ... → (*     )
    """

    def __init__(self, message: str = "Processing"):
        """
        Initialize the spinner.

        Args:
            message: Text to display next to the spinner animation
        """
        self.spinner_chars = [
            "( *    )",
            "(  *   )",
            "(   *  )",
            "(    * )",
            "(     *)",
            "(    * )",
            "(   *  )",
            "(  *   )",
            "( *    )",
            "(*     )"
        ]
        self.message = message
        self.running = False
        self.thread = None

    def _spin(self):
        """Internal method that runs the animation loop."""
        idx = 0
        while self.running:
            char = self.spinner_chars[idx % len(self.spinner_chars)]
            sys.stdout.write(f'\r{Colors.BLUE}{char}{Colors.RESET} {self.message}...')
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1

    def start(self):
        """Start the spinner animation in a background thread."""
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def stop(self, final_message: str = None):
        """
        Stop the spinner and optionally print a final message.

        Args:
            final_message: Optional message to print after stopping
        """
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write('\r' + ' ' * 80 + '\r')  # Clear line
        if final_message:
            print(final_message)
        sys.stdout.flush()


# =============================================================================
# PRINT HELPER FUNCTIONS
# =============================================================================

def print_header(text: str):
    """
    Print a colored section header with decorative borders.

    Args:
        text: Header text (will be centered)

    OUTPUT:
        ════════════════════════════════════════════════════════════
                                 Header Text
        ════════════════════════════════════════════════════════════
    """
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^60}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'═' * 60}{Colors.RESET}\n")


def print_step(step: int, text: str):
    """
    Print a numbered process step.

    Args:
        step: Step number
        text: Step description

    OUTPUT:
        [1] Step description
    """
    print(f"{Colors.BLUE}{Colors.BOLD}[{step}]{Colors.RESET} {text}")


def print_success(text: str):
    """
    Print a success message with green checkmark.

    Args:
        text: Success message

    OUTPUT:
        * Success message
    """
    print(f"{Colors.GREEN}* {text}{Colors.RESET}")


def print_error(text: str):
    """
    Print an error message with red X mark.

    Args:
        text: Error message

    OUTPUT:
        x Error message
    """
    print(f"{Colors.RED}x {text}{Colors.RESET}")
