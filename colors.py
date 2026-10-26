import os
import sys

RESET = "\033[0m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"

_enabled = False


def setup(force_off=False):
    global _enabled
    _enabled = (not force_off) and sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(text, color):
    """Pad first, then paint, so ANSI codes don't break column alignment."""
    if _enabled and color:
        return f"{color}{text}{RESET}"
    return text