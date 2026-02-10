"""
sbuild - Custom exceptions
"""


class BuildError(Exception):
    """Base exception for build errors"""

    pass


class ConfigError(BuildError):
    """Configuration-related errors (missing files, invalid settings)"""

    pass


class EnvironmentSetupError(BuildError):
    """Environment setup errors (missing tools, invalid paths)"""

    pass
