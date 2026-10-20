"""Customization commands: alias, aliases, unalias, commands, command-info, config."""
from __future__ import annotations

from typing import Any

from rich.markup import escape
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
    theme = context.theme
    alias_mgr = context.alias_manager

    if not args:
        handle_aliases(context, [])
        return

    name = args[0].strip().lower()
    if len(args) == 1:
        # Show specific alias
        target = alias_mgr.get(name)
        if target:
            console.print(f"{theme.format_primary(escape(name), bold=True)} -> '{theme.format_warning(escape(target))}'")
        else:
            console.print(f"{theme.format_error('Alias not found:')} '{escape(name)}'")
        return

    # Target is the rest of the arguments joined
    target_cmd = " ".join(args[1:]).strip()

    # Validate name against collision
    err = check_shortcut_collision(name, "aliases", context)
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
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
        console.print(
            f"{theme.format_success('Alias registered:')} "
            f"'{theme.format_primary(escape(name), bold=True)}' -> "
            f"'{theme.format_warning(escape(target_cmd))}'"
        )
    except (AliasLoopError, AliasConflictError, ValueError) as exc:
        console.print(f"{theme.format_error('Failed to create alias:')} {escape(str(exc))}")


def handle_aliases(context: Any, args: list[str]) -> None:
    """List all configured command aliases."""
    console = context.console
    theme = context.theme
    aliases = context.alias_manager.get_all()

    if not aliases:
        console.print(theme.format_muted("No aliases configured."))
        return

    table = theme.create_table(
        title="Configured Aliases",
    )
    table.add_column("Alias", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Target Command", style=theme.warning_style)

    for name, target in sorted(aliases.items()):
        table.add_row(escape(name), escape(target))

    console.print(table)
    console.print(
        f"{theme.format_muted('Create a new alias with ')}"
        f"{theme.format_primary('alias <name> <command>', bold=True)}"
        f"{theme.format_muted(', or remove one with ')}"
        f"{theme.format_primary('unalias <name>', bold=True)}"
        f"{theme.format_muted('.')}\n"
    )


def handle_unalias(context: Any, args: list[str]) -> None:
    """Remove a configured alias."""
    console = context.console
    theme = context.theme
    alias_mgr = context.alias_manager
    name = args[0].strip().lower()

    if alias_mgr.remove_alias(name):
        context.registry.unregister(name)
        console.print(f"{theme.format_success('Alias')} '{theme.format_primary(escape(name), bold=True)}' {theme.format_success('removed.')}")
    else:
        console.print(f"{theme.format_error('Alias not found:')} '{escape(name)}'")


def handle_commands(context: Any, args: list[str]) -> None:
    """List all available commands and shortcuts."""
    registry: CommandRegistry = context.registry
    console = context.console
    theme = context.theme

    table = theme.create_table(
        title="All Available Commands and Shortcuts",
    )
    table.add_column("Category", style=theme.success_style, no_wrap=True)
    table.add_column("Command", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Description", style=theme.text_style)

    all_cmds = registry.list_commands()
    for cmd in all_cmds:
        table.add_row(cmd.category, cmd.name, cmd.description)

    console.print(table)
    console.print(
        f"{theme.format_muted(f'Total commands registered: {len(all_cmds)}. Use ')}"
        f"{theme.format_primary('command-info <name>', bold=True)}"
        f"{theme.format_muted(' for details.')}\n"
    )


def handle_command_info(context: Any, args: list[str]) -> None:
    """Display comprehensive information about a command, shortcut, or alias."""
    registry: CommandRegistry = context.registry
    console = context.console
    theme = context.theme
    name = args[0].strip().lower()

    cmd = registry.get(name)
    if not cmd:
        suggestions = registry.suggest(name)
        console.print(f"{theme.format_error('Command not found:')} '{escape(name)}'")
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

    # If it's an app, website, folder, or alias, show underlying target
    config = context.config
    if cmd.category == "Applications":
        target = config.get_applications().get(name)
        if target:
            grid.add_row("App Target:", theme.format_muted(escape(target)))
    elif cmd.category == "Websites":
        target = config.get_websites().get(name)
        if target:
            grid.add_row("Website URL:", theme.format_muted(escape(target)))
    elif cmd.category == "Folders":
        target = config.get_folder_shortcuts().get(name)
        if target:
            grid.add_row("Folder Path:", theme.format_muted(escape(target)))
    elif cmd.category == "Aliases":
        target = config.get_aliases().get(name)
        if target:
            grid.add_row("Alias Target:", theme.format_muted(escape(target)))

    console.print(theme.create_panel(grid, title=f"Command Details: {escape(cmd.name)}"))


def handle_config(context: Any, args: list[str]) -> None:
    """Display configuration file and folder locations."""
    console = context.console
    theme = context.theme
    config = context.config

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=theme.bold_accent_style, justify="right")
    grid.add_column(overflow="fold")
    grid.add_row("Base Directory:", theme.format_text(escape(str(config.base_dir)), bold=True))
    grid.add_row("Config File:", theme.format_primary(escape(str(config.config_path))))
    grid.add_row("History File:", theme.format_primary(escape(str(config.history_path))))
    grid.add_row("Logs Directory:", theme.format_primary(escape(str(config.logs_dir))))
    grid.add_row("Backups Directory:", theme.format_primary(escape(str(config.backups_dir))))

    console.print(theme.create_panel(grid, title="MayuriShell - Configuration Locations"))


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
