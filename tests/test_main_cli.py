"""Tests for main.py command-line options and crash safety handling."""
from __future__ import annotations

import io
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

from core.version import VERSION
from main import main


def test_main_cli_version(capsys):
    """Test main.py --version prints version and exits with code 0."""
    code = main(["--version"])
    assert code == 0
    captured = capsys.readouterr()
    assert f"MayuriShell {VERSION}" in captured.out


def test_main_cli_selftest(capsys):
    """Test main.py --selftest runs successfully in an isolated temp environment."""
    code = main(["--selftest"])
    assert code == 0
    captured = capsys.readouterr()
    assert "All MayuriShell self-tests PASSED successfully." in captured.out


def test_main_cli_config_dir_invalid(capsys):
    """Test main.py --config-dir refuses dangerous or invalid directories."""
    # 1. Missing argument
    code = main(["--config-dir"])
    assert code == 1
    captured = capsys.readouterr()
    assert "requires a directory path argument" in captured.err

    # 2. Drive root
    drive = "C:\\" if sys.platform == "win32" else "/"
    code = main(["--config-dir", drive])
    assert code == 1
    captured = capsys.readouterr()
    assert "drive root" in captured.err.lower()


def test_main_cli_config_dir_valid(tmp_path: Path):
    """Test main.py --config-dir creates and uses the specified directory."""
    custom_dir = tmp_path / "custom_config_dir"
    assert not custom_dir.exists()

    with patch("main.MayuriShell") as mock_shell_cls:
        mock_instance = MagicMock()
        mock_shell_cls.return_value = mock_instance

        code = main(["--config-dir", str(custom_dir)])
        assert code == 0
        assert custom_dir.exists()
        mock_instance.run.assert_called_once()


def test_main_crash_safety_handling(capsys, tmp_path: Path):
    """Test top-level crash handler catches fatal errors and displays log path."""
    with patch("main.MayuriShell") as mock_shell_cls:
        mock_shell_cls.side_effect = RuntimeError("Simulated startup failure")

        # Mock non-terminal stdin so it does not wait for Enter
        with patch.object(sys.stdin, "isatty", return_value=False):
            code = main(["--config-dir", str(tmp_path / "cfg")])

        assert code == 1
        captured = capsys.readouterr()
        assert "Fatal error encountered:" in captured.err
        assert "Simulated startup failure" in captured.err
        assert "mayurishell.log" in captured.err
