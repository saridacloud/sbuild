# sbuild

[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Python: 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![Status: Beta](https://img.shields.io/badge/Status-Beta-yellow.svg)]()

Unified build system for Conan 2 + CMake projects with native and WebAssembly support.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Project Setup](#project-setup)
- [Environment Caching (Windows)](#environment-caching-windows)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Quick Start

```bash
sbuild build                            # Debug build
sbuild build --release                  # Release build
sbuild build --all                      # Build both debug and release
sbuild test                             # Run CTest suite
sbuild doctor                           # Check environment health
```

<details>
<summary><strong>Installation</strong></summary>

### Prerequisites

- Python >= 3.12
- [Conan 2.x](https://conan.io/)
- CMake 3.29+
- C++ compiler (Visual Studio 2019/2022 on Windows, GCC/Clang on Linux)

### Virtual environment (recommended)

```bash
python -m venv .venv

# Activate
# Windows (cmd):        .venv\Scripts\activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux / macOS:        source .venv/bin/activate

pip install conan
```

### Install from git

```bash
pip install git+https://github.com/saridacloud/sbuild.git

# Specific branch or tag:
pip install git+https://github.com/saridacloud/sbuild.git@main
pip install git+https://github.com/saridacloud/sbuild.git@v1.0.0

# Force update to latest:
pip install --force-reinstall git+https://github.com/saridacloud/sbuild.git@develop
```

### Install from git submodule

If sbuild is included as a submodule (e.g. at `scripts/`):

```bash
pip install -e scripts    # Editable (recommended for development)
pip install scripts       # Regular install
```

</details>

## Commands

| Command | Description |
|---------|-------------|
| `sbuild build` | Incremental build (also the default when running `sbuild` with no command) |
| `sbuild rebuild` | Clean + full rebuild (conan install + cmake configure + build) |
| `sbuild clean` | Remove build artifacts |
| `sbuild configure` | Reconfigure without building (conan install + cmake configure) |
| `sbuild install` | Install built project to a directory |
| `sbuild package` | Create distribution package via CPack |
| `sbuild serve` | Start development server for WASM testing (requires `--platform wasm`) |
| `sbuild test` | Run unit tests via CTest (native only) |
| `sbuild config` | Show fully resolved configuration without building |
| `sbuild doctor` | Check environment health and diagnose setup issues |

### Global Options

| Flag | Short | Description |
|------|-------|-------------|
| `--version` | `-V` | Show version and exit |

---

<details>
<summary><strong>build</strong> — Incremental build</summary>

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Release build (default: debug) |
| `--all` | `-a` | bool | `False` | Build both debug and release |
| `--platform` | `-p` | str | `native` | Build platform: `native` or `wasm` |
| `--clean` | `-c` | bool | `False` | Clean before building |
| `--verbose` | `-v` | bool | `False` | Show full command output |
| `--jobs` | `-j` | int | CPU count | Parallel build jobs |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name (overrides `--arch`) |
| `--build-number` | `-b` | int | — | Override build number |
| `--cmake-args` | | str | — | Additional CMake arguments |

```bash
sbuild build                            # Debug build
sbuild build --release                  # Release build
sbuild build --all                      # Both debug and release
sbuild build --clean                    # Clean before building
sbuild build --arch x64 --release       # x64 release build
sbuild build -p wasm                    # WebAssembly debug build
```

</details>

<details>
<summary><strong>rebuild</strong> — Clean + full rebuild</summary>

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Release build (default: debug) |
| `--all` | `-a` | bool | `False` | Rebuild both debug and release |
| `--platform` | `-p` | str | `native` | Build platform: `native` or `wasm` |
| `--verbose` | `-v` | bool | `False` | Show full command output |
| `--jobs` | `-j` | int | CPU count | Parallel build jobs |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name (overrides `--arch`) |
| `--build-number` | `-b` | int | — | Override build number |
| `--cmake-args` | | str | — | Additional CMake arguments |

```bash
sbuild rebuild                          # Full debug rebuild
sbuild rebuild --release                # Full release rebuild
sbuild rebuild --all                    # Rebuild both debug and release
```

</details>

<details>
<summary><strong>clean</strong> — Remove build artifacts</summary>

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Clean release build (default: debug) |
| `--platform` | `-p` | str | `native` | Build platform: `native` or `wasm` |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name |

```bash
sbuild clean                            # Clean debug build
sbuild clean --release                  # Clean release build
sbuild clean --arch x64                 # Clean x64 debug build
```

</details>

<details>
<summary><strong>configure</strong> — Reconfigure without building</summary>

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Configure release (default: debug) |
| `--platform` | `-p` | str | `native` | Build platform: `native` or `wasm` |
| `--verbose` | `-v` | bool | `False` | Show full command output |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name (overrides `--arch`) |
| `--build-number` | `-b` | int | — | Override build number |
| `--cmake-args` | | str | — | Additional CMake arguments |

```bash
sbuild configure                        # Configure debug
sbuild configure --release              # Configure release
sbuild configure --cmake-args "-DENABLE_FEATURE=ON"
```

</details>

<details>
<summary><strong>install</strong> — Install built project</summary>

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Install release build (default: debug) |
| `--platform` | `-p` | str | `native` | Build platform: `native` or `wasm` |
| `--prefix` | | path | — | Installation prefix directory |
| `--component` | | str | — | Component to install |
| `--system-install` | | bool | `False` | Install to system location |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name |

```bash
sbuild install                          # Install debug to ./install/Debug
sbuild install --release                # Install release to ./install/Release
sbuild install --release --prefix dist  # Install to custom directory
```

</details>

<details>
<summary><strong>package</strong> — Create distribution package via CPack</summary>

Generators: `ZIP`, `NSIS` (Windows installer), `IFW` (Qt Installer Framework)

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Package release build (default: debug) |
| `--all` | `-a` | bool | `False` | Package both debug and release |
| `--platform` | `-p` | str | `native` | Build platform: `native` or `wasm` |
| `--generator` | `-G` | str | — | CPack generator: `ZIP`, `NSIS`, `IFW` |
| `--fresh` | | bool | `False` | Clean rebuild before packaging |
| `--verbose` | `-v` | bool | `False` | Show full command output |
| `--jobs` | `-j` | int | CPU count | Parallel build jobs |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name |

```bash
sbuild package --release                # Create all packages
sbuild package --release -G NSIS        # Windows installer (.exe)
sbuild package --release -G ZIP         # ZIP archive
sbuild package --release --fresh        # Clean rebuild then package
```

</details>

<details>
<summary><strong>serve</strong> — Start development server for WASM testing</summary>

> **Note:** Requires `--platform wasm`.

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Serve release build (default: debug) |
| `--platform` | `-p` | str | `native` | Must be set to `wasm` |
| `--https` | | bool | `False` | Use HTTPS (default port 8443) |
| `--port` | | int | — | Custom port (default: 8080 HTTP, 8443 HTTPS) |

```bash
sbuild serve -p wasm                    # HTTP server on port 8080
sbuild serve -p wasm --https            # HTTPS server on port 8443
sbuild serve -p wasm --port 9000        # Custom port
```

</details>

<details>
<summary><strong>test</strong> — Run unit tests via CTest</summary>

> **Note:** Tests are not supported for WASM builds.

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--release` | `-r` | bool | `False` | Test release build (default: debug) |
| `--platform` | `-p` | str | `native` | Build platform |
| `--filter` | `-R` | str | — | Run tests matching regex pattern |
| `--test-verbose` | | bool | `False` | Verbose CTest output |
| `--rerun-failed` | | bool | `False` | Re-run only failed tests |
| `--output-on-failure` | | bool | `True` | Show output on failure (disable with `--no-output-on-failure`) |
| `--verbose` | `-v` | bool | `False` | Show full command output |
| `--jobs` | `-j` | int | CPU count | Parallel test jobs |
| `--arch` | `-A` | str | — | Target architecture: `x86`, `x64`, `arm64` |
| `--profile` | | str | — | Exact Conan profile name |

```bash
sbuild test                             # Run all tests (debug)
sbuild test --release                   # Run tests for release build
sbuild test --filter "App.*"            # Run tests matching pattern
sbuild test --rerun-failed              # Re-run only failed tests
```

</details>

<details>
<summary><strong>doctor</strong> — Check environment health</summary>

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--verbose` | `-v` | bool | `False` | Show tool paths and details |

```bash
sbuild doctor                           # Run all checks
sbuild doctor -v                        # Show tool paths
```

</details>

## Configuration

### .env — All builds

Single `KEY=VALUE` file for all build environment variables. Values may be quoted (`"value"` or `'value'`).

#### Universal Variables

| Variable | Default | CLI Override | Description |
|----------|---------|-------------|-------------|
| `SBUILD_PLATFORM` | `native` | `--platform` | Default build platform |
| `SBUILD_ARCH` | — | `--arch` | Target architecture (`x86`, `x64`, `arm64`) |
| `SBUILD_VERBOSE` | `false` | `--verbose` | Default verbosity |
| `SBUILD_BUILD_DIR` | `build` | — | Base build directory |
| `SBUILD_INSTALL_DIR` | — | `--prefix` | Default install prefix |
| `SBUILD_PARALLEL_JOBS` | CPU count | `--jobs` | Parallel build jobs |
| `SBUILD_CMAKE_ARGS` | — | `--cmake-args` | Extra CMake arguments (all platforms) |

#### Native Variables (Windows)

| Variable | Required | Description |
|----------|----------|-------------|
| `SBUILD_VCVARS_PATH` | No | Override auto-detection of `vcvarsall.bat` path |
| `SBUILD_VCVARS_ARCH` | No | Override vcvarsall architecture argument (e.g. `amd64`, `amd64_x86`) |
| `SBUILD_QT_IFW_ROOT` | No | Qt Installer Framework root (enables IFW packaging) |

#### WASM Variables

| Variable | Required | Auto cmake `-D`? | Description |
|----------|----------|-----------------|-------------|
| `EMSDK` | Yes | No | Path to Emscripten SDK |
| `SBUILD_WASM_QT_PATH` | Yes | No | Path to Qt WASM kit (e.g. `C:\Qt\6.8.3\wasm_singlethread`) |
| `SBUILD_WASM_QT_HOST_PATH` | No | `-DQT_HOST_PATH=...` | Path to Qt host kit (e.g. `C:\Qt\6.8.3\msvc2022_64`) |
| `SBUILD_WASM_OPENSSL_ROOT_DIR` | No | `-DOPENSSL_ROOT_DIR=...` | OpenSSL root for WASM builds |
| `SBUILD_WASM_CMAKE_ARGS` | No | Yes | WASM-specific extra CMake arguments |

#### CMake Args Merge Order

`SBUILD_CMAKE_ARGS` + `SBUILD_WASM_CMAKE_ARGS` (if WASM) + CLI `--cmake-args` (last wins)

### Resolution Priority

All `SBUILD_` variables follow: **CLI arg > .env file > system env var > default value**

**Conan profile:**
`CLI --profile` (exact name) > `--arch` lookup (`{os}_{arch}_{build_type}`) > Default (`{os}_{build_type}`)

**SBUILD_VCVARS_PATH** (Windows):
`.env` > System env > Auto-detect from known VS install paths

**SBUILD_VCVARS_ARCH** (Windows):
`.env` > System env > Conan profile `arch=` mapping > Default `amd64`

## Project Setup

sbuild expects this layout in the consuming C++ project:

```
my-project/
├── CMakeLists.txt              # Must contain project(Name VERSION x.y.z)
├── profiles/                   # Conan 2 profiles
│   ├── windows_debug           # Default profiles (no arch qualifier)
│   ├── windows_release
│   ├── windows_x64_debug       # Arch-qualified profiles (optional)
│   ├── windows_x64_release
│   ├── linux_debug
│   └── linux_release
├── .env                        # Environment vars — native + WASM (optional; required for WASM builds)
├── src/
└── CMakeUserPresets.json       # Auto-generated by sbuild configure (via Conan)
```

### CMakeLists.txt

Must contain a `project()` directive with a version. sbuild parses this to determine the project name and version for packaging.

```cmake
project(MyApp VERSION 1.2.3)
```

### Conan Profiles

Place profiles in `profiles/` using the naming convention `{os}_{build_type}` (e.g. `windows_debug`, `linux_release`). For cross-compilation, use `{os}_{arch}_{build_type}` (e.g. `windows_x64_debug`) and select with `--arch`. Use `--profile` to bypass naming conventions and select a profile by exact name.

The CMake generator can be configured per-profile via Conan's `[conf]` section (e.g. `tools.cmake.cmaketoolchain:generator=Ninja`). If unset, Conan uses the system default.

### CMake Presets

`sbuild configure` runs Conan, which generates `CMakeUserPresets.json`. sbuild auto-detects preset names:

- **Single-config generators** (Ninja, Unix Makefiles): `conan-debug` / `conan-release`
- **Multi-config generators** (Visual Studio): `conan-default` configure preset with `conan-debug` / `conan-release` build presets
- **WASM**: `wasm-debug` / `wasm-release`

### Build Output

- `build/Debug`, `build/Release` — native (no arch)
- `build/x64/Debug`, `build/x64/Release` — native with `--arch`
- `build/wasm-debug`, `build/wasm-release` — WASM
- `build_logs/` — build logs with automatic rotation (keeps last 10)

### Editor Integration

Pre-configured VS Code tasks are available in [`editors/vscode/tasks.json`](editors/vscode/tasks.json). Copy to your project's `.vscode/` directory and use **Ctrl+Shift+B** for build tasks.

## Environment Caching (Windows)

On Windows, sbuild caches the environment captured from `vcvarsall.bat` to avoid re-running it on every command (~3-5 seconds saved per invocation).

**Location:** `.sbuild/vcvars_cache.pkl` in the project root

**Auto-invalidation:** The cache is automatically invalidated when:
- `vcvarsall.bat` is modified (file timestamp change)
- The target architecture changes (e.g. switching between `x64` and `arm64`)

**Manual invalidation:** Delete the cache directory:
```bash
# Windows (cmd)
rmdir /s /q .sbuild

# PowerShell / Linux
rm -rf .sbuild
```

**Notes:**
- Caching is only used for native builds without extra scripts
- Cache failures never break builds — sbuild falls back to running `vcvarsall.bat`
- Use `-v` (verbose) to see whether the cache was hit or missed

## Troubleshooting

Run `sbuild doctor` to diagnose environment issues. It checks five categories:

| Category | What it checks |
|----------|---------------|
| **Core Tools** | Python version, virtual env, CMake, Conan (version 2), Git, Ninja |
| **Native Environment** | Architecture, `.env` file, Conan profiles, vcvarsall.bat (Windows) or GCC (Linux) |
| **WASM Environment** | `.env` WASM vars, EMSDK path, emsdk_env script, Qt WASM/host paths, OpenSSL |
| **Project Configuration** | `CMakeLists.txt` parsing, CMake presets (both single-config and multi-config) |
| **Packaging Tools** | CPack, Qt IFW, NSIS (Windows) |

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| vcvarsall.bat not found | Visual Studio not installed or not detected | Install VS 2019/2022 with C++ workload, or set `SBUILD_VCVARS_PATH` in `.env` |
| Conan profile not found | Missing `profiles/` directory or misnamed profile | Create `profiles/{os}_{build_type}` (e.g. `profiles/windows_debug`) |
| WASM config missing | `.env` missing WASM vars | Add `EMSDK`, `SBUILD_WASM_QT_PATH` to `.env` |
| CMake presets not found | First build not yet configured | Run `sbuild configure` to generate presets via Conan |
| Conan version mismatch | Conan 1.x installed instead of 2.x | Upgrade with `pip install --upgrade conan` |
| Tests not supported | Running `sbuild test` with `--platform wasm` | Tests are only supported for native builds |

## License

[GPL-3.0-or-later](https://www.gnu.org/licenses/gpl-3.0.html)
