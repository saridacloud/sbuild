"""Tests for sbuild.cli helper functions."""

from sbuild.cli import _get_build_types


def test_default_is_debug():
    assert _get_build_types(all_configs=False, release=False) == ["Debug"]


def test_release_flag():
    assert _get_build_types(all_configs=False, release=True) == ["Release"]


def test_all_configs():
    assert _get_build_types(all_configs=True, release=False) == ["Debug", "Release"]


def test_all_configs_overrides_release():
    assert _get_build_types(all_configs=True, release=True) == ["Debug", "Release"]
