"""
sbuild - Test result reporting

Provides TestReporter for formatting and displaying CTest results.
"""

import re
from typing import Optional

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from .console import console


class TestReporter:
    """Formats and displays test results from CTest output."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def parse_results(self, output_lines: list[str]) -> dict:
        """Parse CTest output and extract test results.

        Returns:
            dict with keys: total, passed, failed, failed_names
        """
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        failed_test_names = []

        # Look for CTest summary line: "X% tests passed, Y tests failed out of Z"
        summary_pattern = re.compile(
            r"(\d+)% tests passed, (\d+) tests failed out of (\d+)"
        )
        # Alternative: "The following tests FAILED:" section
        failed_section_pattern = re.compile(r"^\s*(\d+)\s*-\s*(.+?)\s*\(.*\)$")

        in_failed_section = False
        for line in output_lines:
            # Check for summary line
            match = summary_pattern.search(line)
            if match:
                failed_tests = int(match.group(2))
                total_tests = int(match.group(3))
                passed_tests = total_tests - failed_tests
                continue

            # Track failed test names
            if "The following tests FAILED:" in line:
                in_failed_section = True
                continue

            if in_failed_section:
                if line.strip() == "" or line.startswith("Errors while running"):
                    in_failed_section = False
                    continue
                match = failed_section_pattern.match(line)
                if match:
                    failed_test_names.append(match.group(2).strip())

        return {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "failed_names": failed_test_names,
        }

    def show_summary(
        self,
        total: int,
        passed: int,
        failed: int,
        failed_names: list[str],
        elapsed: float,
        success: bool,
    ) -> None:
        """Display a formatted test summary."""
        if total == 0:
            console.print("\n[yellow]No tests were run.[/yellow]")
            console.print(
                "[dim]Hint: Check that tests are registered with CTest "
                "(enable_testing() + gtest_discover_tests())[/dim]"
            )
            return

        # Build summary table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="bold")
        table.add_column("Value")

        # Status row (use ASCII-safe symbols for Windows compatibility)
        if success:
            status = "[green]PASSED[/green]"
        else:
            status = "[red]FAILED[/red]"

        table.add_row("Status", status)
        table.add_row("Total", str(total))
        table.add_row("Passed", f"[green]{passed}[/green]")

        if failed > 0:
            table.add_row("Failed", f"[red]{failed}[/red]")

        # Format elapsed time
        if elapsed >= 60:
            minutes = int(elapsed // 60)
            seconds = elapsed % 60
            time_str = f"{minutes}m {seconds:.1f}s"
        else:
            time_str = f"{elapsed:.1f}s"
        table.add_row("Duration", f"[dim]{time_str}[/dim]")

        # Calculate pass rate
        pass_rate = (passed / total * 100) if total > 0 else 0
        if pass_rate == 100:
            rate_style = "green"
        elif pass_rate >= 90:
            rate_style = "yellow"
        else:
            rate_style = "red"
        table.add_row("Pass Rate", f"[{rate_style}]{pass_rate:.1f}%[/{rate_style}]")

        # Print summary panel
        title = "[green]Test Summary[/green]" if success else "[red]Test Summary[/red]"
        border_style = "green" if success else "red"
        console.print(Panel(table, title=title, expand=False, border_style=border_style))

        # Show failed test names if any (use ASCII-safe symbols)
        self._show_failed_tests(failed_names)

    def _show_failed_tests(self, failed_names: list[str]) -> None:
        """Display list of failed test names."""
        if not failed_names:
            return

        if len(failed_names) <= 10:
            console.print("\n[red]Failed tests:[/red]")
            for name in failed_names:
                console.print(f"  [red]x[/red] {escape(name)}")
        else:
            console.print(f"\n[red]Failed tests ({len(failed_names)} total):[/red]")
            for name in failed_names[:10]:
                console.print(f"  [red]x[/red] {escape(name)}")
            console.print(f"  [dim]... and {len(failed_names) - 10} more[/dim]")

    def show_failures(self, all_output: list[str]) -> None:
        """Show test failure output details."""
        # Find sections with FAILED or error output
        failure_lines = []
        capture = False
        capture_count = 0

        for line in all_output:
            # Start capturing on failure indicators
            if "FAILED" in line or "error:" in line.lower():
                capture = True
                capture_count = 0

            if capture:
                failure_lines.append(line)
                capture_count += 1
                # Stop after capturing some context
                if capture_count > 20 and line.strip() == "":
                    capture = False

        if failure_lines and len(failure_lines) > 5:
            # Show condensed failure output
            display_lines = (
                failure_lines[:50] if len(failure_lines) > 50 else failure_lines
            )
            console.print(
                Panel(
                    "\n".join(escape(line) for line in display_lines),
                    title="[red]Failure Details[/red]",
                    border_style="red",
                    expand=False,
                )
            )
            if len(failure_lines) > 50:
                console.print(
                    "[dim]Showing first 50 lines. Use --test-verbose for full output.[/dim]"
                )
