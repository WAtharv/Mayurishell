"""Interactive shell loop and REPL for MayuriShell."""
from __future__ import annotations

import os
from pathlib import Path
import platform
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.exceptions import ParseError
from core.executor import CommandExecutor
from core.history import HistoryManager, PromptToolkitHistory
from core.logging_config import get_logger
from core.parser import parse_command_line
from core.registry import CommandRegistry

logger = get_logger()


class ShellContext:
    """Holds shared state across the shell session."""

    def __init__(
        self,
        config: ConfigManager,
        registry: CommandRegistry,
        history_manager: HistoryManager,
        alias_manager: AliasManager | None = None,
        console: Console | None = None,
        current_dir: Path | None = None,
        theme_manager: Any | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.history_manager = history_manager
        self.alias_manager = alias_manager if alias_manager is not None else AliasManager(config)
        self.console = console if console is not None else Console()
        self.current_dir = (current_dir if current_dir is not None else Path.cwd()).resolve()
        from core.theme import ThemeManager
        self.theme_manager: ThemeManager = theme_manager if theme_manager is not None else ThemeManager(config, console=self.console)
        self.running: bool = True
        self.last_mood: str = "neutral"

    @property
    def theme(self) -> Any:
        """Return the current active Theme."""
        return self.theme_manager.current

    def resolve_path(self, raw: str) -> tuple[Path, str | None]:
        """Resolve a raw path relative to current working directory and shortcuts."""
        from services.file_service import resolve_path
        return resolve_path(raw, self.current_dir, self.config.get_folder_shortcuts())


from core.completer import MayuriCompleter

# Alias for backwards compatibility
DynamicCommandCompleter = MayuriCompleter


class MayuriShell:
    """Main interactive REPL shell environment."""

    def __init__(
        self,
        config: ConfigManager,
        registry: CommandRegistry,
        history_manager: HistoryManager,
        alias_manager: AliasManager | None = None,
        console: Console | None = None,
        current_dir: Path | None = None,
        theme_manager: Any | None = None,
    ) -> None:
        self.console = console if console is not None else Console()
        self.alias_manager = alias_manager if alias_manager is not None else AliasManager(config)
        self.context = ShellContext(
            config=config,
            registry=registry,
            history_manager=history_manager,
            alias_manager=self.alias_manager,
            console=self.console,
            current_dir=current_dir,
            theme_manager=theme_manager,
        )
        self.executor = CommandExecutor(registry=registry, console=self.console)
        
        # Configure prompt_toolkit session
        from prompt_toolkit.shortcuts import CompleteStyle
        pt_history = PromptToolkitHistory(history_manager)
        completer = MayuriCompleter(self.context)
        try:
            self.session: PromptSession = PromptSession(
                history=pt_history,
                completer=completer,
                complete_while_typing=False,
                complete_style=CompleteStyle.MULTI_COLUMN,
            )
        except Exception:
            from prompt_toolkit.output import DummyOutput
            self.session = PromptSession(
                history=pt_history,
                completer=completer,
                complete_while_typing=False,
                complete_style=CompleteStyle.MULTI_COLUMN,
                output=DummyOutput(),
            )

    def display_welcome_banner(self) -> None:
        """Display the welcoming startup banner and fetch dashboard."""
        show_welcome = self.context.config.get("preferences", {}).get("show_welcome", True)
        if not show_welcome:
            return
        from commands.appearance import render_banner, render_fetch
        render_banner(self.context)
        render_fetch(self.context)

    def get_prompt_text(self) -> HTML:
        """Construct the prompt string with prompt_toolkit HTML formatting."""
        username = self.context.config.get("username", "Mayuri").lower()
        host = self.context.config.get_prompt_host()
        prompt_symbol = self.context.config.get_prompt_symbol()
        theme = self.context.theme

        show_cwd = self.context.config.get("preferences", {}).get("show_cwd_in_prompt", True)
        short_path = ""
        if show_cwd:
            cur = self.context.current_dir
            home = Path.home().resolve()
            if cur == home:
                short_path = "~"
            else:
                try:
                    rel = cur.relative_to(home)
                    short_path = f"~/{rel.as_posix()}"
                except ValueError:
                    short_path = cur.as_posix()

        escaped_symbol = "&gt;" if prompt_symbol == ">" else prompt_symbol.replace("&", "&amp;").replace("<", "&lt;")

        # In plain mode: strictly ASCII with no formatting tags
        if theme.is_plain:
            cwd_str = f" {short_path}" if short_path else ""
            return HTML(f"{username}@{host}{cwd_str} {escaped_symbol} ")

        # Colored mode: style using theme tokens (no emoji in prompt)
        def _clean_pt_color(color: str) -> str:
            if not color:
                return "default"
            token = color.strip().split()[-1]
            return token

        primary_color = _clean_pt_color(theme.primary)
        accent_color = _clean_pt_color(theme.accent)
        muted_color = _clean_pt_color(theme.muted)

        cwd_segment = f' <style color="{accent_color}">{short_path}</style>' if short_path else ""

        return HTML(
            f'<style color="{primary_color}">{username}</style>'
            f'<style color="{muted_color}">@{host}</style>'
            f'{cwd_segment} '
            f'<style color="{primary_color}">{escaped_symbol}</style> '
        )

    def _show_reactive_mascot(self, cmd_name: str, mood_or_success: str | bool) -> None:
        """Display subtle reactive mascot face after command execution."""
        import sys
        if not sys.stdout.isatty():
            return

        mode = self.context.config.get_reactive_mascot_mode()
        if mode == "off":
            return

        if isinstance(mood_or_success, bool):
            target_mood = "happy" if mood_or_success else "worried"
        else:
            target_mood = mood_or_success

        if mode == "errors" and target_mood != "worried":
            return

        # Skip for specific non-content or self-rendering commands
        if cmd_name.lower() in ("clear", "fetch", "pet"):
            return
        if target_mood != "worried" and cmd_name.lower() in ("mascot", "theme", "help"):
            return

        from core.mascots import get_reactive_face, resolve_mascot_name
        mascot_name = self.context.config.get_mascot_name()
        resolved = resolve_mascot_name(mascot_name)
        theme = self.context.theme
        face = get_reactive_face(resolved, target_mood, is_plain=theme.is_plain)

        if theme.is_plain:
            self.console.print(f" {face}\n")
        else:
            self.console.print(f" {theme.format_muted(face)}\n")

    def run_command_line(self, line: str) -> bool:
        """Parse and execute a single command line.
        
        Returns:
            True if executed cleanly, False on parse/execution errors.
        """
        stripped = line.strip()
        if not stripped:
            return True

        # Store in history (defaults to success=True until evaluated)
        self.context.history_manager.add(stripped)

        try:
            parsed = parse_command_line(stripped)
            if not parsed:
                return True
        except ParseError as p_err:
            theme = self.context.theme
            self.console.print(f"{theme.format_error('Syntax Error:')} {p_err}")
            self.executor.last_mood = "worried"
            self.context.last_mood = "worried"
            self.context.history_manager.update_last_status(success=False)
            self._show_reactive_mascot("error", "worried")
            return False

        result = self.executor.execute(parsed, self.context)
        if self.context.running:
            self._show_reactive_mascot(parsed.name, self.executor.last_mood)
        return bool(result)

    def run(self) -> None:
        """Start and run the main interactive REPL loop."""
        logger.info("MayuriShell REPL session started.")
        self.display_welcome_banner()

        # If stdin is redirected/piped, execute lines in non-interactive batch mode
        import sys
        if sys.stdin and not sys.stdin.isatty():
            for line in sys.stdin:
                line_str = line.strip()
                if line_str:
                    self.run_command_line(line_str)
                if not self.context.running:
                    break
            logger.info("MayuriShell batch session ended.")
            return

        while self.context.running:
            try:
                user_input = self.session.prompt(self.get_prompt_text())
                self.run_command_line(user_input)
            except KeyboardInterrupt:
                # Ctrl+C resets current prompt line without crashing or exiting
                theme = self.context.theme
                self.console.print(f"\n{theme.format_muted('KeyboardInterrupt: Operation cancelled. (Ctrl+D to exit)')}")
                continue
            except EOFError:
                # Ctrl+D exits gracefully with sleepy mascot
                username = self.context.config.get("username", "Mayuri")
                from core.mascots import get_reactive_face, resolve_mascot_name
                mascot_name = self.context.config.get_mascot_name()
                resolved = resolve_mascot_name(mascot_name)
                theme = self.context.theme
                face = get_reactive_face(resolved, "sleepy", is_plain=theme.is_plain)

                if theme.is_plain:
                    self.console.print(f"\nGoodbye, {username}! {face}")
                else:
                    self.console.print(f"\n{theme.format_primary(f'Goodbye, {username}!')} {theme.format_muted(face)}")
                self.context.running = False
                break
            except Exception as unhandled:
                logger.critical("Unexpected error in shell loop: %s", unhandled, exc_info=True)
                theme = self.context.theme
                self.console.print(f"{theme.format_error('Unexpected shell error:')} {unhandled}")

        logger.info("MayuriShell REPL session ended.")
