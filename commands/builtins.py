"""Built-in commands for MayuriShell: help, clear, exit, history, version."""
from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table

from core.registry import ArgumentRules, CommandInfo, CommandRegistry

if TYPE_CHECKING:
    from core.shell import ShellContext

VERSION = "0.1.0"


def handle_help(context: Any, args: list[str]) -> None:
    """Show available commands or detailed info for a specific command."""
    registry: CommandRegistry = context.registry
    console = context.console

    if args:
        target = args[0].lower()
        cmd = registry.get(target)
        if not cmd:
            suggestions = registry.suggest(target)
            console.print(f"[bold red]Command not found:[/bold red] '{target}'")
            if suggestions:
                sugg_str = ", ".join(f"[bold cyan]{s}[/bold cyan]" for s in suggestions)
                console.print(f"  Did you mean: {sugg_str}?")
            return

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold magenta", justify="right")
        grid.add_column()
        grid.add_row("Command:", f"[bold cyan]{cmd.name}[/bold cyan]")
        grid.add_row("Category:", f"[green]{cmd.category}[/green]")
        grid.add_row("Usage:", f"[yellow]{cmd.usage}[/yellow]")
        grid.add_row("Description:", cmd.description)

        console.print(
            Panel(
                grid,
                title=f"[bold pink1]MayuriShell - Command Info: {cmd.name}[/bold pink1]",
                border_style="magenta",
            )
        )
        return

    # List all commands grouped by category
    table = Table(
        title="[bold magenta]Available Commands[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("Category", style="green", no_wrap=True)
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Usage", style="yellow")
    table.add_column("Description", style="white")

    for cat in registry.get_categories():
        for cmd in registry.list_commands(category=cat):
            table.add_row(cat, cmd.name, cmd.usage, cmd.description)

    console.print(table)
    console.print("[dim]Type [bold cyan]help <command>[/bold cyan] for details on a specific command.[/dim]\n")


def handle_clear(context: Any, args: list[str]) -> None:
    """Clear terminal screen."""
    context.console.clear()


def handle_exit(context: Any, args: list[str]) -> None:
    """Exit MayuriShell gracefully."""
    username = context.config.get("username", "Mayuri")
    context.console.print(f"\n[bold pink1]Goodbye, {username}! (,,•́ω•̀,,)ﾉ See you next time![/bold pink1]")
    context.running = False


def handle_history(context: Any, args: list[str]) -> None:
    """Show command history or clear history."""
    console = context.console
    history_mgr = context.history_manager

    if args:
        subcmd = args[0].lower()
        if subcmd == "clear":
            history_mgr.clear()
            console.print("[green]Command history cleared successfully.[/green]")
            return
        else:
            console.print(f"[bold red]Unknown history subcommand:[/bold red] '{subcmd}'. Usage: [yellow]history [clear][/yellow]")
            return

    entries = history_mgr.get_all()
    if not entries:
        console.print("[dim]No command history recorded yet.[/dim]")
        return

    # Display last 50 entries
    display_entries = entries[-50:]
    table = Table(
        title="[bold magenta]Command History (Recent)[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", justify="right", no_wrap=True)
    table.add_column("Timestamp", style="dim cyan", no_wrap=True)
    table.add_column("Command", style="bold white")

    start_idx = len(entries) - len(display_entries) + 1
    for i, entry in enumerate(display_entries, start=start_idx):
        table.add_row(str(i), entry.get("timestamp", "-"), entry.get("command", ""))

    console.print(table)
    console.print("[dim]Tip: Use [bold cyan]history clear[/bold cyan] to wipe history.[/dim]\n")


def handle_version(context: Any, args: list[str]) -> None:
    """Display MayuriShell version and environment details."""
    console = context.console
    content = (
        f"[bold pink1]MayuriShell[/bold pink1] version [bold cyan]{VERSION}[/bold cyan]\n"
        f"Python: [yellow]{sys.version.split()[0]}[/yellow]\n"
        f"Platform: [green]{platform.system()} {platform.release()} ({platform.machine()})[/green]\n"
        f"Architecture: [dim]{platform.architecture()[0]}[/dim]"
    )
    console.print(Panel(content, title="[bold magenta]Version Info[/bold magenta]", border_style="magenta"))


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
