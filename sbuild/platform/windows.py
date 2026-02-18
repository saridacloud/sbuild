"""
sbuild - Windows platform environment

Finds vcvarsall.bat and captures the resulting environment variables
with an architecture argument derived from the target platform.
"""

import os
import pickle
from pathlib import Path

from ..exceptions import EnvironmentSetupError
from .base import PlatformEnv

_CACHE_DIR_NAME = ".sbuild"
_CACHE_FILE_NAME = "vcvars_cache.pkl"

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
        self._cache_hit: bool | None = None

    @property
    def toolchain_path(self) -> Path | None:
        return self._vcvars_path

    @property
    def vcvars_arch(self) -> str:
        """The architecture argument passed to vcvarsall.bat."""
        return self._vcvars_arch

    @property
    def cache_hit(self) -> bool | None:
        """Whether the last activate() used a cached environment.

        None means activate() has not been called yet, True means cache hit,
        False means cache miss (subprocess was invoked).
        """
        return self._cache_hit

    def activate(
        self,
        *,
        extra_scripts: list[Path] | None = None,
        base_env: dict[str, str] | None = None,
        cache_dir: Path | None = None,
    ) -> dict[str, str]:
        env = dict(base_env) if base_env is not None else dict(os.environ)

        has_vcvars = self._vcvars_path is not None
        has_extras = bool(extra_scripts)

        if not has_vcvars and not has_extras:
            return env

        use_cache = has_vcvars and not has_extras and cache_dir is not None

        if use_cache:
            fingerprint = self._build_fingerprint()
            cached = self._load_cache(cache_dir, fingerprint)
            if cached is not None:
                self._cache_hit = True
                return cached

        # Build chained command: [vcvarsall arch &&] [extra1 && extra2 &&] set
        parts: list[str] = []
        if has_vcvars:
            parts.append(f'"{self._vcvars_path}" {self._vcvars_arch}')
        for script in extra_scripts or []:
            parts.append(f'"{script}"')
        parts.append("set")
        chain = " && ".join(parts)
        cmd = f'cmd /c "{chain}"'

        captured = self._run_and_capture_env(cmd, env)

        if use_cache:
            self._cache_hit = False
            self._save_cache(cache_dir, fingerprint, captured)

        return captured

    # --- caching helpers ---

    def _build_fingerprint(self) -> tuple[str, float, str]:
        """Build a cache fingerprint from vcvars path, mtime, and arch."""
        path_str = str(self._vcvars_path)
        try:
            mtime = self._vcvars_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (path_str, mtime, self._vcvars_arch)

    @staticmethod
    def _cache_path(cache_dir: Path) -> Path:
        return cache_dir / _CACHE_DIR_NAME / _CACHE_FILE_NAME

    def _load_cache(
        self, cache_dir: Path, fingerprint: tuple[str, float, str]
    ) -> dict[str, str] | None:
        """Load cached env if fingerprint matches. Returns None on any failure."""
        try:
            path = self._cache_path(cache_dir)
            if not path.exists():
                return None
            with open(path, "rb") as f:
                data = pickle.load(f)
            if data.get("fingerprint") == fingerprint:
                return data["env"]
        except (OSError, pickle.UnpicklingError):
            pass
        return None

    def _save_cache(
        self,
        cache_dir: Path,
        fingerprint: tuple[str, float, str],
        env: dict[str, str],
    ) -> None:
        """Save captured env to cache. Failures are silently ignored."""
        try:
            path = self._cache_path(cache_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump({"fingerprint": fingerprint, "env": env}, f)
        except (OSError, pickle.PicklingError):
            pass

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
