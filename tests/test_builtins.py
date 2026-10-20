"""Unit tests for Stage 1 built-in commands."""
from pathlib import Path
from rich.console import Console

from commands.builtins import register_builtin_commands
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell, ShellContext


def create_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to create an isolated shell instance with console recording."""
    config = ConfigManager(base_dir=tmp_path)
    history = HistoryManager(tmp_path / "history.json")
    registry = CommandRegistry()
    register_builtin_commands(registry)
    console = Console(record=True, color_system=None)

    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        console=console,
    )
    return shell, console


def test_builtin_help_all(tmp_path: Path) -> None:
    """Test 'help' lists all commands."""
    shell, console = create_test_shell(tmp_path)
    res = shell.run_command_line("help")
    assert res is True
    output = console.export_text()
    assert "Available Commands" in output
    assert "help" in output
    assert "version" in output
    assert "exit" in output
    assert "history" in output
    assert "clear" in output


def test_builtin_help_specific_command(tmp_path: Path) -> None:
    """Test 'help <cmd>' displays details for a command."""
    shell, console = create_test_shell(tmp_path)
    res = shell.run_command_line("help version")
    assert res is True
    output = console.export_text()
    assert "Command Info: version" in output
    assert "version" in output


def test_builtin_help_unknown_command(tmp_path: Path) -> None:
    """Test 'help <unknown>' suggests close matches."""
    shell, console = create_test_shell(tmp_path)
    res = shell.run_command_line("help versio")
    assert res is True
    output = console.export_text()
    assert "Command not found: 'versio'" in output
    assert "version" in output


def test_builtin_version(tmp_path: Path) -> None:
    """Test 'version' command output."""
    shell, console = create_test_shell(tmp_path)
    res = shell.run_command_line("version")
    assert res is True
    output = console.export_text()
    assert "MayuriShell version 0.1.0" in output
    assert "Python:" in output


def test_builtin_history(tmp_path: Path) -> None:
    """Test 'history' and 'history clear' commands."""
    shell, console = create_test_shell(tmp_path)
    shell.run_command_line("version")
    shell.run_command_line("help")
    
    # Run history command
    shell.run_command_line("history")
    output = console.export_text()
    assert "Command History" in output
    assert "version" in output

    # Run history clear
    shell.run_command_line("history clear")
    assert len(shell.context.history_manager.get_commands()) == 0


def test_builtin_exit(tmp_path: Path) -> None:
    """Test 'exit' command sets running flag to False."""
    shell, console = create_test_shell(tmp_path)
    assert shell.context.running is True
    shell.run_command_line("exit")
    assert shell.context.running is False
    output = console.export_text()
    assert "Goodbye, Mayuri!" in output


def test_builtin_clear(tmp_path: Path) -> None:
    """Test 'clear' command executes without errors."""
    shell, console = create_test_shell(tmp_path)
    res = shell.run_command_line("clear")
    assert res is True
