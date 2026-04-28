---
name: build-test-sbuild
description: Use whenever the user asks to build, compile, test, clean, package, or diagnose build failures in a C++ project — sbuild is the build tool for these projects and all build/test requests should go through it. Also activate when you see sbuild commands, SBUILD_ environment variables in .env files, build_logs/ directories, Conan profiles, or CMake preset files. Use this skill even for simple requests like "build this" or "run the tests" — if the project has sbuild installed (check with `which sbuild`), use this skill. Do NOT activate for projects that use cmake/conan/make directly without sbuild, or for non-C++ projects.
---

# sbuild

sbuild is a unified build system CLI wrapping Conan 2 + CMake behind a single command. It is installed as a pip package in the project's Python venv.

## Commands — when to use which

| Command | What it does | When to use |
|---------|-------------|-------------|
| `sbuild build` | Incremental compile | Source-only changes (`.cpp`, `.h`) |
| `sbuild build --clean` | Wipe artifacts, then compile (no reconfigure) | Stale object files, linker errors from removed sources |
| `sbuild rebuild` | Full pipeline: conan install + cmake configure + build | CMake changes (`CMakeLists.txt`, `*.cmake`), Conan changes (`conanfile.py`, `profiles/`), `.env` changes, preset changes, or when `build` fails with stale cache |
| `sbuild configure` | Conan install + cmake configure only, no build | Verifying config changes take effect before building |
| `sbuild clean` | Delete build directory entirely | Last resort — prefer `rebuild` |
| `sbuild test` | Run CTest suite | After a successful build |
| `sbuild install` | Install built artifacts | Deploying locally |
| `sbuild package` | Create CPack distribution (ZIP, NSIS, IFW) | Creating distributable packages |
| `sbuild serve` | Local HTTP/HTTPS dev server | WASM testing in browser |
| `sbuild config` | Show resolved configuration without building | Inspecting what sbuild will do before running it |
| `sbuild doctor` | Check environment health | First thing to run when tools are missing or environment seems broken |

### Key flags

| Flag | Short | Purpose |
|------|-------|---------|
| `--release` | `-r` | Release build type (default is Debug) |
| `--verbose` | `-v` | Full command output instead of live summary panel |
| `--jobs N` | `-j N` | Parallel build jobs (default: CPU count) |
| `--arch` | | Target architecture (`x86`, `x64`, `arm64`) |
| `--profile` | | Explicit Conan profile name (overrides arch-based lookup) |
| `--cmake-args` | | Extra CMake arguments |
| `--clean` | `-c` | Clean before building (`build` command only) |
| `--filter` | `-R` | Test name regex filter (`test` command only) |
| `--rerun-failed` | | Re-run only failed tests (`test` command only) |
| `--test-verbose` | | Verbose CTest output (`test` command only) |

## Workflow rules

These rules prevent wasteful rebuilds and missed diagnostics.

### Read the log before rebuilding

When a build or test fails, **always read the latest log file first** before re-running anything. The logs contain full compiler output, CMake configuration details, and Conan resolution — often the answer is already there.

```bash
ls -t build_logs/    # find the latest log
```

Log files live in `build_logs/`, are timestamped (`YYYYMMDDHHmmss_sbuild.log`), and auto-rotated (keeps last 10). Each log includes a diagnostic header with:
- Platform and architecture info
- Python version
- The exact command that was invoked
- Fully resolved configuration (project name, paths, presets, tool versions)

### Pick the right rebuild level

Escalate only as far as needed — don't `clean` when `rebuild` suffices, don't `rebuild` when `build` suffices:

1. **Source-only change** (`.cpp`, `.h` files) -> `sbuild build`
2. **CMake or Conan change** (`CMakeLists.txt`, `conanfile.py`, profiles, `.env`) -> `sbuild rebuild`
3. **Stale build that `build` can't fix** (linker errors from removed files) -> `sbuild build --clean`
4. **Corrupt build directory or switching branches with incompatible build trees** -> `sbuild clean` then `sbuild build`

