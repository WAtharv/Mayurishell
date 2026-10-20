"""Customization commands: alias, aliases, unalias, commands, command-info, config."""
from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table

from commands.applications import check_shortcut_collision
from core.exceptions import AliasConflictError, AliasLoopError
from core.registry import ArgumentRules, CommandInfo, CommandRegistry


def create_alias_launcher_handler(alias_name: str, target: str):
    """Factory to create a command handler for an alias shortcut."""
    def handler(context: Any, args: list[str]) -> None:
        # Alias is resolved and executed through the shell's alias resolver
        pass
    return handler


def handle_alias(context: Any, args: list[str]) -> None:
    """Create a new command alias or list existing aliases."""
    console = context.console
    alias_mgr = context.alias_manager

    if not args:
        handle_aliases(context, [])
        return

    name = args[0].strip().lower()
    if len(args) == 1:
        # Show specific alias
        target = alias_mgr.get(name)
        if target:
            console.print(f"[bold cyan]{name}[/bold cyan] -> '[yellow]{target}[/yellow]'")
        else:
            console.print(f"[bold red]Alias not found:[/bold red] '{name}'")
        return

    # Target is the rest of the arguments joined
    target_cmd = " ".join(args[1:]).strip()

    # Validate name against collision
    err = check_shortcut_collision(name, "aliases", context)
    if err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        return

    try:
        alias_mgr.add_alias(name, target_cmd, registry=context.registry)
        
        # Register in registry for tab-completion
        context.registry.register(
            CommandInfo(
                name=name,
                description=f"Alias for: {target_cmd}",
                handler=create_alias_launcher_handler(name, target_cmd),
                usage=f"{name} [args...]",
                category="Aliases",
            )
        )
        console.print(f"[green]Alias registered: '[bold cyan]{name}[/bold cyan]' -> '[yellow]{target_cmd}[/yellow]'[/green]")
    except (AliasLoopError, AliasConflictError, ValueError) as exc:
        console.print(f"[bold red]Failed to create alias:[/bold red] {exc}")


def handle_aliases(context: Any, args: list[str]) -> None:
    """List all configured command aliases."""
    console = context.console
    aliases = context.alias_manager.get_all()

    if not aliases:
        console.print("[dim]No aliases configured.[/dim]")
        return

    table = Table(
        title="[bold magenta]Configured Aliases[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
    )
    table.add_column("Alias", style="bold cyan", no_wrap=True)
    table.add_column("Target Command", style="yellow")

    for name, target in sorted(aliases.items()):
        table.add_row(name, target)

    console.print(table)
    console.print("[dim]Create a new alias with [bold cyan]alias <name> <command>[/bold cyan], or remove one with [bold cyan]unalias <name>[/bold cyan].[/dim]\n")


def handle_unalias(context: Any, args: list[str]) -> None:
    """Remove a configured alias."""
    console = context.console
    alias_mgr = context.alias_manager
    name = args[0].strip().lower()

    if alias_mgr.remove_alias(name):
        context.registry.unregister(name)
        console.print(f"[green]Alias '[bold cyan]{name}[/bold cyan]' removed.[/green]")
    else:
        console.print(f"[bold red]Alias not found:[/bold red] '{name}'")


def handle_commands(context: Any, args: list[str]) -> None:
    """List all available commands and shortcuts."""
    registry: CommandRegistry = context.registry
    console = context.console

    table = Table(
        title="[bold magenta]All Available Commands and Shortcuts[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
    )
    table.add_column("Category", style="green", no_wrap=True)
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Description", style="white")

    all_cmds = registry.list_commands()
    for cmd in all_cmds:
        table.add_row(cmd.category, cmd.name, cmd.description)

    console.print(table)
    console.print(f"[dim]Total commands registered: {len(all_cmds)}. Use [bold cyan]command-info <name>[/bold cyan] for details.[/dim]\n")


