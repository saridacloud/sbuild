"""Tests for sbuild.config — utilities, ConfigManager, and pure data holders."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sbuild.config import (
    BuildConfig,
    ConfigManager,
    NativeConfig,
    WasmConfig,
    conan_to_friendly_arch,
    detect_architecture,
    load_env_file,
    normalize_arch,
    parse_cmake_project_info,
    parse_conan_profile_arch,
    resolve_profile_path,
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

    def test_double_quoted_value_stripped(self, env_file):
        result = load_env_file(env_file)
        assert result["DOUBLE_QUOTED"] == "-DFOO=BAR -DBAZ=QUX"

    def test_single_quoted_value_stripped(self, env_file):
        result = load_env_file(env_file)
        assert result["SINGLE_QUOTED"] == "some value"

    def test_mismatched_quotes_not_stripped(self, env_file):
        result = load_env_file(env_file)
        assert result["MISMATCHED_QUOTES"] == "\"not matched'"


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


# -- detect_architecture ------------------------------------------------------

class TestDetectArchitecture:
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
            assert detect_architecture() == expected


# -- normalize_arch -----------------------------------------------------------

class TestNormalizeArch:
    def test_x86_passthrough(self):
        assert normalize_arch("x86") == "x86"

    def test_x64_to_x86_64(self):
        assert normalize_arch("x64") == "x86_64"

    def test_arm64_to_armv8(self):
        assert normalize_arch("arm64") == "armv8"

    def test_conan_name_passthrough_x86_64(self):
        assert normalize_arch("x86_64") == "x86_64"

    def test_conan_name_passthrough_armv8(self):
        assert normalize_arch("armv8") == "armv8"

    def test_unknown_passthrough(self):
        assert normalize_arch("mips") == "mips"


# -- resolve_profile_path -----------------------------------------------------

class TestResolveProfilePath:
    def test_default_os_build_type(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_debug").write_text("[settings]\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            result = resolve_profile_path(tmp_path, "Debug")
        assert result == profiles / "windows_debug"

    def test_default_returns_none_when_missing(self, tmp_path):
        with patch("sbuild.config.platform.system", return_value="Windows"):
            result = resolve_profile_path(tmp_path, "Debug")
        assert result is None

    def test_arch_qualified_profile(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text("[settings]\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            result = resolve_profile_path(tmp_path, "Debug", arch="x64")
        assert result == profiles / "windows_x64_debug"

    def test_arch_returns_none_when_missing(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        # Only default profile exists, not arch-qualified
        (profiles / "windows_debug").write_text("[settings]\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            result = resolve_profile_path(tmp_path, "Debug", arch="x64")
        assert result is None  # Does NOT fall back to default

    def test_profile_override(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "my_custom").write_text("[settings]\n", encoding="utf-8")
        result = resolve_profile_path(tmp_path, "Debug", profile="my_custom")
        assert result == profiles / "my_custom"

    def test_profile_override_returns_none_when_missing(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        result = resolve_profile_path(tmp_path, "Debug", profile="nonexistent")
        assert result is None

    def test_profile_takes_precedence_over_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "my_custom").write_text("[settings]\n", encoding="utf-8")
        (profiles / "windows_x64_debug").write_text("[settings]\n", encoding="utf-8")
        result = resolve_profile_path(tmp_path, "Debug", arch="x64", profile="my_custom")
        assert result == profiles / "my_custom"

    def test_linux_profile_name(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "linux_x86_release").write_text("[settings]\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Linux"):
            result = resolve_profile_path(tmp_path, "Release", arch="x86")
        assert result == profiles / "linux_x86_release"


# -- ConfigManager._resolve ---------------------------------------------------

class TestConfigManagerResolve:
    """Test the generic _resolve method priority chain."""

    def test_cli_wins_over_env(self, project_root):
        (project_root / ".env").write_text("SBUILD_PLATFORM=wasm\n")
        mgr = ConfigManager(project_root=project_root, platform="native")
        cfg = mgr.resolve()
        assert cfg.platform == "native"

    def test_env_file_second_priority(self, project_root):
        (project_root / ".env").write_text("SBUILD_VERBOSE=true\n")
        with patch.dict("os.environ", {}, clear=True):
            mgr = ConfigManager(project_root=project_root)
            cfg = mgr.resolve()
        assert cfg.verbose is True

    def test_system_env_third_priority(self, project_root):
        with patch.dict("os.environ", {"SBUILD_VERBOSE": "true"}):
            mgr = ConfigManager(project_root=project_root)
            cfg = mgr.resolve()
        assert cfg.verbose is True

    def test_default_when_nothing_set(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            mgr = ConfigManager(project_root=project_root)
            cfg = mgr.resolve()
        assert cfg.platform == "native"


# -- ConfigManager: platform resolution ---------------------------------------

class TestConfigManagerPlatform:
    def test_cli_platform_wins(self, project_root):
        (project_root / ".env").write_text("SBUILD_PLATFORM=native\n")
        cfg = ConfigManager(project_root=project_root, platform="native").resolve()
        assert cfg.platform == "native"

    def test_env_file_platform(self, project_root):
        (project_root / ".env").write_text("SBUILD_PLATFORM=native\n")
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform == "native"

    def test_unknown_platform_raises(self, project_root):
        with pytest.raises(ConfigError, match="Unknown platform"):
            ConfigManager(project_root=project_root, platform="unknown").resolve()


# -- ConfigManager: verbose resolution ----------------------------------------

class TestConfigManagerVerbose:
    def test_cli_true(self, project_root):
        cfg = ConfigManager(project_root=project_root, verbose=True).resolve()
        assert cfg.verbose is True

    def test_cli_false(self, project_root):
        cfg = ConfigManager(project_root=project_root, verbose=False).resolve()
        assert cfg.verbose is False

    def test_env_true_values(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            for val in ("true", "1", "yes", "True", "YES"):
                (project_root / ".env").write_text(f"SBUILD_VERBOSE={val}\n")
                cfg = ConfigManager(project_root=project_root).resolve()
                assert cfg.verbose is True

    def test_env_false_values(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            (project_root / ".env").write_text("SBUILD_VERBOSE=false\n")
            cfg = ConfigManager(project_root=project_root).resolve()
            assert cfg.verbose is False

    def test_default_false(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.verbose is False


# -- ConfigManager: jobs resolution -------------------------------------------

class TestConfigManagerJobs:
    def test_cli_wins(self, project_root):
        (project_root / ".env").write_text("SBUILD_PARALLEL_JOBS=4\n")
        cfg = ConfigManager(project_root=project_root, jobs=8).resolve()
        assert cfg.jobs == 8

    def test_env_file(self, project_root):
        (project_root / ".env").write_text("SBUILD_PARALLEL_JOBS=16\n")
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.jobs == 16

    def test_invalid_env_uses_default(self, project_root):
        (project_root / ".env").write_text("SBUILD_PARALLEL_JOBS=abc\n")
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        import os
        assert cfg.jobs == (os.cpu_count() or 4)

    def test_default_cpu_count(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        import os
        assert cfg.jobs == (os.cpu_count() or 4)


# -- ConfigManager: build_dir_base resolution ---------------------------------

class TestConfigManagerBuildDirBase:
    def test_env_file(self, project_root):
        (project_root / ".env").write_text("SBUILD_BUILD_DIR=out\n")
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.build_dir_base == "out"

    def test_system_env(self, project_root):
        with patch.dict("os.environ", {"SBUILD_BUILD_DIR": "output"}):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.build_dir_base == "output"

    def test_default_build(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.build_dir_base == "build"


# -- ConfigManager: install_prefix resolution ---------------------------------

class TestConfigManagerInstallPrefix:
    def test_cli_wins(self, project_root):
        (project_root / ".env").write_text("SBUILD_INSTALL_DIR=/env\n")
        cfg = ConfigManager(project_root=project_root, install_prefix=Path("/custom")).resolve()
        assert cfg.install_prefix == Path("/custom")

    def test_env_file(self, project_root):
        (project_root / ".env").write_text("SBUILD_INSTALL_DIR=/install\n")
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.install_prefix == Path("/install")

    def test_default_none(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.install_prefix is None


# -- ConfigManager: cmake_args resolution -------------------------------------

class TestConfigManagerCmakeArgs:
    def test_cli_only(self, project_root):
        cfg = ConfigManager(project_root=project_root, cmake_args="-DFOO=1").resolve()
        assert cfg.cmake_args == "-DFOO=1"

    def test_env_only(self, project_root):
        (project_root / ".env").write_text("SBUILD_CMAKE_ARGS=-DBAR=2\n")
        cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.cmake_args == "-DBAR=2"

    def test_merge_env_and_cli(self, project_root):
        (project_root / ".env").write_text("SBUILD_CMAKE_ARGS=-DBAR=2\n")
        cfg = ConfigManager(project_root=project_root, cmake_args="-DFOO=1").resolve()
        assert cfg.cmake_args == "-DBAR=2 -DFOO=1"

    def test_wasm_args_included(self, project_root, wasm_env_vars, tmp_path):
        # Write .env with WASM vars + cmake args
        env_content = (
            f"EMSDK={tmp_path / 'emsdk'}\n"
            f"SBUILD_WASM_QT_PATH={tmp_path / 'qt_wasm'}\n"
            f"SBUILD_WASM_QT_HOST_PATH={tmp_path / 'qt_host'}\n"
            f"SBUILD_PLATFORM=wasm\n"
            f"SBUILD_CMAKE_ARGS=-DA=1\n"
            f"SBUILD_WASM_CMAKE_ARGS=-DB=2\n"
        )
        (project_root / ".env").write_text(env_content)
        cfg = ConfigManager(
            project_root=project_root, platform="wasm", cmake_args="-DC=3",
        ).resolve()
        assert cfg.cmake_args == "-DA=1 -DB=2 -DC=3"

    def test_wasm_args_ignored_for_native(self, project_root):
        (project_root / ".env").write_text(
            "SBUILD_CMAKE_ARGS=-DA=1\nSBUILD_WASM_CMAKE_ARGS=-DB=2\n"
        )
        cfg = ConfigManager(project_root=project_root, platform="native").resolve()
        assert cfg.cmake_args == "-DA=1"

    def test_none_when_empty(self, project_root):
        cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.cmake_args is None

    def test_quoted_env_value(self, project_root):
        (project_root / ".env").write_text('SBUILD_CMAKE_ARGS="-DFOO=BAR -DBAZ=1"\n')
        cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.cmake_args == "-DFOO=BAR -DBAZ=1"


# -- ConfigManager: arch resolution -------------------------------------------

class TestConfigManagerArch:
    def test_cli_arch_wins(self, project_root):
        (project_root / ".env").write_text("SBUILD_ARCH=x86\n")
        cfg = ConfigManager(project_root=project_root, arch="x64").resolve()
        assert cfg.platform_config.requested_arch == "x64"

    def test_env_arch_second_priority(self, project_root):
        (project_root / ".env").write_text("SBUILD_ARCH=arm64\n")
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform_config.requested_arch == "arm64"

    def test_system_env_third_priority(self, project_root):
        with patch.dict("os.environ", {"SBUILD_ARCH": "x86"}):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform_config.requested_arch == "x86"

    def test_none_when_nothing_set(self, project_root):
        with patch.dict("os.environ", {}, clear=True):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform_config.requested_arch is None


# -- ConfigManager: build_dir computation ------------------------------------

class TestConfigManagerBuildDir:
    def test_native_default(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.build_dir == project_root / "build" / "Debug"

    def test_native_with_arch(self, project_root):
        profiles = project_root / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(project_root=project_root, build_type="Debug", arch="x64").resolve()
        assert cfg.build_dir == project_root / "build" / "Debug"

    def test_native_without_arch(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.build_dir == project_root / "build" / "Debug"

    def test_native_release(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Release").resolve()
        assert cfg.build_dir == project_root / "build" / "Release"

    def test_arch_and_release(self, project_root):
        profiles = project_root / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_release").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(
                project_root=project_root, build_type="Release", arch="x64",
            ).resolve()
        assert cfg.build_dir == project_root / "build" / "Release"


# -- ConfigManager: preset computation ----------------------------------------

class TestConfigManagerPreset:
    def test_native_no_presets_file(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.preset_name == "conan-debug"

    def test_native_release_preset(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Release").resolve()
        assert cfg.preset_name == "conan-release"

    def test_native_multi_config(self, project_root):
        import json
        presets = {
            "version": 4,
            "include": ["build/generators/CMakePresets.json"],
        }
        (project_root / "CMakeUserPresets.json").write_text(json.dumps(presets))
        gen_dir = project_root / "build" / "generators"
        gen_dir.mkdir(parents=True)
        (gen_dir / "CMakePresets.json").write_text(json.dumps({
            "version": 4,
            "configurePresets": [{"name": "conan-default"}],
            "buildPresets": [{"name": "conan-debug"}, {"name": "conan-release"}],
        }))
        cfg = ConfigManager(project_root=project_root, build_type="Release").resolve()
        assert cfg.preset_name == "conan-default"
        assert cfg.build_preset_name == "conan-release"

    def test_native_build_preset_name(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.build_preset_name == "conan-debug"
        cfg2 = ConfigManager(project_root=project_root, build_type="Release").resolve()
        assert cfg2.build_preset_name == "conan-release"


# -- ConfigManager: project info -----------------------------------------------

class TestConfigManagerProjectInfo:
    def test_parses_cmake_info(self, project_root):
        cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.project_name == "TestProject"
        assert cfg.version == "1.2.3"

    def test_capitalizes_build_type(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="debug").resolve()
        assert cfg.build_type == "Debug"


# -- ConfigManager: native arch detection -------------------------------------

class TestConfigManagerNativeArch:
    def test_detect_with_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(project_root=tmp_path, build_type="Debug", arch="x64").resolve()
        assert cfg.platform_config.requested_arch == "x64"
        assert cfg.platform_config.friendly_arch == "x64"
        assert cfg.platform_config.conan_profile_path == profiles / "windows_x64_debug"
        assert cfg.platform_config.target_arch == "x86_64"

    def test_detect_with_profile_override(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "my_custom").write_text(
            "[settings]\narch=armv8\nos=Windows\n", encoding="utf-8"
        )
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        cfg = ConfigManager(
            project_root=tmp_path, build_type="Debug", profile="my_custom",
        ).resolve()
        assert cfg.platform_config.profile_override == "my_custom"
        assert cfg.platform_config.conan_profile_path == profiles / "my_custom"
        assert cfg.platform_config.target_arch == "armv8"

    def test_detect_with_env_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x86_debug").write_text(
            "[settings]\narch=x86\nos=Windows\n", encoding="utf-8"
        )
        (tmp_path / ".env").write_text("SBUILD_ARCH=x86\n", encoding="utf-8")
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(project_root=tmp_path, build_type="Debug").resolve()
        assert cfg.platform_config.requested_arch == "x86"
        assert cfg.platform_config.conan_profile_path == profiles / "windows_x86_debug"

    def test_detect_backward_compatible_no_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"), \
             patch("sbuild.config.detect_architecture", return_value="x86_64"):
            cfg = ConfigManager(project_root=tmp_path, build_type="Debug").resolve()
        assert cfg.platform_config.requested_arch is None
        assert cfg.platform_config.friendly_arch == "x64"
        assert cfg.platform_config.conan_profile_path == profiles / "windows_debug"

    def test_cli_arch_overrides_env_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        (tmp_path / ".env").write_text("SBUILD_ARCH=x86\n", encoding="utf-8")
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(
                project_root=tmp_path, build_type="Debug", arch="x64",
            ).resolve()
        assert cfg.platform_config.requested_arch == "x64"

    def test_reads_target_arch_from_profile(self, project_root):
        profiles = project_root / "profiles"
        profiles.mkdir()
        profile = profiles / "windows_debug"
        profile.write_text("[settings]\narch=x86\nos=Windows\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"), \
             patch("sbuild.config.detect_architecture", return_value="x86_64"):
            cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.platform_config.target_arch == "x86"
        assert cfg.platform_config.friendly_arch == "x64"


# -- ConfigManager: arch regression tests ------------------------------------

class TestConfigManagerArchRegression:
    """Regression tests for arch detection bugs (x86 on x86_64 host)."""

    def test_detect_with_arch_no_profile_uses_requested_arch(self, tmp_path):
        """Bug 1: When profile doesn't exist, fallback should use requested arch, not host."""
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(
                project_root=tmp_path, build_type="Debug", arch="x86",
            ).resolve()
        assert cfg.platform_config.target_arch == "x86"

    def test_detect_with_x64_normalizes_target_arch(self, tmp_path):
        """Bug 2: x64 should normalize to x86_64 in target_arch."""
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(
                project_root=tmp_path, build_type="Debug", arch="x64",
            ).resolve()
        assert cfg.platform_config.target_arch == "x86_64"

    def test_detect_with_arm64_normalizes_target_arch(self, tmp_path):
        """Bug 2: arm64 should normalize to armv8 in target_arch."""
        (tmp_path / "CMakeLists.txt").write_text(
            "project(Test VERSION 1.0.0)\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = ConfigManager(
                project_root=tmp_path, build_type="Debug", arch="arm64",
            ).resolve()
        assert cfg.platform_config.target_arch == "armv8"


