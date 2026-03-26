#!/usr/bin/env python3
"""
sbuild - Unified build system for Conan 2 + CMake projects

Usage:
    sbuild build                        # Native debug build (default)
    sbuild build --release              # Native release build
    sbuild build --all                  # Build both debug and release
    sbuild build --clean                # Clean before building
    sbuild rebuild                      # Clean + full rebuild
    sbuild rebuild --all                # Rebuild both debug and release
    sbuild build --platform wasm        # WASM debug build
    sbuild serve --platform wasm        # Start HTTP server for WASM
    sbuild package --release            # Package release build
    sbuild package --all                # Package both debug and release
    sbuild package --fresh              # Clean rebuild before packaging
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.markup import escape

from .config import BuildConfig, ConfigManager
from .session import BuildSession
from .exceptions import BuildError, ConfigError
from .console import console
from . import __version__


app = typer.Typer(
    help="sbuild - Unified build system for Conan 2 + CMake projects.\n\n"
         "Run [cyan]sbuild COMMAND --help[/cyan] for command-specific examples.",
    no_args_is_help=False,
    invoke_without_command=True,
    rich_markup_mode="rich",
)

# Common option types defined once
ReleaseOpt = Annotated[bool, typer.Option("--release", "-r", help="Release build (default: debug)")]
AllConfigsOpt = Annotated[bool, typer.Option("--all", "-a", help="Process both debug and release")]
PlatformOpt = Annotated[Optional[str], typer.Option("--platform", "-p", help="Build platform (native or wasm)")]
VerboseOpt = Annotated[Optional[bool], typer.Option("--verbose", "-v", help="Show command output")]
JobsOpt = Annotated[Optional[int], typer.Option("--jobs", "-j", help="Parallel jobs")]
ArchOpt = Annotated[Optional[str], typer.Option("--arch", "-A", help="Target architecture (x86, x64, arm64)")]
ProfileOpt = Annotated[Optional[str], typer.Option("--profile", help="Exact Conan profile name (overrides --arch)")]


def _build_type(release: bool) -> str:
    """Return 'Release' or 'Debug' based on the flag."""
    return "Release" if release else "Debug"


def _get_build_types(all_configs: bool, release: bool) -> list[str]:
    """Get list of build types based on flags."""
    if all_configs:
        return ["Debug", "Release"]
    return [_build_type(release)]


def _create_config(
    build_type: str,
    *,
    platform: str | None = None,
    verbose: bool | None = None,
    jobs: int | None = None,
    cmake_args: str | None = None,
    build_number: int | None = None,
    arch: str | None = None,
    profile: str | None = None,
    install_prefix: Path | None = None,
) -> BuildConfig:
    """Create a fully-resolved BuildConfig via ConfigManager."""
    return ConfigManager(
        project_root=Path.cwd(),
        platform=platform,
        verbose=verbose,
        jobs=jobs,
        cmake_args=cmake_args,
        build_type=build_type,
        build_number=build_number,
        arch=arch,
        profile=profile,
        install_prefix=install_prefix,
    ).resolve()


def _do_build(
    config: BuildConfig,
    *,
    clean_first: bool = False,
    always_configure: bool = False,
):
    """Execute build action."""
    command = "rebuild" if (clean_first and always_configure) else "build"
    with BuildSession(config, command=command) as session:
        session.show_header()

        if clean_first:
            if not session.runner.clean():
                session.show_failure("clean")
                session.exit_with_error()
            if command == "rebuild":
                session.console.print()

        # Configure if forced or if build dir doesn't exist yet
        if always_configure or not session.config.build_dir.exists():
            if not session.runner.configure():
                session.show_failure("configure")
                session.exit_with_error()

        if not session.runner.build():
            session.show_failure("build")
            session.exit_with_error()

        session.show_success(command)


def _version_callback(value: bool) -> None:
    if value:
        print(f"sbuild {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    clean: Annotated[bool, typer.Option("--clean", "-c", help="Clean before building")] = False,
    jobs: JobsOpt = None,
    verbose: VerboseOpt = None,
    build_number: Annotated[Optional[int], typer.Option("--build-number", "-b", help="Override build number")] = None,
    cmake_args: Annotated[Optional[str], typer.Option("--cmake-args", help="Additional CMake arguments")] = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
    version: Annotated[bool, typer.Option("--version", "-V", help="Show version and exit",
                                          callback=_version_callback, is_eager=True)] = False,
):
    """Default action: incremental build."""
    if ctx.invoked_subcommand is None:
        config = _create_config(
            _build_type(release),
            platform=platform, verbose=verbose, jobs=jobs,
            cmake_args=cmake_args, build_number=build_number,
            arch=arch, profile=profile,
        )
        _do_build(config, clean_first=clean)


@app.command()
def build(
    release: ReleaseOpt = False,
    all_configs: AllConfigsOpt = False,
    platform: PlatformOpt = None,
    clean: Annotated[bool, typer.Option("--clean", "-c", help="Clean before building")] = False,
    jobs: JobsOpt = None,
    verbose: VerboseOpt = None,
    build_number: Annotated[Optional[int], typer.Option("--build-number", "-b", help="Override build number")] = None,
    cmake_args: Annotated[Optional[str], typer.Option("--cmake-args", help="Additional CMake arguments")] = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Incremental build (default action).

    [bold]Examples:[/bold]

      [cyan]sbuild build[/cyan]                    Debug build
      [cyan]sbuild build --release[/cyan]          Release build
      [cyan]sbuild build --all[/cyan]              Build both debug and release
      [cyan]sbuild build --clean[/cyan]            Clean before building
      [cyan]sbuild build -r -v[/cyan]              Release build with verbose output
      [cyan]sbuild build -p wasm[/cyan]            WebAssembly debug build

    [bold]Cross-compilation:[/bold]

      [cyan]sbuild build --arch x86[/cyan]          Cross-compile for x86 (uses profiles/windows_x86_debug)
      [cyan]sbuild build --arch x64[/cyan]          Explicit x64 (uses profiles/windows_x64_debug)
      [cyan]sbuild build --profile custom[/cyan]    Use exact profile name from profiles/

      When [cyan]--arch[/cyan] is specified, sbuild looks for [cyan]profiles/{os}_{arch}_{build_type}[/cyan].
      Without [cyan]--arch[/cyan], it uses [cyan]profiles/{os}_{build_type}[/cyan] (default behavior).
      Set [cyan]SBUILD_ARCH[/cyan] in [cyan].env[/cyan] or as env var for CI ([cyan]--arch[/cyan] takes precedence).

      The MSVC toolchain architecture is auto-detected from the Conan profile's
      [cyan]arch=[/cyan] setting. Override manually with [cyan]SBUILD_VCVARS_ARCH[/cyan] in .env.
    """
    build_types = _get_build_types(all_configs, release)
    for bt in build_types:
        config = _create_config(
            bt,
            platform=platform, verbose=verbose, jobs=jobs,
            cmake_args=cmake_args, build_number=build_number,
            arch=arch, profile=profile,
        )
        _do_build(config, clean_first=clean)


