"""
sbuild - Platform environment abstraction

Factory for creating platform-specific environment handlers.
"""

import platform

from .base import PlatformEnv

IS_WINDOWS: bool = platform.system() == "Windows"


def create_platform_env(env_overrides: dict[str, str] | None = None) -> PlatformEnv:
    """Create platform-appropriate environment handler."""
    if IS_WINDOWS:
        from .windows import WindowsEnv

        return WindowsEnv(env_overrides)

    from .linux import LinuxEnv

    return LinuxEnv()


__all__ = ["PlatformEnv", "create_platform_env", "IS_WINDOWS"]
