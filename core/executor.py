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
    hint: str | None = None

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def success(cls, message: str | None = None) -> CommandResult:
        return cls(ok=True, cancelled=False, message=message)

    @classmethod
    def fail(cls, message: str | None = None, hint: str | None = None) -> CommandResult:
        return cls(ok=False, cancelled=False, message=message, hint=hint)

    @classmethod
    def cancel(cls, message: str | None = None) -> CommandResult:
        return cls(ok=True, cancelled=True, message=message)


class CommandExecutor:
    """Safely dispatches and executes parsed commands."""

    def __init__(self, registry: CommandRegistry, console: Console | None = None) -> None:
        self.registry = registry
        self.console = console if console is not None else Console()
        self.last_mood: str = "neutral"
        self._unknown_command_count: int = 0

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

        theme = getattr(context, "theme", None)
        is_plain = theme.is_plain if theme else True

        cmd_info = self.registry.get(parsed.name)
        if not cmd_info:
            self.last_mood = "worried"
            self.last_result = CommandResult.fail(
                "Command not found",
                hint="Type 'help' to see all commands or press Tab to complete.",
            )
            if hasattr(context, "last_mood"):
                context.last_mood = "worried"

            # Privacy: never write the typed unknown command or its arguments to the log
            self._unknown_command_count += 1
            logger.warning("Command failed: unknown command (count: %d)", self._unknown_command_count)

            hist_mgr = getattr(context, "history_manager", None)
            if hist_mgr and hasattr(hist_mgr, "update_last_status"):
                hist_mgr.update_last_status(success=False)

            from rich.markup import escape
            from core.suggestions import (
                is_secret_like,
                suggest_command_corrections,
                should_prefill,
                get_history_suggestions,
                get_directory_hints,
                get_available_app_hints,
                DESTRUCTIVE_COMMANDS,
            )

            # Check if input looks like a secret or token
            raw_input = getattr(parsed, "raw", "") or f"{parsed.name} {' '.join(parsed.args)}".strip()
            if is_secret_like(raw_input) or is_secret_like(parsed.name):
                # Ensure secret is not stored in history
                if hist_mgr and hasattr(hist_mgr, "entries") and hist_mgr.entries:
                    if hist_mgr.entries[-1].get("command", "").strip() == raw_input.strip():
                        hist_mgr.entries.pop()
                        try:
                            hist_mgr.save()
                        except Exception:
                            pass
                if theme and not is_plain:
                    self.console.print(theme.format_error("Command not found."))
                else:
                    self.console.print("Command not found.")
                return False

            # Truncate echoed name to 40 characters
            echoed_name = parsed.name[:40]

            is_interactive = getattr(context, "is_interactive", True)
            suggestions_enabled = (
                context.config.get_suggestions_enabled()
                if hasattr(context, "config")
                else False
            )

            if not is_interactive or not suggestions_enabled:
                if theme and not is_plain:
                    self.console.print(f"{theme.format_error('Command not found:')} {escape(echoed_name)}")
                else:
                    self.console.print(f"Command not found: {escape(echoed_name)}")
                return False

            cat_face = "(=;.;=)" if is_plain else "(=;･ω･;=)"
            hint_str = "Type 'help' to see all commands or press Tab to complete."
            if theme and not is_plain:
                self.console.print(f"{theme.format_error('Command not found:')} {escape(echoed_name)} {cat_face}")
                self.console.print(f"  {theme.format_muted(f'Hint: {hint_str}')}")
            else:
                self.console.print(f"Command not found: {escape(echoed_name)} {cat_face}")
                self.console.print(f"  Hint: {hint_str}")

            corrections = suggest_command_corrections(parsed.name, parsed.args, context)
            if corrections:
                if theme and not is_plain:
                    self.console.print(theme.format_text("Did you mean?", bold=True))
                else:
                    self.console.print("Did you mean?")

                for corr in corrections:
                    base_cand = corr.split()[0].lower()
                    if base_cand in DESTRUCTIVE_COMMANDS:
                        # Show only command name and usage, never arguments
                        if theme and not is_plain:
                            self.console.print(f"  {theme.format_primary('->', bold=True)} {theme.format_accent(escape(base_cand))}")
                        else:
                            self.console.print(f"  -> {escape(base_cand)}")
                        cand_info = self.registry.get(base_cand)
                        if cand_info and cand_info.usage:
                            self.console.print(f"  Usage: {escape(cand_info.usage)}")
                    else:
                        if theme and not is_plain:
                            self.console.print(f"  {theme.format_primary('->', bold=True)} {theme.format_accent(escape(corr))}")
                        else:
                            self.console.print(f"  -> {escape(corr)}")
                        if self.registry.has_command(base_cand) and not corr.startswith("help "):
                            if theme and not is_plain:
                                self.console.print(f"  {theme.format_primary('->', bold=True)} help {theme.format_accent(escape(base_cand))}")
                            else:
                                self.console.print(f"  -> help {escape(base_cand)}")

                # Safe prefill check
                can_prefill, prefill_line = should_prefill(corrections, context, is_interactive)
                if can_prefill and prefill_line:
                    shell_obj = getattr(context, "shell", None)
                    if shell_obj and hasattr(shell_obj, "next_prefill"):
                        shell_obj.next_prefill = prefill_line
                    elif hasattr(context, "next_prefill"):
                        context.next_prefill = prefill_line

                    prefill_msg = f"Prefilled prompt with '{prefill_line}'. Press Enter to run."
                    if theme and not is_plain:
                        self.console.print(f"  {theme.format_muted(escape(prefill_msg))}")
                    else:
                        self.console.print(f"  {escape(prefill_msg)}")

                # Extra suggestions
                first_base = corrections[0].split()[0].lower()
                hist_suggs = get_history_suggestions(first_base, context)
                for hs in hist_suggs:
                    self.console.print(f"  Recent: {escape(hs)}")

                cur_dir = getattr(context, "current_dir", None)
                dir_hints = get_directory_hints(cur_dir)
                if dir_hints:
                    self.console.print(f"  Directory hints: {', '.join(dir_hints)}")

                app_hints = get_available_app_hints(parsed.name, context)
                for ah in app_hints:
                    if ah.startswith("add-app"):
                        self.console.print(f"  Available app: {escape(ah)}")
                    else:
                        self.console.print(f"  -> {escape(ah)}")

            tip_msg = "Tip: Press Tab while typing to complete commands."
            if theme and not is_plain:
                self.console.print(theme.format_muted(tip_msg))
            else:
                self.console.print(tip_msg)

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

                # Print hint if available
                if result.hint:
                    if theme and not is_plain:
                        self.console.print(f"  {theme.format_muted(f'Hint: {result.hint}')}")
                    else:
                        self.console.print(f"  Hint: {result.hint}")

                # Check argument suggestions on failure
                is_interactive = getattr(context, "is_interactive", True)
                suggestions_enabled = (
                    context.config.get_suggestions_enabled()
                    if hasattr(context, "config")
                    else False
                )
                if is_interactive and suggestions_enabled and parsed.args:
                    from rich.markup import escape
                    from core.suggestions import suggest_arguments
                    arg_sugg = suggest_arguments(parsed.name, parsed.args, context)
                    if arg_sugg:
                        sugg_cmds, usage_str = arg_sugg
                        if theme and not is_plain:
                            self.console.print(theme.format_text("Did you mean?", bold=True))
                        else:
                            self.console.print("Did you mean?")
                        for sc in sugg_cmds:
                            if theme and not is_plain:
                                self.console.print(f"  {theme.format_primary('->', bold=True)} {theme.format_accent(escape(sc))}")
                            else:
                                self.console.print(f"  -> {escape(sc)}")
                        if usage_str:
                            self.console.print(f"Usage: {escape(usage_str)}")
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

            is_interactive = getattr(context, "is_interactive", True)
            suggestions_enabled = (
                context.config.get_suggestions_enabled()
                if hasattr(context, "config")
                else False
            )
            if is_interactive and suggestions_enabled and parsed.args:
                from rich.markup import escape
                from core.suggestions import suggest_arguments
                arg_sugg = suggest_arguments(parsed.name, parsed.args, context)
                if arg_sugg:
                    sugg_cmds, _ = arg_sugg
                    if theme and not is_plain:
                        self.console.print(theme.format_text("Did you mean?", bold=True))
                    else:
                        self.console.print("Did you mean?")
                    for sc in sugg_cmds:
                        if theme and not is_plain:
                            self.console.print(f"  {theme.format_primary('->', bold=True)} {theme.format_accent(escape(sc))}")
                        else:
                            self.console.print(f"  -> {escape(sc)}")
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
