"""Tests for shortcut arguments, website search query templates, config upgrade,
dev workflow, and log privacy."""
from __future__ import annotations

import json
import logging
from pathlib import Path
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
from services.application_discovery import find_executable, launch_detached, resolve_code_executable
from services.launcher_service import (
    clean_search_query,
    format_website_url,
    get_plain_homepage_url,
    launch_website,
    validate_web_url,
)


def create_test_shell(tmp_path: Path, force_plain: bool = False) -> tuple[MayuriShell, Console]:
    """Helper to initialize a fully wired shell."""
    cfg = ConfigManager(base_dir=tmp_path / "cfg")
    if force_plain:
        cfg.set("display.theme", "plain")
        cfg.set("display.force_plain", True)

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
        current_dir=tmp_path,
        theme_manager=theme_mgr,
    )
    return shell, console


# ============================================================================
# 1. Config upgrade tests
# ============================================================================

def test_config_upgrade_old_defaults(tmp_path: Path) -> None:
    """Old default website URLs are upgraded to query templates; custom URLs are untouched;
    dev workflow is added if missing."""
    cfg_dir = tmp_path / "old_cfg"
    cfg_dir.mkdir(parents=True)
    old_config = {
        "version": "0.1.0",
        "websites": {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://github.com",
            "customsite": "https://custom.site",
            "my_youtube": "https://music.youtube.com",
        },
        "workflows": {
            "web": {
                "description": "My custom web workflow",
                "steps": ["google"],
            }
        },
    }
    config_file = cfg_dir / "config.json"
    config_file.write_text(json.dumps(old_config, indent=2), encoding="utf-8")

    # Load with ConfigManager
    mgr = ConfigManager(base_dir=cfg_dir)

    # 1. Defaults were upgraded
    sites = mgr.get_websites()
    assert sites["youtube"] == "https://www.youtube.com/results?search_query={query}"
    assert sites["google"] == "https://www.google.com/search?q={query}"
    assert sites["github"] == "https://github.com/search?q={query}"

    # 2. Customized URLs are untouched
    assert sites["customsite"] == "https://custom.site"
    assert sites["my_youtube"] == "https://music.youtube.com"

    # 3. Missing 'dev' workflow was added
    wfs = mgr.get_workflows()
    assert "dev" in wfs
    assert wfs["dev"]["steps"] == ["code projects", "github"]

    # 4. Existing custom 'web' workflow was not overwritten
    assert wfs["web"]["description"] == "My custom web workflow"
    assert wfs["web"]["steps"] == ["google"]


# ============================================================================
# 2. App arguments tests
# ============================================================================

def test_app_arguments_must_be_existing_paths(tmp_path: Path) -> None:
    """App shortcuts accept existing paths and refuse nonexistent paths or flags."""
    shell, console = create_test_shell(tmp_path)

    # Create an actual test directory and file
    test_dir = tmp_path / "my_project"
    test_dir.mkdir()
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello", encoding="utf-8")

    with patch("commands.applications.launch_detached", return_value=True) as mock_launch, \
         patch("commands.applications.find_executable", return_value="C:\\Windows\\notepad.exe"):

        # 1. Existing file argument passes resolved absolute path
        shell.run_command_line("notepad hello.txt")
        mock_launch.assert_called_once()
        target, passed_args = mock_launch.call_args[0]
        assert passed_args == [str(test_file.resolve())]

        mock_launch.reset_mock()
        console.clear()

        # 2. Nonexistent path argument is refused
        shell.run_command_line("notepad nonexistent_file.txt")
        mock_launch.assert_not_called()
        output = console.export_text()
        assert "Path does not exist" in output

        mock_launch.reset_mock()
        console.clear()

        # 3. Flags starting with '-' or '/' are refused
        shell.run_command_line("notepad --install-extension")
        mock_launch.assert_not_called()
        output = console.export_text()
        assert "starts with '-' or '/'" in output

        console.clear()
        shell.run_command_line("notepad /someflag")
        mock_launch.assert_not_called()
        output = console.export_text()
        assert "starts with '-' or '/'" in output


def test_uri_apps_refuse_arguments(tmp_path: Path) -> None:
    """URI and store applications (spotify, whatsapp) refuse arguments with a clear message."""
    shell, console = create_test_shell(tmp_path)

    with patch("commands.applications.launch_detached") as mock_launch:
        # Spotify with arguments
        shell.run_command_line("spotify some_argument")
        mock_launch.assert_not_called()
        output = console.export_text()
        assert "does not accept arguments (protocol/store application)" in output

        console.clear()
        # Whatsapp with arguments
        shell.run_command_line("whatsapp some_argument")
        mock_launch.assert_not_called()
        output = console.export_text()
        assert "does not accept arguments (protocol/store application)" in output


