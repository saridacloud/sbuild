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
