"""
sbuild - Console utilities

Provides a shared Rich console instance for consistent output formatting.
"""

from rich.console import Console

# Global console instance
_console = Console()


def get_console() -> Console:
    """Get the global console instance"""
    return _console


# Export as module-level variable for convenience
console = _console
