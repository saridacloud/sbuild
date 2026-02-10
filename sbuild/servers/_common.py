"""
sbuild - Shared server utilities

Common handler, signal setup, and serve loop for HTTP/HTTPS servers.
"""

import http.server
import os
import signal
import ssl
import sys
from pathlib import Path
from typing import Optional

from ..console import console

# Flag to signal shutdown
_shutdown_requested = False


class COOPCOEPHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that adds COOP/COEP headers for SharedArrayBuffer support.

    Required for multi-threaded WebAssembly (Qt wasm_multithread).
    See: https://web.dev/coop-coep/
    """

    def end_headers(self):
        # Required for SharedArrayBuffer (multi-threaded WASM)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, format, *args):
        # Suppress default logging (use rich console instead)
        pass


def serve_common(
    build_dir: Path,
    port: int,
    bind: str,
    ssl_context: Optional[ssl.SSLContext] = None,
    extra_messages: Optional[list[str]] = None,
) -> None:
    """Start an HTTP(S) server with COOP/COEP headers.

    Args:
        build_dir: Directory to serve files from
        port: Port to listen on
        bind: Address to bind to
        ssl_context: If provided, wrap the socket for HTTPS
        extra_messages: Additional console messages to show before starting
    """
    global _shutdown_requested
    _shutdown_requested = False

    original_dir = os.getcwd()

    def signal_handler(signum, frame):
        global _shutdown_requested
        _shutdown_requested = True
        console.print("\n[yellow]Shutting down...[/yellow]")

    # Register signal handler for graceful shutdown on Windows
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        os.chdir(build_dir)

        scheme = "https" if ssl_context else "http"
        console.print(f"[cyan]Serving WASM build from:[/cyan] {build_dir}")
        console.print(f"[green]{scheme.upper()} server running on:[/green] {scheme}://{bind}:{port}/")
        console.print("[dim]COOP/COEP headers enabled for SharedArrayBuffer[/dim]")

        for msg in extra_messages or []:
            console.print(msg)

        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        server_address = (bind, port)
        httpd = http.server.HTTPServer(server_address, COOPCOEPHandler)
        httpd.timeout = 0.5  # Short timeout to check for shutdown

        if ssl_context:
            httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)

        # Use polling loop instead of serve_forever for better Ctrl+C handling
        while not _shutdown_requested:
            httpd.handle_request()

        console.print("[yellow]Server stopped.[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error: {e}[/red]")
    finally:
        os.chdir(original_dir)
