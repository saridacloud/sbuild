"""
sbuild - Native runner

Build runner for native (conan + cmake) builds with vcvars64 support on Windows.
"""

import os
from pathlib import Path
from typing import Optional

from ..config import BuildConfig, NativeConfig
from ..console import console
from ..logging import LogManager
from ..platform import IS_WINDOWS, create_platform_env
from .base import BaseRunner


class NativeRunner(BaseRunner):
    """Build runner for native (conan + cmake) builds"""

    supports_tests = True
    supports_serve = False

    def __init__(self, config: BuildConfig, log_manager: Optional[LogManager] = None):
        super().__init__(config, log_manager)

        native_config = config.platform_config
        assert isinstance(native_config, NativeConfig)
        self._native_config = native_config

        self._env: dict[str, str] = dict(os.environ)

        # Load environment variables from .env file if available
        if native_config.env_vars:
            self._env.update(native_config.env_vars)

            # Add Qt IFW bin directory to PATH if configured
            if "QT_IFW_ROOT" in native_config.env_vars:
                qt_ifw_bin = Path(native_config.env_vars["QT_IFW_ROOT"]) / "bin"
                if qt_ifw_bin.exists():
                    self._env["PATH"] = str(qt_ifw_bin) + os.pathsep + self._env.get("PATH", "")

        # Activate platform toolchain (vcvars on Windows, passthrough on Linux)
        self._platform = create_platform_env(
            env_overrides=native_config.env_vars,
        )
        self._env = self._platform.activate(base_env=self._env)

    def _get_command_env(self) -> Optional[dict[str, str]]:
        """Get environment variables for command execution"""
        return self._env

    def _prepare_command(self, cmd: str) -> str:
        """No-op: vcvars env is now passed via env= parameter"""
        return cmd

    def configure(self) -> bool:
        """Run conan install + cmake configure"""
        arch = self._native_config.arch

        # Install dependencies with Conan
        # Use project-specific profile if it exists
        os_name = "windows" if self.config.is_windows else "linux"
        profile_path = self.config.project_root / "profiles" / f"{os_name}_{self.config.build_type.lower()}"

        if profile_path.exists():
            cmd = f"conan install . --profile:all={profile_path} --build=missing"
            if self.log_manager:
                self.log_manager.write(f"Using project profile: {profile_path}")
        else:
            # Fall back to specifying settings directly
            cmd = f"conan install . -s arch={arch} -s build_type={self.config.build_type} --build=missing"
            if self.log_manager:
                self.log_manager.write("Using default Conan settings (no project profile found)")

        if not self.run_command(cmd, f"Installing dependencies (arch: {arch})"):
            return False

        # Generate build files with CMake
        cmd = f"cmake -Wno-dev --preset {self.config.preset_name}"
        if self.config.build_number is not None:
            cmd += f" -DBUILD_NUMBER={self.config.build_number}"
        if self.config.cmake_args:
            cmd += f" {self.config.cmake_args}"
        return self.run_command(cmd, "Configuring project")

    def build(self) -> bool:
        """Build the project"""
        cmd = f"cmake --build --preset {self.config.preset_name} -j{self.config.jobs}"
        return self.run_command(cmd, f"Building {self.config.build_type}")

    def show_setup_info(self) -> None:
        """Show native build setup information"""
        if IS_WINDOWS:
            if self._platform.toolchain_path:
                if self.config.verbose:
                    console.print(
                        f"[green]Found vcvars64:[/green] [dim]{self._platform.toolchain_path}[/dim]"
                    )
            else:
                console.print(
                    "[yellow]Warning: Visual Studio vcvars64.bat not found. Build may fail.[/yellow]"
                )
                console.print(
                    "[dim]Please install Visual Studio 2019 or 2022 with C++ tools.[/dim]"
                )

        if self.config.verbose:
            console.print(
                f"[green]Detected architecture:[/green] [dim]{self._native_config.arch}[/dim]"
            )

            # Show loaded environment variables from .env
            if self._native_config.env_vars:
                console.print("[green]Loaded from .env:[/green]")
                for key, value in self._native_config.env_vars.items():
                    console.print(f"  [dim]{key}={value}[/dim]")
