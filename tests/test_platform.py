"""Tests for sbuild.platform — create_platform_env, LinuxEnv, WindowsEnv."""

import pickle
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sbuild.exceptions import EnvironmentSetupError


# -- create_platform_env ------------------------------------------------------

class TestCreatePlatformEnv:
    def test_returns_windows_env_on_windows(self):
        with patch("sbuild.platform.IS_WINDOWS", True):
            with patch("sbuild.platform.windows.WindowsEnv._find_vcvarsall", return_value=None):
                from sbuild.platform import create_platform_env
                env = create_platform_env()
                from sbuild.platform.windows import WindowsEnv
                assert isinstance(env, WindowsEnv)

    def test_returns_linux_env_on_linux(self):
        with patch("sbuild.platform.IS_WINDOWS", False):
            from sbuild.platform import create_platform_env
            env = create_platform_env()
            from sbuild.platform.linux import LinuxEnv
            assert isinstance(env, LinuxEnv)


# -- LinuxEnv -----------------------------------------------------------------

class TestLinuxEnv:
    def test_toolchain_path_is_none(self):
        from sbuild.platform.linux import LinuxEnv
        env = LinuxEnv()
        assert env.toolchain_path is None

    def test_activate_no_scripts(self):
        from sbuild.platform.linux import LinuxEnv
        env = LinuxEnv()
        base = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result = env.activate(base_env=base)
        assert result == base


# -- WindowsEnv._find_vcvarsall -----------------------------------------------

class TestWindowsEnvFindVcvarsall:
    def test_from_env_overrides(self, tmp_path):
        from sbuild.platform.windows import WindowsEnv
        vcvars = tmp_path / "vcvarsall.bat"
        vcvars.write_text("@echo off", encoding="utf-8")
        path = WindowsEnv._find_vcvarsall({"VCVARS_PATH": str(vcvars)})
        assert path == vcvars

    def test_override_not_found_raises(self):
        from sbuild.platform.windows import WindowsEnv
        with pytest.raises(EnvironmentSetupError, match="VCVARS_PATH not found"):
            WindowsEnv._find_vcvarsall({"VCVARS_PATH": "C:/nonexistent/vcvarsall.bat"})

    def test_no_override_no_known_returns_none(self):
        from sbuild.platform.windows import WindowsEnv
        with patch("sbuild.platform.windows.os.environ", {}):
            with patch("sbuild.platform.windows._KNOWN_VCVARSALL_PATHS", []):
                path = WindowsEnv._find_vcvarsall({})
                assert path is None

    def test_known_path_found(self, tmp_path):
        from sbuild.platform.windows import WindowsEnv
        vcvars = tmp_path / "vcvarsall.bat"
        vcvars.write_text("@echo off", encoding="utf-8")
        with patch("sbuild.platform.windows.os.environ", {}):
            with patch("sbuild.platform.windows._KNOWN_VCVARSALL_PATHS", [str(vcvars)]):
                path = WindowsEnv._find_vcvarsall({})
                assert path == vcvars


# -- WindowsEnv._resolve_vcvars_arch -----------------------------------------

class TestResolveVcvarsArch:
    def test_x86_64_maps_to_amd64(self):
        from sbuild.platform.windows import WindowsEnv
        assert WindowsEnv._resolve_vcvars_arch(None, "x86_64") == "amd64"

    def test_x86_maps_to_amd64_x86(self):
        from sbuild.platform.windows import WindowsEnv
        assert WindowsEnv._resolve_vcvars_arch(None, "x86") == "amd64_x86"

    def test_armv8_maps_to_amd64_arm64(self):
        from sbuild.platform.windows import WindowsEnv
        assert WindowsEnv._resolve_vcvars_arch(None, "armv8") == "amd64_arm64"

    def test_unknown_arch_falls_back_to_default(self):
        from sbuild.platform.windows import WindowsEnv
        assert WindowsEnv._resolve_vcvars_arch(None, "riscv64") == "amd64"

    def test_env_overrides_take_precedence(self):
        from sbuild.platform.windows import WindowsEnv
        result = WindowsEnv._resolve_vcvars_arch({"VCVARS_ARCH": "x86"}, "x86_64")
        assert result == "x86"

    def test_os_environ_override(self):
        from sbuild.platform.windows import WindowsEnv
        with patch("sbuild.platform.windows.os.environ", {"VCVARS_ARCH": "arm64"}):
            result = WindowsEnv._resolve_vcvars_arch(None, "x86_64")
        assert result == "arm64"

    def test_env_overrides_beat_os_environ(self):
        from sbuild.platform.windows import WindowsEnv
        with patch("sbuild.platform.windows.os.environ", {"VCVARS_ARCH": "arm64"}):
            result = WindowsEnv._resolve_vcvars_arch({"VCVARS_ARCH": "x86"}, "x86_64")
        assert result == "x86"


# -- WindowsEnv caching ------------------------------------------------------

def _make_windows_env(tmp_path):
    """Create a WindowsEnv with a fake vcvarsall.bat in tmp_path."""
    from sbuild.platform.windows import WindowsEnv

    vcvars = tmp_path / "vcvarsall.bat"
    vcvars.write_text("@echo off", encoding="utf-8")

    with patch("sbuild.platform.windows.os.environ", {}):
        with patch("sbuild.platform.windows._KNOWN_VCVARSALL_PATHS", [str(vcvars)]):
            env = WindowsEnv(env_overrides={}, target_arch="x86_64")
    return env


