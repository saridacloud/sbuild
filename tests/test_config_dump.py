"""Tests for resolved configuration dump feature."""

from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sbuild.session import BuildSession


class TestLogResolvedConfig:
    """Test that _log_resolved_config writes expected sections to log."""

    def test_writes_resolved_config_section(self, project_root):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner  # trigger lazy init + log
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "Resolved Configuration" in content

    def test_writes_project_info(self, project_root):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "TestProject" in content
        assert "1.2.3" in content

    def test_writes_build_directory(self, project_root):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "Build directory:" in content

    def test_writes_presets(self, project_root):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "Configure preset:" in content
        assert "Build preset:" in content

    def test_writes_profiling_timers(self, project_root):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "Config creation:" in content
        assert "Runner init:" in content

    def test_writes_sbuild_version(self, project_root):
        from sbuild import __version__

        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert f"sbuild version: {__version__}" in content

    def test_early_command_log_line(self, project_root):
        with BuildSession(project_root=project_root, command="build") as session:
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "Command: sbuild build" in content
        assert "CLI Parameters" not in content

    def test_writes_command_in_resolved_config(self, project_root):
        with BuildSession(project_root=project_root, command="rebuild") as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "  Command: rebuild" in content

    def test_writes_verbose_in_resolved_config(self, project_root):
        with BuildSession(project_root=project_root, verbose=True) as session:
            _ = session.runner
            log_path = session.log_path

        content = log_path.read_text(encoding="utf-8")
        assert "  Verbose: True" in content


class TestShowConfigConsole:
    """Test that _show_config_console produces expected output."""

    def test_prints_project_info(self, project_root, capsys):
        with BuildSession(project_root=project_root, command="config") as session:
            _ = session.runner
            session._show_config_console()

        # Rich prints to stdout; capsys captures it
        captured = capsys.readouterr()
        assert "TestProject" in captured.out
        assert "1.2.3" in captured.out

    def test_prints_command(self, project_root, capsys):
        with BuildSession(project_root=project_root, command="config") as session:
            _ = session.runner
            session._show_config_console()

        captured = capsys.readouterr()
        assert "config" in captured.out

    def test_prints_build_directory(self, project_root, capsys):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            session._show_config_console()

        captured = capsys.readouterr()
        assert "Build directory" in captured.out

    def test_prints_presets(self, project_root, capsys):
        with BuildSession(project_root=project_root) as session:
            _ = session.runner
            session._show_config_console()

        captured = capsys.readouterr()
        assert "Configure preset" in captured.out
        assert "Build preset" in captured.out


class TestVerboseShowsConfig:
    """Test that verbose mode shows config in show_header, non-verbose doesn't."""

    def test_verbose_shows_config(self, project_root, capsys):
        with BuildSession(project_root=project_root, verbose=True, command="build") as session:
            session.show_header()

        captured = capsys.readouterr()
        assert "sbuild version" in captured.out

    def test_non_verbose_hides_config(self, project_root, capsys):
        with BuildSession(project_root=project_root, verbose=False, command="build") as session:
            session.show_header()

        captured = capsys.readouterr()
        assert "sbuild version" not in captured.out


class TestRunnerConfigSummary:
    """Test that runners return expected config summary sections."""

    def test_native_runner_has_architecture_section(self, project_root):
        with BuildSession(project_root=project_root) as session:
            summary = session.runner.get_config_summary()

        assert "Architecture" in summary
        labels = [label for label, _ in summary["Architecture"]]
        assert "Host architecture" in labels
        assert "Target architecture" in labels

    def test_base_runner_returns_empty(self):
        from sbuild.runners.base import BaseRunner

        # BaseRunner is abstract, so create a minimal concrete subclass
        class StubRunner(BaseRunner):
            def configure(self): return True
            def build(self): return True

        config = MagicMock()
        runner = StubRunner(config)
        assert runner.get_config_summary() == {}
