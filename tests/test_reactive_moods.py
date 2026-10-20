"""Tests for reactive mascot mood transitions, failure reporting, cancellation handling,
history status tracking, and privacy logging.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.appearance import register_appearance_commands
from commands.applications import register_application_commands
from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from commands.files import register_file_commands
from commands.navigation import register_navigation_commands
from commands.organization import register_organization_commands
from commands.processes import register_process_commands
from commands.project_scaffolding import register_project_commands
from commands.search import register_search_commands
from commands.system import register_system_commands
from commands.websites import register_website_commands
from commands.workflows import register_workflow_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell
from core.theme import ThemeManager


def create_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Initialize a fully wired test shell with isolated config and history."""
    cfg = ConfigManager(base_dir=tmp_path / "cfg")
    hist = HistoryManager(tmp_path / "hist.json")
    aliases = AliasManager(cfg)
    reg = CommandRegistry()

    register_builtin_commands(reg)
    register_appearance_commands(reg)
    register_application_commands(reg, cfg)
    register_website_commands(reg, cfg)
    register_navigation_commands(reg, cfg)
    register_customization_commands(reg, cfg)
    register_file_commands(reg)
    register_search_commands(reg)
    register_system_commands(reg)
    register_process_commands(reg)
    register_organization_commands(reg, cfg)
    register_project_commands(reg, cfg)
    register_workflow_commands(reg, cfg)

    console = Console(record=True, force_terminal=True, width=120)
    theme_mgr = ThemeManager(cfg, console=console)
    shell = MayuriShell(
        config=cfg,
        registry=reg,
        history_manager=hist,
        alias_manager=aliases,
        console=console,
        theme_manager=theme_mgr,
    )
    shell.context.current_dir = tmp_path
    return shell, console


