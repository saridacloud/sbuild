"""
sbuild - Configuration management

Provides dataclasses for build configuration with environment detection.
"""

import json
import os
import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .exceptions import ConfigError, EnvironmentSetupError


def load_env_file(env_file: Path) -> dict[str, str]:
    """Load environment variables from a .env file"""
    env_vars = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
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
    """Extract project name and version from CMakeLists.txt"""
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


class PlatformConfig(ABC):
    """Abstract base for platform-specific build configuration."""

    @abstractmethod
    def build_dir_name(self, build_type: str) -> str:
        """Return the build directory name for the given build type."""
        ...

    @abstractmethod
    def preset_name(self, build_type: str) -> str:
        """Return the CMake preset name for the given build type."""
        ...

    def build_preset_name(self, build_type: str) -> str:
        """CMake build preset name. Defaults to same as configure preset."""
        return self.preset_name(build_type)

    @abstractmethod
    def get_environment(self) -> dict[str, str]:
        """Return environment variables dict for subprocess."""
        ...

    @abstractmethod
    def validate(self) -> None:
        """Validate configuration. Raise on errors."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable platform label (empty for native)."""
        return ""



_ARCH_MAPPING = {
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

_FRIENDLY_ARCH_MAP = {
    "x86": "x86",
    "x64": "x86_64",
    "arm64": "armv8",
}

VALID_ARCH_VALUES = list(_FRIENDLY_ARCH_MAP.keys())


def normalize_arch(friendly_arch: str) -> str:
    """Convert a friendly architecture name to its Conan equivalent."""
    return _FRIENDLY_ARCH_MAP.get(friendly_arch, friendly_arch)


def resolve_arch(
    cli_arch: str | None,
    env_vars: dict[str, str],
) -> str | None:
    """Resolve arch from CLI > .env > system env. Returns friendly name or None."""
    if cli_arch:
        return cli_arch
    env_arch = env_vars.get("SBUILD_ARCH")
    if env_arch:
        return env_arch
    sys_arch = os.environ.get("SBUILD_ARCH")
    if sys_arch:
        return sys_arch
    return None


def resolve_profile_path(
    project_root: Path,
    build_type: str,
    arch: str | None = None,
    profile: str | None = None,
) -> Path | None:
    """Resolve the Conan profile path.

    Priority: --profile > --arch > default (os_buildtype).
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

    # Default: {os}_{build_type}
    path = profiles_dir / f"{os_name}_{build_type.lower()}"
    return path if path.exists() else None


@dataclass
class NativeConfig(PlatformConfig):
    """Configuration for native (conan + cmake) builds"""

    arch: str = "x86_64"
    target_arch: str = "x86_64"
    env_vars: dict[str, str] = field(default_factory=dict)
    project_root: Path = field(default_factory=lambda: Path("."))
    requested_arch: str | None = None
    profile_override: str | None = None
    conan_profile_path: Path | None = None

    @classmethod
    def detect(
        cls,
        project_root: Optional[Path] = None,
        build_type: str = "Debug",
        arch: str | None = None,
        profile: str | None = None,
    ) -> "NativeConfig":
        """Auto-detect native build configuration"""
        config = cls()
        config.arch = cls.detect_architecture()
        config.project_root = project_root or Path(".")

        # Load .env first so SBUILD_ARCH is available for profile resolution
        if project_root:
            env_file = project_root / ".env"
            config.env_vars = load_env_file(env_file)

        # Resolve effective arch (CLI > .env > system env)
        effective_arch = resolve_arch(arch, config.env_vars)
        config.requested_arch = effective_arch
        config.profile_override = profile

        # Resolve profile path
        config.conan_profile_path = resolve_profile_path(
            config.project_root, build_type, arch=effective_arch, profile=profile,
        )

        # Detect target arch from resolved profile (or fall back to requested/host arch)
        fallback_arch = normalize_arch(effective_arch) if effective_arch else config.arch
        config.target_arch = cls._detect_target_arch(config.conan_profile_path, fallback_arch)

        return config

    @classmethod
    def _detect_target_arch(cls, profile_path: Path | None, fallback_arch: str) -> str:
        """Detect target architecture from resolved Conan profile, falling back to fallback_arch."""
        if profile_path and profile_path.exists():
            arch = parse_conan_profile_arch(profile_path)
            if arch:
                return arch
        return fallback_arch

    @classmethod
    def detect_target_architecture(cls, project_root: Optional[Path], build_type: str) -> str:
        """Detect target architecture from Conan profile, falling back to host arch."""
        if project_root:
            os_name = "windows" if platform.system() == "Windows" else "linux"
            profile_path = project_root / "profiles" / f"{os_name}_{build_type.lower()}"
            arch = parse_conan_profile_arch(profile_path)
            if arch:
                return arch
        return cls.detect_architecture()

    @staticmethod
    def detect_architecture() -> str:
        """Detect system architecture and return Conan architecture string"""
        machine = platform.machine().lower()
        return _ARCH_MAPPING.get(machine, machine)

    def build_dir_name(self, build_type: str) -> str:
        if self.requested_arch:
            return f"{self.requested_arch}/{build_type}"
        return build_type

    def preset_name(self, build_type: str) -> str:
        return _resolve_configure_preset(self.project_root, build_type)

    def build_preset_name(self, build_type: str) -> str:
        """Build preset is always conan-{build_type} (Conan generates type-specific build presets)."""
        return f"conan-{build_type.lower()}"

    def get_environment(self) -> dict[str, str]:
        return dict(self.env_vars)

    def validate(self) -> None:
        pass  # Native config is always valid


@dataclass
class WasmConfig(PlatformConfig):
    """Configuration for WebAssembly builds"""

    emsdk_path: Path = field(default_factory=lambda: Path())
    qt_wasm_path: Path = field(default_factory=lambda: Path())
    qt_host_path: Path = field(default_factory=lambda: Path())
    openssl_path: Optional[Path] = None

    @classmethod
    def from_env_file(cls, env_file: Path) -> "WasmConfig":
        """Load configuration from .env.wasm file"""
        if not env_file.exists():
            raise ConfigError(
                f"WASM configuration not found: {env_file}\n"
                "Create .env.wasm with:\n"
                "  EMSDK=<path to emsdk>\n"
                "  QT_WASM_PATH=<path to Qt WASM>\n"
                "  QT_HOST_PATH=<path to Qt host>"
            )

        env_vars = load_env_file(env_file)

        # Validate required variables
        required = ["EMSDK", "QT_WASM_PATH", "QT_HOST_PATH"]
        missing = [var for var in required if var not in env_vars]
        if missing:
            raise ConfigError(
                f"Missing required variables in .env.wasm: {', '.join(missing)}"
            )

        return cls(
            emsdk_path=Path(env_vars["EMSDK"]),
            qt_wasm_path=Path(env_vars["QT_WASM_PATH"]),
            qt_host_path=Path(env_vars["QT_HOST_PATH"]),
            openssl_path=Path(env_vars["OPENSSL"]) if "OPENSSL" in env_vars else None,
        )

    def validate(self) -> None:
        """Validate all paths exist"""
        errors = []

        if not self.emsdk_path.exists():
            errors.append(f"EMSDK path not found: {self.emsdk_path}")

        if not self.qt_wasm_path.exists():
            errors.append(f"QT_WASM_PATH not found: {self.qt_wasm_path}")

        if not self.qt_host_path.exists():
            errors.append(f"QT_HOST_PATH not found: {self.qt_host_path}")

        if self.openssl_path and not self.openssl_path.exists():
            errors.append(f"OPENSSL path not found: {self.openssl_path}")

        if errors:
            raise EnvironmentSetupError(
                "Invalid WASM configuration:\n  " + "\n  ".join(errors)
            )

    def get_environment(self) -> dict[str, str]:
        """Return environment variables dict for subprocess"""
        env = {
            "EMSDK": str(self.emsdk_path),
            "QT_WASM_PATH": str(self.qt_wasm_path),
            "QT_HOST_PATH": str(self.qt_host_path),
        }
        if self.openssl_path:
            env["OPENSSL"] = str(self.openssl_path)
        return env

    def build_dir_name(self, build_type: str) -> str:
        return f"wasm-{build_type.lower()}"

    def preset_name(self, build_type: str) -> str:
        return f"wasm-{build_type.lower()}"

    @property
    def display_name(self) -> str:
        return "WASM"


_CONFIG_FACTORIES: dict[str, Callable[..., PlatformConfig]] = {
    "native": lambda root, bt, arch=None, profile=None: NativeConfig.detect(root, bt, arch=arch, profile=profile),
    "wasm": lambda root, bt, **_kw: WasmConfig.from_env_file(root / ".env.wasm"),
}


@dataclass
class BuildConfig:
    """Unified build configuration"""

    project_root: Path
    build_type: str = "Debug"  # "Debug" or "Release"
    platform: str = "native"  # "native" or "wasm"
    verbose: bool = False
    jobs: int = os.cpu_count() or 4
    cmake_args: Optional[str] = None
    build_number: Optional[int] = None  # Override git commit count for packaging
    arch: Optional[str] = None  # Target architecture (x86, x64, arm64)
    profile: Optional[str] = None  # Exact Conan profile name override

    # Set during initialization
    platform_config: Optional[PlatformConfig] = field(default=None, init=False)
    _cmake_info: tuple[str, str] = field(default=("unknown", "0.0.0"), init=False, repr=False)

    def __post_init__(self):
        """Initialize platform-specific configuration"""
        self.build_type = self.build_type.capitalize()

        factory = _CONFIG_FACTORIES.get(self.platform)
        if factory is None:
            raise ConfigError(f"Unknown platform: {self.platform}")
        self.platform_config = factory(self.project_root, self.build_type, arch=self.arch, profile=self.profile)
        self.platform_config.validate()

        # Cache CMakeLists.txt parsing (avoids re-parsing on every property access)
        self._cmake_info = parse_cmake_project_info(self.project_root / "CMakeLists.txt")

    @property
    def build_dir(self) -> Path:
        """Return appropriate build directory"""
        return self.project_root / "build" / self.platform_config.build_dir_name(self.build_type)

    @property
    def preset_name(self) -> str:
        """Return CMake configure preset name"""
        return self.platform_config.preset_name(self.build_type)

    @property
    def build_preset_name(self) -> str:
        """Return CMake build preset name"""
        return self.platform_config.build_preset_name(self.build_type)

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows"""
        return platform.system() == "Windows"

    @property
    def project_name(self) -> str:
        """Return project name from CMakeLists.txt"""
        return self._cmake_info[0]

    @property
    def version(self) -> str:
        """Return project version from CMakeLists.txt"""
        return self._cmake_info[1]

    def get_resolved_build_number(self) -> int:
        """Return resolved build number from generated version.h or CLI override"""
        import re

        # CLI override takes precedence
        if self.build_number is not None:
            return self.build_number

        # Read from generated version.h (single source of truth after configure)
        version_h = self.build_dir / "generated" / "version.h"
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
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return 0
