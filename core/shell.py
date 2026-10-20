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
    ) -> None:
        self.config = config
        self.registry = registry
        self.history_manager = history_manager
        self.alias_manager = alias_manager if alias_manager is not None else AliasManager(config)
        self.console = console if console is not None else Console()
        self.current_dir = (current_dir if current_dir is not None else Path.cwd()).resolve()
        self.running: bool = True

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
        """Display the welcoming startup banner."""
        username = self.context.config.get("username", "Mayuri")
        banner_content = (
            "[bold pink1]╔══════════════════════════════════════════════╗[/bold pink1]\n"
            "[bold pink1]║                 [/bold pink1][bold white]MAYURISHELL[/bold white][bold pink1]                  ║[/bold pink1]\n"
            "[bold pink1]║          [/bold pink1][dim white]YOUR PC. YOUR COMMANDS.[/dim white][bold pink1]             ║[/bold pink1]\n"
            "[bold pink1]╚══════════════════════════════════════════════╝[/bold pink1]\n\n"
            f"[bold cyan]Welcome back, {username}![/bold cyan]\n"
            "Type [bold yellow]'help'[/bold yellow] to explore your commands.\n"
        )
        self.console.print(banner_content)

    def get_prompt_text(self) -> HTML:
        """Construct the prompt string with prompt_toolkit HTML formatting."""
        username = self.context.config.get("username", "Mayuri").lower()
        hostname = (platform.node() or "pc").lower()
        
        show_cwd = self.context.config.get("preferences", {}).get("show_cwd_in_prompt", True)
        cwd_segment = ""
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
            cwd_segment = f" <ansiyellow>{short_path}</ansiyellow>"

        return HTML(f"<ansibrightmagenta>{username}@{hostname}</ansibrightmagenta>{cwd_segment} <ansicyan>&gt;</ansicyan> ")

    def run_command_line(self, line: str) -> bool:
        """Parse and execute a single command line.
        
        Returns:
            True if executed cleanly, False on parse/execution errors.
        """
        stripped = line.strip()
        if not stripped:
            return True

        # Store in history
        self.context.history_manager.add(stripped)

        try:
            parsed = parse_command_line(stripped)
            if not parsed:
                return True
        except ParseError as p_err:
            self.console.print(f"[bold red]Syntax Error:[/bold red] {p_err}")
            return False

        return self.executor.execute(parsed, self.context)

    def run(self) -> None:
        """Start and run the main interactive REPL loop."""
        logger.info("MayuriShell REPL session started.")
        self.display_welcome_banner()

        while self.context.running:
            try:
                user_input = self.session.prompt(self.get_prompt_text())
                self.run_command_line(user_input)
            except KeyboardInterrupt:
                # Ctrl+C resets current prompt line without crashing or exiting
                self.console.print("\n[dim]KeyboardInterrupt: Operation cancelled. (Ctrl+D to exit)[/dim]")
                continue
            except EOFError:
                # Ctrl+D exits gracefully
                username = self.context.config.get("username", "Mayuri")
                self.console.print(f"\n[bold pink1]Goodbye, {username}! (,,•́ω•̀,,)ﾉ[/bold pink1]")
                self.context.running = False
                break
            except Exception as unhandled:
                logger.critical("Unexpected error in shell loop: %s", unhandled, exc_info=True)
                self.console.print(f"[bold red]Unexpected shell error:[/bold red] {unhandled}")

        logger.info("MayuriShell REPL session ended.")