def handle_command_info(context: Any, args: list[str]) -> None:
    """Display comprehensive information about a command, shortcut, or alias."""
    registry: CommandRegistry = context.registry
    console = context.console
    name = args[0].strip().lower()

    cmd = registry.get(name)
    if not cmd:
        suggestions = registry.suggest(name)
        console.print(f"[bold red]Command not found:[/bold red] '{name}'")
        if suggestions:
            sugg_str = ", ".join(f"[bold cyan]{s}[/bold cyan]" for s in suggestions)
            console.print(f"  Did you mean: {sugg_str}?")
        return

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()
    grid.add_row("Name:", f"[bold cyan]{cmd.name}[/bold cyan]")
    grid.add_row("Category:", f"[green]{cmd.category}[/green]")
    grid.add_row("Usage:", f"[yellow]{cmd.usage}[/yellow]")
    grid.add_row("Description:", cmd.description)

    # If it's an app, website, folder, or alias, show underlying target
    config = context.config
    if cmd.category == "Applications":
        target = config.get_applications().get(name)
        if target:
            grid.add_row("App Target:", f"[dim]{target}[/dim]")
    elif cmd.category == "Websites":
        target = config.get_websites().get(name)
        if target:
            grid.add_row("Website URL:", f"[dim]{target}[/dim]")
    elif cmd.category == "Folders":
        target = config.get_folder_shortcuts().get(name)
        if target:
            grid.add_row("Folder Path:", f"[dim]{target}[/dim]")
    elif cmd.category == "Aliases":
        target = config.get_aliases().get(name)
        if target:
            grid.add_row("Alias Target:", f"[dim]{target}[/dim]")

    console.print(Panel(grid, title=f"[bold pink1]Command Details: {cmd.name}[/bold pink1]", border_style="magenta"))


def handle_config(context: Any, args: list[str]) -> None:
    """Display configuration file and folder locations."""
    console = context.console
    config = context.config

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()
    grid.add_row("Base Directory:", f"[bold white]{config.base_dir}[/bold white]")
    grid.add_row("Config File:", f"[cyan]{config.config_path}[/cyan]")
    grid.add_row("History File:", f"[cyan]{config.history_path}[/cyan]")
    grid.add_row("Logs Directory:", f"[cyan]{config.logs_dir}[/cyan]")
    grid.add_row("Backups Directory:", f"[cyan]{config.backups_dir}[/cyan]")

    console.print(Panel(grid, title="[bold pink1]MayuriShell - Configuration Locations[/bold pink1]", border_style="magenta"))


def register_customization_commands(registry: CommandRegistry, config: Any) -> None:
    """Register customization and inspection commands."""
    registry.register(
        CommandInfo(
            name="alias",
            description="Create an alias or list aliases",
            handler=handle_alias,
            usage="alias [name] [command...]",
            category="Customization",
        )
    )

    registry.register(
        CommandInfo(
            name="aliases",
            description="List all configured command aliases",
            handler=handle_aliases,
            usage="aliases",
            category="Customization",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="unalias",
            description="Remove an alias",
            handler=handle_unalias,
            usage="unalias <name>",
            category="Customization",
            arg_rules=ArgumentRules(min_args=1, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="commands",
            description="List all registered commands and shortcuts",
            handler=handle_commands,
            usage="commands",
            category="General",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="command-info",
            description="Display detailed information about a command or shortcut",
            handler=handle_command_info,
            usage="command-info <name>",
            category="General",
            arg_rules=ArgumentRules(min_args=1, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="config",
            description="Display configuration file locations",
            handler=handle_config,
            usage="config",
            category="General",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    # Register individual aliases as commands
    for name, target in config.get_aliases().items():
        registry.register(
            CommandInfo(
                name=name.lower(),
                description=f"Alias for: {target}",
                handler=create_alias_launcher_handler(name, target),
                usage=f"{name} [args...]",
                category="Aliases",
            )
        )
