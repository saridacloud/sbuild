"""Tests for sbuild.session.BuildSession lifecycle."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sbuild.config import ConfigManager
from sbuild.exceptions import BuildError, ConfigError
from sbuild.session import BuildSession


def _make_config(project_root: Path, **overrides) -> "BuildConfig":
    """Helper: create a BuildConfig via ConfigManager."""
    return ConfigManager(project_root=project_root, **overrides).resolve()


class TestBuildSessionEnter:
    def test_creates_config_and_log_manager(self, project_root):
        config = _make_config(project_root)
        session = BuildSession(config)
        with session as s:
            assert s.config is not None
            assert s.log_manager is not None
            assert s.log_path is not None

    def test_build_type_capitalized(self, project_root):
        config = _make_config(project_root, build_type="release")
        with BuildSession(config) as s:
            assert s.config.build_type == "Release"


class TestBuildSessionExit:
    def test_closes_log_on_normal_exit(self, project_root):
        config = _make_config(project_root)
        session = BuildSession(config)
        with session as s:
            log_manager = s.log_manager
        assert log_manager.log_file.closed

    def test_suppresses_build_error(self, project_root):
        # BuildError should be suppressed (not re-raised)
        config = _make_config(project_root)
        session = BuildSession(config)
        with session:
            raise BuildError("test error")
        # If we get here, the error was suppressed

    def test_suppresses_keyboard_interrupt(self, project_root):
        config = _make_config(project_root)
        session = BuildSession(config)
        with session:
            raise KeyboardInterrupt()
        # If we get here, the interrupt was suppressed

    def test_does_not_suppress_system_exit(self, project_root):
        config = _make_config(project_root)
        session = BuildSession(config)
        with pytest.raises(SystemExit):
            with session:
                raise SystemExit(1)


class TestBuildSessionRunner:
    def test_runner_lazy_creation(self, project_root):
        config = _make_config(project_root)
        session = BuildSession(config)
        with session as s:
            assert s._runner is None
            _ = s.runner
            assert s._runner is not None

    def test_runner_cached(self, project_root):
        config = _make_config(project_root)
        session = BuildSession(config)
        with session as s:
            r1 = s.runner
            r2 = s.runner
            assert r1 is r2
