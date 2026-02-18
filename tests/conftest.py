"""Shared fixtures for sbuild tests."""

import pytest
from pathlib import Path


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a minimal project directory with CMakeLists.txt."""
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_text(
        "project(TestProject VERSION 1.2.3 LANGUAGES CXX)\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    """Create a sample .env file."""
    p = tmp_path / ".env"
    p.write_text(
        "# This is a comment\n"
        "\n"
        "FOO=bar\n"
        "BAZ=qux\n"
        "SPACED_KEY = spaced_value \n"
        "EQUAL_VALUE=a=b=c\n"
        "EMPTY_VALUE=\n"
        "NO_EQUALS_LINE\n"
        'DOUBLE_QUOTED="-DFOO=BAR -DBAZ=QUX"\n'
        "SINGLE_QUOTED='some value'\n"
        "MISMATCHED_QUOTES=\"not matched'\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def wasm_env_vars(tmp_path: Path) -> dict[str, str]:
    """Create directories and return WASM env vars dict (unified .env style)."""
    emsdk = tmp_path / "emsdk"
    qt_wasm = tmp_path / "qt_wasm"
    qt_host = tmp_path / "qt_host"
    emsdk.mkdir()
    qt_wasm.mkdir()
    qt_host.mkdir()

    return {
        "EMSDK": str(emsdk),
        "SBUILD_WASM_QT_PATH": str(qt_wasm),
        "SBUILD_WASM_QT_HOST_PATH": str(qt_host),
    }
