"""
sbuild - Configuration management

Provides dataclasses for build configuration with environment detection.
"""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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


@dataclass
class NativeConfig:
    """Configuration for native (conan + cmake) builds"""

    vcvars_path: Optional[Path] = None
    arch: str = "x86_64"
    env_vars: dict[str, str] = field(default_factory=dict)

    @classmethod
    def detect(cls, project_root: Optional[Path] = None) -> "NativeConfig":
        """Auto-detect native build configuration"""
        config = cls()
        config.arch = cls._detect_architecture()

        # Load optional .env file for additional environment variables
        if project_root:
            env_file = project_root / ".env"
            config.env_vars = load_env_file(env_file)

        if platform.system() == "Windows":
            # Check .env and OS environment for explicit VCVARS_PATH
            vcvars_override = config.env_vars.get("VCVARS_PATH") or os.environ.get("VCVARS_PATH")
            if vcvars_override:
                path = Path(vcvars_override)
                if path.exists():
                    config.vcvars_path = path
                else:
                    raise ConfigError(f"VCVARS_PATH not found: {vcvars_override}")
            else:
                config.vcvars_path = cls._find_vcvars()

        return config

    @staticmethod
    def _detect_architecture() -> str:
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

    @staticmethod
    def _find_vcvars() -> Optional[Path]:
        """Find vcvars64.bat path on Windows"""
        possible_paths = [
            "C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat",
            "C:/Program Files/Microsoft Visual Studio/2022/Enterprise/VC/Auxiliary/Build/vcvars64.bat",
            "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat",
            "C:/Program Files (x86)/Microsoft Visual Studio/2019/Professional/VC/Auxiliary/Build/vcvars64.bat",
            "C:/Program Files (x86)/Microsoft Visual Studio/2019/Enterprise/VC/Auxiliary/Build/vcvars64.bat",
            "C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Auxiliary/Build/vcvars64.bat",
        ]

        for path_str in possible_paths:
            path = Path(path_str)
            if path.exists():
                return path
        return None


@dataclass
class WasmConfig:
    """Configuration for WebAssembly builds"""

    emsdk_path: Path
    qt_wasm_path: Path
    qt_host_path: Path
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

    # Platform-specific configs (set during initialization)
    native_config: Optional[NativeConfig] = field(default=None, init=False)
    wasm_config: Optional[WasmConfig] = field(default=None, init=False)

    def __post_init__(self):
        """Initialize platform-specific configuration"""
        self.build_type = self.build_type.capitalize()

        if self.platform == "native":
            self.native_config = NativeConfig.detect(self.project_root)
        elif self.platform == "wasm":
            env_file = self.project_root / ".env.wasm"
            self.wasm_config = WasmConfig.from_env_file(env_file)

    @property
    def build_dir(self) -> Path:
        """Return appropriate build directory"""
        if self.platform == "wasm":
            return self.project_root / "build" / f"wasm-{self.build_type.lower()}"
        return self.project_root / "build" / self.build_type

    @property
    def preset_name(self) -> str:
        """Return CMake preset name"""
        if self.platform == "wasm":
            return f"wasm-{self.build_type.lower()}"
        return f"conan-{self.build_type.lower()}"

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
