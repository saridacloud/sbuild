# sbuild

One CLI to drive Conan 2, CMake, CTest, and CPack across native Windows/Linux and WebAssembly targets — with live terminal output, environment diagnostics, and packaging built in.

Provides the `sbuild` CLI command with Rich-powered live output, automatic log rotation, and platform-specific runners for native (Conan + CMake with vcvars64) and WebAssembly (Emscripten + CMake) builds.

## Requirements

- Python >= 3.12
- [Conan 2.x](https://conan.io/) (system tool, not a Python dependency of sbuild)
- CMake 3.29+
- A C++ compiler (Visual Studio 2019/2022 on Windows, GCC/Clang on Linux)

## Installation

### Recommended: Use a virtual environment

Create a virtual environment in your project to keep sbuild and its dependencies isolated:

```bash
# Create (once)
python -m venv .venv

# Activate
# Windows (cmd)
.venv\Scripts\activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

# Then install sbuild (and other tools like conan) inside the venv
pip install conan
pip install git+https://github.com/saridacloud/sbuild.git
```

> **Tip:** Add `.venv/` to your `.gitignore`.

### From git server

Install directly from a git repository URL:

```bash
pip install git+https://github.com/saridacloud/sbuild.git
```

Or with a specific branch/tag:

```bash
pip install git+https://github.com/saridacloud/sbuild.git@main
pip install git+https://github.com/saridacloud/sbuild.git@v1.0.0
```

Or force to update to the latest commit:

```bash
pip install --force-reinstall git+https://github.com/saridacloud/sbuild.git@develop
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
sbuild test --filter "App.*"          # Run tests matching pattern
sbuild package --release                # Create distribution package
sbuild package --release -G NSIS        # Windows installer
sbuild package --release -G ZIP         # ZIP archive
sbuild package --release --fresh        # Clean rebuild then package
sbuild doctor                           # Check environment health
sbuild doctor -v                        # Show tool paths and details
sbuild install --release                # Install to ./install/Release
sbuild install --release --prefix dist  # Install to custom directory
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

### Editor Integration

Pre-configured VS Code tasks are available in [`editors/vscode/tasks.json`](editors/vscode/tasks.json).
Copy to your project's `.vscode/` directory.

Then use **Ctrl+Shift+B** for build tasks or **Ctrl+Shift+P** → *Tasks: Run Task* for all tasks.

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

## Target Project Structure

sbuild expects a specific layout in the consuming C++ project:

```
my-project/
├── CMakeLists.txt              # Must contain project(Name VERSION x.y.z)
├── profiles/                   # Conan 2 profiles
│   ├── windows_debug
│   ├── windows_release
│   ├── linux_debug
│   └── linux_release
├── .env                        # Native env vars (optional)
├── .env.wasm                   # WASM env vars (optional, enables WASM builds)
├── src/                        # Your source code
│   └── ...
└── CMakeUserPresets.json       # Auto-generated by `sbuild configure` (via Conan)
```

### CMakeLists.txt

Must contain a `project()` directive with a version:

```cmake
project(MyApp VERSION 1.2.3)
```

sbuild parses this to determine the project name and version for packaging.

### Conan profiles

Place Conan 2 profiles in a `profiles/` directory using the naming convention `{os}_{build_type}`:

- `profiles/windows_debug`, `profiles/windows_release`
- `profiles/linux_debug`, `profiles/linux_release`

### .env (native builds)

Optional `KEY=VALUE` file for native build environment variables:

```
VCVARS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat
QT_IFW_ROOT=C:\Qt\Tools\QtInstallerFramework\4.8
```

`VCVARS_PATH` overrides auto-detection of the Visual Studio environment script.

### .env.wasm (WebAssembly builds)

Required for WASM builds. Must define at minimum:

```
EMSDK=C:\path\to\emsdk
QT_WASM_PATH=C:\Qt\6.8.3\wasm_singlethread
QT_HOST_PATH=C:\Qt\6.8.3\msvc2022_64
```

Optional: `OPENSSL` for OpenSSL support in WASM builds.

### CMake presets

`sbuild configure` runs Conan, which generates `CMakeUserPresets.json`. A manually maintained `CMakePresets.json` may also be present. The expected preset names are:

- Native: `conan-debug`, `conan-release`
- WASM: `wasm-debug`, `wasm-release`

### Build output

Build artifacts are written to subdirectories under `build/`:

- `build/Debug`, `build/Release` (native)
- `build/wasm-debug`, `build/wasm-release` (WASM)

Build logs are saved to `build_logs/` with automatic rotation (keeps last 10).

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
