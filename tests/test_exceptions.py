"""Tests for sbuild.exceptions hierarchy."""

from sbuild.exceptions import BuildError, ConfigError, EnvironmentSetupError


def test_build_error_is_exception():
    assert issubclass(BuildError, Exception)


def test_config_error_is_build_error():
    assert issubclass(ConfigError, BuildError)


def test_environment_setup_error_is_build_error():
    assert issubclass(EnvironmentSetupError, BuildError)


def test_exceptions_carry_message():
    msg = "something went wrong"
    for cls in (BuildError, ConfigError, EnvironmentSetupError):
        err = cls(msg)
        assert str(err) == msg
