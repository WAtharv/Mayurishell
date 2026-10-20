"""Tests for MayuriShell theme system, terminal detection, and token enforcement."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
from unittest.mock import MagicMock, patch

from rich import box
from rich.console import Console

from core.config_manager import ConfigManager
from core.theme import THEMES, Theme, ThemeManager, should_force_plain_mode


def test_theme_definitions() -> None:
    """Verify all 6 required themes exist and have all semantic color tokens."""
    expected_themes = {"kawaii", "catppuccin", "tokyo-night", "rose-pine", "gruvbox", "plain"}
    assert set(THEMES.keys()) == expected_themes

    required_tokens = {"primary", "accent", "success", "error", "warning", "muted", "border", "text"}
    for name, theme in THEMES.items():
        assert isinstance(theme, Theme)
        assert set(theme.colors.keys()) == required_tokens
        assert theme.name == name
        assert theme.display_name != ""
        assert theme.description != ""
        if name == "plain":
            assert theme.is_plain is True
            assert theme.box_style == box.ASCII
        else:
            assert theme.is_plain is False


def test_theme_formatters() -> None:
    """Test format_* helper methods on Theme."""
    kawaii = THEMES["kawaii"]
    assert kawaii.format_primary("Hello") == f"[{kawaii.primary}]Hello[/{kawaii.primary}]"
    assert kawaii.format_primary("Hello", bold=True) == f"[bold {kawaii.primary}]Hello[/bold {kawaii.primary}]"
    assert kawaii.format_success("Done") == f"[{kawaii.success}]Done[/{kawaii.success}]"
    assert kawaii.format_error("Failed") == f"[{kawaii.error}]Failed[/{kawaii.error}]"

    plain = THEMES["plain"]
    assert plain.format_primary("Hello") == "Hello"
    assert plain.format_primary("Hello", bold=True) == "Hello"
    assert plain.format_success("Done") == "Done"
    assert plain.format_error("Failed") == "Failed"
    assert plain.format_muted("Muted") == "Muted"


def test_theme_manager_switching_and_fallback(tmp_path: Path) -> None:
    """Test switching themes via ThemeManager and fallback behavior."""
    cfg = ConfigManager(base_dir=tmp_path / "cfg")
    console = Console(record=True, force_terminal=True)
    mgr = ThemeManager(cfg, console=console)

    # Default is kawaii
    assert mgr.current.name == "kawaii"

    # Switch to catppuccin
    success, msg = mgr.set_theme("catppuccin")
    assert success is True
    assert mgr.current.name == "catppuccin"
    assert cfg.get_theme_name() == "catppuccin"

    # Switch to unknown theme: fails, does not change active
    success, msg = mgr.set_theme("neon-cyberpunk")
    assert success is False
    assert "Unknown theme" in msg
    assert mgr.current.name == "catppuccin"

    # Switch to plain
    success, msg = mgr.set_theme("plain")
    assert success is True
    assert mgr.current.name == "plain"
    assert mgr.current.is_plain is True


def test_should_force_plain_mode_detection() -> None:
    """Test environment and config detection for falling back to plain mode."""
    # 1. Config option display.force_plain
    assert should_force_plain_mode(config_force_plain=True) is True

    # 2. NO_COLOR env var
    with patch.dict(os.environ, {"NO_COLOR": "1"}):
        assert should_force_plain_mode(config_force_plain=False) is True

    with patch.dict(os.environ, {"NO_COLOR": ""}):
        with patch.dict(os.environ, {"WT_SESSION": "fake-session"}):
            # When WT_SESSION is set and NO_COLOR is empty, not forced plain
            assert should_force_plain_mode(config_force_plain=False) is False

    # 3. Legacy console without WT_SESSION and non-UTF8 encoding
    with patch.dict(os.environ, {}, clear=True):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.encoding = "cp1252"
            assert should_force_plain_mode(config_force_plain=False) is True


def test_no_hardcoded_colors_or_box_styles_outside_theme() -> None:
    """Scan all files in commands/ and services/ to ensure no hardcoded colors or box styles exist.
    
    Hardcoded colors and box styles must reside ONLY within core/theme.py.
    """
    project_root = Path(__file__).parent.parent
    scan_dirs = [project_root / "commands", project_root / "services"]

    # Patterns matching hardcoded rich color markup like [red], [bold cyan], style="yellow", etc.
    hardcoded_color_pattern = re.compile(
        r'(\[(?:bold\s+|dim\s+)?(?:red|green|blue|cyan|magenta|yellow|pink\d?|purple\d?|white|black|gold\d?|orchid\d?|spring_green\d?|gray|grey)\]'
        r'|style=["\'](?:bold\s+|dim\s+)?(?:red|green|blue|cyan|magenta|yellow|pink\d?|purple\d?|white|black|gold\d?|orchid\d?)["\']'
        r'|#[0-9a-fA-F]{3,8}'
        r'|\bbox\.(?:ROUNDED|SQUARE|ASCII|HEAVY|DOUBLE|MINIMAL|SIMPLE)\b)',
        re.IGNORECASE,
    )

    violations: list[str] = []

    for directory in scan_dirs:
        for py_file in directory.glob("*.py"):
            lines = py_file.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, start=1):
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("#"):
                    continue
                match = hardcoded_color_pattern.search(line)
                if match:
                    violations.append(f"{py_file.name}:{lineno} -> {line.strip()} (matched: '{match.group(0)}')")

    assert not violations, "Found hardcoded colors or box styles outside core/theme.py:\n" + "\n".join(violations)
