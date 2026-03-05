"""
sbuild - Configuration management

Provides ConfigManager for centralized config resolution and pure data holder
dataclasses for build configuration.
"""

import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .exceptions import ConfigError, EnvironmentSetupError


# --- Section 1: File Parsers ---


def load_env_file(env_file: Path) -> dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip()
                    # Strip matching surrounding quotes
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    env_vars[key.strip()] = value
    return env_vars


def parse_conan_profile_arch(profile_path: Path) -> str | None:
    """Extract the arch setting from a Conan profile's [settings] section."""
    if not profile_path.exists():
        return None

    in_settings = False
    with open(profile_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("["):
                in_settings = stripped.lower() == "[settings]"
                continue
            if in_settings and "=" in stripped:
                key, _, value = stripped.partition("=")
                if key.strip() == "arch":
                    return value.strip()
    return None


def parse_cmake_project_info(cmake_file: Path) -> tuple[str, str]:
    """Extract project name and version from CMakeLists.txt."""
    import re

    name = "unknown"  # Default fallback
    version = "0.0.0"

    if cmake_file.exists():
        content = cmake_file.read_text(encoding="utf-8")
        # Match: project(name VERSION x.y.z ...)
        match = re.search(
            r'project\s*\(\s*(\S+).*?VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)',
            content,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            name = match.group(1)
            version = match.group(2)

    return name, version


def _resolve_configure_preset(project_root: Path, build_type: str) -> str:
    """Resolve the CMake configure preset name from CMakeUserPresets.json.

    Reads the presets file and follows includes to find available configure presets.
    Returns 'conan-{build_type}' for single-config generators (e.g. Ninja),
    'conan-default' for multi-config generators (e.g. Visual Studio),
    or falls back to 'conan-{build_type}' convention if no file exists.
    """
    conventional = f"conan-{build_type.lower()}"
    configure_names: set[str] = set()

    presets_file = project_root / "CMakeUserPresets.json"
    if not presets_file.exists():
        return conventional

    try:
        data = json.loads(presets_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return conventional

    # Collect configure presets from the main file
    for preset in data.get("configurePresets", []):
        if "name" in preset:
            configure_names.add(preset["name"])

    # Follow includes to find more configure presets
    for include in data.get("include", []):
        inc_path = project_root / include
        if inc_path.exists():
            try:
                inc_data = json.loads(inc_path.read_text(encoding="utf-8"))
                for preset in inc_data.get("configurePresets", []):
                    if "name" in preset:
                        configure_names.add(preset["name"])
            except (json.JSONDecodeError, OSError):
                pass

    # Prefer type-specific preset (single-config), fall back to conan-default (multi-config)
    if conventional in configure_names:
        return conventional
    if "conan-default" in configure_names:
        return "conan-default"
    return conventional


# --- Section 2: Architecture ---


# Canonical table: (friendly, conan)
_ARCH_TABLE = [("x86", "x86"), ("x64", "x86_64"), ("arm64", "armv8"), ("arm", "armv7")]
_FRIENDLY_TO_CONAN = {f: c for f, c in _ARCH_TABLE}
_CONAN_TO_FRIENDLY = {c: f for f, c in _ARCH_TABLE}

# platform.machine() -> conan arch
_MACHINE_TO_CONAN = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "i386": "x86",
    "i686": "x86",
    "arm64": "armv8",
    "aarch64": "armv8",
    "armv8": "armv8",
    "armv7l": "armv7",
    "armv7": "armv7",
    "armv6l": "armv6",
    "armv6": "armv6",
}


def normalize_arch(friendly_arch: str) -> str:
    """Convert a friendly architecture name to its Conan equivalent."""
    return _FRIENDLY_TO_CONAN.get(friendly_arch, friendly_arch)


def conan_to_friendly_arch(conan_arch: str) -> str:
    """Convert a Conan architecture name to its friendly equivalent."""
    return _CONAN_TO_FRIENDLY.get(conan_arch, conan_arch)


def detect_architecture() -> str:
    """Detect system architecture and return Conan architecture string."""
    machine = platform.machine().lower()
    return _MACHINE_TO_CONAN.get(machine, machine)


# --- Section 3: Data Holders ---


def resolve_build_number(build_number: int | None, build_dir: Path, project_root: Path) -> int:
    """Return resolved build number from generated version.h or CLI override.

    Priority: CLI override > version.h in build dir > git commit count > 0.
    """
    import re

    # CLI override takes precedence
    if build_number is not None:
        return build_number

    # Read from generated version.h (single source of truth after configure)
    version_h = build_dir / "generated" / "version.h"
    if version_h.exists():
        content = version_h.read_text(encoding="utf-8")
        match = re.search(r"#define\s+\w*VERSION_BUILD\s+(\d+)", content)
        if match:
            return int(match.group(1))

    # Fallback: calculate from git if version.h doesn't exist yet
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0


@dataclass(frozen=True)
class NativeConfig:
    """Configuration for native (conan + cmake) builds."""

    host_arch: str = "x86_64"
    target_arch: str = "x86_64"
    requested_arch: str | None = None
    friendly_arch: str = "x64"  # Always populated — used for display and profile fallback
    conan_profile_path: Path | None = None
    profile_override: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(
        cls,
        project_root: Path,
        build_type: str,
        env_vars: dict[str, str],
        cli_arch: str | None = None,
        cli_profile: str | None = None,
    ) -> "NativeConfig":
        """Build NativeConfig with arch resolution and profile detection."""
        host_arch = detect_architecture()

        # Resolve effective arch (CLI > .env > system env)
        effective_arch = cli_arch or env_vars.get("SBUILD_ARCH") or os.environ.get("SBUILD_ARCH")

        # Compute friendly_arch: explicit arch wins, otherwise derive from host
        friendly_arch = effective_arch if effective_arch else conan_to_friendly_arch(host_arch)

        # Resolve profile path
        conan_profile_path = cls._resolve_profile_path(
            project_root, build_type,
            arch=effective_arch, profile=cli_profile,
            fallback_friendly_arch=friendly_arch if not effective_arch else None,
        )

        # Detect target arch from resolved profile (or fall back to requested/host arch)
        fallback_arch = normalize_arch(effective_arch) if effective_arch else host_arch
        target_arch = fallback_arch
        if conan_profile_path and conan_profile_path.exists():
            arch = parse_conan_profile_arch(conan_profile_path)
            if arch:
                target_arch = arch

        # Build merged env_vars: .env values + SBUILD_ vars from os.environ as fallback
        merged_env = dict(env_vars)
        for key, value in os.environ.items():
            if key.startswith("SBUILD_") and key not in merged_env:
                merged_env[key] = value

        return cls(
            host_arch=host_arch,
            target_arch=target_arch,
            requested_arch=effective_arch,
            friendly_arch=friendly_arch,
            conan_profile_path=conan_profile_path,
            profile_override=cli_profile,
            env_vars=merged_env,
        )

    @staticmethod
    def _resolve_profile_path(
        project_root: Path,
        build_type: str,
        arch: str | None = None,
        profile: str | None = None,
        fallback_friendly_arch: str | None = None,
    ) -> Path | None:
        """Resolve the Conan profile path.

        Priority: --profile > --arch > fallback_friendly_arch > default (os_buildtype).
        Returns None if no matching profile file exists.
        """
        profiles_dir = project_root / "profiles"
        os_name = "windows" if platform.system() == "Windows" else "linux"

        if profile:
            path = profiles_dir / profile
            return path if path.exists() else None

        if arch:
            path = profiles_dir / f"{os_name}_{arch}_{build_type.lower()}"
            if path.exists():
                return path
            return None  # Don't fall back — explicit arch must match

        # No explicit arch: try arch-qualified profile first, then fall back to unqualified
        if fallback_friendly_arch:
            path = profiles_dir / f"{os_name}_{fallback_friendly_arch}_{build_type.lower()}"
            if path.exists():
                return path

        # Default: {os}_{build_type}
        path = profiles_dir / f"{os_name}_{build_type.lower()}"
        return path if path.exists() else None


@dataclass(frozen=True)
class WasmConfig:
    """Configuration for WebAssembly builds."""

    emsdk_path: Path = field(default_factory=Path)
    qt_wasm_path: Path = field(default_factory=Path)
    qt_host_path: Path | None = None
    openssl_root_dir: Path | None = None
    environment: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env_vars: dict[str, str]) -> "WasmConfig":
        """Build WasmConfig from env vars with validation."""
        required = {"EMSDK": "EMSDK", "SBUILD_WASM_QT_PATH": "SBUILD_WASM_QT_PATH"}
        missing = [name for name in required if name not in env_vars]
        if missing:
            raise ConfigError(
                f"Missing required WASM variables in .env: {', '.join(missing)}\n"
                "Required variables:\n"
                "  EMSDK=<path to emsdk>\n"
                "  SBUILD_WASM_QT_PATH=<path to Qt WASM>"
            )

        emsdk_path = Path(env_vars["EMSDK"])
        qt_wasm_path = Path(env_vars["SBUILD_WASM_QT_PATH"])
        qt_host_path = (
            Path(env_vars["SBUILD_WASM_QT_HOST_PATH"])
            if "SBUILD_WASM_QT_HOST_PATH" in env_vars
            else None
        )
        openssl_root_dir = (
            Path(env_vars["SBUILD_WASM_OPENSSL_ROOT_DIR"])
            if "SBUILD_WASM_OPENSSL_ROOT_DIR" in env_vars
            else None
        )

        # Validate paths
        errors = []
        if not emsdk_path.exists():
            errors.append(f"EMSDK path not found: {emsdk_path}")
        if not qt_wasm_path.exists():
            errors.append(f"SBUILD_WASM_QT_PATH not found: {qt_wasm_path}")
        if qt_host_path is not None and not qt_host_path.exists():
            errors.append(f"SBUILD_WASM_QT_HOST_PATH not found: {qt_host_path}")
        if openssl_root_dir and not openssl_root_dir.exists():
            errors.append(f"SBUILD_WASM_OPENSSL_ROOT_DIR not found: {openssl_root_dir}")
        if errors:
            raise EnvironmentSetupError(
                "Invalid WASM configuration:\n  " + "\n  ".join(errors)
            )

        # Pre-compute environment dict for subprocess
        environment: dict[str, str] = {
            "EMSDK": str(emsdk_path),
            "QT_WASM_PATH": str(qt_wasm_path),
        }
        if qt_host_path is not None:
            environment["QT_HOST_PATH"] = str(qt_host_path)

        return cls(
            emsdk_path=emsdk_path,
            qt_wasm_path=qt_wasm_path,
            qt_host_path=qt_host_path,
            openssl_root_dir=openssl_root_dir,
            environment=environment,
        )


@dataclass(frozen=True)
class BuildConfig:
    """Unified build configuration."""

    project_root: Path
    build_type: str = "Debug"  # "Debug" or "Release"
    platform: str = "native"  # "native" or "wasm"
    verbose: bool = False
    jobs: int = field(default_factory=lambda: os.cpu_count() or 4)
    cmake_args: Optional[str] = None
    build_number: Optional[int] = None
    build_dir: Path = field(default_factory=lambda: Path("build/Debug"))
    build_dir_base: str = "build"
    preset_name: str = "conan-debug"
    build_preset_name: str = "conan-debug"
    project_name: str = "unknown"
    version: str = "0.0.0"
    install_prefix: Optional[Path] = None
    env_vars: dict[str, str] = field(default_factory=dict)
    platform_config: "NativeConfig | WasmConfig" = field(default_factory=NativeConfig)


# --- Section 4: ConfigManager ---


_UNSET = object()


class ConfigManager:
    """Single point of config resolution.

    Receives raw CLI args, loads .env once, resolves everything,
    and produces a fully-populated BuildConfig.
    """

    def __init__(self, *, project_root: Path | None = None, **cli_args):
        self._project_root = project_root or Path.cwd()
        self._cli = cli_args
        self._env = load_env_file(self._project_root / ".env")

    def _resolve(self, env_name: str, cli_value=_UNSET, *, default=None, as_type=str):
        """Generic: CLI > .env > os.environ > default."""
        if cli_value is not _UNSET and cli_value is not None:
            return cli_value
        raw = self._env.get(env_name) or os.environ.get(env_name)
        if raw is not None:
            if as_type is bool:
                return raw.lower() in ("true", "1", "yes")
            if as_type is int:
                try:
                    return int(raw)
                except ValueError:
                    return default
            if as_type is Path:
                return Path(raw)
            return raw
        return default

    def resolve(self) -> BuildConfig:
        """Resolve all config and return fully-populated BuildConfig."""
        # 1. Simple values
        platform_name = self._resolve(
            "SBUILD_PLATFORM", self._cli.get("platform"), default="native",
        )
        verbose = self._resolve(
            "SBUILD_VERBOSE", self._cli.get("verbose"), default=False, as_type=bool,
        )
        jobs = self._resolve(
            "SBUILD_PARALLEL_JOBS", self._cli.get("jobs"),
            default=os.cpu_count() or 4, as_type=int,
        )
        build_type = (self._cli.get("build_type") or "Debug").capitalize()
        build_dir_base = self._resolve("SBUILD_BUILD_DIR", default="build")
        install_prefix = self._resolve(
            "SBUILD_INSTALL_DIR", self._cli.get("install_prefix"), as_type=Path,
        )
        build_number = self._cli.get("build_number")

        # 2. Merged value: cmake_args
        cmake_args = self._resolve_cmake_args(platform_name)

        # 3. Platform-specific config (delegated to dataclass factory methods)
        if platform_name == "wasm":
            platform_config = WasmConfig.from_env(self._env)
        elif platform_name == "native":
            platform_config = NativeConfig.from_env(
                self._project_root, build_type, self._env,
                cli_arch=self._cli.get("arch"),
                cli_profile=self._cli.get("profile"),
            )
        else:
            raise ConfigError(f"Unknown platform: {platform_name}")

        # 4. Derived values
        build_dir = self._compute_build_dir(platform_name, build_type, build_dir_base)
        preset_name = self._compute_preset_name(platform_name, build_type)
        build_preset_name = self._compute_build_preset_name(platform_name, build_type)
        project_name, version = parse_cmake_project_info(
            self._project_root / "CMakeLists.txt",
        )

        return BuildConfig(
            project_root=self._project_root,
            build_type=build_type,
            platform=platform_name,
            verbose=verbose,
            jobs=jobs,
            cmake_args=cmake_args,
            build_number=build_number,
            build_dir=build_dir,
            build_dir_base=build_dir_base,
            preset_name=preset_name,
            build_preset_name=build_preset_name,
            project_name=project_name,
            version=version,
            install_prefix=install_prefix,
            env_vars=dict(self._env),
            platform_config=platform_config,
        )

    def _resolve_cmake_args(self, platform_name: str) -> str | None:
        """Merge cmake args: SBUILD_CMAKE_ARGS + SBUILD_WASM_CMAKE_ARGS (if wasm) + CLI."""
        parts: list[str] = []
        universal = self._env.get("SBUILD_CMAKE_ARGS", "").strip()
        if universal:
            if len(universal) >= 2 and universal[0] == universal[-1] and universal[0] in ('"', "'"):
                universal = universal[1:-1]
            parts.append(universal)
        if platform_name == "wasm":
            wasm_args = self._env.get("SBUILD_WASM_CMAKE_ARGS", "").strip()
            if wasm_args:
                if len(wasm_args) >= 2 and wasm_args[0] == wasm_args[-1] and wasm_args[0] in ('"', "'"):
                    wasm_args = wasm_args[1:-1]
                parts.append(wasm_args)
        cli_cmake_args = self._cli.get("cmake_args")
        if cli_cmake_args:
            cli_cmake_args = cli_cmake_args.strip()
            if cli_cmake_args:
                parts.append(cli_cmake_args)
        return " ".join(parts) if parts else None

    def _compute_build_dir(self, platform_name: str, build_type: str, build_dir_base: str) -> Path:
        """Compute the build directory path."""
        if platform_name == "wasm":
            dir_name = f"wasm-{build_type.lower()}"
        else:
            dir_name = build_type
        return self._project_root / build_dir_base / dir_name

    def _compute_preset_name(self, platform_name: str, build_type: str) -> str:
        """Compute the CMake configure preset name."""
        if platform_name == "wasm":
            return f"wasm-{build_type.lower()}"
        return _resolve_configure_preset(self._project_root, build_type)

    def _compute_build_preset_name(self, platform_name: str, build_type: str) -> str:
        """Compute the CMake build preset name."""
        if platform_name == "wasm":
            return f"wasm-{build_type.lower()}"
        return f"conan-{build_type.lower()}"
