"""
sbuild - Environment health checks

Provides the `doctor` diagnostic report: verifies tools, platform config,
WASM environment, project files, and packaging tools.
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.table import Table

from .config import (
    NativeConfig,
    WasmConfig,
    load_env_file,
    parse_cmake_project_info,
)
from .console import console
from .exceptions import ConfigError
from .platform import IS_WINDOWS, create_platform_env


class CheckStatus(str, Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    version: str | None = None
    path: Path | None = None
    message: str | None = None
    fix_hint: str | None = None


@dataclass
class DoctorReport:
    """Runs all environment checks and displays a Rich-formatted report."""

    project_root: Path
    verbose: bool = False
    _sections: dict[str, list[CheckResult]] = field(default_factory=dict, init=False)
    _vcvars_env: Optional[dict[str, str]] = field(default=None, init=False)
    _is_windows: bool = field(default=False, init=False)
    _platform: object = field(default=None, init=False)

    def __post_init__(self):
        self._is_windows = IS_WINDOWS
        self._platform = create_platform_env()
        if self._platform.toolchain_path:
            try:
                self._vcvars_env = self._platform.activate()
            except Exception:
                pass

    # --- public API ---

    def check_all(self) -> bool:
        """Run every check section. Returns False if any FAIL."""
        self._sections["Core Tools"] = self._check_core_tools()
        self._sections["Native Environment"] = self._check_native_env()
        self._sections["WASM Environment"] = self._check_wasm_env()
        self._sections["Project Configuration"] = self._check_project_config()
        self._sections["Packaging Tools"] = self._check_packaging_tools()

        return not any(
            r.status == CheckStatus.FAIL
            for results in self._sections.values()
            for r in results
        )

    def display(self) -> None:
        """Render grouped Rich tables + summary."""
        ok = warn = fail = 0

        for title, results in self._sections.items():
            table = Table(
                title=f"  {title}",
                title_style="bold",
                show_header=True,
                header_style="dim",
                padding=(0, 1),
                expand=False,
            )
            table.add_column("Status", width=6, justify="center")
            table.add_column("Check", min_width=20)
            table.add_column("Details")
            if self.verbose:
                table.add_column("Path", style="dim")

            hints: list[str] = []

            for r in results:
                status_text = _status_markup(r.status)
                detail = r.version or r.message or ""
                row = [status_text, r.name, detail]
                if self.verbose:
                    row.append(str(r.path) if r.path else "")
                table.add_row(*row)

                if r.status == CheckStatus.OK:
                    ok += 1
                elif r.status == CheckStatus.WARN:
                    warn += 1
                    if r.fix_hint:
                        hints.append(r.fix_hint)
                else:
                    fail += 1
                    if r.fix_hint:
                        hints.append(r.fix_hint)

            console.print(table)

            if hints:
                console.print("  [bold]Recommendations:[/bold]")
                for h in hints:
                    console.print(f"    - {h}")
            console.print()

        # Summary
        parts = [f"[green]{ok} OK[/green]"]
        if warn:
            parts.append(f"[yellow]{warn} WARN[/yellow]")
        if fail:
            parts.append(f"[red]{fail} FAIL[/red]")
        console.print("  " + " | ".join(parts))

    # --- check sections ---

    def _check_core_tools(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        # Python
        v = sys.version_info
        py_ver = f"{v.major}.{v.minor}.{v.micro}"
        status = CheckStatus.OK if v >= (3, 12) else CheckStatus.FAIL
        results.append(CheckResult(
            "Python",
            status,
            version=py_ver,
            path=Path(sys.executable),
            fix_hint="Python >= 3.12 is required" if status != CheckStatus.OK else None,
        ))

        # Virtual environment
        in_venv = sys.prefix != sys.base_prefix
        if in_venv:
            results.append(CheckResult(
                "Virtual env",
                CheckStatus.OK,
                path=Path(sys.prefix),
            ))
        else:
            results.append(CheckResult(
                "Virtual env",
                CheckStatus.WARN,
                message="Not using a virtual environment",
                fix_hint="Recommended: create a venv with 'python -m venv .venv' and activate it",
            ))

        # CMake
        results.append(_check_tool_version(
            "cmake", ["--version"], required=True,
            fix_hint="Install CMake: https://cmake.org/download/",
            vcvars_env=self._vcvars_env,
        ))

        # Conan
        results.append(self._check_conan())

        # Git
        results.append(_check_tool_version(
            "git", ["--version"], required=True,
            fix_hint="Install Git: https://git-scm.com/downloads",
            vcvars_env=self._vcvars_env,
        ))

        # Ninja
        results.append(_check_tool_version(
            "ninja", ["--version"], required=False,
            fix_hint="Optional: install Ninja for faster builds (pip install ninja)",
            vcvars_env=self._vcvars_env,
        ))

        return results

    def _check_conan(self) -> CheckResult:
        r = _check_tool_version(
            "conan", ["--version"], required=True,
            fix_hint="Install Conan 2: pip install conan",
            vcvars_env=self._vcvars_env,
        )
        if r.status == CheckStatus.OK and r.version:
            major = int(r.version.split(".")[0])
            if major != 2:
                r.status = CheckStatus.FAIL
                r.message = f"Conan {r.version} (major version 2 required)"
                r.fix_hint = "Upgrade to Conan 2: pip install --upgrade conan"
        return r

    def _check_native_env(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        # Architecture
        arch = NativeConfig.detect_architecture()
        results.append(CheckResult("Architecture", CheckStatus.OK, message=arch))

        # .env file
        env_file = self.project_root / ".env"
        if env_file.exists():
            results.append(CheckResult(".env file", CheckStatus.OK, path=env_file))
        else:
            results.append(CheckResult(
                ".env file", CheckStatus.WARN, path=env_file,
                message="Not found",
                fix_hint="Create .env with native environment variables (e.g. QT_IFW_ROOT)",
            ))

        # Conan profiles
        results.extend(self._check_conan_profiles(self._is_windows))

        # Platform-specific
        if self._is_windows:
            results.append(self._check_vcvars())
            if self._platform.toolchain_path:
                from .platform.windows import WindowsEnv
                if isinstance(self._platform, WindowsEnv):
                    results.append(CheckResult(
                        "vcvars arch", CheckStatus.OK,
                        message=self._platform.vcvars_arch,
                    ))
        else:
            results.append(_check_tool_version(
                "gcc", ["--version"], required=True,
                fix_hint="Install GCC: sudo apt install build-essential",
            ))
            results.append(_check_tool_version(
                "g++", ["--version"], required=True,
                fix_hint="Install G++: sudo apt install build-essential",
            ))

        return results

    def _check_conan_profiles(self, is_windows: bool) -> list[CheckResult]:
        profiles_dir = self.project_root / "profiles"
        if not profiles_dir.is_dir():
            return [CheckResult(
                "Conan profiles", CheckStatus.WARN,
                message="profiles/ directory not found",
                fix_hint="Create a profiles/ directory with Conan profiles",
            )]

        os_name = "windows" if is_windows else "linux"
        results: list[CheckResult] = []
        for bt in ("debug", "release"):
            profile = profiles_dir / f"{os_name}_{bt}"
            if profile.exists():
                results.append(CheckResult(
                    f"Profile {os_name}_{bt}", CheckStatus.OK, path=profile,
                ))
            else:
                results.append(CheckResult(
                    f"Profile {os_name}_{bt}", CheckStatus.WARN,
                    path=profile,
                    message="Not found",
                    fix_hint=f"Create profiles/{os_name}_{bt} for Conan",
                ))
        return results

    def _check_vcvars(self) -> CheckResult:
        if self._platform.toolchain_path:
            return CheckResult("vcvarsall.bat", CheckStatus.OK, path=self._platform.toolchain_path)
        return CheckResult(
            "vcvarsall.bat", CheckStatus.FAIL,
            message="Not found",
            fix_hint="Install Visual Studio 2019/2022 with C++ desktop workload",
        )

    def _check_wasm_env(self) -> list[CheckResult]:
        env_file = self.project_root / ".env.wasm"
        if not env_file.exists():
            return [CheckResult(
                "WASM environment", CheckStatus.WARN,
                message="Skipped - .env.wasm not found",
                fix_hint="Create .env.wasm with EMSDK, QT_WASM_PATH, QT_HOST_PATH to enable WASM checks",
            )]

        results: list[CheckResult] = []

        # Load config
        try:
            wasm = WasmConfig.from_env_file(env_file)
        except ConfigError as e:
            return [CheckResult(
                ".env.wasm", CheckStatus.FAIL,
                message=str(e),
                fix_hint="Fix .env.wasm: ensure EMSDK, QT_WASM_PATH, QT_HOST_PATH are set",
            )]

        results.append(CheckResult(".env.wasm", CheckStatus.OK, path=env_file))

        # EMSDK path
        results.append(_check_path("EMSDK path", wasm.emsdk_path))

        # emsdk_env script
        script = "emsdk_env.bat" if self._is_windows else "emsdk_env.sh"
        script_path = wasm.emsdk_path / script
        results.append(_check_path(
            f"emsdk_env ({script})", script_path,
            fix_hint=f"Expected {script} inside EMSDK directory",
        ))

        # QT paths
        results.append(_check_path("QT_WASM_PATH", wasm.qt_wasm_path))
        results.append(_check_path("QT_HOST_PATH", wasm.qt_host_path))

        # OpenSSL (optional)
        if wasm.openssl_path is not None:
            results.append(_check_path("OpenSSL path", wasm.openssl_path, required=False))

        return results

    def _check_project_config(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        # CMakeLists.txt
        cmake_file = self.project_root / "CMakeLists.txt"
        if not cmake_file.exists():
            results.append(CheckResult(
                "CMakeLists.txt", CheckStatus.FAIL,
                message="Not found",
                fix_hint="Run sbuild doctor from a project directory containing CMakeLists.txt",
            ))
        else:
            name, version = parse_cmake_project_info(cmake_file)
            if name != "unknown":
                results.append(CheckResult(
                    "CMakeLists.txt", CheckStatus.OK,
                    message=f"{name} {version}",
                    path=cmake_file,
                ))
            else:
                results.append(CheckResult(
                    "CMakeLists.txt", CheckStatus.WARN,
                    message="Could not parse project(NAME VERSION ...)",
                    path=cmake_file,
                    fix_hint="Ensure CMakeLists.txt contains project(Name VERSION x.y.z)",
                ))

        # CMake Presets - check both standard preset files
        presets_file = self.project_root / "CMakePresets.json"
        user_presets_file = self.project_root / "CMakeUserPresets.json"
        preset_files_found = [f for f in (presets_file, user_presets_file) if f.exists()]

        if not preset_files_found:
            results.append(CheckResult(
                "CMake Presets", CheckStatus.WARN,
                message="No preset files found (CMakePresets.json or CMakeUserPresets.json)",
                fix_hint="Run 'sbuild configure' to generate CMakeUserPresets.json via Conan",
            ))
        else:
            results.extend(self._check_cmake_presets(preset_files_found))

        return results

    def _check_cmake_presets(self, preset_files: list[Path]) -> list[CheckResult]:
        results: list[CheckResult] = []
        preset_names: set[str] = set()

        for preset_file in preset_files:
            try:
                data = json.loads(preset_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                results.append(CheckResult(
                    preset_file.name, CheckStatus.WARN,
                    message=f"Parse error: {e}",
                    path=preset_file,
                ))
                continue

            results.append(CheckResult(preset_file.name, CheckStatus.OK, path=preset_file))
            preset_names.update(_collect_preset_names(data))

            # Also check included preset files
            for include in data.get("include", []):
                inc_path = self.project_root / include
                if inc_path.exists():
                    try:
                        inc_data = json.loads(inc_path.read_text(encoding="utf-8"))
                        preset_names.update(_collect_preset_names(inc_data))
                    except (json.JSONDecodeError, OSError):
                        pass

        expected = ["conan-debug", "conan-release", "wasm-debug", "wasm-release"]
        for name in expected:
            if name in preset_names:
                results.append(CheckResult(f"Preset '{name}'", CheckStatus.OK))
            else:
                # WASM presets are expected only when .env.wasm exists
                is_wasm = name.startswith("wasm-")
                wasm_env = (self.project_root / ".env.wasm").exists()
                if is_wasm and not wasm_env:
                    results.append(CheckResult(
                        f"Preset '{name}'", CheckStatus.WARN,
                        message="Not found (WASM not configured)",
                    ))
                else:
                    results.append(CheckResult(
                        f"Preset '{name}'", CheckStatus.WARN,
                        message="Not found",
                        fix_hint=f"Run 'sbuild configure' to generate the '{name}' preset",
                    ))

        return results

    def _check_nsis(self) -> CheckResult:
        """Check for NSIS (makensis), falling back to registry and known paths."""
        r = _check_tool_version(
            "makensis", ["/VERSION"], required=False,
            fix_hint="Install NSIS: https://nsis.sourceforge.io/Download",
            vcvars_env=self._vcvars_env,
        )
        if r.status == CheckStatus.OK:
            return r

        # PATH lookup failed – try registry and known install directories
        nsis_path = _find_nsis()
        if nsis_path is None:
            return r  # original WARN result

        # Found makensis outside PATH – get its version
        try:
            result = subprocess.run(
                [str(nsis_path), "/VERSION"],
                capture_output=True, text=True, timeout=5,
            )
            version = _parse_version(result.stdout + result.stderr)
        except (OSError, subprocess.TimeoutExpired):
            version = None

        label = f"{version} ({nsis_path.parent})" if version else str(nsis_path.parent)
        return CheckResult(
            "makensis", CheckStatus.OK,
            version=label, path=nsis_path,
        )

    def _check_packaging_tools(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        # CPack
        results.append(_check_tool_version(
            "cpack", ["--version"], required=False,
            fix_hint="CPack is bundled with CMake - ensure CMake is installed",
            vcvars_env=self._vcvars_env,
        ))

        # Qt IFW
        env_vars = load_env_file(self.project_root / ".env")
        qt_ifw_root = env_vars.get("QT_IFW_ROOT")
        if qt_ifw_root:
            ifw_bin = Path(qt_ifw_root) / "bin"
            if ifw_bin.exists():
                results.append(CheckResult(
                    "Qt IFW", CheckStatus.OK,
                    path=ifw_bin,
                    message=f"QT_IFW_ROOT={qt_ifw_root}",
                ))
            else:
                results.append(CheckResult(
                    "Qt IFW", CheckStatus.WARN,
                    path=ifw_bin,
                    message="bin/ not found",
                    fix_hint=f"QT_IFW_ROOT bin directory missing: {ifw_bin}",
                ))
        else:
            results.append(CheckResult(
                "Qt IFW", CheckStatus.WARN,
                message="QT_IFW_ROOT not set in .env",
                fix_hint="Set QT_IFW_ROOT in .env to enable IFW packaging",
            ))

        # NSIS (Windows only)
        if self._is_windows:
            results.append(self._check_nsis())

        return results


# --- helpers ---


def _status_markup(status: CheckStatus) -> str:
    """Return Rich-formatted status label."""
    if status == CheckStatus.OK:
        return "[green]  OK  [/green]"
    if status == CheckStatus.WARN:
        return "[yellow] WARN [/yellow]"
    return "[red] FAIL [/red]"



def _check_path(
    name: str,
    path: Path,
    *,
    required: bool = True,
    fix_hint: str | None = None,
) -> CheckResult:
    """Check if a path exists and return an appropriate CheckResult."""
    if path.exists():
        return CheckResult(name, CheckStatus.OK, path=path)
    return CheckResult(
        name,
        CheckStatus.FAIL if required else CheckStatus.WARN,
        path=path,
        message="Directory not found" if path.suffix == "" else "Not found",
        fix_hint=fix_hint or f"{name} path does not exist: {path}",
    )


def _parse_version(output: str) -> str | None:
    """Extract a version string (x.y or x.y.z) from command output."""
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
    return match.group(1) if match else None

def _check_tool_version(
    tool: str,
    version_args: list[str],
    *,
    required: bool,
    fix_hint: str | None = None,
    vcvars_env: Optional[dict[str, str]] = None,
) -> CheckResult:
    """Run a tool with version_args, parse version, return CheckResult."""
    try:
        result = subprocess.run(
            [tool] + version_args,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout + result.stderr
        version = _parse_version(output)
        path = _which(tool)
        return CheckResult(tool, CheckStatus.OK, version=version, path=path)
    except FileNotFoundError:
        if vcvars_env:
            # Retry with the vcvars-captured environment (its PATH includes VS tools).
            # Must use shell=True so cmd.exe resolves the tool via the env's PATH.
            try:
                cmd = " ".join([tool] + version_args)
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=vcvars_env,
                )
                if result.returncode != 0:
                    raise FileNotFoundError
                output = result.stdout + result.stderr
                version = _parse_version(output)
                label = f"{version} (via vcvarsall)" if version else "(via vcvarsall)"
                return CheckResult(tool, CheckStatus.OK, version=label)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        return CheckResult(
            tool,
            CheckStatus.FAIL if required else CheckStatus.WARN,
            message="Not found",
            fix_hint=fix_hint,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            tool,
            CheckStatus.FAIL if required else CheckStatus.WARN,
            message="Timed out",
            fix_hint=fix_hint,
        )


def _find_nsis() -> Path | None:
    """Locate makensis.exe via Windows registry and known install directories."""
    # 1. Check Windows registry
    if IS_WINDOWS:
        import winreg

        for key_path in (r"SOFTWARE\NSIS", r"SOFTWARE\WOW6432Node\NSIS"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    install_dir, _ = winreg.QueryValueEx(key, "")
                    candidate = Path(install_dir) / "makensis.exe"
                    if candidate.is_file():
                        return candidate
            except OSError:
                continue

    # 2. Check common install directories
    for directory in (
        Path(r"C:\Program Files\NSIS"),
        Path(r"C:\Program Files (x86)\NSIS"),
    ):
        candidate = directory / "makensis.exe"
        if candidate.is_file():
            return candidate

    return None


def _which(tool: str) -> Path | None:
    """Locate executable on PATH."""
    import shutil

    p = shutil.which(tool)
    return Path(p) if p else None


def _collect_preset_names(data: dict) -> set[str]:
    """Gather all configure and build preset names from a CMake preset dict."""
    names: set[str] = set()
    for key in ("configurePresets", "buildPresets"):
        for preset in data.get(key, []):
            if "name" in preset:
                names.add(preset["name"])
    return names
