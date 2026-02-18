"""
sbuild - Native runner

Build runner for native (conan + cmake) builds with vcvarsall.bat support on Windows.
"""

import os
import time
from pathlib import Path
from typing import Optional

from ..config import BuildConfig, NativeConfig
from ..console import console
from ..exceptions import ConfigError
from ..logging import LogManager
from ..platform import IS_WINDOWS, create_platform_env
from .base import BaseRunner


class NativeRunner(BaseRunner):
    """Build runner for native (conan + cmake) builds"""

    def __init__(self, config: BuildConfig, log_manager: Optional[LogManager] = None):
        super().__init__(config, log_manager)

        native_config = config.platform_config
        if not isinstance(native_config, NativeConfig):
            raise TypeError(f"Expected NativeConfig, got {type(native_config).__name__}")
        self._native_config = native_config

        # Activate platform toolchain (vcvarsall on Windows, passthrough on Linux)
        self._platform = create_platform_env(
            env_overrides=native_config.env_vars,
            target_arch=native_config.target_arch,
        )
        t0 = time.perf_counter()
        self._env: dict[str, str] = self._platform.activate(
            base_env=dict(os.environ), cache_dir=config.project_root,
        )
        self._activate_elapsed = time.perf_counter() - t0

        # Apply .env overrides on top of activated env (always fresh, not cached)
        if native_config.env_vars:
            self._env.update(native_config.env_vars)
            if "SBUILD_QT_IFW_ROOT" in native_config.env_vars:
                qt_ifw_bin = Path(native_config.env_vars["SBUILD_QT_IFW_ROOT"]) / "bin"
                if qt_ifw_bin.exists():
                    self._env["PATH"] = (
                        str(qt_ifw_bin) + os.pathsep + self._env.get("PATH", "")
                    )

    def _get_command_env(self) -> Optional[dict[str, str]]:
        """Get environment variables for command execution"""
        return self._env

    def configure(self) -> bool:
        """Run conan install + cmake configure"""
        arch = self._native_config.target_arch
        profile_path = self._native_config.conan_profile_path

        # Validate explicit --profile or --arch when profile file doesn't exist
        if (self._native_config.profile_override or self._native_config.requested_arch) and not profile_path:
            profiles_dir = self.config.project_root / "profiles"
            available = [p.name for p in profiles_dir.iterdir()] if profiles_dir.exists() else []
            if self._native_config.profile_override:
                raise ConfigError(
                    f"Profile not found: profiles/{self._native_config.profile_override}\n"
                    f"Available profiles: {', '.join(available) if available else '(none)'}"
                )
            os_name = "windows" if IS_WINDOWS else "linux"
            expected = f"{os_name}_{self._native_config.requested_arch}_{self.config.build_type.lower()}"
            raise ConfigError(
                f"Arch-qualified profile not found: profiles/{expected}\n"
                f"Available profiles: {', '.join(available) if available else '(none)'}"
            )

        # Install dependencies with Conan
        if profile_path and profile_path.exists():
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
        cmd = f"cmake --build --preset {self.config.build_preset_name} -j{self.config.jobs}"
        return self.run_command(cmd, f"Building {self.config.build_type}")

    def get_config_summary(self) -> dict[str, list[tuple[str, str]]]:
        """Return native build configuration as grouped key-value pairs."""
        sections: dict[str, list[tuple[str, str]]] = {}

        # Toolchain section (Windows only)
        if IS_WINDOWS:
            toolchain: list[tuple[str, str]] = []
            if self._platform.toolchain_path:
                toolchain.append(("vcvarsall.bat", str(self._platform.toolchain_path)))
                toolchain.append(("vcvars arch", self._platform.vcvars_arch))
                if self._platform.cache_hit is True:
                    toolchain.append(("vcvars env", "loaded from cache"))
                elif self._platform.cache_hit is False:
                    toolchain.append(("vcvars env", "captured (cache updated)"))
                toolchain.append(("Activation time", f"{self._activate_elapsed:.2f}s"))
            else:
                toolchain.append(("vcvarsall.bat", "NOT FOUND"))
            sections["Toolchain"] = toolchain

        # Architecture section
        arch: list[tuple[str, str]] = []
        arch.append(("Host architecture", self._native_config.host_arch))
        arch.append(("Target architecture", self._native_config.target_arch))
        if self._native_config.requested_arch:
            arch.append(("Requested arch", self._native_config.requested_arch))
        if self._native_config.profile_override:
            arch.append(("Profile override", self._native_config.profile_override))
        if self._native_config.conan_profile_path:
            arch.append(("Conan profile", str(self._native_config.conan_profile_path)))
        sections["Architecture"] = arch

        # Environment (.env) section
        if self._native_config.env_vars:
            env_items: list[tuple[str, str]] = []
            for key, value in self._native_config.env_vars.items():
                env_items.append((key, value))
            sections["Environment (.env)"] = env_items

        return sections

    def show_setup_info(self) -> None:
        """Show critical native build warnings."""
        if IS_WINDOWS and not self._platform.toolchain_path:
            console.print(
                "[yellow]Warning: Visual Studio vcvarsall.bat not found. Build may fail.[/yellow]"
            )
            console.print(
                "[dim]Please install Visual Studio 2019 or 2022 with C++ tools.[/dim]"
            )
