"""Integration tests for process management commands: processes, process find/info/kill."""
from pathlib import Path
from unittest.mock import MagicMock, patch
from rich.console import Console

from commands.processes import register_process_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell


def create_process_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to initialize shell with process commands."""
    config = ConfigManager(base_dir=tmp_path / "appdata")
    history = HistoryManager(tmp_path / "appdata" / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_process_commands(registry)

    console = Console(record=True, color_system=None, width=120)
    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        console=console,
        current_dir=tmp_path,
    )
    return shell, console


def test_command_processes_listing(tmp_path: Path) -> None:
    """Test processes command listing top processes with Working Set header."""
    shell, console = create_process_test_shell(tmp_path)

    mock_list = [
        {"pid": 1234, "name": "code.exe", "cpu_percent": 12.0, "memory_formatted": "250.0 MB", "username": "Mayuri"},
        {"pid": 5678, "name": "spotify.exe", "cpu_percent": 2.5, "memory_formatted": "120.0 MB", "username": "Mayuri"},
    ]

    with patch("commands.processes.list_processes", return_value=mock_list) as mock_call:
        shell.run_command_line("processes --sort cpu --limit 10")
        mock_call.assert_called_once_with(sort_by="cpu", limit=10)
        output = console.export_text()
        assert "Running Processes" in output
        assert "Memory (Working Set)" in output
        assert "code.exe" in output
        assert "spotify.exe" in output


def test_command_process_no_args_shows_usage(tmp_path: Path) -> None:
    """Test 'process' without arguments displays usage guide."""
    shell, console = create_process_test_shell(tmp_path)

    shell.run_command_line("process")
    output = console.export_text()
    assert "MayuriShell Process Management" in output
    assert "Usage:" in output
    assert "process find <name>" in output
    assert "process info <pid>" in output
    assert "process kill <pid>" in output


def test_command_process_find(tmp_path: Path) -> None:
    """Test process find displays matching processes."""
    shell, console = create_process_test_shell(tmp_path)

    mock_matches = [
        {"pid": 3333, "name": "discord.exe", "memory_formatted": "320.0 MB", "username": "Mayuri"},
    ]

    with patch("commands.processes.find_processes", return_value=mock_matches):
        shell.run_command_line("process find discord")
        output = console.export_text()
        assert "Processes Matching 'discord'" in output
        assert "discord.exe" in output
        assert "3333" in output


def test_command_process_info(tmp_path: Path) -> None:
    """Test process info displays detailed metadata card without cmdline."""
    shell, console = create_process_test_shell(tmp_path)

    mock_detail = {
        "pid": 4444,
        "name": "target_app.exe",
        "status": "running",
        "user": "Mayuri",
        "exe": "C:\\Program Files\\App\\target_app.exe",
        "threads": 8,
        "cpu_percent": 3.2,
        "memory_rss_formatted": "150.0 MB",
        "memory_vms_formatted": "300.0 MB",
        "start_time": "2026-10-20 10:00:00",
        "ppid": 1000,
    }

    with patch("commands.processes.get_process_detail", return_value=mock_detail):
        shell.run_command_line("process info 4444")
        output = console.export_text()
        assert "Process Details: target_app.exe" in output
        assert "PID:" in output
        assert "4444" in output
        assert "Executable Path:" in output
        assert "C:\\Program Files\\App\\target_app.exe" in output
        assert "cmdline" not in output
        assert "environ" not in output


def test_command_process_kill_invalid_pid_rejected(tmp_path: Path) -> None:
    """Test process kill rejects non-numeric PIDs, negative numbers, and wildcards."""
    shell, console = create_process_test_shell(tmp_path)

    # Name instead of PID
    shell.run_command_line("process kill chrome")
    output = console.export_text()
    assert "PID must be a positive number, not a name or text" in output

    # Wildcards
    shell.run_command_line("process kill *")
    output = console.export_text()
    assert "Wildcards are not allowed in PID" in output

    # Negative number
    shell.run_command_line("process kill -5")
    output = console.export_text()
    assert "PID must be a positive integer" in output


def test_command_process_kill_refuses_protected_processes(tmp_path: Path) -> None:
    """Test process kill refuses killing protected processes (e.g. System, shell)."""
    shell, console = create_process_test_shell(tmp_path)

    with patch("commands.processes.is_protected_process", return_value=(True, "Refusing to kill MayuriShell itself.")):
        shell.run_command_line("process kill 1234")
        output = console.export_text()
        assert "Action Refused" in output
        assert "Refusing to kill MayuriShell itself" in output


def test_command_process_kill_confirmation_cancelled(tmp_path: Path) -> None:
    """Test process kill prompts user and aborts when cancelled (default No)."""
    shell, console = create_process_test_shell(tmp_path)

    mock_detail = {"name": "notepad.exe", "create_time": 1700000000.0}
    with patch("commands.processes.is_protected_process", return_value=(False, "")), \
         patch("commands.processes.get_process_detail", return_value=mock_detail), \
         patch("commands.processes.confirm_prompt", return_value=False), \
         patch("commands.processes.kill_process_guarded") as mock_kill:
        shell.run_command_line("process kill 5555")
        mock_kill.assert_not_called()
        output = console.export_text()
        assert "Process termination cancelled by user" in output


def test_command_process_kill_confirmed_and_force(tmp_path: Path) -> None:
    """Test process kill proceeds when confirmed and reports force kill in prompt."""
    shell, console = create_process_test_shell(tmp_path)

    mock_detail = {"name": "app.exe", "create_time": 1700000000.0}
    with patch("commands.processes.is_protected_process", return_value=(False, "")), \
         patch("commands.processes.get_process_detail", return_value=mock_detail), \
         patch("commands.processes.confirm_prompt", return_value=True) as mock_prompt, \
         patch("commands.processes.kill_process_guarded", return_value=(True, "Forcefully killed process 'app.exe' (PID 6666).")) as mock_kill:
        shell.run_command_line("process kill 6666 --force")
        # Ensure prompt specifies force kill
        prompt_arg = mock_prompt.call_args[0][1]
        assert "FORCE KILL" in prompt_arg
        mock_kill.assert_called_once_with(6666, force=True, expected_name="app.exe", expected_create_time=1700000000.0)
        output = console.export_text()
        assert "Success:" in output
        assert "Forcefully killed" in output
