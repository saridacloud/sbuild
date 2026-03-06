# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `UnicodeDecodeError` crash in build output reader thread when compiler output contains non-UTF-8 bytes (e.g. `0xb0` degree symbol on Linux) — subprocess pipes now use `errors="replace"` to substitute invalid bytes

### Added

- **Tool Versions** section in config dump — `sbuild config`, verbose mode, and build logs now show detected versions of Python, CMake, Conan, Git, and Ninja (native) or emcc (WASM)
- `get_tool_version()` public helper in `doctor.py` — lightweight version detection for a single tool

### Changed

- **BREAKING:** `resolve_profile_path()` moved from module-level function to `NativeConfig._resolve_profile_path()` static method (no longer a public API)
- **BREAKING:** `BuildConfig.get_resolved_build_number()` extracted to standalone `resolve_build_number(build_number, build_dir, project_root)` function
- `NativeConfig.from_env()` classmethod now handles arch resolution, profile detection, and target arch detection (previously in `ConfigManager._build_native_config()`)
- `WasmConfig.from_env()` classmethod now handles validation and environment dict construction (previously in `ConfigManager._build_wasm_config()`)
- Architecture maps consolidated from 3 manually-maintained dicts (`_ARCH_MAPPING`, `_FRIENDLY_ARCH_MAP`, `_CONAN_TO_FRIENDLY_MAP`) to single canonical `_ARCH_TABLE` + derived dicts + `_MACHINE_TO_CONAN`
- `ConfigManager` slimmed from ~237 to ~90 lines — delegates platform config construction to dataclass factory methods
- Removed unused `platform_config` parameter from `_compute_build_dir()`, `_compute_preset_name()`, `_compute_build_preset_name()`
- Removed standalone `_strip_quotes()` function — quote stripping inlined where needed

### Added

- `--fresh` option for `sbuild install` — clean rebuild before installing (mirrors `sbuild package --fresh`)
- `friendly_arch` field on `NativeConfig` — always populated (derived from `--arch` or host architecture), used for display and profile fallback
- `conan_to_friendly_arch()` helper function — reverse mapping from Conan arch names to friendly equivalents (e.g. `x86_64` → `x64`)
- Profile fallback for implicit arch — without `--arch`, tries `{os}_{friendly_arch}_{build_type}` profile before falling back to `{os}_{build_type}`

### Removed

- Architecture-isolated build directories — `--arch` no longer creates `build/{arch}/{build_type}` subfolders; build dir is always `build/{build_type}` (switch arch via rebuild)

### Fixed

- Rich Live panel leaving residual border/content lines after transient cleanup by switching to synchronous rendering (`auto_refresh=False` + explicit `refresh=True`)
- VSCode tasks: venv-installed tools (conan, cmake, etc.) now found on all platforms — global `windows`/`linux`/`osx` blocks prepend `.venv` to PATH, simplifying all task commands to bare `sbuild` (removed per-task platform overrides)

### Added

- `ConfigManager` class — single point of config resolution; receives raw CLI args, loads `.env` once, resolves everything via generic `_resolve()` method (CLI > .env > os.environ > default priority), and produces a fully-populated `BuildConfig`
- `detect_architecture()` standalone function (extracted from `NativeConfig.detect_architecture()`)

### Changed

- **BREAKING:** `BuildSession` now takes a pre-built `BuildConfig` instead of ~10 individual args
- `BuildConfig`, `NativeConfig`, `WasmConfig` are now frozen dataclasses (pure data holders with no logic)
- `WasmConfig.qt_host_path` uses `None` instead of empty `Path()` as sentinel for "not set"
- Pre-computed fields on `BuildConfig`: `build_dir`, `preset_name`, `build_preset_name`, `project_name`, `version` (no longer properties or delegated to platform config)
- `NativeConfig.env_vars` now includes SBUILD_* vars from os.environ, eliminating `WindowsEnv` os.environ fallbacks

### Removed

- `PlatformConfig` abstract base class — `NativeConfig` and `WasmConfig` are independent dataclasses
- `_CONFIG_FACTORIES` registry — `ConfigManager` handles platform dispatch directly
- 10+ individual `resolve_*()` functions — replaced by `ConfigManager._resolve()`
- `NativeConfig.detect()` classmethod — logic moved to `ConfigManager._build_native_config()`
- `WasmConfig.from_env()` classmethod — logic moved to `ConfigManager._build_wasm_config()`
- `_get_project_env()` from CLI — `ConfigManager` loads `.env` internally
- `BuildConfig.__post_init__` — all resolution moved to `ConfigManager.resolve()`
- `get_environment()` methods from config classes — replaced by pre-computed `.environment` field on `WasmConfig`
- `validate()`, `display_name`, `build_dir_name()`, `preset_name()`, `build_preset_name()` methods from config classes

### Added (previous)

