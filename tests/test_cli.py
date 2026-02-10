"""Tests for sbuild.cli helper functions."""

from sbuild.cli import _get_build_types


def test_default_is_debug():
    assert _get_build_types(all_configs=False, release=False) == ["debug"]


def test_release_flag():
    assert _get_build_types(all_configs=False, release=True) == ["release"]


def test_all_configs():
    assert _get_build_types(all_configs=True, release=False) == ["debug", "release"]


def test_all_configs_overrides_release():
    assert _get_build_types(all_configs=True, release=True) == ["debug", "release"]