class TestWindowsEnvCaching:
    """Tests for vcvarsall.bat environment caching."""

    def test_cache_hit_property_none_initially(self, tmp_path):
        env = _make_windows_env(tmp_path)
        assert env.cache_hit is None

    def test_cache_miss_calls_subprocess(self, tmp_path):
        """First call with cache_dir invokes subprocess (cache miss)."""
        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake", "INCLUDE": "C:\\inc"}

        with patch.object(env, "_run_and_capture_env", return_value=fake_env) as mock_run:
            result = env.activate(base_env={}, cache_dir=tmp_path)

        mock_run.assert_called_once()
        assert result == fake_env
        assert env.cache_hit is False

    def test_cache_hit_skips_subprocess(self, tmp_path):
        """Second call uses cache, subprocess not called again."""
        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake", "INCLUDE": "C:\\inc"}

        with patch.object(env, "_run_and_capture_env", return_value=fake_env):
            env.activate(base_env={}, cache_dir=tmp_path)

        # Second call — subprocess should NOT be called
        with patch.object(env, "_run_and_capture_env") as mock_run:
            result = env.activate(base_env={}, cache_dir=tmp_path)

        mock_run.assert_not_called()
        assert result == fake_env
        assert env.cache_hit is True

    def test_cache_invalidated_on_arch_change(self, tmp_path):
        """Different arch invalidates cache."""
        from sbuild.platform.windows import WindowsEnv

        vcvars = tmp_path / "vcvarsall.bat"
        vcvars.write_text("@echo off", encoding="utf-8")
        fake_env = {"PATH": "C:\\fake"}

        # Create first env with amd64 arch and populate cache
        with patch("sbuild.platform.windows.os.environ", {}):
            with patch("sbuild.platform.windows._KNOWN_VCVARSALL_PATHS", [str(vcvars)]):
                env1 = WindowsEnv(env_overrides={}, target_arch="x86_64")
        with patch.object(env1, "_run_and_capture_env", return_value=fake_env):
            env1.activate(base_env={}, cache_dir=tmp_path)
        assert env1.cache_hit is False

        # Create second env with different arch — should miss cache
        with patch("sbuild.platform.windows.os.environ", {}):
            with patch("sbuild.platform.windows._KNOWN_VCVARSALL_PATHS", [str(vcvars)]):
                env2 = WindowsEnv(env_overrides={}, target_arch="armv8")
        with patch.object(env2, "_run_and_capture_env", return_value=fake_env) as mock_run:
            env2.activate(base_env={}, cache_dir=tmp_path)

        mock_run.assert_called_once()
        assert env2.cache_hit is False

    def test_cache_invalidated_on_mtime_change(self, tmp_path):
        """Touching vcvarsall.bat invalidates cache."""
        import time

        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake"}

        with patch.object(env, "_run_and_capture_env", return_value=fake_env):
            env.activate(base_env={}, cache_dir=tmp_path)

        # Modify mtime of vcvarsall.bat
        vcvars = env.toolchain_path
        time.sleep(0.05)
        vcvars.write_text("@echo updated", encoding="utf-8")

        with patch.object(env, "_run_and_capture_env", return_value=fake_env) as mock_run:
            env.activate(base_env={}, cache_dir=tmp_path)

        mock_run.assert_called_once()
        assert env.cache_hit is False

    def test_no_caching_with_extra_scripts(self, tmp_path):
        """Extra scripts disable caching."""
        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake"}
        extra = tmp_path / "extra.bat"
        extra.write_text("@echo off", encoding="utf-8")

        with patch.object(env, "_run_and_capture_env", return_value=fake_env):
            env.activate(base_env={}, cache_dir=tmp_path, extra_scripts=[extra])

        # cache_hit stays None when caching is not used
        assert env.cache_hit is None

    def test_no_caching_without_cache_dir(self, tmp_path):
        """cache_dir=None means no caching."""
        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake"}

        with patch.object(env, "_run_and_capture_env", return_value=fake_env):
            env.activate(base_env={})

        assert env.cache_hit is None

    def test_corrupt_cache_file_handled_gracefully(self, tmp_path):
        """Bad pickle data falls back to subprocess."""
        from sbuild.platform.windows import _CACHE_DIR_NAME, _CACHE_FILE_NAME

        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake"}

        # Write corrupt data
        cache_dir = tmp_path / _CACHE_DIR_NAME
        cache_dir.mkdir()
        (cache_dir / _CACHE_FILE_NAME).write_bytes(b"not a pickle")

        with patch.object(env, "_run_and_capture_env", return_value=fake_env) as mock_run:
            result = env.activate(base_env={}, cache_dir=tmp_path)

        mock_run.assert_called_once()
        assert result == fake_env
        assert env.cache_hit is False

    def test_cache_dir_created_automatically(self, tmp_path):
        """The .sbuild/ directory is created on first cache write."""
        from sbuild.platform.windows import _CACHE_DIR_NAME, _CACHE_FILE_NAME

        env = _make_windows_env(tmp_path)
        fake_env = {"PATH": "C:\\fake"}

        cache_file = tmp_path / _CACHE_DIR_NAME / _CACHE_FILE_NAME
        assert not cache_file.exists()

        with patch.object(env, "_run_and_capture_env", return_value=fake_env):
            env.activate(base_env={}, cache_dir=tmp_path)

        assert cache_file.exists()
        data = pickle.loads(cache_file.read_bytes())
        assert data["env"] == fake_env
        assert "fingerprint" in data