@app.command()
def rebuild(
    release: ReleaseOpt = False,
    all_configs: AllConfigsOpt = False,
    platform: PlatformOpt = None,
    jobs: JobsOpt = None,
    verbose: VerboseOpt = None,
    build_number: Annotated[Optional[int], typer.Option("--build-number", "-b", help="Override build number")] = None,
    cmake_args: Annotated[Optional[str], typer.Option("--cmake-args", help="Additional CMake arguments")] = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Clean + full rebuild (conan install + cmake configure + build).

    [bold]Examples:[/bold]

      [cyan]sbuild rebuild[/cyan]                  Full debug rebuild
      [cyan]sbuild rebuild --release[/cyan]        Full release rebuild
      [cyan]sbuild rebuild --all[/cyan]            Rebuild both debug and release
      [cyan]sbuild rebuild --arch x64[/cyan]       Rebuild for x64 architecture
    """
    build_types = _get_build_types(all_configs, release)
    for bt in build_types:
        config = _create_config(
            bt,
            platform=platform, verbose=verbose, jobs=jobs,
            cmake_args=cmake_args, build_number=build_number,
            arch=arch, profile=profile,
        )
        _do_build(config, clean_first=True, always_configure=True)


@app.command()
def clean(
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Remove build artifacts.

    [bold]Examples:[/bold]

      [cyan]sbuild clean[/cyan]                    Clean debug build
      [cyan]sbuild clean --release[/cyan]          Clean release build
      [cyan]sbuild clean --arch x64[/cyan]         Clean x64 debug build
    """
    config = _create_config(
        _build_type(release),
        platform=platform, arch=arch, profile=profile,
    )
    with BuildSession(config, command="clean") as session:
        session.show_header()

        if session.runner.clean():
            session.show_success("clean")
        else:
            session.show_failure("clean")
            session.exit_with_error()


@app.command()
def configure(
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    verbose: VerboseOpt = None,
    build_number: Annotated[Optional[int], typer.Option("--build-number", "-b", help="Override build number")] = None,
    cmake_args: Annotated[Optional[str], typer.Option("--cmake-args", help="Additional CMake arguments")] = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Reconfigure without building (conan install + cmake configure).

    [bold]Examples:[/bold]

      [cyan]sbuild configure[/cyan]                Configure debug
      [cyan]sbuild configure --release[/cyan]      Configure release
      [cyan]sbuild configure --arch x64[/cyan]     Configure for x64 architecture
      [cyan]sbuild configure --cmake-args "-DENABLE_FEATURE=ON"[/cyan]
    """
    config = _create_config(
        _build_type(release),
        platform=platform, verbose=verbose,
        cmake_args=cmake_args, build_number=build_number,
        arch=arch, profile=profile,
    )
    with BuildSession(config, command="configure") as session:
        session.show_header()

        if session.runner.configure():
            session.show_success("configure")
        else:
            session.show_failure("configure")
            session.exit_with_error()


@app.command()
def install(
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    prefix: Annotated[Optional[Path], typer.Option(help="Installation prefix")] = None,
    component: Annotated[Optional[str], typer.Option(help="Component to install")] = None,
    system_install: Annotated[bool, typer.Option("--system-install", help="Install to system location")] = False,
    fresh: Annotated[bool, typer.Option("--fresh", help="Clean rebuild before installing")] = False,
    verbose: VerboseOpt = None,
    jobs: JobsOpt = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Install built project.

    [bold]Examples:[/bold]

      [cyan]sbuild install[/cyan]                  Install debug to ./install/Debug
      [cyan]sbuild install --release[/cyan]        Install release to ./install/Release
      [cyan]sbuild install --prefix dist[/cyan]    Install to custom directory
      [cyan]sbuild install --fresh[/cyan]          Clean rebuild then install
    """
    config = _create_config(
        _build_type(release),
        platform=platform, arch=arch, profile=profile,
        install_prefix=prefix, verbose=verbose, jobs=jobs,
    )
    if fresh:
        _do_build(config, clean_first=True, always_configure=True)

    with BuildSession(config, command="install") as session:
        if session.runner.install(config.install_prefix, component, system_install):
            session.console.print("\n[green]Install complete![/green]")
        else:
            session.console.print("\n[red]Install failed![/red]")
            session.exit_with_error()


@app.command()
def package(
    release: ReleaseOpt = False,
    all_configs: AllConfigsOpt = False,
    platform: PlatformOpt = None,
    generator: Annotated[Optional[str], typer.Option(
        "--generator", "-G", help="CPack generator (ZIP, NSIS, IFW)")] = None,
    fresh: Annotated[bool, typer.Option("--fresh", help="Clean rebuild before packaging")] = False,
    jobs: JobsOpt = None,
    verbose: VerboseOpt = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Create distribution package using CPack.

    [bold]Generators:[/bold] ZIP, NSIS (Windows installer), IFW (Qt Installer Framework)

    [bold]Examples:[/bold]

      [cyan]sbuild package --release[/cyan]             Create all packages
      [cyan]sbuild package --release -G NSIS[/cyan]     Windows installer (.exe)
      [cyan]sbuild package --release -G ZIP[/cyan]      ZIP archive
      [cyan]sbuild package --release -G IFW[/cyan]      Qt IFW installer
      [cyan]sbuild package --all[/cyan]                 Package both debug and release
      [cyan]sbuild package --release --fresh[/cyan]     Clean rebuild then package
    """
    build_types = _get_build_types(all_configs, release)
    for bt in build_types:
        config = _create_config(
            bt,
            platform=platform, verbose=verbose, jobs=jobs,
            arch=arch, profile=profile,
        )
        if fresh:
            _do_build(config, clean_first=True, always_configure=True)

        with BuildSession(config, command="package") as session:
            if session.runner.package(generator):
                session.console.print("\n[green]Package created![/green]")
            else:
                session.console.print("\n[red]Package failed![/red]")
                session.exit_with_error()


@app.command()
def serve(
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    https: Annotated[bool, typer.Option("--https", help="Use HTTPS (port 8443)")] = False,
    port: Annotated[Optional[int], typer.Option("--port", help="Custom port")] = None,
):
    """
    Start development server for WASM testing.

    [bold]Note:[/bold] Requires --platform wasm

    [bold]Examples:[/bold]

      [cyan]sbuild serve -p wasm[/cyan]             HTTP server on port 8080
      [cyan]sbuild serve -p wasm --https[/cyan]     HTTPS server on port 8443
      [cyan]sbuild serve -p wasm --port 9000[/cyan] Custom port
    """
    try:
        config = _create_config(
            _build_type(release),
            platform=platform,
        )
        with BuildSession(config, command="serve") as session:
            if not session.runner.supports_serve:
                console.print("[red]Error: 'serve' command is not supported for this platform[/red]")
                console.print("[dim]Usage: sbuild serve --platform wasm[/dim]")
                raise typer.Exit(1)

            session.runner.serve(https=https, port=port)

    except (BuildError, ConfigError) as e:
        console.print(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def doctor(
    verbose: VerboseOpt = False,
):
    """
    Check environment health and diagnose setup issues.

    [bold]Examples:[/bold]

      [cyan]sbuild doctor[/cyan]                    Run all checks
      [cyan]sbuild doctor -v[/cyan]                 Show tool paths
    """
    from .doctor import DoctorReport

    report = DoctorReport(Path.cwd(), verbose)
    passed = report.check_all()
    report.display()
    if not passed:
        raise typer.Exit(1)



@app.command("config")
def show_config(
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Show resolved build configuration without building.

    [bold]Examples:[/bold]

      [cyan]sbuild config[/cyan]                    Show debug native config
      [cyan]sbuild config --release[/cyan]          Show release config
      [cyan]sbuild config --arch x64[/cyan]         Show x64 config
      [cyan]sbuild config -p wasm[/cyan]            Show WASM config
    """
    try:
        config = _create_config(
            _build_type(release),
            platform=platform, verbose=True,
            arch=arch, profile=profile,
        )
        with BuildSession(config, command="config") as session:
            # Access runner to trigger full config resolution + log writing
            _ = session.runner
            session._show_config_console()
    except (BuildError, ConfigError) as e:
        console.print(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def test(
    release: ReleaseOpt = False,
    platform: PlatformOpt = None,
    filter: Annotated[Optional[str], typer.Option("-R", "--filter", help="Run tests matching regex pattern")] = None,
    test_verbose: Annotated[bool, typer.Option("--test-verbose", help="Verbose CTest output")] = False,
    rerun_failed: Annotated[bool, typer.Option("--rerun-failed", help="Re-run only failed tests")] = False,
    output_on_failure: Annotated[bool, typer.Option(
        "--output-on-failure/--no-output-on-failure", help="Show output on failure")] = True,
    jobs: JobsOpt = None,
    verbose: VerboseOpt = None,
    arch: ArchOpt = None,
    profile: ProfileOpt = None,
):
    """
    Run unit tests via CTest.

    [bold]Examples:[/bold]

      [cyan]sbuild test[/cyan]                     Run all tests (debug)
      [cyan]sbuild test --release[/cyan]           Run tests for release build
      [cyan]sbuild test --filter Entity[/cyan]     Run tests matching 'Entity'
      [cyan]sbuild test --filter "App.*"[/cyan]  Run tests matching pattern
      [cyan]sbuild test --rerun-failed[/cyan]      Re-run only failed tests
      [cyan]sbuild test --test-verbose[/cyan]      Show full CTest output
    """
    config = _create_config(
        _build_type(release),
        platform=platform, verbose=verbose, jobs=jobs,
        arch=arch, profile=profile,
    )
    with BuildSession(config, command="test") as session:
        if not session.runner.supports_tests:
            console.print("[red]Error: Tests are not supported for this platform[/red]")
            raise typer.Exit(1)

        success = session.runner.run_tests(
            test_filter=filter,
            test_verbose=test_verbose,
            rerun_failed=rerun_failed,
            output_on_failure=output_on_failure,
        )

        if not success:
            session.exit_with_error()


if __name__ == "__main__":
    app()
