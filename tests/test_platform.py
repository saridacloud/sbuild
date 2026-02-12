"""Tests for sbuild.platform — create_platform_env, LinuxEnv, WindowsEnv."""

from pathlib import Path
from unittest.mock import patch

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
