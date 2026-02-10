"""
sbuild - Platform environment interface

Abstract base class for platform-specific toolchain activation.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class PlatformEnv(ABC):
    """Interface for platform-specific environment activation."""

    @property
    @abstractmethod
    def toolchain_path(self) -> Path | None:
        """Platform toolchain path (e.g. vcvars64.bat), or None if not found."""

    @abstractmethod
    def activate(
        self,
        *,
        extra_scripts: list[Path] | None = None,
        base_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Activate platform toolchain + optional extra scripts, return captured env dict.

        If no toolchain and no extra_scripts, returns base_env (or os.environ copy).
        """

    @staticmethod
    def _run_and_capture_env(cmd: str, env: dict[str, str]) -> dict[str, str]:
        """Run a shell command and parse key=value environment output.

        Raises EnvironmentSetupError on non-zero return code.
        """
        import subprocess
        from ..exceptions import EnvironmentSetupError

        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, env=env,
        )

        if result.returncode != 0:
            raise EnvironmentSetupError(
                f"Toolchain activation failed (rc={result.returncode}): {result.stderr}"
            )

        captured: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                captured[key] = value

        return captured
