"""
sbuild - Console utilities

Provides a shared Rich console instance for consistent output formatting.
"""

from rich.console import Console

# Global console instance
_console = Console()

# Export as module-level variable for convenience
console = _console
