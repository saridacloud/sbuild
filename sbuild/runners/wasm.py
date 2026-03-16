"""
sbuild - WebAssembly runner

Build runner for WebAssembly (emscripten + cmake) builds.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from rich.markup import escape

from ..config import BuildConfig, WasmConfig
from ..console import console
from ..doctor import get_tool_version
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
        env.update(wasm_config.environment)

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

        # Auto-inject cmake defines from WASM config
        if self._wasm_config.qt_host_path is not None:
            cmd += f" -DQT_HOST_PATH={self._wasm_config.qt_host_path}"
        if self._wasm_config.openssl_root_dir:
            cmd += f" -DOPENSSL_ROOT_DIR={self._wasm_config.openssl_root_dir}"

        if self.config.cmake_args:
            cmd += f" {self.config.cmake_args}"
        return self.run_command(cmd, "Configuring WASM project")

    def build(self) -> bool:
        """Build the WASM project"""
        cmd = f"cmake --build --preset {self.config.build_preset_name} -j{self.config.jobs}"
        return self.run_command(cmd, f"Building WASM {self.config.build_type}")

    def _get_tool_versions(self) -> list[tuple[str, str]]:
        """Detect versions of build tools using the activated environment."""
        if hasattr(self, "_tool_versions_cache"):
            return self._tool_versions_cache
        env = self._get_command_env()
        tools: list[tuple[str, str]] = []
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        tools.append(("Python", py_ver))
        for name, args in [("cmake", None), ("conan", None), ("git", None), ("emcc", None)]:
            ver = get_tool_version(name, args, env=env)
            tools.append((name, ver or "not found"))
        self._tool_versions_cache = tools
        return tools

    def get_config_summary(self) -> dict[str, list[tuple[str, str]]]:
        """Return WASM build configuration as grouped key-value pairs."""
        sections: dict[str, list[tuple[str, str]]] = {}

        toolchain: list[tuple[str, str]] = []
        if IS_WINDOWS and self._platform.toolchain_path:
            toolchain.append(("vcvarsall.bat", str(self._platform.toolchain_path)))
        toolchain.append(("EMSDK", str(self._wasm_config.emsdk_path)))
        toolchain.append(("SBUILD_WASM_QT_PATH", str(self._wasm_config.qt_wasm_path)))
        if self._wasm_config.qt_host_path is not None:
            toolchain.append(("SBUILD_WASM_QT_HOST_PATH", str(self._wasm_config.qt_host_path)))
        if self._wasm_config.openssl_root_dir:
            toolchain.append(("SBUILD_WASM_OPENSSL_ROOT_DIR", str(self._wasm_config.openssl_root_dir)))
        sections["WASM Toolchain"] = toolchain

        # Auto-injected cmake defines
        auto_defines: list[tuple[str, str]] = []
        if self._wasm_config.qt_host_path is not None:
            auto_defines.append(("-DQT_HOST_PATH", str(self._wasm_config.qt_host_path)))
        if self._wasm_config.openssl_root_dir:
            auto_defines.append(("-DOPENSSL_ROOT_DIR", str(self._wasm_config.openssl_root_dir)))
        if auto_defines:
            sections["Auto-injected cmake defines"] = auto_defines

        # Tool Versions section
        sections["Tool Versions"] = self._get_tool_versions()

        return sections

    def serve(self, https: bool = False, port: Optional[int] = None) -> None:
        """Start development server for WASM testing"""
        from ..servers import serve_http, serve_https as serve_https_fn

        if not self.config.build_dir.exists():
            console.print(
                f"[red]Build directory not found: {escape(str(self.config.build_dir))}[/red]"
            )
            console.print("[yellow]Please build the WASM project first.[/yellow]")
            return

        if https:
            # Try openssl from PATH first, fall back to SBUILD_WASM_OPENSSL_ROOT_DIR/bin/openssl
            openssl_path = None
            system_openssl = shutil.which("openssl")
            if system_openssl:
                openssl_path = Path(system_openssl)
            elif self._wasm_config.openssl_root_dir:
                candidate = self._wasm_config.openssl_root_dir / "bin" / "openssl"
                if IS_WINDOWS:
                    candidate = candidate.with_suffix(".exe")
                if candidate.exists():
                    openssl_path = candidate

            serve_https_fn(
                self.config.build_dir,
                port=port or 8443,
                openssl_path=openssl_path,
            )
        else:
            serve_http(self.config.build_dir, port=port or 8080)


