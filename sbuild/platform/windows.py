"""
sbuild - Windows platform environment

Finds vcvars64.bat and captures the resulting environment variables.
Consolidates logic previously in vcvars.py and NativeConfig._find_vcvars().
"""

import os
from pathlib import Path

from ..exceptions import EnvironmentSetupError
from .base import PlatformEnv

_KNOWN_VCVARS_PATHS = [
    "C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat",
    "C:/Program Files/Microsoft Visual Studio/2022/Enterprise/VC/Auxiliary/Build/vcvars64.bat",
    "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat",
    "C:/Program Files (x86)/Microsoft Visual Studio/2019/Professional/VC/Auxiliary/Build/vcvars64.bat",
    "C:/Program Files (x86)/Microsoft Visual Studio/2019/Enterprise/VC/Auxiliary/Build/vcvars64.bat",
    "C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Auxiliary/Build/vcvars64.bat",
]


class WindowsEnv(PlatformEnv):
    """Windows platform environment with vcvars64 activation."""

    def __init__(self, env_overrides: dict[str, str] | None = None):
        self._vcvars_path = self._find_vcvars(env_overrides)

    @property
    def toolchain_path(self) -> Path | None:
        return self._vcvars_path

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

        # Build chained command: [vcvars &&] [extra1 && extra2 &&] set
        parts: list[str] = []
        if has_vcvars:
            parts.append(f'"{self._vcvars_path}"')
        for script in extra_scripts or []:
            parts.append(f'"{script}"')
        parts.append("set")
        chain = " && ".join(parts)
        cmd = f'cmd /c "{chain}"'

        return self._run_and_capture_env(cmd, env)

    @staticmethod
    def _find_vcvars(env_overrides: dict[str, str] | None = None) -> Path | None:
        """Find vcvars64.bat, checking overrides first, then known paths."""
        # Check env_overrides dict, then os.environ for VCVARS_PATH
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
        for path_str in _KNOWN_VCVARS_PATHS:
            path = Path(path_str)
            if path.exists():
                return path

        return None
