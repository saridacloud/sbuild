"""Tests for VS multi-config preset reconciliation and install --config.

Regression coverage for building sarida-rtai-core (and any project using the
Visual Studio multi-config generator) where Conan emits the configure preset
``conan-default`` for every build type:

* ``cmake --install <dir>`` without ``--config`` installed the wrong config.
* Conan's root ``CMakeUserPresets.json`` includes both the Debug and Release
  generator preset files, so CMake aborts with ``Duplicate preset: conan-default``.
"""

import json
from unittest.mock import MagicMock

from sbuild.runners.base import BaseRunner
from sbuild.runners.native import NativeRunner


class _ConcreteRunner(BaseRunner):
    def configure(self):  # pragma: no cover - abstract stub
        pass

    def build(self):  # pragma: no cover - abstract stub
        pass


def _base_runner():
    return object.__new__(_ConcreteRunner)


def _native_runner():
    return object.__new__(NativeRunner)


class TestInstallPassesConfig:
    def test_install_command_includes_config(self, tmp_path):
        runner = _base_runner()
        cfg = MagicMock()
        cfg.project_root = tmp_path
        cfg.build_type = "Release"
        cfg.build_dir = tmp_path / "build" / "Release"
        cfg.build_dir.mkdir(parents=True)
        runner.config = cfg

        captured = {}

        def fake_run(cmd, desc):
            captured["cmd"] = cmd
            return True

        runner.run_command = fake_run
        assert runner.install(prefix=tmp_path / "install") is True
        assert "--config Release" in captured["cmd"]


class TestReconcileCMakePresets:
    def _setup(self, tmp_path, configure_presets, build_presets=None):
        runner = _native_runner()
        cfg = MagicMock()
        cfg.project_root = tmp_path
        cfg.build_dir = tmp_path / "build" / "Release"
        cfg.build_type = "Release"
        cfg.preset_name = "conan-release"  # convention-based guess made pre-conan-install
        runner.config = cfg
        runner.log_manager = None

        gen = cfg.build_dir / "generators"
        gen.mkdir(parents=True)
        (gen / "CMakePresets.json").write_text(
            json.dumps(
                {
                    "configurePresets": [{"name": n} for n in configure_presets],
                    "buildPresets": [{"name": n} for n in (build_presets or [])],
                }
            ),
            encoding="utf-8",
        )
        # Root file starts in the broken state: includes BOTH build types.
        (tmp_path / "CMakeUserPresets.json").write_text(
            json.dumps(
                {
                    "version": 4,
                    "include": [
                        "build/Debug/generators/CMakePresets.json",
                        "build/Release/generators/CMakePresets.json",
                    ],
                }
            ),
            encoding="utf-8",
        )
        return runner

    def test_vs_multiconfig_returns_conan_default_and_pins_single_include(self, tmp_path):
        runner = self._setup(tmp_path, ["conan-default"], ["conan-release"])
        preset = runner._reconcile_cmake_presets()
        assert preset == "conan-default"
        data = json.loads((tmp_path / "CMakeUserPresets.json").read_text(encoding="utf-8"))
        assert data["include"] == ["build/Release/generators/CMakePresets.json"]

    def test_ninja_singleconfig_prefers_conventional_preset(self, tmp_path):
        runner = self._setup(tmp_path, ["conan-release"], ["conan-release"])
        preset = runner._reconcile_cmake_presets()
        assert preset == "conan-release"
        data = json.loads((tmp_path / "CMakeUserPresets.json").read_text(encoding="utf-8"))
        assert data["include"] == ["build/Release/generators/CMakePresets.json"]

    def test_missing_generators_file_is_a_noop(self, tmp_path):
        runner = _native_runner()
        cfg = MagicMock()
        cfg.project_root = tmp_path
        cfg.build_dir = tmp_path / "build" / "Release"
        cfg.build_type = "Release"
        cfg.preset_name = "conan-release"
        runner.config = cfg
        runner.log_manager = None
        # No generators/CMakePresets.json on disk -> keep the pre-resolved guess.
        assert runner._reconcile_cmake_presets() == "conan-release"
