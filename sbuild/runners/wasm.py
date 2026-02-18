"""
sbuild - WebAssembly runner

Build runner for WebAssembly (emscripten + cmake) builds.
"""

import os
from pathlib import Path
from typing import Optional

from ..config import BuildConfig, WasmConfig
from ..console import console
from ..exceptions import EnvironmentSetupError
from ..logging import LogManager
from ..platform import IS_WINDOWS, create_platform_env
from .base import BaseRunner


class WasmRunner(BaseRunner):
    """Build runner for WebAssembly (emscripten + cmake) builds"""

    supports_tests = False
    supports_serve = True

    def __init__(self, config: BuildConfig, log_manager: Optional[LogManager] = None):
        super().__init__(config, log_manager)

        wasm_config = config.platform_config
        if not isinstance(wasm_config, WasmConfig):
            raise TypeError(f"Expected WasmConfig, got {type(wasm_config).__name__}")
        self._wasm_config = wasm_config

        # Build base env from platform config environment
        env = dict(os.environ)
        env.update(wasm_config.get_environment())

        # Activate emscripten via platform env
        script_name = "emsdk_env.bat" if IS_WINDOWS else "emsdk_env.sh"
        emsdk_script = wasm_config.emsdk_path / script_name
        if not emsdk_script.exists():
            raise EnvironmentSetupError(f"{script_name} not found: {emsdk_script}")

        self._platform = create_platform_env()

        if IS_WINDOWS and not self._platform.toolchain_path:
            console.print(
                "[yellow]Warning: vcvarsall.bat not found. cmake may not be available.[/yellow]"
            )

        self._env = self._platform.activate(extra_scripts=[emsdk_script], base_env=env)

    def _get_command_env(self) -> Optional[dict[str, str]]:
        """Get activated Emscripten environment"""
        return self._env

    def configure(self) -> bool:
        """Run cmake configure with WASM preset"""
        cmd = f"cmake --preset {self.config.preset_name}"
        if self.config.cmake_args:
            cmd += f" {self.config.cmake_args}"
        return self.run_command(cmd, "Configuring WASM project")

    def build(self) -> bool:
        """Build the WASM project"""
        cmd = f"cmake --build --preset {self.config.build_preset_name} -j{self.config.jobs}"
        return self.run_command(cmd, f"Building WASM {self.config.build_type}")

    def get_config_summary(self) -> dict[str, list[tuple[str, str]]]:
        """Return WASM build configuration as grouped key-value pairs."""
        sections: dict[str, list[tuple[str, str]]] = {}

        toolchain: list[tuple[str, str]] = []
        if IS_WINDOWS and self._platform.toolchain_path:
            toolchain.append(("vcvarsall.bat", str(self._platform.toolchain_path)))
        toolchain.append(("EMSDK", str(self._wasm_config.emsdk_path)))
        toolchain.append(("Qt WASM path", str(self._wasm_config.qt_wasm_path)))
        toolchain.append(("Qt Host path", str(self._wasm_config.qt_host_path)))
        if self._wasm_config.openssl_path:
            toolchain.append(("OpenSSL path", str(self._wasm_config.openssl_path)))
        sections["WASM Toolchain"] = toolchain

        return sections

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
            openssl_path = self._wasm_config.openssl_path
            serve_https_fn(
                self.config.build_dir,
                port=port or 8443,
                openssl_path=openssl_path,
            )
        else:
            serve_http(self.config.build_dir, port=port or 8080)