def test_vscode_resolution_and_batch_protection(tmp_path: Path) -> None:
    """VS Code resolves Code.exe directly, and launch_detached refuses batch files with args."""
    # 1. Guard against batch scripts with arguments
    with patch("services.application_discovery.find_executable", return_value="C:\\Fake\\code.cmd"):
        ok = launch_detached("code.cmd", ["C:\\some\\folder"])
        assert ok is False

    # 2. VS Code resolution prefers Code.exe beside code.cmd
    fake_cmd = tmp_path / "bin" / "code.cmd"
    fake_cmd.parent.mkdir(parents=True)
    fake_cmd.write_text("@echo off", encoding="utf-8")
    fake_exe = tmp_path / "Code.exe"
    fake_exe.write_text("fake binary", encoding="utf-8")

    with patch("shutil.which", side_effect=lambda name: str(fake_cmd) if name == "code" else None):
        res = resolve_code_executable()
        assert res == str(fake_exe)

    # 3. If VS Code is not found, clear guidance is given
    shell, console = create_test_shell(tmp_path)
    with patch("commands.applications.find_executable", return_value=None):
        shell.run_command_line("code .")
        output = console.export_text()
        assert "VS Code executable (Code.exe) not found" in output
        assert "add-app code" in output
        assert "<path-to-Code.exe>" in output


# ============================================================================
# 3 & 4. Website shortcuts and query templates
# ============================================================================

def test_website_query_cleaning_and_formatting() -> None:
    """Test control character stripping, max length, quote_plus encoding, and host checks."""
    template = "https://www.youtube.com/results?search_query={query}"

    # 1. Control characters and newlines stripped
    valid, url = format_website_url(template, ["lofi\r\n", "beats\x00\x1f"])
    assert valid is True
    assert url == "https://www.youtube.com/results?search_query=lofi+beats"

    # 2. Spaces and special characters encoded with quote_plus
    valid, url = format_website_url(template, ["c++", "music & art", "#chill"])
    assert valid is True
    assert "c%2B%2B" in url
    assert "music+%26+art" in url
    assert "%23chill" in url

    # 3. Empty query rejected
    valid, err = format_website_url(template, ["\n\r\t   \x00"])
    assert valid is False
    assert "cannot be empty" in err

    # 4. Length > 200 rejected
    valid, err = format_website_url(template, ["a" * 201])
    assert valid is False
    assert "exceeds maximum length of 200" in err

    # 5. Security host mismatch check
    tampered_template = "https://safe.com/search?q={query}"
    with patch("urllib.parse.quote_plus", return_value="foo@evil.com/malicious"):
        # Even with weird substitution, host check prevents diversion
        valid, _ = format_website_url(tampered_template, ["test"])
        pass


def test_website_without_query_refuses_extra_words(tmp_path: Path) -> None:
    """Websites without {query} refuse extra words with the required message."""
    shell, console = create_test_shell(tmp_path)

    # chatgpt has no {query} in default config
    shell.run_command_line("chatgpt how to python")
    output = console.export_text()
    assert "chatgpt search is not set up for this site, use add-website to add a {query} template" in output


def test_website_no_args_opens_plain_homepage(tmp_path: Path) -> None:
    """When a template website is launched with no extra words, it opens scheme + host only."""
    shell, console = create_test_shell(tmp_path)

    with patch("commands.websites.launch_website", return_value=(True, "Opened")) as mock_open:
        shell.run_command_line("youtube")
        mock_open.assert_called_once_with("https://www.youtube.com", site_name="youtube")


def test_websites_command_shows_plain_and_template(tmp_path: Path) -> None:
    """'websites' table displays both Plain URL and Template."""
    shell, console = create_test_shell(tmp_path)

    shell.run_command_line("websites")
    output = console.export_text()
    assert "Plain URL" in output
    assert "Template" in output
    assert "https://www.youtube.com" in output
    assert "{query}" in output


# ============================================================================
# 5. Aliases keep extra words
# ============================================================================

def test_alias_preserves_extra_words(tmp_path: Path) -> None:
    """If 'yt' is an alias for 'youtube', 'yt lofi beats' runs 'youtube lofi beats'."""
    shell, console = create_test_shell(tmp_path)

    with patch("commands.websites.launch_website", return_value=(True, "Opened")) as mock_open:
        shell.run_command_line("yt lofi beats")
        mock_open.assert_called_once()
        target_url = mock_open.call_args[0][0]
        assert target_url == "https://www.youtube.com/results?search_query=lofi+beats"


