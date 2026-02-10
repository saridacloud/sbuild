"""Tests for sbuild.test_reporter.TestReporter.parse_results()."""

from sbuild.test_reporter import TestReporter


def _parse(lines: list[str]) -> dict:
    return TestReporter().parse_results(lines)


class TestParseResultsAllPassed:
    def test_basic(self):
        result = _parse(["100% tests passed, 0 tests failed out of 12"])
        assert result == {"total": 12, "passed": 12, "failed": 0, "failed_names": []}


class TestParseResultsSomeFailed:
    def test_counts_and_names(self):
        lines = [
            "75% tests passed, 1 tests failed out of 4",
            "",
            "The following tests FAILED:",
            "      3 - MyTest.Failure (Failed)",
            "",
        ]
        result = _parse(lines)
        assert result["total"] == 4
        assert result["passed"] == 3
        assert result["failed"] == 1
        assert result["failed_names"] == ["MyTest.Failure"]

    def test_multiple_failures(self):
        lines = [
            "50% tests passed, 2 tests failed out of 4",
            "The following tests FAILED:",
            "      1 - Alpha (Failed)",
            "      3 - Beta (Timeout)",
            "Errors while running CTest",
        ]
        result = _parse(lines)
        assert result["failed"] == 2
        assert result["failed_names"] == ["Alpha", "Beta"]


class TestParseResultsEdgeCases:
    def test_empty_input(self):
        result = _parse([])
        assert result == {"total": 0, "passed": 0, "failed": 0, "failed_names": []}

    def test_no_summary_line(self):
        result = _parse(["Some random CTest output", "Test: 1/5"])
        assert result["total"] == 0

    def test_failed_section_ended_by_blank_line(self):
        lines = [
            "50% tests passed, 1 tests failed out of 2",
            "The following tests FAILED:",
            "      1 - Broken (Failed)",
            "",
            "Some other text",
        ]
        result = _parse(lines)
        assert result["failed_names"] == ["Broken"]

    def test_failed_section_ended_by_errors_line(self):
        lines = [
            "50% tests passed, 1 tests failed out of 2",
            "The following tests FAILED:",
            "      1 - Broken (Failed)",
            "Errors while running CTest output",
        ]
        result = _parse(lines)
        assert result["failed_names"] == ["Broken"]

    def test_realistic_ctest_output(self):
        lines = [
            "Test project /home/user/build",
            "    Start 1: unit_tests",
            "1/3 Test #1: unit_tests ...................   Passed    0.12 sec",
            "    Start 2: integration_tests",
            "2/3 Test #2: integration_tests ............   Passed    1.45 sec",
            "    Start 3: flaky_test",
            "3/3 Test #3: flaky_test ...................***Failed    0.01 sec",
            "",
            "66% tests passed, 1 tests failed out of 3",
            "",
            "The following tests FAILED:",
            "      3 - flaky_test (Failed)",
            "Errors while running CTest output from /home/user/build",
        ]
        result = _parse(lines)
        assert result["total"] == 3
        assert result["passed"] == 2
        assert result["failed"] == 1
        assert result["failed_names"] == ["flaky_test"]
