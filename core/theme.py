"""Theme system and terminal capability detection for MayuriShell."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import sys
from typing import Any

from rich import box
from rich.box import Box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.logging_config import get_logger

logger = get_logger()


@dataclass(frozen=True)
class Theme:
    """Represents a visual theme with semantic color tokens and border box style."""
    name: str
    display_name: str
    description: str
    colors: dict[str, str]
    box_style: Box
    is_plain: bool = False

    @property
    def primary(self) -> str:
        return self.colors.get("primary", "")

    @property
    def accent(self) -> str:
        return self.colors.get("accent", "")

    @property
    def success(self) -> str:
        return self.colors.get("success", "")

    @property
    def error(self) -> str:
        return self.colors.get("error", "")

    @property
    def warning(self) -> str:
        return self.colors.get("warning", "")

    @property
    def muted(self) -> str:
        return self.colors.get("muted", "")

    @property
    def border(self) -> str:
        return self.colors.get("border", "")

    @property
    def text(self) -> str:
        return self.colors.get("text", "")

    def format(self, token: str, text: str, bold: bool = False) -> str:
        """Wrap text in a Rich markup tag for the given token, or return plain text in plain mode."""
        if self.is_plain:
            return text
        color = self.colors.get(token, "")
        if not color:
            return text
        tag = f"bold {color}" if bold else color
        return f"[{tag}]{text}[/{tag}]"

    def format_primary(self, text: str, bold: bool = False) -> str:
        return self.format("primary", text, bold=bold)

    def format_accent(self, text: str, bold: bool = False) -> str:
        return self.format("accent", text, bold=bold)

    def format_success(self, text: str, bold: bool = False) -> str:
        return self.format("success", text, bold=bold)

    def format_error(self, text: str, bold: bool = False) -> str:
        return self.format("error", text, bold=bold)

    def format_warning(self, text: str, bold: bool = False) -> str:
        return self.format("warning", text, bold=bold)

    def format_muted(self, text: str) -> str:
        return self.format("muted", text)

    def format_text(self, text: str, bold: bool = False) -> str:
        return self.format("text", text, bold=bold)

    def style(self, token: str, bold: bool = False) -> str | None:
        """Return style string for Rich Table columns, or None if plain/empty."""
        if self.is_plain:
            return None
        val = self.colors.get(token, "")
        if not val:
            return None
        return f"bold {val}" if bold else val

    @property
    def primary_style(self) -> str | None:
        return self.style("primary")

    @property
    def bold_primary_style(self) -> str | None:
        return self.style("primary", bold=True)

    @property
    def accent_style(self) -> str | None:
        return self.style("accent")

    @property
    def bold_accent_style(self) -> str | None:
        return self.style("accent", bold=True)

    @property
    def success_style(self) -> str | None:
        return self.style("success")

    @property
    def warning_style(self) -> str | None:
        return self.style("warning")

    @property
    def muted_style(self) -> str | None:
        return self.style("muted")

    @property
    def text_style(self) -> str | None:
        return self.style("text")

    @property
    def bold_text_style(self) -> str | None:
        return self.style("text", bold=True)

    @property
    def overflow(self) -> str:
        return "crop" if self.is_plain else "ellipsis"

    def create_table(self, title: str | None = None, **kwargs: Any) -> Table:
        """Create a Rich Table pre-styled with the theme's box and border styles."""
        table_kwargs = {
            "box": self.box_style,
        }
        if not self.is_plain and self.border:
            table_kwargs["border_style"] = self.border
        if not self.is_plain and self.bold_primary_style:
            table_kwargs["header_style"] = self.bold_primary_style
        if title:
            table_kwargs["title"] = self.format_accent(title, bold=True)
        table_kwargs.update(kwargs)
        return Table(**table_kwargs)

    def create_panel(self, renderable: Any, title: str | None = None, **kwargs: Any) -> Panel:
        """Create a Rich Panel pre-styled with the theme's box and border styles."""
        panel_kwargs = {
            "box": self.box_style,
        }
        if not self.is_plain and self.border:
            panel_kwargs["border_style"] = self.border
        if title:
            panel_kwargs["title"] = self.format_accent(title, bold=True)
        panel_kwargs.update(kwargs)
        return Panel(renderable, **panel_kwargs)


