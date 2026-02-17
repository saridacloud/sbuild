"""
sbuild - Build session context manager

Provides BuildSession for managing build lifecycle including logging,
console output, error handling, and runner instantiation.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

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
        platform: str = "native",
        build_type: str = "debug",
        verbose: bool = False,
        jobs: int = os.cpu_count() or 4,
        cmake_args: Optional[str] = None,
        build_number: Optional[int] = None,
        project_root: Optional[Path] = None,
        arch: Optional[str] = None,
        profile: Optional[str] = None,
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
            arch: Target architecture (x86, x64, arm64)
            profile: Exact Conan profile name override
        """
        self.platform = platform
        self.build_type = build_type.capitalize()
        self.verbose = verbose
        self.jobs = jobs
        self.cmake_args = cmake_args
        self.build_number = build_number
        self.arch = arch
        self.profile = profile

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

        # Profiling timers
        self._session_start: float | None = None
        self._config_elapsed: float | None = None
        self._runner_elapsed: float | None = None

    def __enter__(self) -> "BuildSession":
        """Set up logging and create build configuration."""
        self._session_start = time.perf_counter()

        # Initialize log manager
        self.log_manager = LogManager(self.project_root)
        self.log_path = self.log_manager.start_logging()

        # Create logging console that writes to both console and log file
        self.console = LoggingConsole(base_console, self.log_manager)

        # Log configuration
        self.log_manager.write_section("CLI Parameters")
        self.log_manager.write(f"Platform: {self.platform}")
        self.log_manager.write(f"Build type: {self.build_type}")
        self.log_manager.write(f"Jobs: {self.jobs}")
        self.log_manager.write(f"Verbose: {self.verbose}")
        if self.arch:
            self.log_manager.write(f"Arch: {self.arch}")
        if self.profile:
            self.log_manager.write(f"Profile: {self.profile}")
        if self.build_number is not None:
            self.log_manager.write(f"Build number: {self.build_number}")
        if self.cmake_args:
            self.log_manager.write(f"CMake args: {self.cmake_args}")

        # Create build configuration (timed)
        t0 = time.perf_counter()
        self.config = BuildConfig(
            project_root=self.project_root,
            build_type=self.build_type,
            platform=self.platform,
            verbose=self.verbose,
            jobs=self.jobs,
            cmake_args=self.cmake_args,
            build_number=self.build_number,
            arch=self.arch,
            profile=self.profile,
        )
        self._config_elapsed = time.perf_counter() - t0

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Handle errors and cleanup logging."""
        suppress_exception = False

        if exc_type is not None:
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
            t0 = time.perf_counter()
            self._runner = self._create_runner()
            self._runner_elapsed = time.perf_counter() - t0
            self._log_resolved_config()
        return self._runner

    def _create_runner(self) -> "BaseRunner":
        """Create runner based on platform."""
        from .runners import RUNNER_REGISTRY

        if self.config is None:
            raise RuntimeError("BuildSession not entered - use 'with' statement")

        runner_cls = RUNNER_REGISTRY.get(self.platform)
        if runner_cls is None:
            raise ConfigError(f"Unknown platform: {self.platform}")
        return runner_cls(self.config, self.log_manager)

    def _log_resolved_config(self) -> None:
        """Write full resolved configuration to log file."""
        if self.log_manager is None or self.config is None or self._runner is None:
            return

        self.log_manager.write_section("Resolved Configuration")

        # General info
        self.log_manager.write(f"  sbuild version: {__version__}")
        self.log_manager.write(f"  Project: {self.config.project_name} {self.config.version}")
        self.log_manager.write(f"  Project root: {self.config.project_root}")
        self.log_manager.write(f"  Platform: {self.platform}")
        self.log_manager.write(f"  Build type: {self.build_type}")
        self.log_manager.write(f"  Jobs: {self.jobs}")
        self.log_manager.write(f"  Build directory: {self.config.build_dir}")
        self.log_manager.write(f"  Configure preset: {self.config.preset_name}")
        self.log_manager.write(f"  Build preset: {self.config.build_preset_name}")
        if self.cmake_args:
            self.log_manager.write(f"  CMake args: {self.cmake_args}")
        if self.build_number is not None:
            self.log_manager.write(f"  Build number: {self.build_number}")

        # Profiling
        if self._config_elapsed is not None:
            self.log_manager.write(f"  Config creation: {self._config_elapsed:.2f}s")
        if self._runner_elapsed is not None:
            self.log_manager.write(f"  Runner init: {self._runner_elapsed:.2f}s")

        # Runner-specific sections
        for section_name, items in self._runner.get_config_summary().items():
            self.log_manager.write_section(section_name)
            for label, value in items:
                self.log_manager.write(f"  {label}: {value}")

    def _show_config_console(self) -> None:
        """Print resolved configuration to console with Rich markup."""
        if self.config is None or self._runner is None:
            return

        # General info
        base_console.print(f"[green]sbuild version:[/green] [dim]{__version__}[/dim]")
        base_console.print(
            f"[green]Project:[/green] [dim]{self.config.project_name} {self.config.version}[/dim]"
        )
        base_console.print(f"[green]Project root:[/green] [dim]{self.config.project_root}[/dim]")
        base_console.print(f"[green]Build directory:[/green] [dim]{self.config.build_dir}[/dim]")
        base_console.print(
            f"[green]Configure preset:[/green] [dim]{self.config.preset_name}[/dim]"
        )
        base_console.print(
            f"[green]Build preset:[/green] [dim]{self.config.build_preset_name}[/dim]"
        )
        if self.cmake_args:
            base_console.print(f"[green]CMake args:[/green] [dim]{self.cmake_args}[/dim]")
        if self.build_number is not None:
            base_console.print(f"[green]Build number:[/green] [dim]{self.build_number}[/dim]")

        # Profiling
        parts = []
        if self._config_elapsed is not None:
            parts.append(f"config: {self._config_elapsed:.2f}s")
        if self._runner_elapsed is not None:
            parts.append(f"init: {self._runner_elapsed:.2f}s")
        if parts:
            base_console.print(f"[green]Profiling:[/green] [dim]{', '.join(parts)}[/dim]")

        # Runner-specific sections
        for section_name, items in self._runner.get_config_summary().items():
            base_console.print(f"[bold]{section_name}:[/bold]")
            for label, value in items:
                base_console.print(f"  [green]{label}:[/green] [dim]{value}[/dim]")

    def show_header(self, action: str) -> None:
        """Display build header with action and configuration."""
        if self.config is None or self.console is None:
            return

        # Show critical warnings from runner (e.g. vcvarsall not found)
        if hasattr(self.runner, "show_setup_info"):
            self.runner.show_setup_info()

        mode = f"[cyan]{self.build_type.upper()}[/cyan]"
        display = self.config.platform_config.display_name
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
                f"{self.config.project_name} - {action.capitalize()} ({mode}{platform_str}{arch_str})",
                expand=False,
            )
        )
        self.console.print(f"[dim]Log file: {self.log_path}[/dim]")

        if self.verbose:
            self._show_config_console()

        self.console.print()

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
        if self._session_start is not None:
            total = time.perf_counter() - self._session_start
            self.console.print(f"[dim]Total time: {total:.2f}s[/dim]")
        self.console.print(f"[dim]Log saved to: {self.log_path}[/dim]")

    def show_failure(self, action: str) -> None:
        """Display failure message."""
        if self.console is None:
            return

        self.console.print(f"\n[red]{action.capitalize()} failed![/red]")
        if self._session_start is not None:
            total = time.perf_counter() - self._session_start
            self.console.print(f"[dim]Total time: {total:.2f}s[/dim]")
        self.console.print(f"[yellow]Check log for details: {self.log_path}[/yellow]")

    def exit_with_error(self, code: int = 1) -> None:
        """Exit the process with an error code."""
        if self.log_manager:
            self.log_manager.close()
        sys.exit(code)
