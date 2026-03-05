"""
sbuild - Abstract base runner

Provides shared functionality for all build runners including command execution
with real-time output preview.
"""

import platform
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import ClassVar, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel

from ..config import BuildConfig
from ..console import console
from ..exceptions import BuildError
from ..logging import LogManager
from ..test_reporter import TestReporter


class BaseRunner(ABC):
    """Abstract base class for build runners"""

    supports_tests: ClassVar[bool] = True
    supports_serve: ClassVar[bool] = False

    _PANEL_MAX_LINES: ClassVar[int] = 8
    _PANEL_HEIGHT: ClassVar[int] = 10
    _ERROR_TAIL_LINES: ClassVar[int] = 30
    _ERROR_SEARCH_LINES: ClassVar[int] = 100
    _ERROR_CONTEXT_LIMIT: ClassVar[int] = 20
    _ERROR_DISPLAY_CAP: ClassVar[int] = 25

    _ERROR_KEYWORDS: ClassVar[list[str]] = [
        "error:", "failed:", "fatal:", "undefined reference",
        "cannot find", "no such file", "permission denied", "command not found",
    ]

    def __init__(self, config: BuildConfig, log_manager: Optional[LogManager] = None):
        self.config = config
        self.log_manager = log_manager

    def get_config_summary(self) -> dict[str, list[tuple[str, str]]]:
        """Return runner-specific configuration as grouped key-value pairs.

        Returns a dict mapping section names to ordered lists of (label, value) tuples.
        Subclasses override to add platform-specific info.
        """
        return {}

    @abstractmethod
    def configure(self) -> bool:
        """Configure the build (cmake configure step)"""
        pass

    @abstractmethod
    def build(self) -> bool:
        """Execute the build"""
        pass

    def serve(self, **kwargs) -> None:
        """Start development server. Override in subclasses that support it."""
        raise BuildError(f"{type(self).__name__} does not support 'serve'")

    def _require_build_dir(self) -> bool:
        """Check that the build directory exists. Prints error and returns False if missing."""
        if not self.config.build_dir.exists():
            console.print(f"[red]Build directory not found: {self.config.build_dir}[/red]")
            console.print("[yellow]Please build the project first.[/yellow]")
            return False
        return True

    def clean(self) -> bool:
        """Clean build directory"""
        if self.config.build_dir.exists():
            try:
                shutil.rmtree(self.config.build_dir)
                console.print(
                    f"[green][OK][/green] Cleaned {self.config.build_type} build"
                )
                return True
            except Exception as e:
                console.print(f"[red][FAIL][/red] Failed to clean: {e}")
                return False
        return True

    def install(
        self,
        prefix: Optional[Path] = None,
        component: Optional[str] = None,
        system_install: bool = False,
    ) -> bool:
        """Install the project"""
        if not self._require_build_dir():
            return False

        # If no prefix specified and not a system install, use default
        if not prefix and not system_install:
            prefix = self.config.project_root / "install" / self.config.build_type
            console.print(f"[yellow]No prefix specified. Using default: {prefix}[/yellow]")

        cmd = f"cmake --install {self.config.build_dir}"

        if prefix:
            cmd += f" --prefix {prefix}"

        if component:
            cmd += f" --component {component}"

        desc = "Installing"
        if component:
            desc += f" ({component})"
        if prefix:
            desc += f" to {prefix}"
        elif system_install:
            desc += " to system location"

        return self.run_command(cmd, desc)

    def _get_platform_suffix(self) -> str:
        """Get platform suffix for package filenames."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "windows":
            return "win64" if machine in ("amd64", "x86_64") else f"win-{machine}"
        elif system == "linux":
            return f"linux-{machine}"
        elif system == "darwin":
            return f"macos-{machine}"
        return f"{system}-{machine}"

    def package(self, generator: Optional[str] = None) -> bool:
        """Create installation package"""
        import contextlib

        if not self._require_build_dir():
            return False

        if generator and generator.upper() == "NSIS" and platform.system() != "Windows":
            console.print("[yellow]Warning: NSIS generator is only available on Windows[/yellow]")
            return False

        with contextlib.chdir(self.config.build_dir):
            cmd = f"cpack -C {self.config.build_type}"
            if generator:
                cmd += f" -G {generator}"
                suffix = self._get_platform_suffix()
                # Use generator-specific file names since CPACK_IFW_PACKAGE_FILE_NAME
                # is not reliably respected by CPack at runtime
                if generator.upper() == "IFW":
                    build_num = self.config.get_resolved_build_number()
                    cmd += f" -D CPACK_PACKAGE_FILE_NAME={self.config.project_name}-{self.config.version}-build{build_num}-{suffix}-ifw"
                elif generator.upper() == "NSIS":
                    build_num = self.config.get_resolved_build_number()
                    cmd += f" -D CPACK_PACKAGE_FILE_NAME={self.config.project_name}-{self.config.version}-build{build_num}-{suffix}-setup"

            desc = "Creating package"
            if generator:
                desc += f" ({generator})"

            return self.run_command(cmd, desc, cwd=self.config.build_dir)

    def run_tests(
        self,
        test_filter: Optional[str] = None,
        test_verbose: bool = False,
        rerun_failed: bool = False,
        output_on_failure: bool = True,
    ) -> bool:
        """Run tests via CTest with detailed summary."""
        if not self._require_build_dir():
            return False

        cmd = f"ctest --test-dir {self.config.build_dir}"

        if test_filter:
            cmd += f" -R {test_filter}"
        if test_verbose:
            cmd += " -V"
        if rerun_failed:
            cmd += " --rerun-failed"
        if output_on_failure:
            cmd += " --output-on-failure"
        if self.config.jobs:
            cmd += f" -j {self.config.jobs}"

        # Run tests and capture output for summary parsing
        cwd = self.config.project_root
        prepared_cmd = self._prepare_command(cmd)
        env = self._get_command_env()

        if self.log_manager:
            self.log_manager.write_section("Command: Running tests")
            self.log_manager.write(f"Working directory: {cwd}")
            self.log_manager.write(f"Command: {cmd}")

        start_time = time.time()
        all_output: list[str] = []
        last_lines: deque = deque(maxlen=self._PANEL_MAX_LINES)
        process = None

        try:
            process = subprocess.Popen(
                prepared_cmd,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
            )

            reader_thread = threading.Thread(
                target=self._read_process_output, args=(process, last_lines, all_output)
            )
            reader_thread.daemon = True
            reader_thread.start()

            if self.config.verbose:
                # Verbose mode: show full output
                while process.poll() is None:
                    time.sleep(0.1)
                reader_thread.join(timeout=1.0)
                for line in all_output:
                    console.print(line, highlight=False)
            else:
                self._show_live_panel(process, last_lines, "Running Tests")

            return_code = process.returncode
            elapsed = time.time() - start_time

            if self.log_manager:
                self.log_manager.write(f"Exit code: {return_code}")
                self.log_manager.write(f"Execution time: {elapsed:.2f}s")

            # Use TestReporter to parse and display results
            reporter = TestReporter(verbose=self.config.verbose)
            results = reporter.parse_results(all_output)

            reporter.show_summary(
                total=results["total"],
                passed=results["passed"],
                failed=results["failed"],
                failed_names=results["failed_names"],
                elapsed=elapsed,
                success=return_code == 0,
            )

            if return_code != 0 and output_on_failure and not self.config.verbose:
                reporter.show_failures(all_output)

            return return_code == 0

        except KeyboardInterrupt:
            if process:
                process.terminate()
            raise
        except Exception as e:
            console.print(f"[red]Error running tests: {e}[/red]")
            return False

    def _prepare_command(self, cmd: str) -> str:
        """Prepare command for execution. Override in subclasses for platform-specific handling."""
        return cmd

    def _get_command_env(self) -> Optional[dict[str, str]]:
        """Get environment variables for command execution. Override in subclasses."""
        return None

    def _read_process_output(self, proc: subprocess.Popen, lines_queue: deque, all_lines: list[str]) -> None:
        """Read subprocess output in background thread"""
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    stripped_line = line.rstrip()
                    lines_queue.append(stripped_line)
                    all_lines.append(stripped_line)
                    if self.log_manager:
                        self.log_manager.write(f"  {stripped_line}")
        except (IOError, OSError):
            pass

    @property
    def _live_console(self) -> Console:
        """Get the underlying Rich Console for Live context"""
        return console

    def _show_live_panel(self, process, last_lines, title):
        """Show a Rich Live panel tracking process output until it exits"""
        with Live(
            console=self._live_console,
            refresh_per_second=4,
            transient=True,
            auto_refresh=False,
        ) as live:
            while process.poll() is None:
                lines_to_show = (
                    list(last_lines) if last_lines else ["[dim]Starting...[/dim]"]
                )

                # Pad to consistent height
                while len(lines_to_show) < self._PANEL_MAX_LINES:
                    lines_to_show.append("")

                content = "\n".join(lines_to_show)

                panel = Panel(
                    content,
                    title=f"[cyan]{title}[/cyan]",
                    border_style="cyan",
                    expand=True,
                    height=self._PANEL_HEIGHT,
                )

                live.update(panel, refresh=True)
                time.sleep(0.1)

    def run_command(
        self,
        cmd: str,
        description: str,
        cwd: Optional[Path] = None,
    ) -> bool:
        """Execute a command with real-time output preview"""
        cwd = cwd or self.config.project_root
        prepared_cmd = self._prepare_command(cmd)
        env = self._get_command_env()

        if self.log_manager:
            self.log_manager.write_section(f"Command: {description}")
            self.log_manager.write(f"Working directory: {cwd}")
            self.log_manager.write(f"Command: {cmd}")
            if prepared_cmd != cmd:
                self.log_manager.write(f"Prepared command: {prepared_cmd}")

        start_time = time.time()

        if self.config.verbose:
            return self._run_verbose(prepared_cmd, description, cwd, env, start_time)
        else:
            return self._run_with_panel(prepared_cmd, description, cwd, env, start_time)

    def _run_verbose(
        self,
        cmd: str,
        description: str,
        cwd: Path,
        env: Optional[dict],
        start_time: float,
    ) -> bool:
        """Run command in verbose mode with full output"""
        console.print(f"[dim]$ {cmd}[/dim]")

        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )

        if self.log_manager and result.stdout:
            for line in result.stdout.splitlines():
                self.log_manager.write(f"  {line}")

        if result.stdout:
            console.print(result.stdout, end="", highlight=False)

        elapsed = time.time() - start_time

        if self.log_manager:
            self.log_manager.write(f"Exit code: {result.returncode}")
            self.log_manager.write(f"Execution time: {elapsed:.2f}s")

        if result.returncode == 0:
            console.print(f"[green][OK][/green] {description} [dim]({elapsed:.1f}s)[/dim]")
            return True
        else:
            console.print(f"[red][FAIL][/red] {description} [dim]({elapsed:.1f}s)[/dim]")
            return False

    def _run_with_panel(
        self,
        cmd: str,
        description: str,
        cwd: Path,
        env: Optional[dict],
        start_time: float,
    ) -> bool:
        """Run command with Rich Live panel showing last N lines"""
        last_lines = deque(maxlen=self._PANEL_MAX_LINES)
        all_output = []
        return_code = None
        process = None

        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
            )

            reader_thread = threading.Thread(
                target=self._read_process_output, args=(process, last_lines, all_output)
            )
            reader_thread.daemon = True
            reader_thread.start()

            self._show_live_panel(process, last_lines, description)

            return_code = process.returncode
            elapsed = time.time() - start_time

            if self.log_manager:
                self.log_manager.write(f"Exit code: {return_code}")
                self.log_manager.write(f"Execution time: {elapsed:.2f}s")

            if return_code == 0:
                console.print(f"[green][OK][/green] {description} [dim]({elapsed:.1f}s)[/dim]")
                return True
            else:
                console.print(f"[red][FAIL][/red] {description} [dim]({elapsed:.1f}s)[/dim]")
                self._show_error_output(all_output)
                return False

        except KeyboardInterrupt:
            if process:
                process.terminate()
            raise
        except Exception as e:
            console.print(f"[red]Error running command: {e}[/red]")
            return False

    def _show_error_output(self, all_output: list[str]) -> None:
        """Show comprehensive error output"""
        if not all_output:
            console.print("[red]No output captured[/red]")
            return

        # Find the last N lines or all lines if fewer
        error_lines = all_output[-self._ERROR_TAIL_LINES:] if len(all_output) > self._ERROR_TAIL_LINES else all_output

        # Search last N lines for error indicators (case-insensitive)
        search_lines = all_output[-self._ERROR_SEARCH_LINES:] if len(all_output) > self._ERROR_SEARCH_LINES else all_output

        # Find lines with error indicators
        error_context = []
        for i, line in enumerate(search_lines):
            if any(kw in line.lower() for kw in self._ERROR_KEYWORDS):
                start_idx = max(0, i - 2)
                end_idx = min(len(search_lines), i + 3)
                context_lines = search_lines[start_idx:end_idx]
                error_context.extend(context_lines)
                if len(error_context) > self._ERROR_CONTEXT_LIMIT:
                    break

        # Show error context if found, otherwise show last lines
        display_lines = error_context if error_context else error_lines

        # Remove duplicates while preserving order
        seen = set()
        unique_lines = []
        for line in display_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)

        console.print(
            Panel(
                "\n".join(unique_lines[-self._ERROR_DISPLAY_CAP:]),
                title="[red]Build Errors[/red]",
                border_style="red",
                expand=False,
            )
        )

        if len(all_output) > self._ERROR_TAIL_LINES:
            console.print(
                f"[dim]Showing last {min(len(unique_lines), self._ERROR_DISPLAY_CAP)} relevant lines. "
                "Use -v/--verbose to see full output[/dim]"
            )
