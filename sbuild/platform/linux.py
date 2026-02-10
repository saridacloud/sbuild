"""
sbuild - Linux platform environment

Passthrough environment with optional script sourcing.
"""

import os
import subprocess
from pathlib import Path

from ..exceptions import EnvironmentSetupError
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
    ) -> dict[str, str]:
        env = dict(base_env) if base_env is not None else dict(os.environ)

        if not extra_scripts:
            return env

        # Chain: source script1 && source script2 && ... && env
        sources = " && ".join(f'source "{script}"' for script in extra_scripts)
        cmd = f'bash -c "{sources} && env"'

        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, env=env,
        )

        if result.returncode != 0:
            raise EnvironmentSetupError(
                f"Script activation failed (rc={result.returncode}): {result.stderr}"
            )

        captured: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                captured[key] = value

        return captured
