"""
sbuild - Unified build system for Conan 2 + CMake projects

This package provides a unified build system for native and WebAssembly builds.
"""

__version__ = "1.2.8"

from .logging import LogManager
from .console import console
from .config import BuildConfig, ConfigManager, NativeConfig, WasmConfig, detect_architecture
from .exceptions import BuildError, ConfigError, EnvironmentSetupError
from .session import BuildSession
from .test_reporter import TestReporter

__all__ = [
    "LogManager",
    "console",
    "BuildConfig",
    "ConfigManager",
    "NativeConfig",
    "WasmConfig",
    "detect_architecture",
    "BuildError",
    "ConfigError",
    "EnvironmentSetupError",
    "BuildSession",
    "TestReporter",
]
