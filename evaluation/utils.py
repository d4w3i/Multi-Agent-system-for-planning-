"""
=============================================================================
UTILS.PY - Utility Functions for Logging and Error Handling
=============================================================================

This module provides helper functions for logging and error handling
in the evaluation package. It centralizes logging configuration
to ensure consistency throughout the package.

PURPOSE:
- Configure logging with a consistent format
- Provide helpers for colored messages (error, success, warning)
- Avoid duplicating logging configuration in every module

PYTHON LOGGING SYSTEM:

Python logging follows a hierarchy:
- Logger: object that receives messages (e.g.: getLogger('myapp'))
- Handler: where to send messages (console, file, etc.)
- Formatter: how to format messages

    Logger ('ground_truth_extractor')
    ├── ConsoleHandler (stdout)
    │   └── Formatter: "HH:MM:SS - LEVEL - message"
    └── FileHandler (optional)
        └── Formatter: "timestamp - name - LEVEL - message"

LOGGING LEVELS:
- DEBUG: Detailed information for debugging
- INFO: Confirmation that things are working
- WARNING: Something unexpected, but the program continues
- ERROR: Serious problem, some functionality is not working
- CRITICAL: Fatal error, the program may terminate

ANSI COLORS:
Colored messages use ANSI escape codes:
- \033[91m = Red (errors)
- \033[92m = Green (success)
- \033[93m = Yellow (warning)
- \033[0m = Reset (back to normal)

USAGE:

    from evaluation.utils import setup_logging, log_error, log_success

    # Initial setup
    logger = setup_logging()

    # Normal logger usage
    logger.info("Processing started")

    # Colored helpers
    log_error("Something went wrong")
    log_success("Task completed")
=============================================================================
"""
import logging
from pathlib import Path
from typing import Optional
import sys

# =============================================================================
# FUNCTION setup_logging - Logging System Configuration

def setup_logging(log_file: Optional[Path] = None) -> logging.Logger:
    """
    Configure and return a logger for the ground_truth_extractor package.

    This function:
    1. Creates/gets a logger with a specific name
    2. Configures a console handler
    3. (Optional) Configures a file handler
    4. Sets formatters for readable output

    Args:
        log_file (Optional[Path]): Optional path to save logs to file.
                                  If None, logs only to console.

    Returns:
        logging.Logger: Configured logger ready for use.
    """

    # -------------------------------------------------------------------------
    # Step 1: Get/create the logger
    logger = logging.getLogger('ground_truth_extractor')

    # Set the minimum logger level
    # INFO means DEBUG will be ignored (unless specific handlers override)
    logger.setLevel(logging.INFO)

    # -------------------------------------------------------------------------
    # Step 2: Avoid duplicate handlers
    # This prevents duplicate messages when multiple modules import
    if logger.handlers:
        return logger

    # -------------------------------------------------------------------------
    # Step 3: Configure Console Handler
    console_handler = logging.StreamHandler(sys.stdout)

    # INFO level for console - doesn't show DEBUG
    console_handler.setLevel(logging.INFO)

    # Formatter for console - compact format
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)

    # -------------------------------------------------------------------------
    # Step 4: Configure File Handler (optional)
    if log_file:
        # FileHandler writes to file
        file_handler = logging.FileHandler(log_file)

        # DEBUG level for file - captures everything
        file_handler.setLevel(logging.DEBUG)

        # More detailed formatter for file
        # Also includes the logger name (%(name)s)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)

        logger.addHandler(file_handler)

    return logger

# =============================================================================
# FUNCTION log_error - Helper for Colored Error Messages

def log_error(message: str):
    """
    Log an error message with red color.

    Uses the 'ground_truth_extractor' logger and wraps the message
    with ANSI color codes.

    ANSI CODES USED:
    - \033[91m : Start bright red color
    - \033[0m  : Reset color (back to default)

    Args:
        message (str): The error message to log.
    """

    # Get the logger (must already be configured with setup_logging)
    logger = logging.getLogger('ground_truth_extractor')

    # Log with ERROR level, wrapping the message in color codes
    logger.error(f"\033[91m{message}\033[0m")  # Red

# =============================================================================
# FUNCTION log_success - Helper for Colored Success Messages

def log_success(message: str):
    """
    Log a success message with green color.

    Uses the 'ground_truth_extractor' logger and wraps the message
    with ANSI color codes.

    ANSI CODES USED:
    - \033[92m : Start bright green color
    - \033[0m  : Reset color

    Args:
        message (str): The success message to log.

    """

    logger = logging.getLogger('ground_truth_extractor')

    # Log with INFO level (success is not an error)
    # \033[92m = bright green
    logger.info(f"\033[92m{message}\033[0m")  # Green

# =============================================================================
# FUNCTION log_warning - Helper for Colored Warning Messages

def log_warning(message: str):
    """
    Log a warning message with yellow color.

    Uses the 'ground_truth_extractor' logger and wraps the message
    with ANSI codes to render it yellow in the terminal.

    WHEN TO USE:
    - Non-ideal but non-blocking situations
    - Deprecation warnings
    - Missing data that will be ignored
    - Sub-optimal configurations

    ANSI CODES USED:
    - \033[93m : Start bright yellow color
    - \033[0m  : Reset color

    DIFFERENCE BETWEEN WARNING AND ERROR:
    - WARNING: The program continues but something may not be ideal
    - ERROR: Something went wrong and may impact the result

    Args:
        message (str): The warning message to log.

    Example:
        log_warning("No commit messages found, using empty list")
        # Output: 10:30:45 - WARNING - No commit messages found... (in yellow)

        log_warning(f"Skipping invalid file: {filename}")
        # Output: 10:30:45 - WARNING - Skipping invalid file: ... (in yellow)
    """

    logger = logging.getLogger('ground_truth_extractor')

    # Log with WARNING level
    # \033[93m = bright yellow
    logger.warning(f"\033[93m{message}\033[0m")  # Yellow