# -- ConfigManager: WASM config -----------------------------------------------

class TestConfigManagerWasm:
    def test_wasm_config_valid(self, project_root, wasm_env_vars, tmp_path):
        env_content = "\n".join(f"{k}={v}" for k, v in wasm_env_vars.items())
        (project_root / ".env").write_text(env_content)
        cfg = ConfigManager(project_root=project_root, platform="wasm").resolve()
        assert cfg.platform == "wasm"
        assert cfg.platform_config.emsdk_path == tmp_path / "emsdk"
        assert cfg.platform_config.qt_wasm_path == tmp_path / "qt_wasm"
        assert cfg.platform_config.qt_host_path == tmp_path / "qt_host"

    def test_wasm_missing_required(self, project_root):
        (project_root / ".env").write_text("EMSDK=/some/path\n")
        with pytest.raises(ConfigError, match="Missing required"):
            ConfigManager(project_root=project_root, platform="wasm").resolve()

    def test_wasm_missing_emsdk(self, project_root):
        (project_root / ".env").write_text("SBUILD_WASM_QT_PATH=/some/path\n")
        with pytest.raises(ConfigError, match="Missing required"):
            ConfigManager(project_root=project_root, platform="wasm").resolve()

    def test_wasm_environment_field(self, project_root, wasm_env_vars, tmp_path):
        env_content = "\n".join(f"{k}={v}" for k, v in wasm_env_vars.items())
        (project_root / ".env").write_text(env_content)
        cfg = ConfigManager(project_root=project_root, platform="wasm").resolve()
        env = cfg.platform_config.environment
        assert "EMSDK" in env
        assert "QT_WASM_PATH" in env
        assert "QT_HOST_PATH" in env

    def test_wasm_without_host_path(self, project_root, tmp_path):
        emsdk = tmp_path / "emsdk2"
        qt_wasm = tmp_path / "qt_wasm2"
        emsdk.mkdir()
        qt_wasm.mkdir()
        (project_root / ".env").write_text(
            f"EMSDK={emsdk}\nSBUILD_WASM_QT_PATH={qt_wasm}\n"
        )
        cfg = ConfigManager(project_root=project_root, platform="wasm").resolve()
        assert cfg.platform_config.qt_host_path is None
        assert "QT_HOST_PATH" not in cfg.platform_config.environment

    def test_wasm_build_dir(self, project_root, wasm_env_vars):
        env_content = "\n".join(f"{k}={v}" for k, v in wasm_env_vars.items())
        (project_root / ".env").write_text(env_content)
        cfg = ConfigManager(
            project_root=project_root, platform="wasm", build_type="Debug",
        ).resolve()
        assert cfg.build_dir == project_root / "build" / "wasm-debug"

    def test_wasm_preset_name(self, project_root, wasm_env_vars):
        env_content = "\n".join(f"{k}={v}" for k, v in wasm_env_vars.items())
        (project_root / ".env").write_text(env_content)
        cfg = ConfigManager(
            project_root=project_root, platform="wasm", build_type="Debug",
        ).resolve()
        assert cfg.preset_name == "wasm-debug"
        assert cfg.build_preset_name == "wasm-debug"


