"""Tests for sbuild.doctor helper functions."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sbuild.doctor import (
    CheckResult,
    CheckStatus,
    DoctorReport,
    _check_path,
    _collect_preset_names,
    _parse_version,
    _status_markup,
)


# -- _parse_version ----------------------------------------------------------

class TestParseVersion:
    @pytest.mark.parametrize(
        "output, expected",
        [
            ("cmake version 3.28.1", "3.28.1"),
            ("Conan version 2.1.0", "2.1.0"),
            ("git version 2.43.0.windows.1", "2.43.0"),
            ("1.12", "1.12"),
            ("1.12.0", "1.12.0"),
            ("no version here!", None),
            ("", None),
        ],
        ids=["cmake", "conan", "git", "bare_xy", "bare_xyz", "no_match", "empty"],
    )
    def test_parse_version(self, output, expected):
        assert _parse_version(output) == expected


# -- _collect_preset_names ----------------------------------------------------

class TestCollectPresetNames:
    def test_configure_presets(self):
        data = {"configurePresets": [{"name": "conan-debug"}, {"name": "conan-release"}]}
        assert _collect_preset_names(data) == {"conan-debug", "conan-release"}

    def test_build_presets(self):
        data = {"buildPresets": [{"name": "conan-debug"}]}
        assert _collect_preset_names(data) == {"conan-debug"}

    def test_both(self):
        data = {
            "configurePresets": [{"name": "a"}],
            "buildPresets": [{"name": "b"}],
        }
        assert _collect_preset_names(data) == {"a", "b"}

    def test_empty_dict(self):
        assert _collect_preset_names({}) == set()

    def test_missing_name_key(self):
        data = {"configurePresets": [{"hidden": True}]}
        assert _collect_preset_names(data) == set()


# -- _status_markup -----------------------------------------------------------

class TestStatusMarkup:
    def test_ok(self):
        assert "green" in _status_markup(CheckStatus.OK)
        assert "OK" in _status_markup(CheckStatus.OK)

    def test_warn(self):
        assert "yellow" in _status_markup(CheckStatus.WARN)
        assert "WARN" in _status_markup(CheckStatus.WARN)

    def test_fail(self):
        assert "red" in _status_markup(CheckStatus.FAIL)
        assert "FAIL" in _status_markup(CheckStatus.FAIL)


# -- _check_path --------------------------------------------------------------

class TestCheckPath:
    def test_existing_path(self, tmp_path):
        result = _check_path("MyDir", tmp_path)
        assert result.status == CheckStatus.OK
        assert result.path == tmp_path

    def test_missing_required(self, tmp_path):
        missing = tmp_path / "nonexistent"
        result = _check_path("Missing", missing, required=True)
        assert result.status == CheckStatus.FAIL

    def test_missing_optional(self, tmp_path):
        missing = tmp_path / "optional_dir"
        result = _check_path("OptDir", missing, required=False)
        assert result.status == CheckStatus.WARN

    def test_directory_not_found_message(self, tmp_path):
        missing = tmp_path / "nodir"
        result = _check_path("Dir", missing)
        assert result.message == "Directory not found"

    def test_file_not_found_message(self, tmp_path):
        missing = tmp_path / "nofile.txt"
        result = _check_path("File", missing)
        assert result.message == "Not found"

    def test_fix_hint_passthrough(self, tmp_path):
        missing = tmp_path / "gone"
        result = _check_path("X", missing, fix_hint="install X")
        assert result.fix_hint == "install X"

    def test_fix_hint_default(self, tmp_path):
        missing = tmp_path / "gone"
        result = _check_path("X", missing)
        assert str(missing) in result.fix_hint


# -- _check_cmake_presets (via DoctorReport) -----------------------------------

def _make_report(project_root: Path) -> DoctorReport:
    """Create a DoctorReport without running platform activation."""
    with patch.object(DoctorReport, "__post_init__", lambda self: None):
        report = DoctorReport(project_root=project_root)
    return report


class TestCheckCmakePresets:
    """Tests for multi-file CMake preset detection in _check_project_config."""

    def test_no_preset_files(self, tmp_path):
        """No preset files → WARN with correct fix_hint."""
        (tmp_path / "CMakeLists.txt").write_text('project(Test VERSION 1.0.0)')
        report = _make_report(tmp_path)
        results = report._check_project_config()

        preset_results = [r for r in results if r.name == "CMake Presets"]
        assert len(preset_results) == 1
        assert preset_results[0].status == CheckStatus.WARN
        assert "CMakeUserPresets.json" in preset_results[0].message
        assert "sbuild configure" in preset_results[0].fix_hint

    def test_only_user_presets(self, tmp_path):
        """Only CMakeUserPresets.json → OK + presets found."""
        (tmp_path / "CMakeLists.txt").write_text('project(Test VERSION 1.0.0)')
        presets = {
            "version": 4,
            "configurePresets": [
                {"name": "conan-debug"},
                {"name": "conan-release"},
            ],
        }
        (tmp_path / "CMakeUserPresets.json").write_text(json.dumps(presets))

        report = _make_report(tmp_path)
        results = report._check_project_config()

        # Should have an OK result for the file itself
        file_results = [r for r in results if r.name == "CMakeUserPresets.json"]
        assert len(file_results) == 1
        assert file_results[0].status == CheckStatus.OK

        # Presets should be found
        conan_debug = [r for r in results if r.name == "Preset 'conan-debug'"]
        assert conan_debug[0].status == CheckStatus.OK

    def test_both_files_merged(self, tmp_path):
        """Both files present → presets merged from both."""
        (tmp_path / "CMakeLists.txt").write_text('project(Test VERSION 1.0.0)')

        main_presets = {
            "version": 4,
            "configurePresets": [
                {"name": "conan-debug"},
                {"name": "conan-release"},
            ],
        }
        user_presets = {
            "version": 4,
            "configurePresets": [
                {"name": "wasm-debug"},
                {"name": "wasm-release"},
            ],
        }
        (tmp_path / "CMakePresets.json").write_text(json.dumps(main_presets))
        (tmp_path / "CMakeUserPresets.json").write_text(json.dumps(user_presets))
        (tmp_path / ".env.wasm").write_text("")  # enable WASM preset expectation

        report = _make_report(tmp_path)
        results = report._check_project_config()

        # Both files reported as OK
        file_names = [r.name for r in results if r.status == CheckStatus.OK]
        assert "CMakePresets.json" in file_names
        assert "CMakeUserPresets.json" in file_names

        # All four presets found
        for preset in ("conan-debug", "conan-release", "wasm-debug", "wasm-release"):
            match = [r for r in results if r.name == f"Preset '{preset}'"]
            assert match[0].status == CheckStatus.OK

    def test_only_cmake_presets_backward_compat(self, tmp_path):
        """Only CMakePresets.json (no user presets) → still works."""
        (tmp_path / "CMakeLists.txt").write_text('project(Test VERSION 1.0.0)')
        presets = {
            "version": 4,
            "configurePresets": [
                {"name": "conan-debug"},
                {"name": "conan-release"},
            ],
        }
        (tmp_path / "CMakePresets.json").write_text(json.dumps(presets))

        report = _make_report(tmp_path)
        results = report._check_project_config()

        file_results = [r for r in results if r.name == "CMakePresets.json"]
        assert len(file_results) == 1
        assert file_results[0].status == CheckStatus.OK

        conan_debug = [r for r in results if r.name == "Preset 'conan-debug'"]
        assert conan_debug[0].status == CheckStatus.OK