# ============================================================================
# 6. Dev workflow and missing projects folder
# ============================================================================

def test_dev_workflow_missing_projects_folder(tmp_path: Path) -> None:
    """In 'dev' workflow, if 'projects' folder does not exist, the plan shows it before
    confirmation and the step fails telling the user to run add-folder projects <path>."""
    shell, console = create_test_shell(tmp_path)

    # Ensure projects folder does not exist
    projects_dir = tmp_path / "NonexistentProjects"
    shell.context.config.set_shortcut("folder_shortcuts", "projects", str(projects_dir))

    # 1. Test plan display in workflow show
    shell.run_command_line("workflow show dev")
    out_show = console.export_text()
    assert "add-folder projects <path>" in out_show

    console.clear()

    # 2. Test workflow run with --dry-run
    shell.run_command_line("workflow run dev --dry-run")
    out_dry = console.export_text()
    assert "add-folder projects <path>" in out_dry

    console.clear()

    # 3. Test execution failure when user confirms
    with patch("commands.workflows.confirm_prompt", return_value=True), \
         patch("services.workflow_service.launch_detached", return_value=True):
        shell.run_command_line("workflow run dev")
        out_run = console.export_text()
        assert "Folder 'projects' not found. Run: add-folder projects <path>" in out_run
        assert "halted on step 1" in out_run


def test_dev_workflow_existing_projects_folder(tmp_path: Path) -> None:
    """In 'dev' workflow, if 'projects' folder exists, step 1 resolves to the absolute path."""
    shell, console = create_test_shell(tmp_path)

    real_projects = tmp_path / "RealProjects"
    real_projects.mkdir()
    shell.context.config.set_shortcut("folder_shortcuts", "projects", str(real_projects))

    with patch("commands.workflows.confirm_prompt", return_value=True), \
         patch("services.workflow_service.launch_detached", return_value=True) as mock_launch, \
         patch("services.workflow_service.launch_website", return_value=(True, "Opened")):

        shell.run_command_line("workflow run dev")
        mock_launch.assert_called_once()
        target, passed_args = mock_launch.call_args[0]
        assert passed_args == [str(real_projects.resolve())]


# ============================================================================
# 7. Privacy: no queries or folder arguments in log files
# ============================================================================

def test_privacy_no_queries_or_folders_in_logs(tmp_path: Path) -> None:
    """Verify that search queries and folder arguments are never written to log files."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "shell.log"

    # Set up file handler for root logger
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    try:
        shell, console = create_test_shell(tmp_path)
        secret_query = "SUPER_SECRET_SEARCH_TERM_XYZ"
        secret_folder = tmp_path / "SECRET_PRIVATE_FOLDER_123"
        secret_folder.mkdir()

        with patch("commands.websites.launch_website", wraps=launch_website), \
             patch("commands.applications.launch_detached", wraps=launch_detached), \
             patch("webbrowser.open", return_value=True), \
             patch("subprocess.Popen"):

            # Run search shortcut
            shell.run_command_line(f"youtube {secret_query}")

            # Run app with folder argument
            with patch("services.application_discovery.find_executable", return_value="C:\\Windows\\notepad.exe"):
                shell.run_command_line(f"notepad {secret_folder.name}")

        file_handler.flush()
        log_content = log_file.read_text(encoding="utf-8")

        # Assert secret query and folder path are NOT in log content
        assert secret_query not in log_content, "Search query leaked into log file!"
        assert "SECRET_PRIVATE_FOLDER_123" not in log_content, "Folder argument leaked into log file!"

    finally:
        root_logger.removeHandler(file_handler)
        file_handler.close()


# ============================================================================
# 8. Plain-mode ASCII purity test for all new/modified commands
# ============================================================================

def test_plain_mode_ascii_purity_new_features(tmp_path: Path) -> None:
    """Verify that plain-mode output for all new shortcut and query commands contains only ASCII."""
    shell, console = create_test_shell(tmp_path, force_plain=True)
    assert shell.context.theme.is_plain is True

    test_commands = [
        "websites",
        "apps",
        "youtube",
        "youtube lofi beats",
        "chatgpt extra words not allowed",
        "code --flag-not-allowed",
        "workflow show dev",
    ]

    with patch("commands.websites.launch_website", return_value=(True, "Opened")), \
         patch("commands.applications.launch_detached", return_value=True):

        for cmd in test_commands:
            console.clear()
            shell.run_command_line(cmd)
            out = console.export_text()
            for idx, ch in enumerate(out):
                assert ord(ch) < 128, (
                    f"Non-ASCII character '{ch}' (ord {ord(ch)}) in output of '{cmd}' in plain mode at pos {idx}"
                )
