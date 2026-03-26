"""
sbuild - HTTPS server for WASM testing with secure context

Generates a self-signed certificate on first run for testing features
that require secure context (like Clipboard API).
"""

import platform
import ssl
import subprocess
from pathlib import Path
from typing import Optional

from rich.markup import escape

from ..console import console
from ._common import serve_common


def _generate_self_signed_cert(
    cert_file: Path, key_file: Path, openssl_path: Optional[Path] = None
) -> bool:
    """Generate a self-signed certificate using OpenSSL"""
    if cert_file.exists() and key_file.exists():
        console.print(f"[dim]Using existing certificate: {escape(str(cert_file))}[/dim]")
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
        console.print(f"[green]Certificate generated:[/green] {escape(str(cert_file))}")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]OpenSSL failed: {escape(e.stderr.decode())}[/red]")
        return False
    except FileNotFoundError:
        console.print("[red]OpenSSL not found.[/red]")
        console.print("[yellow]Ensure openssl is on PATH or set SBUILD_WASM_OPENSSL_ROOT_DIR in .env[/yellow]")
        if platform.system() == "Windows":
            console.print("[dim]Example: SBUILD_WASM_OPENSSL_ROOT_DIR=C:\\Program Files\\Git\\usr[/dim]")
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
    cert_file = build_dir / "server.pem"
    key_file = build_dir / "server.key"

    if not _generate_self_signed_cert(cert_file, key_file, openssl_path):
        return

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_file), str(key_file))

    serve_common(
        build_dir,
        port,
        bind,
        ssl_context=context,
        extra_messages=[
            "[yellow]NOTE: Browser will show certificate warning - accept it to continue[/yellow]",
        ],
    )
