"""Tests for sbuild.doctor helper functions."""

from pathlib import Path

import pytest

from sbuild.doctor import (
    CheckResult,
    CheckStatus,
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