# -- BuildConfig: get_resolved_build_number -----------------------------------

class TestBuildConfigBuildNumber:
    def test_override_returns_override(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_number=42).resolve()
        assert cfg.get_resolved_build_number() == 42

    def test_version_h_parsing(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        gen_dir = cfg.build_dir / "generated"
        gen_dir.mkdir(parents=True)
        version_h = gen_dir / "version.h"
        version_h.write_text(
            '#define APP_VERSION_BUILD 99\n', encoding="utf-8"
        )
        assert cfg.get_resolved_build_number() == 99

    def test_git_fallback(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="157\n")
            result = cfg.get_resolved_build_number()
            assert result == 157

    def test_failure_returns_zero(self, project_root):
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = cfg.get_resolved_build_number()
            assert result == 0


# -- NativeConfig: pure data holder -------------------------------------------

class TestNativeConfigDataHolder:
    """Test that NativeConfig is a simple frozen data holder."""

    def test_default_values(self):
        cfg = NativeConfig()
        assert cfg.host_arch == "x86_64"
        assert cfg.target_arch == "x86_64"
        assert cfg.requested_arch is None
        assert cfg.friendly_arch == "x64"
        assert cfg.env_vars == {}

    def test_frozen(self):
        cfg = NativeConfig()
        with pytest.raises(AttributeError):
            cfg.host_arch = "armv8"

    def test_with_values(self):
        cfg = NativeConfig(
            host_arch="x86_64", target_arch="x86",
            requested_arch="x86", env_vars={"FOO": "bar"},
        )
        assert cfg.target_arch == "x86"
        assert cfg.env_vars == {"FOO": "bar"}


# -- WasmConfig: pure data holder ---------------------------------------------

class TestWasmConfigDataHolder:
    """Test that WasmConfig is a simple frozen data holder."""

    def test_default_values(self):
        cfg = WasmConfig()
        assert cfg.qt_host_path is None
        assert cfg.openssl_root_dir is None
        assert cfg.environment == {}

    def test_frozen(self):
        cfg = WasmConfig()
        with pytest.raises(AttributeError):
            cfg.emsdk_path = Path("/new")

    def test_with_values(self, tmp_path):
        cfg = WasmConfig(
            emsdk_path=tmp_path / "emsdk",
            qt_wasm_path=tmp_path / "qt",
            qt_host_path=tmp_path / "host",
            environment={"EMSDK": str(tmp_path / "emsdk")},
        )
        assert cfg.qt_host_path == tmp_path / "host"
        assert "EMSDK" in cfg.environment


# -- conan_to_friendly_arch ---------------------------------------------------

class TestConanToFriendlyArch:
    def test_x86_64_to_x64(self):
        assert conan_to_friendly_arch("x86_64") == "x64"

    def test_x86_passthrough(self):
        assert conan_to_friendly_arch("x86") == "x86"

    def test_armv8_to_arm64(self):
        assert conan_to_friendly_arch("armv8") == "arm64"

    def test_armv7_to_arm(self):
        assert conan_to_friendly_arch("armv7") == "arm"

    def test_unknown_passthrough(self):
        assert conan_to_friendly_arch("mips") == "mips"


# -- friendly_arch derived from host ------------------------------------------

class TestFriendlyArchFromHost:
    def test_friendly_arch_from_x86_64_host(self, project_root):
        with patch("sbuild.config.detect_architecture", return_value="x86_64"):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform_config.friendly_arch == "x64"

    def test_friendly_arch_from_armv8_host(self, project_root):
        with patch("sbuild.config.detect_architecture", return_value="armv8"):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform_config.friendly_arch == "arm64"

    def test_friendly_arch_from_x86_host(self, project_root):
        with patch("sbuild.config.detect_architecture", return_value="x86"):
            cfg = ConfigManager(project_root=project_root).resolve()
        assert cfg.platform_config.friendly_arch == "x86"


# -- profile fallback with arch-qualified names --------------------------------

class TestProfileFallbackArchQualified:
    def test_profile_fallback_arch_qualified_first(self, tmp_path):
        """Without --arch, finds arch-qualified profile before unqualified."""
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text("[settings]\narch=x86_64\n", encoding="utf-8")
        (profiles / "windows_debug").write_text("[settings]\narch=x86_64\n", encoding="utf-8")
        (tmp_path / "CMakeLists.txt").write_text("project(T VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"), \
             patch("sbuild.config.detect_architecture", return_value="x86_64"):
            cfg = ConfigManager(project_root=tmp_path, build_type="Debug").resolve()
        assert cfg.platform_config.conan_profile_path == profiles / "windows_x64_debug"

    def test_profile_fallback_to_unqualified(self, tmp_path):
        """Without --arch, falls back to unqualified profile when arch-qualified missing."""
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_debug").write_text("[settings]\narch=x86_64\n", encoding="utf-8")
        (tmp_path / "CMakeLists.txt").write_text("project(T VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"), \
             patch("sbuild.config.detect_architecture", return_value="x86_64"):
            cfg = ConfigManager(project_root=tmp_path, build_type="Debug").resolve()
        assert cfg.platform_config.conan_profile_path == profiles / "windows_debug"


# -- preset resolution with presets file ---------------------------------------

class TestPresetResolutionWithFile:
    def test_preset_found_in_json(self, project_root):
        import json
        presets = {
            "version": 4,
            "configurePresets": [{"name": "conan-debug"}, {"name": "conan-release"}],
        }
        (project_root / "CMakeUserPresets.json").write_text(json.dumps(presets))
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.preset_name == "conan-debug"

    def test_fallback_to_default_when_type_missing(self, project_root):
        import json
        presets = {
            "version": 4,
            "configurePresets": [{"name": "conan-default"}],
        }
        (project_root / "CMakeUserPresets.json").write_text(json.dumps(presets))
        cfg = ConfigManager(project_root=project_root, build_type="Debug").resolve()
        assert cfg.preset_name == "conan-default"
