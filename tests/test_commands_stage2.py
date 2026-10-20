"""Integration tests for Stage 2 commands and shortcuts."""
from pathlib import Path
from unittest.mock import patch
from rich.console import Console

from commands.applications import register_application_commands
from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from commands.navigation import register_navigation_commands
from commands.websites import register_website_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell


def create_stage2_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to initialize a fully wired shell for Stage 2 testing."""
    config = ConfigManager(base_dir=tmp_path)
    history = HistoryManager(tmp_path / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    # Register all commands
    register_builtin_commands(registry)
    register_application_commands(registry, config)
    register_website_commands(registry, config)
    register_navigation_commands(registry, config)
    register_customization_commands(registry, config)

    console = Console(record=True, color_system=None, width=140)
    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        console=console,
    )
    return shell, console


def test_command_apps_and_add_app(tmp_path: Path) -> None:
    """Test 'apps' listing and 'add-app' command."""
    shell, console = create_stage2_shell(tmp_path)
    
    # Run apps
    shell.run_command_line("apps")
    output = console.export_text()
    assert "Configured Applications" in output
    assert "notepad" in output
    assert "spotify" in output
    assert "whatsapp" in output

    # Run add-app
    shell.run_command_line("add-app myeditor C:\\fake\\editor.exe")
    assert "myeditor" in shell.context.config.get_applications()
    assert shell.context.registry.has_command("myeditor")


def test_add_app_name_clash_validation(tmp_path: Path) -> None:
    """Test add-app rejects names that clash with builtins or invalid characters."""
    shell, console = create_stage2_shell(tmp_path)

    # Clashes with builtin 'help'
    shell.run_command_line("add-app help C:\\fake\\help.exe")
    output = console.export_text()
    assert "conflicts with built-in command" in output

    # Invalid characters
    shell.run_command_line("add-app bad_name! C:\\fake\\exe")
    output = console.export_text()
    assert "Names may only contain letters, numbers, and hyphens" in output


def test_direct_app_shortcut_execution(tmp_path: Path) -> None:
    """Test typing an app shortcut directly (e.g. 'spotify')."""
    shell, console = create_stage2_shell(tmp_path)

    with patch("commands.applications.launch_detached", return_value=True) as mock_launch:
        shell.run_command_line("spotify")
        mock_launch.assert_called_once_with("spotify:", [])
        output = console.export_text()
        assert "Launched spotify" in output


def test_command_websites_and_add_website(tmp_path: Path) -> None:
    """Test 'websites' listing and 'add-website' command."""
    shell, console = create_stage2_shell(tmp_path)

    shell.run_command_line("websites")
    output = console.export_text()
    assert "Configured Websites" in output
    assert "youtube" in output
    assert "github" in output

    # Add website
    shell.run_command_line("add-website blog myblog.dev")
    assert "blog" in shell.context.config.get_websites()
    assert shell.context.config.get_websites()["blog"] == "https://myblog.dev"
    assert shell.context.registry.has_command("blog")


def test_add_website_url_validation(tmp_path: Path) -> None:
    """Test add-website rejects non-http schemes."""
    shell, console = create_stage2_shell(tmp_path)

    shell.run_command_line("add-website badsite ftp://files.net")
    output = console.export_text()
    assert "Invalid URL" in output
    assert "Only 'http' and 'https' are allowed" in output


def test_direct_website_shortcut_execution(tmp_path: Path) -> None:
    """Test typing a website shortcut directly opens browser."""
    shell, console = create_stage2_shell(tmp_path)

    with patch("services.launcher_service.webbrowser.open", return_value=True) as mock_open:
        shell.run_command_line("youtube")
        mock_open.assert_called_once_with("https://www.youtube.com")


def test_command_add_folder_and_missing_folder_message(tmp_path: Path) -> None:
    """Test add-folder and missing folder handling with user instructions."""
    shell, console = create_stage2_shell(tmp_path)

    missing_path = tmp_path / "does_not_exist"
    shell.run_command_line(f"add-folder mywork {missing_path}")
    assert "mywork" in shell.context.config.get_folder_shortcuts()
    assert shell.context.registry.has_command("mywork")

    # Typing the folder shortcut when missing shows clear error and fix suggestion
    shell.run_command_line("mywork")
    output = console.export_text()
    assert "Folder error for 'mywork'" in output
    assert "Update this shortcut to an existing directory using: add-folder mywork <path>" in output


def test_direct_folder_shortcut_execution(tmp_path: Path) -> None:
    """Test typing a folder shortcut opens File Explorer."""
    shell, console = create_stage2_shell(tmp_path)
    real_folder = tmp_path / "my_docs"
    real_folder.mkdir()

    shell.run_command_line(f"add-folder docs {real_folder}")

    with patch("os.startfile", create=True) as mock_startfile:
        shell.run_command_line("docs")
        mock_startfile.assert_called_once_with(str(real_folder.resolve()))


def test_alias_and_resolution_flow(tmp_path: Path) -> None:
    """Test creating an alias and executing it through the shell."""
    shell, console = create_stage2_shell(tmp_path)

    # List aliases
    shell.run_command_line("aliases")
    output = console.export_text()
    assert "Configured Aliases" in output

    # Add alias
    shell.run_command_line("alias v version")
    assert shell.context.config.get_aliases()["v"] == "version"

    # Typing alias 'v' resolves to 'version' and executes
    shell.run_command_line("v")
    output = console.export_text()
    assert "MayuriShell version 0.1.0" in output

    # Unalias
    shell.run_command_line("unalias v")
    assert "v" not in shell.context.config.get_aliases()


def test_commands_and_command_info(tmp_path: Path) -> None:
    """Test 'commands' listing and 'command-info' inspection."""
    shell, console = create_stage2_shell(tmp_path)

    shell.run_command_line("commands")
    output = console.export_text()
    assert "All Available Commands and Shortcuts" in output
    assert "Applications" in output
    assert "Websites" in output
    assert "Folders" in output

    shell.run_command_line("command-info spotify")
    output = console.export_text()
    assert "Command Details: spotify" in output
    assert "App Target:" in output


def test_command_config(tmp_path: Path) -> None:
    """Test 'config' displays configuration directories."""
    shell, console = create_stage2_shell(tmp_path)

    shell.run_command_line("config")
    output = console.export_text()
    assert "MayuriShell - Configuration Locations" in output
    assert "Config File:" in output
    assert "History File:" in output
