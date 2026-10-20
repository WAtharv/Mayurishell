"""Tests for diagnostics command and export sanitization."""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import platform
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.builtins import get_real_desktop_path, handle_diagnostics
from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from core.shell import ShellContext


@pytest.fixture
def diag_context(tmp_path: Path):
    """Create test shell context for diagnostics."""
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    config = ConfigManager(base_dir=appdata)
    registry = CommandRegistry()
    history = MagicMock()
    history.get_all.return_value = [{"command": "super_secret_command_123", "timestamp": "2026-10-20"}]
    console = Console(record=True, width=120)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = ShellContext(
        config=config,
        registry=registry,
        history_manager=history,
        console=console,
        current_dir=work_dir,
    )
    return ctx


def test_diagnostics_interactive_output(diag_context: ShellContext):
    """Test interactive diagnostics output contains all required fields."""
    # Write a test log with errors and warnings
    log_file = diag_context.config.logs_dir / "mayurishell.log"
    log_file.write_text(
        "2026-10-20 - INFO - Started shell\n"
        "2026-10-20 - WARNING - Minor issue\n"
        "2026-10-20 - ERROR - Failed operation\n",
        encoding="utf-8",
    )

    handle_diagnostics(diag_context, [])
    out = diag_context.console.export_text()

    assert "MayuriShell Diagnostics" in out
    assert "Shell Version" in out
    assert "Python" in out
    assert "OS Platform" in out
    assert "Terminal" in out
    assert "Config File" in out
    assert "Command History" in out
    assert "Commands & Shortcuts" in out
    assert "Log File" in out
    assert "Log Error Count" in out
    assert "Dependencies" in out
    assert "psutil" in out
    assert "rich" in out
    assert "prompt_toolkit" in out
    assert "send2trash" in out


def test_diagnostics_export_sanitization(diag_context: ShellContext, tmp_path: Path):
    """Requirement 6: Test that diagnostics --export writes a sanitized report to Desktop."""
    desktop_mock = tmp_path / "desktop"
    desktop_mock.mkdir()

    # Create log with some error lines
    log_file = diag_context.config.logs_dir / "mayurishell.log"
    log_file.write_text(
        "2026-10-20 - INFO - Started shell\n"
        "2026-10-20 - ERROR - secret_password_should_not_leak\n"
        "2026-10-20 - WARNING - another_warning\n",
        encoding="utf-8",
    )

    with patch("commands.builtins.get_real_desktop_path", return_value=desktop_mock):
        handle_diagnostics(diag_context, ["--export"])

    out = diag_context.console.export_text()
    assert "Diagnostics report exported to:" in out

    # Check generated report file
    reports = list(desktop_mock.glob("mayurishell_diagnostics_*.txt"))
    assert len(reports) == 1
    report_file = reports[0]
    content = report_file.read_text(encoding="utf-8")

    # 1. Sanitization of username and hostname
    assert "<user>" in content
    assert "<host>" in content
    real_user = getpass.getuser()
    if real_user and len(real_user) > 2 and real_user not in ("<user>", "None"):
        assert real_user not in content

    # 2. No command history or secret commands
    assert "super_secret_command_123" not in content

    # 3. No log message contents or lines
    assert "secret_password_should_not_leak" not in content
    assert "another_warning" not in content

    # 4. Only counts from the log
    assert "Error Count:         1" in content
    assert "Warning Count:       1" in content
    assert "Total Log Lines:     3" in content

    # 5. Home path replaced with ~
    assert "~" in content


def test_diagnostics_export_no_overwrite(diag_context: ShellContext, tmp_path: Path):
    """Test that diagnostics --export never overwrites an existing report."""
    desktop_mock = tmp_path / "desktop"
    desktop_mock.mkdir()

    with patch("commands.builtins.get_real_desktop_path", return_value=desktop_mock), \
         patch("commands.builtins.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20261020_120000"
        mock_dt.datetime.now.return_value = mock_now

        # First export
        handle_diagnostics(diag_context, ["--export"])
        # Second export with identical timestamp
        handle_diagnostics(diag_context, ["--export"])

    reports = sorted(desktop_mock.glob("mayurishell_diagnostics_*.txt"))
    assert len(reports) == 2
    assert reports[0].name != reports[1].name
