"""Command execution engine for MayuriShell."""
from __future__ import annotations

import traceback
from typing import Any

from rich.console import Console

from core.exceptions import ArgumentError, CommandNotFoundError, ParseError
from core.logging_config import get_logger
from core.parser import ParsedCommand
from core.registry import CommandRegistry

logger = get_logger()


class CommandExecutor:
    """Safely dispatches and executes parsed commands."""

    def __init__(self, registry: CommandRegistry, console: Console | None = None) -> None:
        self.registry = registry
        self.console = console if console is not None else Console()

    def execute(self, parsed: ParsedCommand, context: Any) -> bool:
        """Execute a parsed command with the given shell context.
        
        Returns:
            True if execution was successful or handled cleanly,
            False if an error occurred.
        """
        cmd_info = self.registry.get(parsed.name)
        if not cmd_info:
            suggestions = self.registry.suggest(parsed.name)
            logger.warning("Command not found: '%s' (suggestions: %s)", parsed.name, suggestions)
            
            self.console.print(f"[bold red]Command not found:[/bold red] '{parsed.name}'")
            if suggestions:
                suggestions_str = ", ".join(f"[bold cyan]{s}[/bold cyan]" for s in suggestions)
                self.console.print(f"  Did you mean: {suggestions_str}?")
            else:
                self.console.print("  Type [bold cyan]help[/bold cyan] to see available commands.")
            return False

        try:
            # Validate arguments
            cmd_info.arg_rules.validate(parsed.args)

            # Invoke handler
            cmd_info.handler(context, parsed.args)
            return True

        except ArgumentError as arg_err:
            logger.warning("Argument error in command '%s': %s", parsed.name, arg_err)
            self.console.print(f"[bold red]Error:[/bold red] {arg_err}")
            self.console.print(f"  Usage: [dim]{cmd_info.usage}[/dim]")
            return False

        except Exception as exc:
            logger.error("Unhandled error executing '%s': %s\n%s", parsed.name, exc, traceback.format_exc())
            self.console.print(f"[bold red]Execution error in '{parsed.name}':[/bold red] {exc}")
            return False
