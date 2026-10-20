"""Command execution engine for MayuriShell."""
from __future__ import annotations

from dataclasses import dataclass
import traceback
from typing import Any

from rich.console import Console

from core.exceptions import (
    ArgumentError,
    CommandCancelled,
    CommandError,
    CommandNotFoundError,
    ParseError,
)
from core.logging_config import get_logger
from core.parser import ParsedCommand
from core.registry import CommandRegistry

logger = get_logger()


@dataclass
class CommandResult:
    """Standard result returned by command handlers and execution engine."""

    ok: bool = True
    cancelled: bool = False
    message: str | None = None

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def success(cls, message: str | None = None) -> CommandResult:
        return cls(ok=True, cancelled=False, message=message)

    @classmethod
    def fail(cls, message: str | None = None) -> CommandResult:
        return cls(ok=False, cancelled=False, message=message)

    @classmethod
    def cancel(cls, message: str | None = None) -> CommandResult:
        return cls(ok=True, cancelled=True, message=message)


class CommandExecutor:
    """Safely dispatches and executes parsed commands."""

    def __init__(self, registry: CommandRegistry, console: Console | None = None) -> None:
        self.registry = registry
        self.console = console if console is not None else Console()
        self.last_mood: str = "neutral"

    def execute(self, parsed: ParsedCommand, context: Any) -> CommandResult:
        """Execute a parsed command with the given shell context.
        
        Returns:
            CommandResult reflecting success, failure, or cancellation.
        """
        # Resolve aliases if AliasManager is present on context
        alias_mgr = getattr(context, "alias_manager", None)
        if alias_mgr:
            from core.exceptions import AliasLoopError
            try:
                resolved_name, resolved_args = alias_mgr.resolve(parsed.name, parsed.args)
                if resolved_name != parsed.name or resolved_args != parsed.args:
                    parsed = ParsedCommand(name=resolved_name, args=resolved_args, raw=parsed.raw)
            except AliasLoopError as loop_err:
                self.last_mood = "worried"
                self.last_result = CommandResult.fail(str(loop_err))
                if hasattr(context, "last_mood"):
                    context.last_mood = "worried"
                logger.warning("Command failed or refused: %s", parsed.name)
                hist_mgr = getattr(context, "history_manager", None)
                if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                    hist_mgr.update_last_status(success=False)
                self.console.print(f"[bold red]Alias Loop Error:[/bold red] {loop_err}")
                return False

        cmd_info = self.registry.get(parsed.name)
        if not cmd_info:
            self.last_mood = "worried"
            self.last_result = CommandResult.fail("Command not found")
            if hasattr(context, "last_mood"):
                context.last_mood = "worried"
            logger.warning("Command failed or refused: %s", parsed.name)
            hist_mgr = getattr(context, "history_manager", None)
            if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                hist_mgr.update_last_status(success=False)

            suggestions = self.registry.suggest(parsed.name)
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
            handler_res = cmd_info.handler(context, parsed.args)

            # Normalize return value
            if isinstance(handler_res, CommandResult):
                result = handler_res
            elif handler_res is False:
                result = CommandResult.fail()
            else:
                result = CommandResult.success()

            self.last_result = result

            # Set reactive mood and history status based on outcome
            if result.cancelled:
                self.last_mood = "neutral"
                hist_mgr = getattr(context, "history_manager", None)
                if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                    hist_mgr.update_last_status(success=True)
            elif not result.ok:
                self.last_mood = "worried"
                logger.warning("Command failed or refused: %s", parsed.name)
                hist_mgr = getattr(context, "history_manager", None)
                if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                    hist_mgr.update_last_status(success=False)
            else:
                self.last_mood = "happy"
                hist_mgr = getattr(context, "history_manager", None)
                if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                    hist_mgr.update_last_status(success=True)

            if hasattr(context, "last_mood"):
                context.last_mood = self.last_mood

            return result.ok

        except ArgumentError as arg_err:
            self.last_mood = "worried"
            self.last_result = CommandResult.fail(str(arg_err))
            if hasattr(context, "last_mood"):
                context.last_mood = "worried"
            logger.warning("Command failed or refused: %s", parsed.name)
            hist_mgr = getattr(context, "history_manager", None)
            if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                hist_mgr.update_last_status(success=False)
            self.console.print(f"[bold red]Error:[/bold red] {arg_err}")
            self.console.print(f"  Usage: [dim]{cmd_info.usage}[/dim]")
            return False

        except CommandCancelled as cancel_err:
            self.last_mood = "neutral"
            self.last_result = CommandResult.cancel(str(cancel_err))
            if hasattr(context, "last_mood"):
                context.last_mood = "neutral"
            hist_mgr = getattr(context, "history_manager", None)
            if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                hist_mgr.update_last_status(success=True)
            if str(cancel_err):
                self.console.print(str(cancel_err))
            return True

        except CommandError as cmd_err:
            self.last_mood = "worried"
            self.last_result = CommandResult.fail(str(cmd_err))
            if hasattr(context, "last_mood"):
                context.last_mood = "worried"
            logger.warning("Command failed or refused: %s", parsed.name)
            hist_mgr = getattr(context, "history_manager", None)
            if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                hist_mgr.update_last_status(success=False)
            if str(cmd_err):
                self.console.print(f"[bold red]Error:[/bold red] {cmd_err}")
            return False

        except Exception as exc:
            self.last_mood = "worried"
            self.last_result = CommandResult.fail(str(exc))
            if hasattr(context, "last_mood"):
                context.last_mood = "worried"
            logger.warning("Command failed or refused: %s", parsed.name)
            hist_mgr = getattr(context, "history_manager", None)
            if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                hist_mgr.update_last_status(success=False)
            logger.error("Unhandled error executing '%s': %s\n%s", parsed.name, exc, traceback.format_exc())
            self.console.print(f"[bold red]Execution error in '{parsed.name}':[/bold red] {exc}")
            return False
