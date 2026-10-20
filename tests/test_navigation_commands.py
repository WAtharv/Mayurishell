"""Integration tests for navigation commands: pwd, cd, ls."""
from pathlib import Path
from rich.console import Console

from commands.navigation import register_navigation_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell


def create_nav_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to initialize shell for navigation testing."""
    config = ConfigManager(base_dir=tmp_path / "appdata")
    history = HistoryManager(tmp_path / "appdata" / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_navigation_commands(registry, config)

    console = Console(record=True, color_system=None, width=140)
    work_dir = tmp_path / "nav_workspace"
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


def test_command_pwd(tmp_path: Path) -> None:
    """Test pwd prints shell's current working directory."""
    shell, console = create_nav_test_shell(tmp_path)
    shell.run_command_line("pwd")
    output = console.export_text()
    assert str(shell.context.current_dir) in output


def test_command_cd_relative_and_parent(tmp_path: Path) -> None:
    """Test cd navigating to child directory and .. parent."""
    shell, console = create_nav_test_shell(tmp_path)
    sub = shell.context.current_dir / "child"
    sub.mkdir()

    shell.run_command_line("cd child")
    assert shell.context.current_dir == sub.resolve()

    shell.run_command_line("cd ..")
    assert shell.context.current_dir == (tmp_path / "nav_workspace").resolve()


def test_command_cd_shortcut_and_precedence(tmp_path: Path) -> None:
    """Test cd precedence when name exists locally and as a shortcut."""
    shell, console = create_nav_test_shell(tmp_path)
    
    # Configure a folder shortcut 'projects'
    global_proj = tmp_path / "global_proj"
    global_proj.mkdir()
    shell.context.config.set_shortcut("folder_shortcuts", "projects", str(global_proj))

    # cd projects when NO local folder exists resolves to shortcut
    shell.run_command_line("cd projects")
    assert shell.context.current_dir == global_proj.resolve()

    # Now go back and create a local 'projects' folder
    shell.context.current_dir = (tmp_path / "nav_workspace").resolve()
    local_proj = shell.context.current_dir / "projects"
    local_proj.mkdir()

    shell.run_command_line("cd projects")
    # Local folder takes precedence!
    assert shell.context.current_dir == local_proj.resolve()
    output = console.export_text()
    assert "precedence over shortcut" in output


def test_command_ls_listing_and_filter(tmp_path: Path) -> None:
    """Test ls listing with patterns and hidden file suppression."""
    shell, console = create_nav_test_shell(tmp_path)
    (shell.context.current_dir / "app.py").write_text("code")
    (shell.context.current_dir / "data.csv").write_text("csv")
    (shell.context.current_dir / ".env").write_text("secret")

    # Regular ls (hides .env)
    shell.run_command_line("ls")
    output = console.export_text()
    assert "app.py" in output
    assert "data.csv" in output
    assert ".env" not in output

    # ls *.py
    shell.run_command_line("ls *.py")
    output = console.export_text()
    assert "app.py" in output

    # ls -a
    shell.run_command_line("ls -a")
    output = console.export_text()
    assert ".env" in output


def test_command_ls_truncates_long_names(tmp_path: Path) -> None:
    """Test ls truncates items with names exceeding 40 characters with ..."""
    shell, console = create_nav_test_shell(tmp_path)
    long_name = "6994a8875ba77_WCE_Hackathon_2026_Brief_Case_Super_Long_Folder"
    (shell.context.current_dir / long_name).mkdir()

    shell.run_command_line("ls")
    output = console.export_text()
    assert "..." in output
    assert long_name not in output  # Full un-truncated name should not appear
