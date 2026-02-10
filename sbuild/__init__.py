"""
sbuild - Unified build system for Conan 2 + CMake projects

This package provides a unified build system for native and WebAssembly builds.
"""

__version__ = "2.0.0"

from .logging import LogManager, LoggingConsole
from .console import console
from .config import BuildConfig, NativeConfig, PlatformConfig, WasmConfig
from .exceptions import BuildError, ConfigError, EnvironmentSetupError
from .session import BuildSession
from .test_reporter import TestReporter

__all__ = [
    "LogManager",
    "LoggingConsole",
    "console",
    "BuildConfig",
    "NativeConfig",
    "PlatformConfig",
    "WasmConfig",
    "BuildError",
    "ConfigError",
    "EnvironmentSetupError",
    "BuildSession",
    "TestReporter",
]