class TestRefusalsAndErrorsSetWorriedMood:
    """Test that all command refusals and errors set mascot mood to 'worried'."""

    def test_flag_argument_refusal(self, tmp_path: Path) -> None:
        """App shortcuts refuse flag arguments like --install-extension and set mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        with patch("commands.applications.find_executable", return_value=r"C:\Program Files\Microsoft VS Code\Code.exe"):
            res = shell.run_command_line("code --install-extension ms-python.python")
            assert res is False
            assert shell.executor.last_mood == "worried"
            assert shell.context.last_mood == "worried"
            assert shell.context.history_manager.entries[-1]["success"] is False

    def test_uri_app_with_arguments_refusal(self, tmp_path: Path) -> None:
        """Protocol apps refuse arguments and set mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("spotify song_name")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_website_without_query_template_refusal(self, tmp_path: Path) -> None:
        """Website shortcuts without {query} template refuse extra words and set mood to worried."""
        shell, _ = create_test_shell(tmp_path)
        shell.run_command_line("add-website chatgpt https://chatgpt.com")

        res = shell.run_command_line("chatgpt hello world")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_wildcard_delete_refusal(self, tmp_path: Path) -> None:
        """delete * is refused for safety and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("delete *")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_protected_process_kill_refusal(self, tmp_path: Path) -> None:
        """Killing critical system processes (e.g. PID 4 System) is refused and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("process kill 4")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_workflow_add_blocked_action_refusal(self, tmp_path: Path) -> None:
        """Adding a workflow step with a dangerous/blocked action is refused and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("workflow add bad 'delete foo'")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_bad_alias_loop_refusal(self, tmp_path: Path) -> None:
        """Defining an alias that collides with existing commands or loops is refused and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("alias cd pwd")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_unknown_command_refusal(self, tmp_path: Path) -> None:
        """Typing a non-existent command reports unknown command and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("nonexistent_shell_cmd_xyz")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_missing_folder_navigation(self, tmp_path: Path) -> None:
        """Navigating to a non-existent directory reports error and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("cd Nonexistent_Folder_12345")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_missing_file_open(self, tmp_path: Path) -> None:
        """Opening a non-existent file reports error and sets mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line("open nonexistent_file.txt")
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False

    def test_syntax_parse_error(self, tmp_path: Path) -> None:
        """Unclosed quotes or syntax errors set mood to worried."""
        shell, _ = create_test_shell(tmp_path)

        res = shell.run_command_line('echo "unclosed quote')
        assert res is False
        assert shell.executor.last_mood == "worried"
        assert shell.context.last_mood == "worried"
        assert shell.context.history_manager.entries[-1]["success"] is False


class TestNormalCommandsSetHappyMood:
    """Test that normal successful commands set mascot mood to 'happy'."""

    def test_normal_pwd_happy(self, tmp_path: Path) -> None:
        shell, _ = create_test_shell(tmp_path)
        res = shell.run_command_line("pwd")
        assert res is True
        assert shell.executor.last_mood == "happy"
        assert shell.context.last_mood == "happy"
        assert shell.context.history_manager.entries[-1]["success"] is True

    def test_normal_ls_happy(self, tmp_path: Path) -> None:
        shell, _ = create_test_shell(tmp_path)
        res = shell.run_command_line("ls")
        assert res is True
        assert shell.executor.last_mood == "happy"
        assert shell.context.last_mood == "happy"
        assert shell.context.history_manager.entries[-1]["success"] is True

    def test_normal_sysinfo_happy(self, tmp_path: Path) -> None:
        shell, _ = create_test_shell(tmp_path)
        res = shell.run_command_line("sysinfo")
        assert res is True
        assert shell.executor.last_mood == "happy"
        assert shell.context.last_mood == "happy"
        assert shell.context.history_manager.entries[-1]["success"] is True

    def test_normal_apps_happy(self, tmp_path: Path) -> None:
        shell, _ = create_test_shell(tmp_path)
        res = shell.run_command_line("apps")
        assert res is True
        assert shell.executor.last_mood == "happy"
        assert shell.context.last_mood == "happy"
        assert shell.context.history_manager.entries[-1]["success"] is True

    def test_normal_help_happy(self, tmp_path: Path) -> None:
        shell, _ = create_test_shell(tmp_path)
        res = shell.run_command_line("help")
        assert res is True
        assert shell.executor.last_mood == "happy"
        assert shell.context.last_mood == "happy"
        assert shell.context.history_manager.entries[-1]["success"] is True

    def test_normal_app_launch_with_argument_happy(self, tmp_path: Path) -> None:
        """Launching app with valid resolved path argument sets mood to happy."""
        shell, _ = create_test_shell(tmp_path)
        target_dir = tmp_path / "my_project"
        target_dir.mkdir()

        with patch("commands.applications.find_executable", return_value=r"C:\Program Files\Microsoft VS Code\Code.exe"), \
             patch("commands.applications.launch_detached", return_value=True) as mock_launch:
            res = shell.run_command_line("code my_project")
            assert res is True
            assert mock_launch.called
            assert shell.executor.last_mood == "happy"
            assert shell.context.history_manager.entries[-1]["success"] is True

    def test_normal_website_launch_with_query_happy(self, tmp_path: Path) -> None:
        """Launching website with query template sets mood to happy."""
        shell, _ = create_test_shell(tmp_path)

        with patch("commands.websites.launch_website", return_value=(True, "Opened")) as mock_launch:
            res = shell.run_command_line("google python decorators")
            assert res is True
            assert mock_launch.called
            assert shell.executor.last_mood == "happy"
            assert shell.context.history_manager.entries[-1]["success"] is True


class TestConfirmationCancellationSetsNeutralMood:
    """Test that answering 'N' to confirmation prompts sets mood to 'neutral' (not worried or happy)."""

    def test_delete_confirmation_cancelled_neutral(self, tmp_path: Path) -> None:
        """Declining delete confirmation sets mood to neutral."""
        shell, _ = create_test_shell(tmp_path)
        test_file = tmp_path / "item_to_delete.txt"
        test_file.write_text("content", encoding="utf-8")

        with patch("commands.files.confirm_prompt", return_value=False):
            res = shell.run_command_line("delete item_to_delete.txt")
            assert res is True  # Cancellation returns clean CommandResult.cancel(ok=True)
            assert shell.executor.last_mood == "neutral"
            assert shell.context.last_mood == "neutral"
            assert test_file.exists()
            assert shell.context.history_manager.entries[-1]["success"] is True

    def test_process_kill_confirmation_cancelled_neutral(self, tmp_path: Path) -> None:
        """Declining process kill confirmation sets mood to neutral."""
        shell, _ = create_test_shell(tmp_path)

        with patch("commands.processes.is_protected_process", return_value=(False, "")), \
             patch("commands.processes.get_process_detail", return_value={"name": "notepad.exe", "create_time": 100.0}), \
             patch("commands.processes.confirm_prompt", return_value=False):
            res = shell.run_command_line("process kill 9999")
            assert res is True
            assert shell.executor.last_mood == "neutral"
            assert shell.context.last_mood == "neutral"

    def test_organize_confirmation_cancelled_neutral(self, tmp_path: Path) -> None:
        """Declining organize execution sets mood to neutral."""
        shell, _ = create_test_shell(tmp_path)
        folder = tmp_path / "docs"
        folder.mkdir()
        doc_file = folder / "file.pdf"
        doc_file.write_text("doc", encoding="utf-8")

        # Set file time in past (> 2 minutes ago)
        old_time = time.time() - 300
        os.utime(str(doc_file), (old_time, old_time))

        with patch("commands.organization.confirm_prompt", return_value=False):
            res = shell.run_command_line(f"organize {folder}")
            assert res is True
            assert shell.executor.last_mood == "neutral"
            assert shell.context.last_mood == "neutral"


class TestPrivacyLoggingOnFailure:
    """Test that failed/refused commands are logged at WARNING without arguments or paths."""

    def test_warning_level_and_no_arguments_logged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        shell, _ = create_test_shell(tmp_path)

        with patch("commands.applications.find_executable", return_value=r"C:\Program Files\Microsoft VS Code\Code.exe"):
            with caplog.at_level(logging.WARNING, logger="mayurishell"):
                caplog.clear()
                shell.run_command_line("code --install-extension ms-python.python")

                # Check that a WARNING was logged
                warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
                assert len(warning_records) >= 1
                msg = warning_records[0].getMessage()
                assert "Command failed or refused: code" in msg
                # Ensure arguments and flags were NOT logged for privacy
                assert "--install-extension" not in msg
                assert "ms-python.python" not in msg

    def test_navigation_failure_logs_name_only(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        shell, _ = create_test_shell(tmp_path)
        secret_folder_name = "SuperSecretFolderXYZ"

        with caplog.at_level(logging.WARNING, logger="mayurishell"):
            caplog.clear()
            shell.run_command_line(f"cd {secret_folder_name}")

            warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warning_records) >= 1
            msg = warning_records[0].getMessage()
            assert "Command failed or refused: cd" in msg
            # Ensure folder path was NOT logged
            assert secret_folder_name not in msg


class TestReactiveMascotFaceRendering:
    """Test that the reactive mascot face rendered to console reflects the mood."""

    def test_worried_face_rendered_on_refusal(self, tmp_path: Path) -> None:
        shell, console = create_test_shell(tmp_path)
        shell.context.config.set_mascot_name("cat")

        from core.mascots import get_reactive_face
        expected_face = get_reactive_face("cat", "worried", is_plain=shell.context.theme.is_plain)

        with patch("sys.stdout.isatty", return_value=True):
            console.clear()
            shell.run_command_line("delete *")
            output = console.export_text()
            assert expected_face in output

    def test_happy_face_rendered_on_success(self, tmp_path: Path) -> None:
        shell, console = create_test_shell(tmp_path)
        shell.context.config.set_mascot_name("cat")

        from core.mascots import get_reactive_face
        expected_face = get_reactive_face("cat", "happy", is_plain=shell.context.theme.is_plain)

        with patch("sys.stdout.isatty", return_value=True):
            console.clear()
            shell.run_command_line("pwd")
            output = console.export_text()
            assert expected_face in output

    def test_neutral_face_rendered_on_cancellation(self, tmp_path: Path) -> None:
        shell, console = create_test_shell(tmp_path)
        shell.context.config.set_mascot_name("cat")
        target_file = tmp_path / "cancel_me.txt"
        target_file.write_text("data", encoding="utf-8")

        from core.mascots import get_reactive_face
        expected_face = get_reactive_face("cat", "neutral", is_plain=shell.context.theme.is_plain)

        with patch("sys.stdout.isatty", return_value=True), \
             patch("commands.files.confirm_prompt", return_value=False):
            console.clear()
            shell.run_command_line(f"delete {target_file.name}")
            output = console.export_text()
            assert expected_face in output

