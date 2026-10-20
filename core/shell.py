"""Interactive shell loop and REPL for MayuriShell."""
from __future__ import annotations

import os
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
    ) -> None:
        self.config = config
        self.registry = registry
        self.history_manager = history_manager
        self.alias_manager = alias_manager if alias_manager is not None else AliasManager(config)
        self.console = console if console is not None else Console()
        self.running: bool = True


class DynamicCommandCompleter(Completer):
    """Dynamic auto-completer for prompt_toolkit that reads from CommandRegistry."""

    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text_before_cursor = document.text_before_cursor.lstrip()
        # Only autocomplete the command name (the first word)
        if " " not in text_before_cursor:
            word = text_before_cursor.lower()
            for cmd in self.registry.list_commands():
                if cmd.name.lower().startswith(word):
                    yield Completion(
                        cmd.name,
                        start_position=-len(word),
                        display_meta=cmd.description[:40],
                    )


class MayuriShell:
    """Main interactive REPL shell environment."""

    def __init__(
        self,
        config: ConfigManager,
        registry: CommandRegistry,
        history_manager: HistoryManager,
        alias_manager: AliasManager | None = None,
        console: Console | None = None,
    ) -> None:
        self.console = console if console is not None else Console()
        self.alias_manager = alias_manager if alias_manager is not None else AliasManager(config)
        self.context = ShellContext(
            config=config,
            registry=registry,
            history_manager=history_manager,
            alias_manager=self.alias_manager,
            console=self.console,
        )
        self.executor = CommandExecutor(registry=registry, console=self.console)
        
        # Configure prompt_toolkit session
        pt_history = PromptToolkitHistory(history_manager)
        completer = DynamicCommandCompleter(registry)
        try:
            self.session: PromptSession = PromptSession(
                history=pt_history,
                completer=completer,
            )
        except Exception:
            from prompt_toolkit.output import DummyOutput
            self.session = PromptSession(
                history=pt_history,
                completer=completer,
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
        return HTML(f"<ansibrightmagenta>{username}@{hostname}</ansibrightmagenta> <ansicyan>&gt;</ansicyan> ")

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
