# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-02-12

### Added

- Cross-compilation support on Windows via `vcvarsall.bat` with architecture argument
- Conan profile arch parser (`parse_conan_profile_arch`) — reads `arch=` from `[settings]` section
- `target_arch` field on `NativeConfig`, auto-detected from the Conan profile for the active build type
- `VCVARS_ARCH` environment variable (in `.env` or system) to manually override the vcvarsall architecture
- Architecture mapping: `x86_64`→`amd64`, `x86`→`amd64_x86`, `armv8`→`amd64_arm64`, `armv7`→`amd64_arm`
- `sbuild doctor` now reports the active vcvars architecture
- Cross-compilation documentation in `sbuild build --help`
- Tests for profile arch parsing, target architecture detection, and vcvars arch resolution

### Changed

- Switched from `vcvars64.bat` to `vcvarsall.bat` for MSVC toolchain activation on Windows
- Config factory signature now passes `build_type` through to platform config detection
- `create_platform_env()` accepts `target_arch` parameter
- `sbuild doctor` labels updated from `vcvars64.bat` to `vcvarsall.bat`

## [1.0.0] - 2026-02-10

### Added

**CLI Commands**
- `sbuild build` — incremental build with `--clean` option
- `sbuild rebuild` — clean + full rebuild (conan install, cmake configure, build)
- `sbuild clean` — remove build artifacts
- `sbuild configure` — reconfigure without building (conan install + cmake configure)
- `sbuild install` — install built project with `--prefix`, `--component`, and `--system-install` options
- `sbuild package` — create distribution packages via CPack
- `sbuild test` — run unit tests via CTest
- `sbuild serve` — start development server for WebAssembly testing
- `sbuild doctor` — check environment health and diagnose setup issues
- `sbuild --version` — display version information

**Build System**
- Conan 2 integration for dependency management
- CMake preset-based builds (`conan-debug`/`conan-release`, `wasm-debug`/`wasm-release`)
- Multi-config support via `--all` flag (build both debug and release in one command)
- Parallel build jobs via `--jobs` (defaults to CPU count)
- CMake arguments passthrough via `--cmake-args`

**Platform Support**
- Native Windows builds with automatic `vcvars64.bat` detection (Visual Studio 2019/2022)
- Native Linux builds with GCC/Clang (passthrough, no toolchain activation needed)
- WebAssembly builds via Emscripten SDK with Qt 6 WASM support

**Testing**
- CTest integration with `sbuild test`
- Regex test filtering (`-R` / `--filter`)
- Rerun only failed tests (`--rerun-failed`)
- Parallel test execution (`--jobs`)
- Output on failure (enabled by default, toggle with `--output-on-failure` / `--no-output-on-failure`)
- Rich-formatted test summaries with pass/fail counts and pass rates

**Packaging**
- CPack integration with `sbuild package`
- Generator selection via `-G` flag: ZIP, NSIS (Windows installer), IFW (Qt Installer Framework)
- Platform-aware package naming
- Build number support (auto-detected from git commit count or `version.h`, override with `--build-number`)
- Fresh rebuild before packaging (`--fresh`)

**Developer Tools**
- `sbuild doctor` diagnostics covering core tools, Conan setup, native environment (vcvars), WASM environment (emsdk, Qt paths), project configuration, CMake presets, and packaging tools (NSIS, Qt IFW)
- HTTP development server for WASM testing (default port 8080)
- HTTPS development server with auto-generated self-signed certificates (default port 8443)
- COOP/COEP response headers for SharedArrayBuffer support in WASM builds

**Terminal Output**
- Rich Live panels displaying the last 8 lines of build output
- Color-coded status messages and build progress
- Error context panels with surrounding output on failure
- Verbose mode (`-v`) for full unfiltered command output

**Logging**
- Automatic build log files saved to `build_logs/`
- Log rotation keeping the last 10 log files
- System info headers in each log file (OS, Python, tool versions)

**Configuration**
- Automatic project name and version parsing from `CMakeLists.txt`
- Conan profile detection from `profiles/` directory
- Environment variable loading from `.env` (native) and `.env.wasm` (WebAssembly)
- Build number auto-detection from git commit count or `version.h`

[1.0.1]: https://github.com/saridacloud/sbuild/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/saridacloud/sbuild/releases/tag/v1.0.0
