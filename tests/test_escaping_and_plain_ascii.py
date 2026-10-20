"""Tests for rich markup escaping of user text and strict ASCII purity in plain mode."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console

from commands.appearance import register_appearance_commands, render_banner
from commands.applications import register_application_commands
from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from commands.files import register_file_commands
from commands.navigation import register_navigation_commands
from commands.processes import register_process_commands
from commands.search import register_search_commands
from commands.system import register_system_commands
from commands.websites import register_website_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell
from core.theme import ThemeManager


def create_full_test_shell(tmp_path: Path, force_plain: bool = False) -> tuple[MayuriShell, Console]:
    """Helper to initialize a fully populated shell with all commands registered."""
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

    console = Console(record=True, force_terminal=True, width=100)
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


def test_escape_user_supplied_text_with_brackets(tmp_path: Path) -> None:
    """Ensure user-supplied text with brackets like 'report [1].txt' does not crash or corrupt Rich markup."""
    shell, console = create_full_test_shell(tmp_path)

    # 1. File name with brackets
    bracket_file = tmp_path / "report [1].txt"
    bracket_file.write_text("sample content", encoding="utf-8")

    shell.run_command_line("ls")
    out = console.export_text()
    assert "report [1].txt" in out

    # 2. File info with brackets
    shell.run_command_line('info "report [1].txt"')
    out2 = console.export_text()
    assert "report [1].txt" in out2

    # 3. Add alias with brackets
    shell.run_command_line("alias test-bracket echo [bracket]")
    out3 = console.export_text()
    assert "[bracket]" in out3
    assert "test-bracket" in out3

    # 4. Add website with brackets
    shell.run_command_line("add-website bracket-site https://example.com/[page]")
    out4 = console.export_text()
    assert "[page]" in out4


def test_plain_mode_strictly_ascii_across_all_commands(tmp_path: Path) -> None:
    """Assert that in plain mode, EVERY command output is 100% strictly ASCII (ord(c) < 128)."""
    shell, console = create_full_test_shell(tmp_path, force_plain=True)
    assert shell.context.theme.is_plain is True

    # 1. Startup banner
    console.clear()
    render_banner(shell.context)
    banner_out = console.export_text()
    for ch in banner_out:
        assert ord(ch) < 128, f"Non-ASCII character '{ch}' (ord {ord(ch)}) in plain banner"

    # 2. Prompt text
    prompt_html = shell.get_prompt_text()
    prompt_str = str(prompt_html.value)
    for ch in prompt_str:
        assert ord(ch) < 128, f"Non-ASCII character '{ch}' (ord {ord(ch)}) in plain prompt"

    # 3. Test various commands in plain mode
    commands_to_test = [
        "help",
        "version",
        "history",
        "apps",
        "websites",
        "pwd",
        "ls",
        "commands",
        "config",
        "uptime",
        "sysinfo",
        "cpu",
        "memory",
        "disk",
        "processes",
        "theme",
        "mascot",
        "fetch",
    ]

    for cmd in commands_to_test:
        console.clear()
        shell.run_command_line(cmd)
        output = console.export_text()
        for idx, ch in enumerate(output):
            assert ord(ch) < 128, (
                f"Non-ASCII character '{ch}' (ord {ord(ch)}) in output of '{cmd}' in plain mode at pos {idx}"
            )


def test_prompt_never_contains_emoji(tmp_path: Path) -> None:
    """Verify the prompt never includes emoji characters in any theme to prevent cursor misalignments."""
    # Test across all themes
    for theme_name in ("kawaii", "catppuccin", "tokyo-night", "rose-pine", "gruvbox", "plain"):
        shell, console = create_full_test_shell(tmp_path)
        shell.context.theme_manager.set_theme(theme_name)
        prompt_text = str(shell.get_prompt_text().value)
        # Check no characters in emoji Unicode ranges
        for ch in prompt_text:
            code = ord(ch)
            # Emoji ranges: 0x1F300-0x1FAFF, 0x2600-0x27BF
            is_emoji = (0x1F300 <= code <= 0x1FAFF) or (0x2600 <= code <= 0x27BF)
            assert not is_emoji, f"Emoji '{ch}' found in prompt for theme '{theme_name}'"