- Universal environment variable defaults: `SBUILD_PLATFORM`, `SBUILD_VERBOSE`, `SBUILD_BUILD_DIR`, `SBUILD_INSTALL_DIR`, `SBUILD_PARALLEL_JOBS`, `SBUILD_CMAKE_ARGS` — all configurable via `.env` or system env with CLI override
- `SBUILD_WASM_CMAKE_ARGS` for WASM-specific cmake arguments
- Auto-injection of `-DQT_HOST_PATH` and `-DOPENSSL_ROOT_DIR` cmake defines from WASM config vars
- CMake args merging: `SBUILD_CMAKE_ARGS` + `SBUILD_WASM_CMAKE_ARGS` (if WASM) + CLI `--cmake-args` (last wins)
- Quote stripping in `.env` file parser — `SBUILD_CMAKE_ARGS="-DFOO=BAR"` now works correctly
- OpenSSL binary lookup: tries `openssl` from PATH first, falls back to `SBUILD_WASM_OPENSSL_ROOT_DIR/bin/openssl`
- Resolver functions for all new env vars following CLI > .env > system env > default priority
- `_get_project_env()` in CLI for lazy-loaded `.env` caching

### Changed

- **BREAKING:** All sbuild-specific env vars now use `SBUILD_` prefix:
  - `VCVARS_PATH` → `SBUILD_VCVARS_PATH`
  - `VCVARS_ARCH` → `SBUILD_VCVARS_ARCH`
  - `QT_IFW_ROOT` → `SBUILD_QT_IFW_ROOT`
  - `QT_WASM_PATH` → `SBUILD_WASM_QT_PATH`
  - `QT_HOST_PATH` → `SBUILD_WASM_QT_HOST_PATH`
  - `OPENSSL` → `SBUILD_WASM_OPENSSL_ROOT_DIR`
- **BREAKING:** Single `.env` file replaces `.env` + `.env.wasm` split — all WASM vars now live in `.env`
- **BREAKING:** `WasmConfig.from_env_file()` replaced with `WasmConfig.from_env(env_vars)` — receives pre-loaded dict instead of file path
- **BREAKING:** `WasmConfig.openssl_path` renamed to `WasmConfig.openssl_root_dir`
- `BuildConfig` now loads `.env` centrally and passes `env_vars` to platform config factories
- `BuildConfig.build_dir` uses configurable `build_dir_base` (from `SBUILD_BUILD_DIR`) instead of hardcoded `"build"`
- `NativeConfig.detect()` accepts optional `env_vars` parameter (avoids re-loading `.env`)
- CLI option defaults changed from hardcoded values to `None` with env-var resolution in command bodies
- `WasmConfig.get_environment()` maps `SBUILD_WASM_QT_PATH` back to `QT_WASM_PATH` for cmake preset compatibility
- `sbuild doctor` WASM checks now detect WASM presence by `EMSDK`/`SBUILD_WASM_QT_PATH` in unified `.env`
- Config dump labels updated to show new `SBUILD_` variable names

### Removed

- `.env.wasm` file support — all configuration now lives in a single `.env` file
- `wasm_env_file` test fixture (replaced with `wasm_env_vars` dict fixture)

### Changed

- Extract magic numbers in `BaseRunner` to named class constants (`_PANEL_MAX_LINES`, `_PANEL_HEIGHT`, `_ERROR_TAIL_LINES`, etc.)
- Extract `_MAX_LOG_FILES` constant in `LogManager` log rotation
- Simplify error keyword matching in `BaseRunner._show_error_output()` with case-insensitive comparison
- Narrow bare `except Exception` blocks to specific exception types in `_read_process_output`, `_load_cache`/`_save_cache`, and `DoctorReport.__post_init__`
- Replace `assert isinstance(...)` with `TypeError` raise in `NativeRunner` and `WasmRunner` constructors
- Remove unused `**kwargs` parameter from `WasmRunner.serve()`
- Remove dead `startswith("<")` filter in `LoggingConsole.print()`
- Add type hints to `BaseRunner._read_process_output()` and `_live_console` property

### Removed

- Unused `VALID_ARCH_VALUES` constant from `config.py`
- Unused `BuildConfig.is_windows` property (use `IS_WINDOWS` constant instead)
- Unused public API exports from `__init__.py` (`LoggingConsole`, `PlatformConfig`, `parse_conan_profile_arch`)
- Redundant `NativeRunner` class-attribute overrides (`supports_tests`, `supports_serve`) identical to `BaseRunner` defaults
- No-op `NativeRunner._prepare_command()` override
- Dead `hasattr` branch in `BaseRunner._live_console` property

### Changed

- Consolidate duplicate "build dir not found" guard into `BaseRunner._require_build_dir()` helper
- Extract `_build_type()` helper in `cli.py` to replace 7 repeated ternary expressions
- Use `contextlib.chdir` instead of manual `os.chdir`/restore in `BaseRunner.package()` and `serve_common()`
- Deduplicate profiles-dir listing in `NativeRunner.configure()` error handling
- Hoist deferred `ConfigError` and `BuildError` imports to module-level in `native.py` and `base.py`
- Simplify `console.py` by removing unnecessary intermediate variable

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

- `.env` variable changes now take effect immediately without clearing the vcvarsall cache — previously, cached environment snapshots contained stale `.env` values that persisted until the cache was invalidated
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
