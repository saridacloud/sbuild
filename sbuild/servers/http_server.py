"""
sbuild - Simple HTTP server for WASM testing
"""

from pathlib import Path

from ._common import serve_common


def serve_http(build_dir: Path, port: int = 8080, bind: str = "0.0.0.0") -> None:
    """Start a simple HTTP server for WASM testing"""
    serve_common(build_dir, port, bind)
