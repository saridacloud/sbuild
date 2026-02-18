# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `sbuild config` command — shows fully resolved configuration without building
- `BaseRunner.get_config_summary()` method for runner-specific config reporting
- `NativeRunner.get_config_summary()` — reports Toolchain, Architecture, and Environment (.env) sections
- `WasmRunner.get_config_summary()` — reports WASM Toolchain section
- Resolved config automatically logged to build log file after runner initialization
- Verbose mode (`-v`) and `sbuild config` display resolved config in console
- `normalize_arch()` helper function in `config.py`
- Tests for config dump feature (`tests/test_config_dump.py`)
- Tests for `normalize_arch()` and corrected architecture fallback behavior

### Fixed

- VSCode tasks now correctly wrap cmake defines with `--cmake-args` flag instead of passing bare `-D` args
- Empty cmake args from VSCode prompt no longer append an empty string to cmake commands
- Target architecture detection now correctly normalizes friendly arch names (e.g. `x64` → `x86_64`) before falling back, fixing incorrect architecture when using `--arch` with profiles that don't specify `arch=`
- Configure status message now shows target architecture instead of host architecture

### Changed

- Renamed `NativeConfig.arch` to `host_arch` for clarity

### Removed

- Legacy `NativeConfig.detect_target_architecture()` method (superseded by `detect()` + `_detect_target_arch()`)

### Changed

- `BuildSession` now accepts a `command` parameter to track the active CLI command
- `show_header()` no longer takes an `action` argument — uses `self.command` instead
- Early CLI parameter logging replaced with single `Command: sbuild {command}` line for crash safety
- Resolved config log now includes `Command` and `Verbose` fields
- Console config output now includes `Command` field

## [1.2.0] - 2026-02-13

### Added

- Cache `vcvarsall.bat` captured environment to `.sbuild/vcvars_cache.pkl` — eliminates ~3-5s subprocess overhead on repeat builds
- Auto-invalidation on vcvarsall.bat modification or architecture change; manual clear via `rmdir .sbuild`
- `cache_hit` property on `WindowsEnv` for verbose-mode cache status reporting
- Execution time profiling for build session and individual runner steps — total elapsed time displayed at end of session
- Tests for cache miss/hit, fingerprint invalidation, corrupt cache fallback, and auto-directory creation
- "Environment Caching (Windows)" section in README

### Changed

- `PlatformEnv.activate()` signature now accepts `cache_dir` parameter (used by Windows, ignored by Linux)
- `NativeRunner` passes `cache_dir=config.project_root` to platform activation
- `sbuild doctor` passes `cache_dir=self.project_root` to platform activation
- Verbose mode now shows vcvars environment cache status (loaded from cache / captured)
- VS Code tasks updated to use `process` type with faster execution times and enhanced presentation options

## [1.1.0] - 2026-02-12

### Added

- `--arch` (`-A`) CLI option for architecture-aware profile selection (x86, x64, arm64)
- `--profile` CLI option for exact Conan profile name override
- `SBUILD_ARCH` environment variable for CI/scripting arch selection (`.env` or system env)
- Architecture-isolated build directories (`build/{arch}/{build_type}`) when `--arch` is used
- `resolve_arch()` helper for unified arch resolution (CLI > .env > system env)
- `resolve_profile_path()` helper for unified profile resolution
- Auto-detection of CMake configure preset names from `CMakeUserPresets.json` — supports both single-config generators (Ninja: `conan-debug`/`conan-release`) and multi-config generators (Visual Studio: `conan-default`)
- `build_preset_name` property on `PlatformConfig` and `BuildConfig` to separate build presets from configure presets
- `sbuild doctor` now distinguishes configure vs build presets and reports multi-config generator setups
- Tests for profile resolution, arch-aware config detection, build directory naming, and preset resolution (single-config, multi-config)

### Changed

- Profile resolution centralized in `NativeConfig.detect()` (removed duplicate logic from `NativeRunner`)
- `NativeConfig` stores resolved `conan_profile_path` for reuse by runner
- `BuildConfig`, `BuildSession` accept `arch` and `profile` parameters
- `.env` file loaded earlier in `NativeConfig.detect()` so `SBUILD_ARCH` is available for profile resolution
- Config factory signature now passes `arch` and `profile` through to platform config detection
- Runners now use `build_preset_name` for `cmake --build` commands instead of `preset_name`, fixing multi-config generator support

### Fixed

- Hardcoded `conan-{build_type}` preset names broke builds with multi-config generators (e.g. Visual Studio) that use `conan-default` as configure preset ([#1](https://github.com/saridacloud/sbuild/issues/1))

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

[Unreleased]: https://github.com/saridacloud/sbuild/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/saridacloud/sbuild/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/saridacloud/sbuild/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/saridacloud/sbuild/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/saridacloud/sbuild/releases/tag/v1.0.0
