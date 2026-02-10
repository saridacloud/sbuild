"""Tests for sbuild.runners.base.BaseRunner._get_platform_suffix."""

from unittest.mock import patch, MagicMock

import pytest

from sbuild.runners.base import BaseRunner


class _ConcreteRunner(BaseRunner):
    """Minimal concrete subclass for testing non-abstract methods."""

    def configure(self):
        pass

    def build(self):
        pass


def _make_runner():
    """Create a concrete runner instance without running __init__."""
    runner = object.__new__(_ConcreteRunner)
    return runner


class TestGetPlatformSuffix:
    @pytest.mark.parametrize(
        "system, machine, expected",
        [
            ("Windows", "AMD64", "win64"),
            ("Windows", "x86_64", "win64"),
            ("Windows", "ARM64", "win-arm64"),
            ("Linux", "x86_64", "linux-x86_64"),
            ("Darwin", "arm64", "macos-arm64"),
            ("FreeBSD", "amd64", "freebsd-amd64"),
        ],
        ids=["win-amd64", "win-x86_64", "win-arm64", "linux", "macos", "unknown"],
    )
    def test_suffix(self, system, machine, expected):
        runner = _make_runner()
        with patch("sbuild.runners.base.platform") as mock_platform:
            mock_platform.system.return_value = system
            mock_platform.machine.return_value = machine
            assert runner._get_platform_suffix() == expected