### Use doctor for environment problems

When you see errors about missing tools (cmake, conan, ninja), wrong versions, or environment setup failures, run `sbuild doctor` before guessing. It checks:
- Core tools: Python 3.12+, CMake, Conan 2, Git, Ninja
- Native toolchain: compiler detection, vcvarsall (Windows), architecture
- WASM toolchain: EMSDK, emscripten, Qt paths
- Project config: CMakeLists.txt, CMake presets, Conan profiles
- Packaging tools: CPack, Qt IFW, NSIS

### Use config to inspect before acting

Run `sbuild config` to see the fully resolved configuration (all settings, paths, presets) without building. This is faster and safer than guessing what values sbuild will use.

## Configuration and .env

sbuild reads configuration from multiple sources with this priority (highest wins):

1. **CLI arguments** (`--release`, `--arch x64`, etc.)
2. **`.env` file** in the project root (loaded automatically, no shell activation needed)
3. **System environment variables**
4. **Defaults**

### SBUILD_ environment variables

All sbuild-specific variables use the `SBUILD_` prefix. Set them in the project's `.env` file.

**General (both platforms):**

| Variable | Purpose |
|----------|---------|
| `SBUILD_PLATFORM` | Build platform: `native` (default) or `wasm` |
| `SBUILD_ARCH` | Target architecture: `x86`, `x64`, `arm64`, `arm` |
| `SBUILD_VERBOSE` | Default verbosity: `true` / `false` |
| `SBUILD_PARALLEL_JOBS` | Number of parallel build jobs |
| `SBUILD_BUILD_DIR` | Base build directory name (default: `build`) |
| `SBUILD_INSTALL_DIR` | Installation prefix path |
| `SBUILD_CMAKE_ARGS` | Extra CMake arguments appended to all builds |

**Windows native:**

| Variable | Purpose |
|----------|---------|
| `SBUILD_VCVARS_ARCH` | MSVC toolchain architecture override |
| `SBUILD_VCVARS_PATH` | Explicit path to `vcvarsall.bat` (skips auto-detection) |

**WASM:**

| Variable | Purpose |
|----------|---------|
| `SBUILD_WASM_CMAKE_ARGS` | WASM-specific CMake arguments (added on top of `SBUILD_CMAKE_ARGS`) |
| `SBUILD_WASM_QT_PATH` | Path to Qt WASM SDK |
| `SBUILD_WASM_QT_HOST_PATH` | Path to Qt host tools |
| `SBUILD_WASM_OPENSSL_ROOT_DIR` | OpenSSL installation for WASM |

**Packaging:**

| Variable | Purpose |
|----------|---------|
| `SBUILD_QT_IFW_ROOT` | Qt Installer Framework root directory |

### How WASM env vars map to CMake

WASM variables are translated to `-D` flags automatically:
- `SBUILD_WASM_QT_PATH` -> `-DQT_DIR=...`
- `SBUILD_WASM_QT_HOST_PATH` -> `-DQT_HOST_PATH=...`
- `SBUILD_WASM_OPENSSL_ROOT_DIR` -> `-DOPENSSL_ROOT_DIR=...`

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `sbuild: command not found` | Check if the Python venv is activated |
| Missing tools or bad environment | Run `sbuild doctor` |
| Build fails after `.env` change | Use `sbuild rebuild` (new env vars need cmake reconfigure) |
| CMake preset errors | Run `sbuild config` to see which preset sbuild expects; check `CMakeUserPresets.json` |
| Conan profile not found | Check `profiles/` directory; sbuild looks for `{os}_{arch}_{build_type}` pattern |
| Windows toolchain failures | Check `SBUILD_VCVARS_PATH` in `.env`; delete `.sbuild/` to clear stale vcvars cache |
| Tests not found after clean | Run `sbuild configure` to regenerate CMake build files |
| WASM build fails with missing paths | Check all `SBUILD_WASM_*` variables in `.env`; `EMSDK` must also be set |
| Unexpected config values | Run `sbuild config` to see resolved values and which source they came from |
