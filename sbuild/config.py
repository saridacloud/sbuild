"""
sbuild - Configuration management

Provides dataclasses for build configuration with environment detection.
"""

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


@dataclass
class NativeConfig(PlatformConfig):
    """Configuration for native (conan + cmake) builds"""

    arch: str = "x86_64"
    env_vars: dict[str, str] = field(default_factory=dict)

    @classmethod
    def detect(cls, project_root: Optional[Path] = None) -> "NativeConfig":
        """Auto-detect native build configuration"""
        config = cls()
        config.arch = cls.detect_architecture()

        if project_root:
            env_file = project_root / ".env"
            config.env_vars = load_env_file(env_file)

        return config

    @staticmethod
    def detect_architecture() -> str:
        """Detect system architecture and return Conan architecture string"""
        machine = platform.machine().lower()

        arch_mapping = {
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

        return arch_mapping.get(machine, machine)

    def build_dir_name(self, build_type: str) -> str:
        return build_type

    def preset_name(self, build_type: str) -> str:
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


_CONFIG_FACTORIES: dict[str, Callable[[Path], PlatformConfig]] = {
    "native": lambda root: NativeConfig.detect(root),
    "wasm": lambda root: WasmConfig.from_env_file(root / ".env.wasm"),
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

    # Platform-specific config (set during initialization)
    platform_config: Optional[PlatformConfig] = field(default=None, init=False)

    def __post_init__(self):
        """Initialize platform-specific configuration"""
        self.build_type = self.build_type.capitalize()

        factory = _CONFIG_FACTORIES.get(self.platform)
        if factory is None:
            raise ConfigError(f"Unknown platform: {self.platform}")
        self.platform_config = factory(self.project_root)
        self.platform_config.validate()

    @property
    def build_dir(self) -> Path:
        """Return appropriate build directory"""
        return self.project_root / "build" / self.platform_config.build_dir_name(self.build_type)

    @property
    def preset_name(self) -> str:
        """Return CMake preset name"""
        return self.platform_config.preset_name(self.build_type)

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows"""
        return platform.system() == "Windows"

    @property
    def project_name(self) -> str:
        """Return project name from CMakeLists.txt"""
        name, _ = parse_cmake_project_info(self.project_root / "CMakeLists.txt")
        return name

    @property
    def version(self) -> str:
        """Return project version from CMakeLists.txt"""
        _, version = parse_cmake_project_info(self.project_root / "CMakeLists.txt")
        return version

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
