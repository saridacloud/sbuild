"""
sbuild - WebAssembly runner

Build runner for WebAssembly (emscripten + cmake) builds.
"""

import os
from pathlib import Path
from typing import Optional

from ..config import BuildConfig
from ..console import console
from ..exceptions import EnvironmentSetupError
from ..logging import LogManager
from ..platform import IS_WINDOWS, create_platform_env
from .base import BaseRunner


class WasmRunner(BaseRunner):
    """Build runner for WebAssembly (emscripten + cmake) builds"""

    def __init__(self, config: BuildConfig, log_manager: Optional[LogManager] = None):
        super().__init__(config, log_manager)
        self._activated_env: Optional[dict[str, str]] = None
        self._platform = create_platform_env()

        if config.wasm_config:
            config.wasm_config.validate()
            self._activated_env = self._activate_emscripten()

    def _activate_emscripten(self) -> dict[str, str]:
        """Activate Emscripten SDK and capture resulting environment"""
        if not self.config.wasm_config:
            raise EnvironmentSetupError("WASM configuration not loaded")

        emsdk_path = self.config.wasm_config.emsdk_path
        env = dict(os.environ)
        env.update(self.config.wasm_config.get_environment())

        script_name = "emsdk_env.bat" if IS_WINDOWS else "emsdk_env.sh"
        emsdk_script = emsdk_path / script_name
        if not emsdk_script.exists():
            raise EnvironmentSetupError(f"{script_name} not found: {emsdk_script}")

        if IS_WINDOWS and not self._platform.toolchain_path:
            console.print(
                "[yellow]Warning: vcvars64.bat not found. cmake may not be available.[/yellow]"
            )

        return self._platform.activate(extra_scripts=[emsdk_script], base_env=env)

    def _get_command_env(self) -> Optional[dict[str, str]]:
        """Get activated Emscripten environment"""
        return self._activated_env

    def configure(self) -> bool:
        """Run cmake configure with WASM preset"""
        cmd = f"cmake --preset {self.config.preset_name}"
        if self.config.cmake_args:
            cmd += f" {self.config.cmake_args}"
        return self.run_command(cmd, "Configuring WASM project")

    def build(self) -> bool:
        """Build the WASM project"""
        cmd = f"cmake --build --preset {self.config.preset_name} -j{self.config.jobs}"
        return self.run_command(cmd, f"Building WASM {self.config.build_type}")

    def serve(self, https: bool = False, port: Optional[int] = None) -> None:
        """Start development server for WASM testing"""
        from ..servers import serve_http, serve_https as serve_https_fn

        if not self.config.build_dir.exists():
            console.print(
                f"[red]Build directory not found: {self.config.build_dir}[/red]"
            )
            console.print("[yellow]Please build the WASM project first.[/yellow]")
            return

        if https:
            openssl_path = (
                self.config.wasm_config.openssl_path
                if self.config.wasm_config
                else None
            )
            serve_https_fn(
                self.config.build_dir,
                port=port or 8443,
                openssl_path=openssl_path,
            )
        else:
            serve_http(self.config.build_dir, port=port or 8080)

    def show_setup_info(self) -> None:
        """Show WASM build setup information"""
        if self.config.verbose and self.config.wasm_config:
            if self._platform.toolchain_path:
                console.print(
                    f"[green]vcvars64:[/green] [dim]{self._platform.toolchain_path}[/dim]"
                )
            console.print(
                f"[green]EMSDK:[/green] [dim]{self.config.wasm_config.emsdk_path}[/dim]"
            )
            console.print(
                f"[green]Qt WASM:[/green] [dim]{self.config.wasm_config.qt_wasm_path}[/dim]"
            )
            console.print(
                f"[green]Qt Host:[/green] [dim]{self.config.wasm_config.qt_host_path}[/dim]"
            )
