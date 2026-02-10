"""
sbuild - HTTPS server for WASM testing with secure context

Generates a self-signed certificate on first run for testing features
that require secure context (like Clipboard API).
"""

import http.server
import os
import platform
import signal
import ssl
import subprocess
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


def _generate_self_signed_cert(
    cert_file: Path, key_file: Path, openssl_path: Optional[Path] = None
) -> bool:
    """Generate a self-signed certificate using OpenSSL"""
    if cert_file.exists() and key_file.exists():
        console.print(f"[dim]Using existing certificate: {cert_file}[/dim]")
        return True

    console.print("[cyan]Generating self-signed certificate...[/cyan]")

    # Get OpenSSL command
    openssl_cmd = str(openssl_path) if openssl_path else "openssl"

    try:
        subprocess.run(
            [
                openssl_cmd,
                "req",
                "-x509",
                "-newkey",
                "rsa:4096",
                "-keyout",
                str(key_file),
                "-out",
                str(cert_file),
                "-days",
                "365",
                "-nodes",
                "-subj",
                "/CN=localhost/O=sbuild-Dev",
            ],
            check=True,
            capture_output=True,
        )
        console.print(f"[green]Certificate generated:[/green] {cert_file}")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]OpenSSL failed: {e.stderr.decode()}[/red]")
        return False
    except FileNotFoundError:
        console.print("[red]OpenSSL not found.[/red]")
        console.print("[yellow]Please set OPENSSL in .env.wasm or install OpenSSL[/yellow]")
        if platform.system() == "Windows":
            console.print("[dim]Example: OPENSSL=C:\\Program Files\\Git\\usr\\bin\\openssl.exe[/dim]")
        else:
            console.print("[dim]OpenSSL is usually available via your package manager (apt, brew, etc.)[/dim]")
        return False


def serve_https(
    build_dir: Path,
    port: int = 8443,
    bind: str = "0.0.0.0",
    openssl_path: Optional[Path] = None,
) -> None:
    """Start an HTTPS server for WASM testing with secure context"""
    global _shutdown_requested
    _shutdown_requested = False

    original_dir = os.getcwd()

    cert_file = build_dir / "server.pem"
    key_file = build_dir / "server.key"

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

        if not _generate_self_signed_cert(cert_file, key_file, openssl_path):
            return

        console.print(f"[cyan]Serving WASM build from:[/cyan] {build_dir}")
        console.print(
            f"[green]HTTPS server running on:[/green] https://{bind}:{port}/"
        )
        console.print("[dim]COOP/COEP headers enabled for SharedArrayBuffer[/dim]")
        console.print(
            "[yellow]NOTE: Browser will show certificate warning - accept it to continue[/yellow]"
        )
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        server_address = (bind, port)
        httpd = http.server.HTTPServer(server_address, COOPCOEPHandler)
        httpd.timeout = 0.5  # Short timeout to check for shutdown

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_file), str(key_file))
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

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
