"""
sbuild - Linux platform environment

Passthrough environment with optional script sourcing.
"""

import os
from pathlib import Path

from .base import PlatformEnv


class LinuxEnv(PlatformEnv):
    """Linux platform environment (no toolchain, optional script sourcing)."""

    @property
    def toolchain_path(self) -> Path | None:
        return None

    def activate(
        self,
        *,
        extra_scripts: list[Path] | None = None,
        base_env: dict[str, str] | None = None,
        cache_dir: Path | None = None,
    ) -> dict[str, str]:
        env = dict(base_env) if base_env is not None else dict(os.environ)

        if not extra_scripts:
            return env

        # Chain: source script1 && source script2 && ... && env
        sources = " && ".join(f'source "{script}"' for script in extra_scripts)
        cmd = f'bash -c "{sources} && env"'

        return self._run_and_capture_env(cmd, env)
