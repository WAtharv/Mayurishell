"""Integration tests for file manipulation commands: open, mkdir, touch, copy, move, rename, delete, info."""
from pathlib import Path
from unittest.mock import patch
from rich.console import Console

from commands.files import register_file_commands
from commands.navigation import register_navigation_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell


def create_files_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to initialize shell with files and navigation commands."""
    config = ConfigManager(base_dir=tmp_path / "appdata")
    history = HistoryManager(tmp_path / "appdata" / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_navigation_commands(registry, config)
    register_file_commands(registry)

    console = Console(record=True, color_system=None, width=140)
    work_dir = tmp_path / "workspace"
    work_dir.mkdir(parents=True)

    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        console=console,
        current_dir=work_dir,
    )
    return shell, console


def test_command_touch_and_mkdir(tmp_path: Path) -> None:
    """Test touch and mkdir creating files and folders."""
    shell, console = create_files_test_shell(tmp_path)

    shell.run_command_line("touch test.txt")
    assert (shell.context.current_dir / "test.txt").is_file()

    shell.run_command_line("mkdir my_folder")
    assert (shell.context.current_dir / "my_folder").is_dir()


def test_command_open_security_warning(tmp_path: Path) -> None:
    """Test open warns and asks confirmation for script/executable files."""
    shell, console = create_files_test_shell(tmp_path)
    script = shell.context.current_dir / "danger.bat"
    script.write_text("echo hi")

    # When user cancels (or default No)
    with patch("commands.files.confirm_prompt", return_value=False):
        shell.run_command_line("open danger.bat")
        output = console.export_text()
        assert "Security Warning" in output
        assert "Execution cancelled by user" in output


def test_command_copy_and_move_with_overwrite(tmp_path: Path) -> None:
    """Test copy and move commands with overwrite flag."""
    shell, console = create_files_test_shell(tmp_path)
    src = shell.context.current_dir / "src.txt"
    dst = shell.context.current_dir / "dst.txt"
    src.write_text("source content")
    dst.write_text("existing content")

    # Copy with -y
    shell.run_command_line("copy -y src.txt dst.txt")
    assert dst.read_text() == "source content"

    # Move with -y
    src2 = shell.context.current_dir / "src2.txt"
    src2.write_text("src 2")
    shell.run_command_line("move -y src2.txt dst.txt")
    assert dst.read_text() == "src 2"
    assert not src2.exists()


def test_command_rename_plain_name(tmp_path: Path) -> None:
    """Test rename enforces plain names without path separators."""
    shell, console = create_files_test_shell(tmp_path)
    item = shell.context.current_dir / "file.txt"
    item.write_text("text")

    shell.run_command_line("rename file.txt other/file.txt")
    output = console.export_text()
    assert "New name must be a plain filename with no path separators" in output

    shell.run_command_line("rename file.txt new_file.txt")
    assert (shell.context.current_dir / "new_file.txt").exists()


def test_command_delete_protected_and_wildcards(tmp_path: Path) -> None:
    """Test delete rejects protected paths, wildcards, and directories without -r."""
    shell, console = create_files_test_shell(tmp_path)

    # Wildcards rejected
    shell.run_command_line("delete *.txt")
    output = console.export_text()
    assert "Wildcards are not allowed in delete" in output

    # Current working directory is protected
    shell.run_command_line("delete .")
    output = console.export_text()
    assert "Deletion refused" in output

    # Directory without -r is rejected
    sub = shell.context.current_dir / "sub_folder"
    sub.mkdir()
    shell.run_command_line("delete sub_folder")
    output = console.export_text()
    assert "is a directory. Use delete -r" in output


def test_command_delete_success_with_send2trash(tmp_path: Path) -> None:
    """Test delete calls send2trash when confirmed."""
    shell, console = create_files_test_shell(tmp_path)
    target = shell.context.current_dir / "to_delete.txt"
    target.write_text("bye")

    with patch("services.file_service.send2trash.send2trash") as mock_trash:
        shell.run_command_line("delete -y to_delete.txt")
        mock_trash.assert_called_once_with(str(target.resolve()))
        output = console.export_text()
        assert "Sent to Recycle Bin: to_delete.txt" in output


def test_command_info(tmp_path: Path) -> None:
    """Test info command displays metadata card."""
    shell, console = create_files_test_shell(tmp_path)
    doc = shell.context.current_dir / "doc.txt"
    doc.write_text("sample content")

    shell.run_command_line("info doc.txt")
    output = console.export_text()
    assert "Item Info: doc.txt" in output
    assert "Size / Items:" in output
    assert "Type:" in output


def test_confirm_prompt_displays_choice(tmp_path: Path) -> None:
    """Test confirm_prompt renders '(y/N)' clearly and defaults to No without input."""
    from commands.files import confirm_prompt
    console = Console(record=True, color_system=None)
    
    # In non-interactive mode (no tty), default_yes=False returns False
    res = confirm_prompt(console, "Are you sure?")
    assert res is False
    output = console.export_text()
    assert "(y/N)" in output
