"""
sbuild - Build session context manager

Provides BuildSession for managing build lifecycle including logging,
console output, error handling, and runner instantiation.
"""

import os
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from rich.panel import Panel

from .config import BuildConfig
from .console import console as base_console
from .exceptions import BuildError, ConfigError
from .logging import LogManager, LoggingConsole

if TYPE_CHECKING:
    from .runners.base import BaseRunner


class BuildSession:
    """Context manager for build lifecycle.

    Handles:
    - Log file setup and rotation
    - Console output with logging
    - Error handling and exit codes
    - Runner instantiation based on platform
    """

    def __init__(
        self,
        platform: str = "native",
        build_type: str = "debug",
        verbose: bool = False,
        jobs: int = os.cpu_count() or 4,
        cmake_args: Optional[str] = None,
        build_number: Optional[int] = None,
        project_root: Optional[Path] = None,
    ):
        """Initialize build session.

        Args:
            platform: Build platform ("native" or "wasm")
            build_type: Build type ("debug" or "release")
            verbose: Show verbose output
            jobs: Number of parallel jobs
            cmake_args: Additional CMake arguments
            build_number: Override build number
            project_root: Project root directory (auto-detected if None)
        """
        self.platform = platform
        self.build_type = build_type.capitalize()
        self.verbose = verbose
        self.jobs = jobs
        self.cmake_args = cmake_args
        self.build_number = build_number

        # Auto-detect project root if not provided
        if project_root is None:
            self.project_root = Path.cwd()
        else:
            self.project_root = project_root

        # Will be initialized in __enter__
        self.config: Optional[BuildConfig] = None
        self.log_manager: Optional[LogManager] = None
        self.log_path: Optional[Path] = None
        self.console: Optional[LoggingConsole] = None
        self._runner: Optional["BaseRunner"] = None
        self._error: Optional[Exception] = None

    def __enter__(self) -> "BuildSession":
        """Set up logging and create build configuration."""
        # Initialize log manager
        self.log_manager = LogManager(self.project_root)
        self.log_path = self.log_manager.start_logging()

        # Create logging console that writes to both console and log file
        self.console = LoggingConsole(base_console, self.log_manager)

        # Log configuration
        self.log_manager.write_section("Build Configuration")
        self.log_manager.write(f"Platform: {self.platform}")
        self.log_manager.write(f"Build type: {self.build_type}")
        self.log_manager.write(f"Jobs: {self.jobs}")
        self.log_manager.write(f"Verbose: {self.verbose}")
        if self.build_number is not None:
            self.log_manager.write(f"Build number: {self.build_number}")
        if self.cmake_args:
            self.log_manager.write(f"CMake args: {self.cmake_args}")

        # Create build configuration
        self.config = BuildConfig(
            project_root=self.project_root,
            build_type=self.build_type,
            platform=self.platform,
            verbose=self.verbose,
            jobs=self.jobs,
            cmake_args=self.cmake_args,
            build_number=self.build_number,
        )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Handle errors and cleanup logging."""
        suppress_exception = False

        if exc_type is not None:
            self._error = exc_val

            if isinstance(exc_val, SystemExit):
                # SystemExit from exit_with_error() - don't suppress, let it propagate
                suppress_exception = False
            elif isinstance(exc_val, (BuildError, ConfigError)):
                self.console.print(f"\n[red]Error: {exc_val}[/red]")
                if self.log_manager:
                    self.log_manager.write(f"Fatal error: {exc_val}")
                suppress_exception = True
            elif isinstance(exc_val, KeyboardInterrupt):
                self.console.print("\n[yellow]Interrupted[/yellow]")
                if self.log_manager:
                    self.log_manager.write("Build interrupted by user")
                suppress_exception = True
            else:
                self.console.print(f"\n[red]Unexpected error: {exc_val}[/red]")
                if self.log_manager:
                    self.log_manager.write(f"Fatal error: {exc_val}")
                suppress_exception = True

        # Always close log manager
        if self.log_manager:
            self.log_manager.close()

        return suppress_exception

    @property
    def runner(self) -> "BaseRunner":
        """Get the appropriate runner for the platform (lazy initialization)."""
        if self._runner is None:
            self._runner = self._create_runner()
        return self._runner

    def _create_runner(self) -> "BaseRunner":
        """Create runner based on platform."""
        from .runners import NativeRunner, WasmRunner

        if self.config is None:
            raise RuntimeError("BuildSession not entered - use 'with' statement")

        if self.platform == "wasm":
            return WasmRunner(self.config, self.log_manager)
        return NativeRunner(self.config, self.log_manager)

    def show_header(self, action: str) -> None:
        """Display build header with action and configuration."""
        if self.config is None or self.console is None:
            return

        # Show setup info if runner has it
        if hasattr(self.runner, "show_setup_info"):
            self.runner.show_setup_info()

        mode = f"[cyan]{self.build_type.upper()}[/cyan]"
        platform_str = (
            f" [magenta]{self.platform.upper()}[/magenta]"
            if self.platform == "wasm"
            else ""
        )
        self.console.print(
            Panel(
                f"{self.config.project_name} - {action.capitalize()} ({mode}{platform_str})",
                expand=False,
            )
        )
        self.console.print(f"[dim]Log file: {self.log_path}[/dim]\n")

    def show_success(self, action: str) -> None:
        """Display success message."""
        if self.console is None:
            return

        if action in ["build", "rebuild"]:
            self.console.print(
                f"\n[green]Build complete![/green] Output: [blue]{self.config.build_dir}[/blue]"
            )
        else:
            self.console.print(f"\n[green]{action.capitalize()} complete![/green]")
        self.console.print(f"[dim]Log saved to: {self.log_path}[/dim]")

    def show_failure(self, action: str) -> None:
        """Display failure message."""
        if self.console is None:
            return

        self.console.print(f"\n[red]{action.capitalize()} failed![/red]")
        self.console.print(f"[yellow]Check log for details: {self.log_path}[/yellow]")

    def exit_with_error(self, code: int = 1) -> None:
        """Exit the process with an error code."""
        if self.log_manager:
            self.log_manager.close()
        sys.exit(code)
