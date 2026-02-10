"""
sbuild - Logging utilities

Provides LogManager for file logging and LoggingConsole for dual output.
"""

import datetime
import platform
import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel


class LogManager:
    """Manages build log files with automatic rotation"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.log_dir = project_root / "build_logs"
        self.log_file = None
        self.log_path = None

    def start_logging(self) -> Path:
        """Initialize log file and cleanup old logs"""
        self.log_dir.mkdir(exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.log_path = self.log_dir / f"{timestamp}_sbuild.log"

        self.log_file = open(self.log_path, "w", encoding="utf-8")

        self._log_header()
        self._cleanup_old_logs()

        return self.log_path

    def _log_header(self):
        """Write log file header with system info"""
        if not self.log_file:
            return

        header = [
            "=" * 80,
            f"sbuild Log - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            f"Platform: {platform.system()} {platform.release()}",
            f"Architecture: {platform.machine()}",
            f"Python: {sys.version.split()[0]}",
            "=" * 80,
            "",
        ]
        self.log_file.write("\n".join(header) + "\n")
        self.log_file.flush()

    def _cleanup_old_logs(self):
        """Keep only the 10 most recent log files"""
        if not self.log_dir.exists():
            return

        log_files = sorted(
            self.log_dir.glob("*_sbuild.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old_log in log_files[10:]:
            try:
                old_log.unlink()
                self.write(f"Deleted old log: {old_log.name}")
            except Exception as e:
                self.write(f"Failed to delete {old_log.name}: {e}")

    def write(self, message: str):
        """Write message to log file"""
        if self.log_file and not self.log_file.closed:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.log_file.write(f"[{timestamp}] {message}\n")
            self.log_file.flush()

    def write_section(self, title: str):
        """Write section separator"""
        separator = "-" * 80
        self.write(f"\n{separator}")
        self.write(title)
        self.write(separator)

    def close(self):
        """Close log file"""
        if self.log_file and not self.log_file.closed:
            self.write("\n" + "=" * 80)
            self.write(
                f"Build log ended - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.write("=" * 80)
            self.log_file.close()


class LoggingConsole:
    """Wrapper around Rich Console that also logs to file"""

    def __init__(self, console: Console, log_manager: Optional[LogManager] = None):
        self.console = console
        self.log_manager = log_manager
        self._original_print = console.print

    def set_log_manager(self, log_manager: LogManager):
        """Attach log manager"""
        self.log_manager = log_manager

    def print(self, *args, **kwargs):
        """Print to console and log file"""
        self._original_print(*args, **kwargs)

        if self.log_manager:
            text_parts = []
            for arg in args:
                if isinstance(arg, (Panel, str)):
                    text = str(arg)
                    plain_text = re.sub(r"\[/?[a-z_]+.*?\]", "", text)
                    if not plain_text.startswith("<"):
                        text_parts.append(plain_text)
                else:
                    text = str(arg)
                    plain_text = re.sub(r"\[/?[a-z_]+.*?\]", "", text)
                    text_parts.append(plain_text)

            if text_parts:
                message = " ".join(text_parts)
                self.log_manager.write(message)

    def __getattr__(self, name):
        """Delegate other methods to original console"""
        return getattr(self.console, name)
