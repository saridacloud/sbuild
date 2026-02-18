"""
sbuild - Unified build system for Conan 2 + CMake projects

This package provides a unified build system for native and WebAssembly builds.
"""

__version__ = "1.2.6"

from .logging import LogManager
from .console import console
from .config import BuildConfig, NativeConfig, WasmConfig
from .exceptions import BuildError, ConfigError, EnvironmentSetupError
from .session import BuildSession
from .test_reporter import TestReporter

__all__ = [
    "LogManager",
    "console",
    "BuildConfig",
    "NativeConfig",
    "WasmConfig",
    "BuildError",
    "ConfigError",
    "EnvironmentSetupError",
    "BuildSession",
    "TestReporter",
]
