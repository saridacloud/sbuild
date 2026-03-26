"""
sbuild - Build session context manager

Provides BuildSession for managing build lifecycle including logging,
console output, error handling, and runner instantiation.
"""

import sys
import time
from typing import Optional, TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel

from . import __version__
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
        config: BuildConfig,
        *,
        command: str = "unknown",
    ):
        """Initialize build session.

        Args:
            config: Fully-populated build configuration (from ConfigManager)
            command: CLI command name (build, rebuild, clean, etc.)
        """
        self.config = config
        self.command = command

        # Will be initialized in __enter__
        self.log_manager: Optional[LogManager] = None
        self.log_path: Optional["__builtins__.Path"] = None  # type: ignore[name-defined]
        self.console: Optional[LoggingConsole] = None
        self._runner: Optional["BaseRunner"] = None

        # Profiling timers
        self._session_start: float | None = None
        self._runner_elapsed: float | None = None

    def __enter__(self) -> "BuildSession":
        """Set up logging."""
        self._session_start = time.perf_counter()

        # Initialize log manager
        self.log_manager = LogManager(self.config.project_root)
        self.log_path = self.log_manager.start_logging()

        # Create logging console that writes to both console and log file
        self.console = LoggingConsole(base_console, self.log_manager)

        # Log command early for crash safety
        self.log_manager.write(f"Command: sbuild {self.command}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Handle errors and cleanup logging."""
        suppress_exception = False

        if exc_type is not None:
            if isinstance(exc_val, SystemExit):
                # SystemExit from exit_with_error() - don't suppress, let it propagate
                suppress_exception = False
            elif isinstance(exc_val, (BuildError, ConfigError)):
                self.console.print(f"\n[red]Error: {escape(str(exc_val))}[/red]")
                if self.log_manager:
                    self.log_manager.write(f"Fatal error: {exc_val}")
                suppress_exception = True
            elif isinstance(exc_val, KeyboardInterrupt):
                self.console.print("\n[yellow]Interrupted[/yellow]")
                if self.log_manager:
                    self.log_manager.write("Build interrupted by user")
                suppress_exception = True
            else:
                self.console.print(f"\n[red]Unexpected error: {escape(str(exc_val))}[/red]")
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
            t0 = time.perf_counter()
            self._runner = self._create_runner()
            self._runner_elapsed = time.perf_counter() - t0
            self._log_resolved_config()
        return self._runner

    def _create_runner(self) -> "BaseRunner":
        """Create runner based on platform."""
        from .runners import RUNNER_REGISTRY

        runner_cls = RUNNER_REGISTRY.get(self.config.platform)
        if runner_cls is None:
            raise ConfigError(f"Unknown platform: {self.config.platform}")
        return runner_cls(self.config, self.log_manager)

    def _log_resolved_config(self) -> None:
        """Write full resolved configuration to log file."""
        if self.log_manager is None or self._runner is None:
            return

        self.log_manager.write_section("Resolved Configuration")

        # General info
        self.log_manager.write(f"  sbuild version: {__version__}")
        self.log_manager.write(f"  Command: {self.command}")
        self.log_manager.write(f"  Project: {self.config.project_name} {self.config.version}")
        self.log_manager.write(f"  Project root: {self.config.project_root}")
        self.log_manager.write(f"  Platform: {self.config.platform}")
        self.log_manager.write(f"  Build type: {self.config.build_type}")
        self.log_manager.write(f"  Jobs: {self.config.jobs}")
        self.log_manager.write(f"  Verbose: {self.config.verbose}")
        self.log_manager.write(f"  Build dir base: {self.config.build_dir_base}")
        self.log_manager.write(f"  Build directory: {self.config.build_dir}")
        self.log_manager.write(f"  Configure preset: {self.config.preset_name}")
        self.log_manager.write(f"  Build preset: {self.config.build_preset_name}")
        if self.config.cmake_args:
            self.log_manager.write(f"  CMake args: {self.config.cmake_args}")
        if self.config.build_number is not None:
            self.log_manager.write(f"  Build number: {self.config.build_number}")
        if hasattr(self.config.platform_config, "profile_override") and self.config.platform_config.profile_override:
            self.log_manager.write(f"  Profile override: {self.config.platform_config.profile_override}")

        # Profiling
        if self._runner_elapsed is not None:
            self.log_manager.write(f"  Runner init: {self._runner_elapsed:.2f}s")

        # Runner-specific sections
        for section_name, items in self._runner.get_config_summary().items():
            self.log_manager.write_section(section_name)
            for label, value in items:
                self.log_manager.write(f"  {label}: {value}")

    def _show_config_console(self) -> None:
        """Print resolved configuration to console with Rich markup."""
        if self._runner is None:
            return

        # General info
        base_console.print(f"[green]sbuild version:[/green] [dim]{__version__}[/dim]")
        base_console.print(f"[green]Command:[/green] [dim]{escape(self.command)}[/dim]")
        base_console.print(
            f"[green]Project:[/green] [dim]{escape(self.config.project_name)} {escape(self.config.version)}[/dim]"
        )
        base_console.print(f"[green]Project root:[/green] [dim]{escape(str(self.config.project_root))}[/dim]")
        base_console.print(f"[green]Build directory:[/green] [dim]{escape(str(self.config.build_dir))}[/dim]")
        base_console.print(
            f"[green]Configure preset:[/green] [dim]{self.config.preset_name}[/dim]"
        )
        base_console.print(
            f"[green]Build preset:[/green] [dim]{self.config.build_preset_name}[/dim]"
        )
        if self.config.cmake_args:
            base_console.print(f"[green]CMake args:[/green] [dim]{escape(self.config.cmake_args)}[/dim]")
        if self.config.build_number is not None:
            base_console.print(f"[green]Build number:[/green] [dim]{self.config.build_number}[/dim]")

        # Profiling
        parts = []
        if self._runner_elapsed is not None:
            parts.append(f"init: {self._runner_elapsed:.2f}s")
        if parts:
            base_console.print(f"[green]Profiling:[/green] [dim]{', '.join(parts)}[/dim]")

        # Runner-specific sections
        for section_name, items in self._runner.get_config_summary().items():
            base_console.print(f"[bold]{section_name}:[/bold]")
            for label, value in items:
                base_console.print(f"  [green]{escape(label)}:[/green] [dim]{escape(value)}[/dim]")

    def show_header(self) -> None:
        """Display build header with command and configuration."""
        if self.console is None:
            return

        # Show critical warnings from runner (e.g. vcvarsall not found)
        if hasattr(self.runner, "show_setup_info"):
            self.runner.show_setup_info()

        mode = f"[cyan]{self.config.build_type.upper()}[/cyan]"
        display = "WASM" if self.config.platform == "wasm" else ""
        platform_str = (
            f" [magenta]{display}[/magenta]"
            if display
            else ""
        )

        # Show target architecture for native builds
        arch_str = ""
        if hasattr(self.config.platform_config, "target_arch"):
            arch_str = f" - {self.config.platform_config.target_arch}"

        self.console.print(
            Panel(
                f"{escape(self.config.project_name)} - {self.command.capitalize()} ({mode}{platform_str}{arch_str})",
                expand=False,
            )
        )
        self.console.print(f"[dim]Log file: {escape(str(self.log_path))}[/dim]")

        if self.config.verbose:
            self._show_config_console()

        self.console.print()

    def show_success(self, action: str) -> None:
        """Display success message."""
        if self.console is None:
            return

        if action in ["build", "rebuild"]:
            self.console.print(
                f"\n[green]Build complete![/green] Output: [blue]{escape(str(self.config.build_dir))}[/blue]"
            )
        else:
            self.console.print(f"\n[green]{action.capitalize()} complete![/green]")
        if self._session_start is not None:
            total = time.perf_counter() - self._session_start
            self.console.print(f"[dim]Total time: {total:.2f}s[/dim]")
        self.console.print(f"[dim]Log saved to: {escape(str(self.log_path))}[/dim]")

    def show_failure(self, action: str) -> None:
        """Display failure message."""
        if self.console is None:
            return

        self.console.print(f"\n[red]{action.capitalize()} failed![/red]")
        if self._session_start is not None:
            total = time.perf_counter() - self._session_start
            self.console.print(f"[dim]Total time: {total:.2f}s[/dim]")
        self.console.print(f"[yellow]Check log for details: {escape(str(self.log_path))}[/yellow]")

    def exit_with_error(self, code: int = 1) -> None:
        """Exit the process with an error code."""
        if self.log_manager:
            self.log_manager.close()
        sys.exit(code)
