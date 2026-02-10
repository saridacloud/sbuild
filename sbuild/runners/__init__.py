"""
sbuild - Runner implementations
"""

from .base import BaseRunner
from .native import NativeRunner
from .wasm import WasmRunner

RUNNER_REGISTRY: dict[str, type[BaseRunner]] = {
    "native": NativeRunner,
    "wasm": WasmRunner,
}

__all__ = ["BaseRunner", "NativeRunner", "WasmRunner", "RUNNER_REGISTRY"]
