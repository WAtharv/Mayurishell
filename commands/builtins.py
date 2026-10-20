"""Built-in commands for MayuriShell: help, clear, exit, history, version."""
from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING, Any

from rich.markup import escape
from rich.table import Table

from core.registry import ArgumentRules, CommandInfo, CommandRegistry

if TYPE_CHECKING:
    from core.shell import ShellContext

VERSION = "0.1.0"


def handle_help(context: Any, args: list[str]) -> None:
    """Show available commands or detailed info for a specific command."""
    registry: CommandRegistry = context.registry
    console = context.console
    theme = context.theme

    if args:
        target = args[0].lower()
        cmd = registry.get(target)
        if not cmd:
            suggestions = registry.suggest(target)
            console.print(f"{theme.format_error('Command not found:')} '{escape(target)}'")
            if suggestions:
                sugg_str = ", ".join(theme.format_primary(s, bold=True) for s in suggestions)
                console.print(f"  Did you mean: {sugg_str}?")
            return

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=theme.bold_accent_style, justify="right")
        grid.add_column(overflow="fold")
        grid.add_row("Command:", theme.format_primary(cmd.name, bold=True))
        grid.add_row("Category:", theme.format_success(cmd.category))
        grid.add_row("Usage:", theme.format_warning(cmd.usage))
        grid.add_row("Description:", escape(cmd.description))

        console.print(
            theme.create_panel(
                grid,
                title=f"MayuriShell - Command Info: {escape(cmd.name)}",
            )
        )
        return

    # List all commands grouped by category
    table = theme.create_table(
        title="Available Commands",
        show_lines=False,
    )
    table.add_column("Category", style=theme.success_style, no_wrap=True)
    table.add_column("Command", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Usage", style=theme.warning_style)
    table.add_column("Description", style=theme.text_style)

    for cat in registry.get_categories():
        for cmd in registry.list_commands(category=cat):
            table.add_row(cat, cmd.name, cmd.usage, cmd.description)

    console.print(table)
    console.print(
        f"{theme.format_muted('Type ')}{theme.format_primary('help <command>', bold=True)}{theme.format_muted(' for details on a specific command.')}\n"
    )


def handle_clear(context: Any, args: list[str]) -> None:
    """Clear terminal screen."""
    context.console.clear()


def handle_exit(context: Any, args: list[str]) -> None:
    """Exit MayuriShell gracefully."""
    theme = context.theme
    username = escape(context.config.get("username", "Mayuri"))
    if theme.is_plain:
        context.console.print(f"\nGoodbye, {username}! (^_^)/ See you next time!")
    else:
        context.console.print(f"\n{theme.format_primary(f'Goodbye, {username}! (,,•́ω•̀,,)ﾉ See you next time!', bold=True)}")
    context.running = False


def handle_history(context: Any, args: list[str]) -> None:
    """Show command history or clear history."""
    console = context.console
    theme = context.theme
    history_mgr = context.history_manager

    if args:
        subcmd = args[0].lower()
        if subcmd == "clear":
            history_mgr.clear()
            console.print(theme.format_success("Command history cleared successfully."))
            return
        else:
            console.print(
                f"{theme.format_error('Unknown history subcommand:')} '{escape(subcmd)}'. "
                f"Usage: {theme.format_warning('history [clear]')}"
            )
            return

    entries = history_mgr.get_all()
    if not entries:
        console.print(theme.format_muted("No command history recorded yet."))
        return

    # Display last 50 entries
    display_entries = entries[-50:]
    table = theme.create_table(
        title="Command History (Recent)",
    )
    table.add_column("#", style=theme.muted_style, justify="right", no_wrap=True)
    table.add_column("Timestamp", style=theme.muted_style, no_wrap=True)
    table.add_column("Command", style=theme.bold_text_style)

    start_idx = len(entries) - len(display_entries) + 1
    for i, entry in enumerate(display_entries, start=start_idx):
        table.add_row(str(i), escape(entry.get("timestamp", "-")), escape(entry.get("command", "")))

    console.print(table)
    console.print(
        f"{theme.format_muted('Tip: Use ')}{theme.format_primary('history clear', bold=True)}{theme.format_muted(' to wipe history.')}\n"
    )


def handle_version(context: Any, args: list[str]) -> None:
    """Display MayuriShell version and environment details."""
    console = context.console
    theme = context.theme
    content = (
        f"{theme.format_primary('MayuriShell', bold=True)} version {theme.format_primary(VERSION, bold=True)}\n"
        f"Python: {theme.format_warning(sys.version.split()[0])}\n"
        f"Platform: {theme.format_success(f'{platform.system()} {platform.release()} ({platform.machine()})')}\n"
        f"Architecture: {theme.format_muted(platform.architecture()[0])}"
    )
    console.print(theme.create_panel(content, title="Version Info"))


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register all Stage 1 core built-in commands."""
    registry.register(
        CommandInfo(
            name="help",
            description="Display command list or details for a specific command",
            handler=handle_help,
            usage="help [command]",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="clear",
            description="Clear the terminal screen",
            handler=handle_clear,
            usage="clear",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="exit",
            description="Exit MayuriShell gracefully",
            handler=handle_exit,
            usage="exit",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="history",
            description="Display command history or clear stored history",
            handler=handle_history,
            usage="history [clear]",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="version",
            description="Display MayuriShell and runtime version information",
            handler=handle_version,
            usage="version",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
