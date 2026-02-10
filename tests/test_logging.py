"""Tests for sbuild.logging — _strip_rich_markup and LogManager."""

from pathlib import Path

from sbuild.logging import LogManager, _strip_rich_markup


# -- _strip_rich_markup -------------------------------------------------------

class TestStripRichMarkup:
    def test_simple_tag(self):
        assert _strip_rich_markup("[green]OK[/green]") == "OK"

    def test_nested_tags(self):
        assert _strip_rich_markup("[bold][red]err[/red][/bold]") == "err"

    def test_no_markup(self):
        assert _strip_rich_markup("plain text") == "plain text"

    def test_empty_string(self):
        assert _strip_rich_markup("") == ""

    def test_tag_with_attributes(self):
        assert _strip_rich_markup("[red on white]text[/red on white]") == "text"

    def test_self_closing_tag(self):
        # Rich uses [/] as a "close all" tag
        result = _strip_rich_markup("[green]ok[/]")
        assert "ok" in result


# -- LogManager ---------------------------------------------------------------

class TestLogManagerStartLogging:
    def test_creates_directory_and_file(self, tmp_path):
        lm = LogManager(tmp_path)
        log_path = lm.start_logging()
        assert log_path.exists()
        assert (tmp_path / "build_logs").is_dir()
        lm.close()

    def test_log_file_contains_header(self, tmp_path):
        lm = LogManager(tmp_path)
        lm.start_logging()
        lm.close()
        content = lm.log_path.read_text(encoding="utf-8")
        assert "sbuild Log" in content


class TestLogManagerWrite:
    def test_writes_timestamped_line(self, tmp_path):
        lm = LogManager(tmp_path)
        lm.start_logging()
        lm.write("hello world")
        lm.close()
        content = lm.log_path.read_text(encoding="utf-8")
        assert "hello world" in content
        # Timestamp format: [HH:MM:SS.mmm]
        assert "] hello world" in content


class TestLogManagerWriteSection:
    def test_adds_separator(self, tmp_path):
        lm = LogManager(tmp_path)
        lm.start_logging()
        lm.write_section("Build Step")
        lm.close()
        content = lm.log_path.read_text(encoding="utf-8")
        assert "Build Step" in content
        assert "---" in content


class TestLogManagerClose:
    def test_writes_footer(self, tmp_path):
        lm = LogManager(tmp_path)
        lm.start_logging()
        lm.close()
        content = lm.log_path.read_text(encoding="utf-8")
        assert "Build log ended" in content

    def test_double_close_is_safe(self, tmp_path):
        lm = LogManager(tmp_path)
        lm.start_logging()
        lm.close()
        lm.close()  # should not raise


class TestLogManagerCleanup:
    def test_keeps_only_10_logs(self, tmp_path):
        log_dir = tmp_path / "build_logs"
        log_dir.mkdir()

        # Pre-create 12 log files with different timestamps
        for i in range(12):
            f = log_dir / f"2024010100000{i:02d}_sbuild.log"
            f.write_text(f"log {i}", encoding="utf-8")

        lm = LogManager(tmp_path)
        lm.start_logging()
        lm.close()

        remaining = list(log_dir.glob("*_sbuild.log"))
        # 12 old + 1 new = 13, cleanup should keep 10
        assert len(remaining) <= 10
