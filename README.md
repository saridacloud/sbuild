# sbuild

Unified build system for Conan 2 + CMake projects with native and WebAssembly support.

Provides the `sbuild` CLI command with Rich-powered live output, automatic log rotation, and platform-specific runners for native (Conan + CMake with vcvars64) and WebAssembly (Emscripten + CMake) builds.

## Requirements

- Python >= 3.12
- [Conan 2.x](https://conan.io/) (system tool, not a Python dependency of sbuild)
- CMake 3.29+
- A C++ compiler (Visual Studio 2019/2022 on Windows, GCC/Clang on Linux)

## Installation

### From git server

Install directly from a git repository URL:

```bash
pip install git+https://github.com/saridacloud/sbuild.git
```

Or with a specific branch/tag:

```bash
pip install git+https://github.com/saridacloud/sbuild.git@main
pip install git+https://github.com/saridacloud/sbuild.git@v2.0.0
```

### From git submodule

If sbuild is included as a git submodule in your project (e.g. at `scripts/`):

```bash
# Editable install (recommended for development)
pip install -e path/to/scripts

# Regular install
pip install path/to/scripts
```

For example, in a project that has sbuild at `scripts/`:

```bash
pip install -e scripts
```

The editable install (`-e`) means changes to the sbuild source are immediately available without reinstalling.

## Usage

Run `sbuild` from your project root directory (where `CMakeLists.txt` lives):

```bash
sbuild --help                           # Show all commands
sbuild build                            # Debug build (default)
sbuild build --release                  # Release build
sbuild build --all                      # Build both debug and release
sbuild build --clean                    # Clean before building
sbuild rebuild                          # Clean + full rebuild
sbuild configure                        # Configure only (conan install + cmake)
sbuild test                             # Run unit tests
sbuild test --filter "Drone.*"          # Run tests matching pattern
sbuild package --release                # Create distribution package
sbuild package --release -G NSIS        # Windows installer
sbuild package --release -G ZIP         # ZIP archive
```

### WebAssembly builds

Requires Emscripten SDK and Qt 6 WebAssembly. Configure paths in `.env.wasm`:

```
# Windows
EMSDK=C:\path\to\emsdk
QT_WASM_PATH=C:\Qt\6.8.3\wasm_singlethread
QT_HOST_PATH=C:\Qt\6.8.3\msvc2022_64

# Linux
# EMSDK=/opt/emsdk
# QT_WASM_PATH=/opt/Qt/6.8.3/wasm_singlethread
# QT_HOST_PATH=/opt/Qt/6.8.3/gcc_64
```

```bash
sbuild build --platform wasm            # WASM debug build
sbuild build --platform wasm --release  # WASM release build
sbuild serve --platform wasm            # HTTP server (port 8080)
sbuild serve --platform wasm --https    # HTTPS server (port 8443)
```

### Common options

| Option | Short | Description |
|--------|-------|-------------|
| `--release` | `-r` | Release build (default: debug) |
| `--all` | `-a` | Process both debug and release |
| `--platform` | `-p` | Build platform: `native` (default) or `wasm` |
| `--verbose` | `-v` | Show full command output |
| `--jobs` | `-j` | Parallel jobs (default: CPU count) |
| `--build-number` | `-b` | Override build number |
| `--cmake-args` | | Additional CMake arguments |

## Project conventions

sbuild auto-detects project settings from the working directory:

- **Project name/version**: Parsed from `CMakeLists.txt` (`project(name VERSION x.y.z)`)
- **Conan profiles**: Looked up in `profiles/` (e.g. `profiles/windows_debug`)
- **Environment variables**: Loaded from `.env` (native) and `.env.wasm` (WebAssembly)
- **vcvars64 override**: Set `VCVARS_PATH` in `.env` or as an environment variable to override auto-detection
- **Build output**: Written to `build/Debug`, `build/Release`, or `build/wasm-debug`
- **Build logs**: Saved to `build_logs/` with automatic rotation (keeps last 10)

## License

This project is licensed under the [GNU General Public License v3.0 or later](https://www.gnu.org/licenses/gpl-3.0.html) (GPL-3.0-or-later).
