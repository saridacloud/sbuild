"""
sbuild - Windows platform environment

Finds vcvarsall.bat and captures the resulting environment variables
with an architecture argument derived from the target platform.
"""

import os
from pathlib import Path

from ..exceptions import EnvironmentSetupError
from .base import PlatformEnv

_KNOWN_VCVARSALL_PATHS = [
    "C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvarsall.bat",
    "C:/Program Files/Microsoft Visual Studio/2022/Enterprise/VC/Auxiliary/Build/vcvarsall.bat",
    "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvarsall.bat",
    "C:/Program Files (x86)/Microsoft Visual Studio/2019/Professional/VC/Auxiliary/Build/vcvarsall.bat",
    "C:/Program Files (x86)/Microsoft Visual Studio/2019/Enterprise/VC/Auxiliary/Build/vcvarsall.bat",
    "C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Auxiliary/Build/vcvarsall.bat",
]

_VCVARS_ARCH_MAPPING: dict[str, str] = {
    "x86_64": "amd64",
    "x86": "amd64_x86",
    "armv8": "amd64_arm64",
    "armv7": "amd64_arm",
}
_DEFAULT_VCVARS_ARCH = "amd64"


class WindowsEnv(PlatformEnv):
    """Windows platform environment with vcvarsall.bat activation."""

    def __init__(self, env_overrides: dict[str, str] | None = None, target_arch: str = "x86_64"):
        self._vcvars_path = self._find_vcvarsall(env_overrides)
        self._vcvars_arch = self._resolve_vcvars_arch(env_overrides, target_arch)

    @property
    def toolchain_path(self) -> Path | None:
        return self._vcvars_path

    @property
    def vcvars_arch(self) -> str:
        """The architecture argument passed to vcvarsall.bat."""
        return self._vcvars_arch

    def activate(
        self,
        *,
        extra_scripts: list[Path] | None = None,
        base_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        env = dict(base_env) if base_env is not None else dict(os.environ)

        has_vcvars = self._vcvars_path is not None
        has_extras = bool(extra_scripts)

        if not has_vcvars and not has_extras:
            return env

        # Build chained command: [vcvarsall arch &&] [extra1 && extra2 &&] set
        parts: list[str] = []
        if has_vcvars:
            parts.append(f'"{self._vcvars_path}" {self._vcvars_arch}')
        for script in extra_scripts or []:
            parts.append(f'"{script}"')
        parts.append("set")
        chain = " && ".join(parts)
        cmd = f'cmd /c "{chain}"'

        return self._run_and_capture_env(cmd, env)

    @staticmethod
    def _resolve_vcvars_arch(
        env_overrides: dict[str, str] | None,
        target_arch: str,
    ) -> str:
        """Determine vcvarsall.bat arch argument.

        Priority: VCVARS_ARCH in env_overrides > VCVARS_ARCH in os.environ
        > mapping from target_arch > default "amd64".
        """
        if env_overrides:
            override = env_overrides.get("VCVARS_ARCH")
            if override:
                return override
        env_override = os.environ.get("VCVARS_ARCH")
        if env_override:
            return env_override
        return _VCVARS_ARCH_MAPPING.get(target_arch, _DEFAULT_VCVARS_ARCH)

    @staticmethod
    def _find_vcvarsall(env_overrides: dict[str, str] | None = None) -> Path | None:
        """Find vcvarsall.bat, checking overrides first, then known paths."""
        override = None
        if env_overrides:
            override = env_overrides.get("VCVARS_PATH")
        if not override:
            override = os.environ.get("VCVARS_PATH")

        if override:
            path = Path(override)
            if path.exists():
                return path
            raise EnvironmentSetupError(f"VCVARS_PATH not found: {override}")

        # Search known installation paths
        for path_str in _KNOWN_VCVARSALL_PATHS:
            path = Path(path_str)
            if path.exists():
                return path

        return None
