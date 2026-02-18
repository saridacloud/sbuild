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
    resolve_arch,
    resolve_profile_path,
    normalize_arch,
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

    def test_preset_name_no_presets_file(self):
        """No CMakeUserPresets.json → falls back to conan-{build_type} convention."""
        cfg = NativeConfig(project_root=Path("/nonexistent"))
        assert cfg.preset_name("Debug") == "conan-debug"
        assert cfg.preset_name("Release") == "conan-release"

    def test_preset_name_single_config(self, tmp_path):
        """Single-config presets file → returns conan-{build_type}."""
        import json
        presets = {
            "version": 4,
            "include": [f"build/Debug/generators/CMakePresets.json"],
        }
        (tmp_path / "CMakeUserPresets.json").write_text(json.dumps(presets))
        gen_dir = tmp_path / "build" / "Debug" / "generators"
        gen_dir.mkdir(parents=True)
        (gen_dir / "CMakePresets.json").write_text(json.dumps({
            "version": 4,
            "configurePresets": [{"name": "conan-debug"}],
        }))

        cfg = NativeConfig(project_root=tmp_path)
        assert cfg.preset_name("Debug") == "conan-debug"

    def test_preset_name_multi_config(self, tmp_path):
        """Multi-config presets file (conan-default) → returns conan-default."""
        import json
        presets = {
            "version": 4,
            "include": [f"build/generators/CMakePresets.json"],
        }
        (tmp_path / "CMakeUserPresets.json").write_text(json.dumps(presets))
        gen_dir = tmp_path / "build" / "generators"
        gen_dir.mkdir(parents=True)
        (gen_dir / "CMakePresets.json").write_text(json.dumps({
            "version": 4,
            "configurePresets": [{"name": "conan-default"}],
            "buildPresets": [{"name": "conan-debug"}, {"name": "conan-release"}],
        }))

        cfg = NativeConfig(project_root=tmp_path)
        assert cfg.preset_name("Debug") == "conan-default"

    def test_build_preset_name(self):
        """Build preset is always conan-{build_type} regardless of generator."""
        cfg = NativeConfig()
        assert cfg.build_preset_name("Debug") == "conan-debug"
        assert cfg.build_preset_name("Release") == "conan-release"

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
        """No presets file → falls back to conan-{build_type} convention."""
        cfg = BuildConfig(project_root=project_root, build_type="release")
        assert cfg.preset_name == "conan-release"

    def test_build_preset_name_native(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="release")
        assert cfg.build_preset_name == "conan-release"

    def test_preset_name_native_multi_config(self, project_root):
        """Multi-config presets → configure preset is conan-default."""
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
        cfg = BuildConfig(project_root=project_root, build_type="release")
        assert cfg.preset_name == "conan-default"
        assert cfg.build_preset_name == "conan-release"

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


# -- resolve_arch -------------------------------------------------------------

class TestResolveArch:
    def test_cli_arch_wins(self):
        result = resolve_arch("x64", {"SBUILD_ARCH": "x86"})
        assert result == "x64"

    def test_env_vars_second_priority(self):
        result = resolve_arch(None, {"SBUILD_ARCH": "arm64"})
        assert result == "arm64"

    def test_system_env_third_priority(self):
        with patch.dict("os.environ", {"SBUILD_ARCH": "x86"}):
            result = resolve_arch(None, {})
        assert result == "x86"

    def test_env_vars_beat_system_env(self):
        with patch.dict("os.environ", {"SBUILD_ARCH": "x86"}):
            result = resolve_arch(None, {"SBUILD_ARCH": "x64"})
        assert result == "x64"

    def test_none_when_nothing_set(self):
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_arch(None, {})
        assert result is None


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


# -- NativeConfig with arch/profile ------------------------------------------

