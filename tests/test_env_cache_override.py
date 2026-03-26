"""Tests for .env vars overriding cached vcvarsall environment."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from sbuild.config import NativeConfig
from sbuild.runners.native import NativeRunner


def _make_mock_config(project_root, env_vars=None):
    """Create a mock BuildConfig with a real NativeConfig."""
    native_config = NativeConfig(
        env_vars=env_vars or {},
        host_arch="x86_64",
        target_arch="x86_64",
    )
    config = MagicMock()
    config.platform_config = native_config
    config.project_root = project_root
    return config


class TestEnvVarsOverrideCachedEnv:
    """Ensure .env variables always override the activated (possibly cached) env."""

    def test_env_vars_applied_after_activation(self, tmp_path):
        """Changed .env vars must appear in runner env even on cache hit."""
        config = _make_mock_config(tmp_path, env_vars={"MY_VAR": "fresh_value"})

        # Mock activate() to return a "cached" env that has a stale MY_VAR
        cached_env = {"PATH": "/usr/bin", "MY_VAR": "stale_cached_value"}

        with patch("sbuild.runners.native.create_platform_env") as mock_create:
            mock_platform = MagicMock()
            mock_platform.activate.return_value = dict(cached_env)
            mock_create.return_value = mock_platform

            runner = NativeRunner(config)

        assert runner._env["MY_VAR"] == "fresh_value"

    def test_env_vars_applied_on_cache_miss(self, tmp_path):
        """On cache miss, .env vars should still be applied on top."""
        config = _make_mock_config(tmp_path, env_vars={"FOO": "bar"})

        with patch("sbuild.runners.native.create_platform_env") as mock_create:
            mock_platform = MagicMock()
            mock_platform.activate.return_value = {"PATH": "/usr/bin"}
            mock_create.return_value = mock_platform

            runner = NativeRunner(config)

        assert runner._env["FOO"] == "bar"

    def test_env_vars_not_merged_before_activation(self, tmp_path):
        """Verify .env vars are NOT passed as base_env to activate()."""
        config = _make_mock_config(tmp_path, env_vars={"SECRET": "value"})

        with patch("sbuild.runners.native.create_platform_env") as mock_create:
            mock_platform = MagicMock()
            mock_platform.activate.return_value = {"PATH": "/usr/bin"}
            mock_create.return_value = mock_platform

            with patch.dict("os.environ", {}, clear=True):
                runner = NativeRunner(config)

            # base_env should be os.environ (empty dict), not containing .env vars
            call_kwargs = mock_platform.activate.call_args[1]
            assert "SECRET" not in call_kwargs["base_env"]

    def test_qt_ifw_root_adds_to_path(self, tmp_path):
        """SBUILD_QT_IFW_ROOT bin dir is prepended to PATH when it exists."""
        qt_ifw = tmp_path / "qt_ifw"
        qt_ifw_bin = qt_ifw / "bin"
        qt_ifw_bin.mkdir(parents=True)

        config = _make_mock_config(
            tmp_path, env_vars={"SBUILD_QT_IFW_ROOT": str(qt_ifw)}
        )

        with patch("sbuild.runners.native.create_platform_env") as mock_create:
            mock_platform = MagicMock()
            mock_platform.activate.return_value = {"PATH": "/usr/bin"}
            mock_create.return_value = mock_platform

            runner = NativeRunner(config)

        assert str(qt_ifw_bin) in runner._env["PATH"]
        # bin dir should be prepended (first in PATH)
        assert runner._env["PATH"].startswith(str(qt_ifw_bin))

    def test_no_env_vars_leaves_activated_env_unchanged(self, tmp_path):
        """With no .env vars, the activated env is used as-is."""
        config = _make_mock_config(tmp_path, env_vars={})

        activated = {"PATH": "/usr/bin", "INCLUDE": "C:\\inc"}

        with patch("sbuild.runners.native.create_platform_env") as mock_create:
            mock_platform = MagicMock()
            mock_platform.activate.return_value = dict(activated)
            mock_create.return_value = mock_platform

            runner = NativeRunner(config)

        assert runner._env == activated