THEMES: dict[str, Theme] = {
    "kawaii": Theme(
        name="kawaii",
        display_name="Kawaii Pastel",
        description="Default pastel aesthetic (pink, lavender, mint)",
        colors={
            "primary": "#ffb7c5",
            "accent": "#c5b4e3",
            "success": "#a8e6cf",
            "error": "#ff6b81",
            "warning": "#ffd97d",
            "muted": "#9e9eb4",
            "border": "#d8b4e2",
            "text": "#ffffff",
        },
        box_style=box.ROUNDED,
        is_plain=False,
    ),
    "catppuccin": Theme(
        name="catppuccin",
        display_name="Catppuccin Mocha",
        description="Soothing pastel palette (mauve, sapphire, peach)",
        colors={
            "primary": "#cba6f7",
            "accent": "#74c7ec",
            "success": "#a6e3a1",
            "error": "#f38ba8",
            "warning": "#fab387",
            "muted": "#6c7086",
            "border": "#89b4fa",
            "text": "#cdd6f4",
        },
        box_style=box.ROUNDED,
        is_plain=False,
    ),
    "tokyo-night": Theme(
        name="tokyo-night",
        display_name="Tokyo Night",
        description="Clean, deep dark blue & neon violet night aesthetic",
        colors={
            "primary": "#7aa2f7",
            "accent": "#7dcfff",
            "success": "#9ece6a",
            "error": "#f7768e",
            "warning": "#e0af68",
            "muted": "#565f89",
            "border": "#3b4261",
            "text": "#c0caf5",
        },
        box_style=box.ROUNDED,
        is_plain=False,
    ),
    "rose-pine": Theme(
        name="rose-pine",
        display_name="Rose Pine",
        description="All natural pine, foam, and soft rose tones",
        colors={
            "primary": "#ebbcba",
            "accent": "#9ccfd8",
            "success": "#31748f",
            "error": "#eb6f92",
            "warning": "#f6c177",
            "muted": "#6e6a86",
            "border": "#524f67",
            "text": "#e0def4",
        },
        box_style=box.ROUNDED,
        is_plain=False,
    ),
    "gruvbox": Theme(
        name="gruvbox",
        display_name="Gruvbox Dark",
        description="Retro groove warm earthy tones with square borders",
        colors={
            "primary": "#d79921",
            "accent": "#689d6a",
            "success": "#98971a",
            "error": "#cc241d",
            "warning": "#d65d0e",
            "muted": "#928374",
            "border": "#504945",
            "text": "#ebdbb2",
        },
        box_style=box.SQUARE,
        is_plain=False,
    ),
    "plain": Theme(
        name="plain",
        display_name="Plain ASCII",
        description="Strictly ASCII, no colors, no emoji, compatible with all terminals",
        colors={
            "primary": "",
            "accent": "",
            "success": "",
            "error": "",
            "warning": "",
            "muted": "",
            "border": "",
            "text": "",
        },
        box_style=box.ASCII,
        is_plain=True,
    ),
}


def should_force_plain_mode(config_force_plain: bool = False, console: Console | None = None) -> bool:
    """Determine whether terminal environment requires falling back to plain ASCII mode.
    
    Triggers plain mode if:
      - display.force_plain is True in config
      - NO_COLOR environment variable is present
      - Console lacks color support (color_system is None)
      - Standard output encoding is not UTF-compatible and not running under modern Windows Terminal (WT_SESSION)
    """
    if config_force_plain:
        return True

    if "NO_COLOR" in os.environ and os.environ["NO_COLOR"].strip() != "":
        return True

    # Check Windows Terminal session (which supports full Unicode and 24-bit color)
    is_wt = bool(os.environ.get("WT_SESSION"))

    # Check stdout encoding
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    is_utf = "utf" in encoding

    # In legacy console (cmd.exe without WT and without UTF-8), degrade to plain
    if not is_wt and not is_utf:
        return True

    if console and console.color_system is None:
        return True

    return False


class ThemeManager:
    """Manages active theme resolution and style application."""

    def __init__(self, config_manager: Any, console: Console | None = None) -> None:
        self.config_manager = config_manager
        self.console = console if console is not None else Console()
        self._active_theme: Theme | None = None
        self.refresh()

    def refresh(self) -> None:
        """Reload active theme from configuration and environment detection."""
        force_plain = self.config_manager.is_force_plain()
        if should_force_plain_mode(force_plain, self.console):
            self._active_theme = THEMES["plain"]
            return

        theme_name = self.config_manager.get_theme_name()
        self._active_theme = THEMES.get(theme_name, THEMES["kawaii"])

    @property
    def current(self) -> Theme:
        """Return the currently active Theme."""
        if self._active_theme is None:
            self.refresh()
        assert self._active_theme is not None
        return self._active_theme

    def set_theme(self, name: str) -> tuple[bool, str]:
        """Validate, activate, and persist a theme by name."""
        clean = name.strip().lower()
        if clean not in THEMES:
            valid_list = ", ".join(THEMES.keys())
            return False, f"Unknown theme '{name}'. Available themes: {valid_list}"

        self.config_manager.set_theme_name(clean)
        self.refresh()
        return True, f"Theme set to '{clean}' ({THEMES[clean].display_name})."

    def list_themes(self) -> list[tuple[str, str, str, bool]]:
        """Return list of (name, display_name, description, is_active)."""
        current_name = self.current.name
        results = []
        for key, thm in THEMES.items():
            results.append((key, thm.display_name, thm.description, key == current_name))
        return results
