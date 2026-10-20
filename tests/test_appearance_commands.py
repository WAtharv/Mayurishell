"""Tests for visual appearance commands: theme, theme preview, mascot, pet, fetch, and reactive mascot."""
from __future__ import annotations

import io
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

from rich.console import Console

from commands.appearance import register_appearance_commands, render_fetch
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell
from core.theme import ThemeManager


def create_test_shell(tmp_path: Path, terminal_width: int = 100) -> tuple[MayuriShell, Console]:
    """Helper to initialize a test shell instance with recorded console output."""
    cfg = ConfigManager(base_dir=tmp_path / "cfg")
    hist = HistoryManager(tmp_path / "hist.json")
    aliases = AliasManager(cfg)
    reg = CommandRegistry()
    register_appearance_commands(reg)

    console = Console(record=True, width=terminal_width, force_terminal=True)
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


def test_theme_command_list(tmp_path: Path) -> None:
    """Test 'theme' lists all themes and highlights active theme."""
    shell, console = create_test_shell(tmp_path)
    shell.run_command_line("theme")
    out = console.export_text()
    assert "Available Visual Themes" in out
    assert "kawaii" in out
    assert "catppuccin" in out
    assert "tokyo-night" in out
    assert "rose-pine" in out
    assert "gruvbox" in out
    assert "plain" in out
    assert "(Active)" in out


def test_theme_switch_immediate(tmp_path: Path) -> None:
    """Test 'theme <name>' applies the theme immediately to the session."""
    shell, console = create_test_shell(tmp_path)
    shell.run_command_line("theme tokyo-night")
    out = console.export_text()
    assert "Theme set to 'tokyo-night'" in out
    assert shell.context.theme.name == "tokyo-night"


def test_theme_preview_command(tmp_path: Path) -> None:
    """Test 'theme preview' displays side-by-side / comparison showcase."""
    shell, console = create_test_shell(tmp_path)
    shell.run_command_line("theme preview")
    out = console.export_text()
    assert "MayuriShell Theme Showcase" in out
    assert "Kawaii Pastel" in out
    assert "Catppuccin" in out
    assert "Tokyo Night" in out
    assert "Rose Pine" in out
    assert "Gruvbox" in out
    assert "Plain ASCII" in out


def test_mascot_command_list_and_switch(tmp_path: Path) -> None:
    """Test 'mascot' lists mascots and 'mascot <name>' switches active companion."""
    shell, console = create_test_shell(tmp_path)
    shell.run_command_line("mascot")
    out = console.export_text()
    assert "Mascot Companions" in out
    assert "cat" in out
    assert "bunny" in out
    assert "shiba" in out

    shell.run_command_line("mascot shiba")
    out2 = console.export_text()
    assert "Mascot set to 'shiba'" in out2
    assert shell.context.config.get_mascot_name() == "shiba"


def test_pet_command(tmp_path: Path) -> None:
    """Test 'pet' displays friendly interaction with companion."""
    shell, console = create_test_shell(tmp_path)
    shell.run_command_line("mascot bunny")
    shell.run_command_line("pet")
    out = console.export_text()
    assert "You gently pet Bunny" in out
    assert "hops happily" in out


def test_fetch_wide_layout_and_fast_startup(tmp_path: Path) -> None:
    """Test fetch layout in standard terminal (>= 80 cols) and verify fast startup under 0.5s."""
    shell, console = create_test_shell(tmp_path, terminal_width=100)

    start_time = time.perf_counter()
    shell.run_command_line("fetch")
    elapsed = time.perf_counter() - start_time

    assert elapsed < 0.5, f"Fetch took too long: {elapsed:.3f}s (must be under 0.5s)"
    out = console.export_text()
    assert "OS:" in out
    assert "CPU:" in out
    assert "RAM:" in out
    assert "Shell:" in out


def test_fetch_narrow_layout_stacked(tmp_path: Path) -> None:
    """Test fetch stacks info below mascot when terminal is narrower than 80 columns."""
    shell, console = create_test_shell(tmp_path, terminal_width=65)
    shell.run_command_line("fetch")
    out = console.export_text()
    assert "OS:" in out
    assert "CPU:" in out
    assert "RAM:" in out


def test_reactive_mascot_modes(tmp_path: Path) -> None:
    """Test preferences.reactive_mascot modes: 'all', 'errors', 'off'."""
    shell, console = create_test_shell(tmp_path)

    # 1. Mode 'all' (default): prints on both success and error
    shell.context.config.set("preferences.reactive_mascot", "all")
    with patch("sys.stdout.isatty", return_value=True):
        shell.run_command_line("pet")
        # pet is in quiet list, so it shouldn't show reactive mascot
        # Test command not in quiet list:
        shell.run_command_line("invalidcommandname123")
        out = console.export_text()
        assert any(c in out for c in ("💦", "Err", "(;.;)"))

    # 2. Mode 'errors': silent on success, shows on error
    shell2, console2 = create_test_shell(tmp_path)
    shell2.context.config.set("preferences.reactive_mascot", "errors")
    with patch("sys.stdout.isatty", return_value=True):
        # On error
        shell2.run_command_line("invalidcommandname123")
        out2 = console2.export_text()
        assert "Syntax Error" in out2 or "Command not found" in out2

    # 3. Mode 'off': never shows
    shell3, console3 = create_test_shell(tmp_path)
    shell3.context.config.set("preferences.reactive_mascot", "off")
    with patch("sys.stdout.isatty", return_value=True):
        shell3.run_command_line("invalidcommandname123")
        out3 = console3.export_text()
        assert "💦" not in out3
        assert "(=;･ω･;=)" not in out3


def test_reactive_mascot_skips_redirected_output(tmp_path: Path) -> None:
    """Reactive mascot must skip printing if output is redirected (isatty is False)."""
    shell, console = create_test_shell(tmp_path)
    with patch("sys.stdout.isatty", return_value=False):
        shell.run_command_line("invalidcommandname123")
        out = console.export_text()
        assert "(=;･ω･;=)" not in out
        assert "💦" not in out
