"""Tests for sbuild.config — load_env_file, parse_cmake_project_info, config classes."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sbuild.config import (
    BuildConfig,
    NativeConfig,
    WasmConfig,
    load_env_file,
    parse_cmake_project_info,
    parse_conan_profile_arch,
)
from sbuild.exceptions import ConfigError, EnvironmentSetupError


# -- load_env_file ------------------------------------------------------------

class TestLoadEnvFile:
    def test_basic_parsing(self, env_file):
        result = load_env_file(env_file)
        assert result["FOO"] == "bar"
        assert result["BAZ"] == "qux"

    def test_comments_skipped(self, env_file):
        result = load_env_file(env_file)
        assert not any(k.startswith("#") for k in result)

    def test_blank_lines_ignored(self, env_file):
        result = load_env_file(env_file)
        assert "" not in result

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_env_file(tmp_path / "nonexistent.env")
        assert result == {}

    def test_no_equals_skipped(self, env_file):
        result = load_env_file(env_file)
        assert "NO_EQUALS_LINE" not in result

    def test_value_with_equals(self, env_file):
        result = load_env_file(env_file)
        assert result["EQUAL_VALUE"] == "a=b=c"

    def test_whitespace_stripped(self, env_file):
        result = load_env_file(env_file)
        assert result["SPACED_KEY"] == "spaced_value"

    def test_empty_value(self, env_file):
        result = load_env_file(env_file)
        assert result["EMPTY_VALUE"] == ""


# -- parse_cmake_project_info -------------------------------------------------

class TestParseCmakeProjectInfo:
    def test_basic(self, project_root):
        name, version = parse_cmake_project_info(project_root / "CMakeLists.txt")
        assert name == "TestProject"
        assert version == "1.2.3"

    def test_extra_args(self, tmp_path):
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text(
            "project(MyApp VERSION 2.0.1 LANGUAGES C CXX)\n", encoding="utf-8"
        )
        name, version = parse_cmake_project_info(cmake)
        assert name == "MyApp"
        assert version == "2.0.1"

    def test_multiline(self, tmp_path):
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text(
            "project(\n  MyApp\n  VERSION 3.1.4\n  LANGUAGES CXX\n)\n",
            encoding="utf-8",
        )
        name, version = parse_cmake_project_info(cmake)
        assert name == "MyApp"
        assert version == "3.1.4"

    def test_missing_file(self, tmp_path):
        name, version = parse_cmake_project_info(tmp_path / "nonexistent.txt")
        assert name == "unknown"
        assert version == "0.0.0"

    def test_empty_file(self, tmp_path):
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("", encoding="utf-8")
        name, version = parse_cmake_project_info(cmake)
        assert name == "unknown"
        assert version == "0.0.0"

    def test_no_project_line(self, tmp_path):
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
        name, version = parse_cmake_project_info(cmake)
        assert name == "unknown"
        assert version == "0.0.0"


# -- parse_conan_profile_arch -------------------------------------------------

class TestParseConanProfileArch:
    def test_arch_from_settings(self, tmp_path):
        profile = tmp_path / "profile"
        profile.write_text("[settings]\narch=x86\nos=Windows\n", encoding="utf-8")
        assert parse_conan_profile_arch(profile) == "x86"

    def test_no_arch_returns_none(self, tmp_path):
        profile = tmp_path / "profile"
        profile.write_text("[settings]\nos=Windows\n", encoding="utf-8")
        assert parse_conan_profile_arch(profile) is None

    def test_arch_in_wrong_section_ignored(self, tmp_path):
        profile = tmp_path / "profile"
        profile.write_text("[options]\narch=x86\n", encoding="utf-8")
        assert parse_conan_profile_arch(profile) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert parse_conan_profile_arch(tmp_path / "nonexistent") is None

    def test_whitespace_stripped(self, tmp_path):
        profile = tmp_path / "profile"
        profile.write_text("[settings]\n  arch = armv8 \n", encoding="utf-8")
        assert parse_conan_profile_arch(profile) == "armv8"

    def test_comments_skipped(self, tmp_path):
        profile = tmp_path / "profile"
        profile.write_text(
            "[settings]\n# arch=x86\narch=x86_64\n", encoding="utf-8"
        )
        assert parse_conan_profile_arch(profile) == "x86_64"

    def test_multiple_sections(self, tmp_path):
        profile = tmp_path / "profile"
        profile.write_text(
            "[options]\nfoo=bar\n\n[settings]\narch=armv7\nos=Linux\n",
            encoding="utf-8",
        )
        assert parse_conan_profile_arch(profile) == "armv7"


# -- NativeConfig -------------------------------------------------------------

class TestNativeConfig:
    def test_build_dir_name(self):
        cfg = NativeConfig()
        assert cfg.build_dir_name("Debug") == "Debug"
        assert cfg.build_dir_name("Release") == "Release"

    def test_preset_name(self):
        cfg = NativeConfig()
        assert cfg.preset_name("Debug") == "conan-debug"
        assert cfg.preset_name("Release") == "conan-release"

    def test_get_environment_empty_by_default(self):
        cfg = NativeConfig()
        assert cfg.get_environment() == {}

    def test_get_environment_with_vars(self):
        cfg = NativeConfig(env_vars={"CC": "gcc", "CXX": "g++"})
        env = cfg.get_environment()
        assert env == {"CC": "gcc", "CXX": "g++"}

    def test_validate_passes(self):
        cfg = NativeConfig()
        cfg.validate()  # should not raise

    @pytest.mark.parametrize(
        "machine, expected",
        [
            ("AMD64", "x86_64"),
            ("x86_64", "x86_64"),
            ("aarch64", "armv8"),
            ("arm64", "armv8"),
            ("riscv64", "riscv64"),  # unknown maps to itself
        ],
    )
    def test_detect_architecture(self, machine, expected):
        with patch("sbuild.config.platform.machine", return_value=machine):
            assert NativeConfig.detect_architecture() == expected

    def test_detect_target_architecture_from_profile(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        profile = profiles / "windows_debug"
        profile.write_text("[settings]\narch=x86\nos=Windows\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            arch = NativeConfig.detect_target_architecture(tmp_path, "Debug")
        assert arch == "x86"

    def test_detect_target_architecture_falls_back_to_host(self, tmp_path):
        with patch("sbuild.config.platform.machine", return_value="AMD64"):
            arch = NativeConfig.detect_target_architecture(tmp_path, "Debug")
        assert arch == "x86_64"


# -- WasmConfig ---------------------------------------------------------------

class TestWasmConfig:
    def test_build_dir_name(self):
        cfg = WasmConfig()
        assert cfg.build_dir_name("Debug") == "wasm-debug"
        assert cfg.build_dir_name("Release") == "wasm-release"

    def test_preset_name(self):
        cfg = WasmConfig()
        assert cfg.preset_name("Debug") == "wasm-debug"
        assert cfg.preset_name("Release") == "wasm-release"

    def test_display_name(self):
        cfg = WasmConfig()
        assert cfg.display_name == "WASM"

    def test_get_environment_basic(self, tmp_path):
        cfg = WasmConfig(
            emsdk_path=tmp_path / "emsdk",
            qt_wasm_path=tmp_path / "qt_wasm",
            qt_host_path=tmp_path / "qt_host",
        )
        env = cfg.get_environment()
        assert "EMSDK" in env
        assert "QT_WASM_PATH" in env
        assert "QT_HOST_PATH" in env
        assert "OPENSSL" not in env

    def test_get_environment_with_openssl(self, tmp_path):
        cfg = WasmConfig(
            emsdk_path=tmp_path / "emsdk",
            qt_wasm_path=tmp_path / "qt_wasm",
            qt_host_path=tmp_path / "qt_host",
            openssl_path=tmp_path / "openssl",
        )
        env = cfg.get_environment()
        assert "OPENSSL" in env

    def test_from_env_file_valid(self, wasm_env_file, tmp_path):
        cfg = WasmConfig.from_env_file(wasm_env_file)
        assert cfg.emsdk_path == tmp_path / "emsdk"
        assert cfg.qt_wasm_path == tmp_path / "qt_wasm"
        assert cfg.qt_host_path == tmp_path / "qt_host"

    def test_from_env_file_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            WasmConfig.from_env_file(tmp_path / "missing.env")

    def test_from_env_file_missing_vars(self, tmp_path):
        env_file = tmp_path / ".env.wasm"
        env_file.write_text("EMSDK=/some/path\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="Missing required"):
            WasmConfig.from_env_file(env_file)

    def test_from_env_file_with_openssl(self, tmp_path):
        emsdk = tmp_path / "emsdk"
        qt_wasm = tmp_path / "qt_wasm"
        qt_host = tmp_path / "qt_host"
        openssl = tmp_path / "openssl"
        for d in (emsdk, qt_wasm, qt_host, openssl):
            d.mkdir()

        env_file = tmp_path / ".env.wasm"
        env_file.write_text(
            f"EMSDK={emsdk}\n"
            f"QT_WASM_PATH={qt_wasm}\n"
            f"QT_HOST_PATH={qt_host}\n"
            f"OPENSSL={openssl}\n",
            encoding="utf-8",
        )
        cfg = WasmConfig.from_env_file(env_file)
        assert cfg.openssl_path == openssl

    def test_validate_all_paths_exist(self, tmp_path):
        emsdk = tmp_path / "emsdk"
        qt_wasm = tmp_path / "qt_wasm"
        qt_host = tmp_path / "qt_host"
        for d in (emsdk, qt_wasm, qt_host):
            d.mkdir()
        cfg = WasmConfig(emsdk_path=emsdk, qt_wasm_path=qt_wasm, qt_host_path=qt_host)
        cfg.validate()  # should not raise

    def test_validate_missing_paths(self, tmp_path):
        cfg = WasmConfig(
            emsdk_path=tmp_path / "missing1",
            qt_wasm_path=tmp_path / "missing2",
            qt_host_path=tmp_path / "missing3",
        )
        with pytest.raises(EnvironmentSetupError, match="Invalid WASM"):
            cfg.validate()


# -- BuildConfig --------------------------------------------------------------

class TestBuildConfig:
    def test_capitalizes_build_type(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="debug")
        assert cfg.build_type == "Debug"

    def test_unknown_platform_raises(self, project_root):
        with pytest.raises(ConfigError, match="Unknown platform"):
            BuildConfig(project_root=project_root, platform="unknown")

    def test_parses_cmake_info(self, project_root):
        cfg = BuildConfig(project_root=project_root)
        assert cfg.project_name == "TestProject"
        assert cfg.version == "1.2.3"

    def test_build_dir(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="debug")
        assert cfg.build_dir == project_root / "build" / "Debug"

    def test_preset_name_native(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="release")
        assert cfg.preset_name == "conan-release"

    def test_native_config_reads_target_arch_from_profile(self, project_root):
        profiles = project_root / "profiles"
        profiles.mkdir()
        profile = profiles / "windows_debug"
        profile.write_text("[settings]\narch=x86\nos=Windows\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = BuildConfig(project_root=project_root, build_type="debug")
        assert cfg.platform_config.target_arch == "x86"


class TestBuildConfigBuildNumber:
    def test_override_returns_override(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_number=42)
        assert cfg.get_resolved_build_number() == 42

    def test_version_h_parsing(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="debug")
        # Create generated/version.h in the build dir
        gen_dir = cfg.build_dir / "generated"
        gen_dir.mkdir(parents=True)
        version_h = gen_dir / "version.h"
        version_h.write_text(
            '#define APP_VERSION_BUILD 99\n', encoding="utf-8"
        )
        assert cfg.get_resolved_build_number() == 99

    def test_git_fallback(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="debug")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="157\n")
            result = cfg.get_resolved_build_number()
            assert result == 157

    def test_failure_returns_zero(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="debug")
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = cfg.get_resolved_build_number()
            assert result == 0