class TestNativeConfigArchProfile:
    def test_detect_with_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug", arch="x64")
        assert cfg.requested_arch == "x64"
        assert cfg.conan_profile_path == profiles / "windows_x64_debug"
        assert cfg.target_arch == "x86_64"

    def test_detect_with_profile_override(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "my_custom").write_text(
            "[settings]\narch=armv8\nos=Windows\n", encoding="utf-8"
        )
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        cfg = NativeConfig.detect(tmp_path, "Debug", profile="my_custom")
        assert cfg.profile_override == "my_custom"
        assert cfg.conan_profile_path == profiles / "my_custom"
        assert cfg.target_arch == "armv8"

    def test_detect_with_env_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x86_debug").write_text(
            "[settings]\narch=x86\nos=Windows\n", encoding="utf-8"
        )
        # Write .env with SBUILD_ARCH
        env_file = tmp_path / ".env"
        env_file.write_text("SBUILD_ARCH=x86\n", encoding="utf-8")
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug")
        assert cfg.requested_arch == "x86"
        assert cfg.conan_profile_path == profiles / "windows_x86_debug"

    def test_detect_backward_compatible_no_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug")
        assert cfg.requested_arch is None
        assert cfg.conan_profile_path == profiles / "windows_debug"

    def test_build_dir_name_with_arch(self):
        cfg = NativeConfig(requested_arch="x64")
        assert cfg.build_dir_name("Debug") == "x64/Debug"
        assert cfg.build_dir_name("Release") == "x64/Release"

    def test_build_dir_name_without_arch(self):
        cfg = NativeConfig()
        assert cfg.build_dir_name("Debug") == "Debug"

    def test_cli_arch_overrides_env_arch(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        # .env has x86, but CLI passes x64
        env_file = tmp_path / ".env"
        env_file.write_text("SBUILD_ARCH=x86\n", encoding="utf-8")
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug", arch="x64")
        assert cfg.requested_arch == "x64"


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


# -- NativeConfig.detect arch regression tests --------------------------------

class TestNativeConfigDetectArchFix:
    """Regression tests for arch detection bugs (x86 on x86_64 host)."""

    def test_detect_with_arch_no_profile_uses_requested_arch(self, tmp_path):
        """Bug 1: When profile doesn't exist, fallback should use requested arch, not host."""
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        # No profile file created — profile lookup will return None
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug", arch="x86")
        assert cfg.target_arch == "x86"

    def test_detect_with_x64_normalizes_target_arch(self, tmp_path):
        """Bug 2: x64 should normalize to x86_64 in target_arch."""
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug", arch="x64")
        assert cfg.target_arch == "x86_64"

    def test_detect_with_arm64_normalizes_target_arch(self, tmp_path):
        """Bug 2: arm64 should normalize to armv8 in target_arch."""
        cmake = tmp_path / "CMakeLists.txt"
        cmake.write_text("project(Test VERSION 1.0.0)\n", encoding="utf-8")
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = NativeConfig.detect(tmp_path, "Debug", arch="arm64")
        assert cfg.target_arch == "armv8"


# -- BuildConfig with arch/profile -------------------------------------------

class TestBuildConfigArch:
    def test_build_dir_with_arch(self, project_root):
        profiles = project_root / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_debug").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = BuildConfig(project_root=project_root, build_type="debug", arch="x64")
        assert cfg.build_dir == project_root / "build" / "x64" / "Debug"

    def test_build_dir_without_arch(self, project_root):
        cfg = BuildConfig(project_root=project_root, build_type="debug")
        assert cfg.build_dir == project_root / "build" / "Debug"

    def test_arch_and_release(self, project_root):
        profiles = project_root / "profiles"
        profiles.mkdir()
        (profiles / "windows_x64_release").write_text(
            "[settings]\narch=x86_64\nos=Windows\n", encoding="utf-8"
        )
        with patch("sbuild.config.platform.system", return_value="Windows"):
            cfg = BuildConfig(project_root=project_root, build_type="release", arch="x64")
        assert cfg.build_dir == project_root / "build" / "x64" / "Release"
