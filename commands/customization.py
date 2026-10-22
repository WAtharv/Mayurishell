"""Customization commands: alias, aliases, unalias, commands, command-info, config."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.markup import escape
from rich.table import Table

from commands.applications import check_shortcut_collision
from commands.files import confirm_prompt
from core.exceptions import AliasConflictError, AliasLoopError
from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.config_service import (
    apply_imported_config,
    backup_config,
    build_import_preview,
    export_config,
    is_safe_regular_file,
    list_backups,
    load_and_validate_import_file,
    restore_config,
    validate_backup_data,
)


def create_alias_launcher_handler(alias_name: str, target: str):
    """Factory to create a command handler for an alias shortcut."""
    def handler(context: Any, args: list[str]) -> CommandResult:
        # Alias is resolved and executed through the shell's alias resolver
        return CommandResult.success()
    return handler


def handle_alias(context: Any, args: list[str]) -> CommandResult:
    """Create a new command alias or list existing aliases."""
    console = context.console
    theme = context.theme
    alias_mgr = context.alias_manager

    if not args:
        return handle_aliases(context, [])

    name = args[0].strip().lower()
    if len(args) == 1:
        # Show specific alias
        target = alias_mgr.get(name)
        if target:
            console.print(f"{theme.format_primary(escape(name), bold=True)} -> '{theme.format_warning(escape(target))}'")
            return CommandResult.success()
        else:
            console.print(f"{theme.format_error('Alias not found:')} '{escape(name)}'")
            return CommandResult.fail()

    # Target is the rest of the arguments joined
    target_cmd = " ".join(args[1:]).strip()

    # Validate name against collision
    err = check_shortcut_collision(name, "aliases", context)
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail()

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
        return CommandResult.success()
    except (AliasLoopError, AliasConflictError, ValueError) as exc:
        console.print(f"{theme.format_error('Failed to create alias:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_aliases(context: Any, args: list[str]) -> CommandResult:
    """List all configured command aliases."""
    console = context.console
    theme = context.theme
    aliases = context.alias_manager.get_all()

    if not aliases:
        console.print(theme.format_muted("No aliases configured."))
        return CommandResult.success()

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
    return CommandResult.success()


def handle_unalias(context: Any, args: list[str]) -> CommandResult:
    """Remove a configured alias."""
    console = context.console
    theme = context.theme
    alias_mgr = context.alias_manager
    name = args[0].strip().lower()

    if alias_mgr.remove_alias(name):
        context.registry.unregister(name)
        console.print(f"{theme.format_success('Alias')} '{theme.format_primary(escape(name), bold=True)}' {theme.format_success('removed.')}")
        return CommandResult.success()
    else:
        console.print(f"{theme.format_error('Alias not found:')} '{escape(name)}'")
        return CommandResult.fail()


def handle_commands(context: Any, args: list[str]) -> CommandResult:
    """List all available commands and shortcuts."""
    registry: CommandRegistry = context.registry
    console = context.console
    theme = context.theme

    table = theme.create_table(
        title="All Available Commands and Shortcuts",
    )
    table.add_column("Category", style=theme.success_style, no_wrap=True)
    table.add_column("Command", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Description", style=theme.text_style, overflow="fold")

    all_cmds = registry.list_commands()
    for cmd in all_cmds:
        table.add_row(cmd.category, cmd.name, cmd.description)

    console.print(table)
    console.print(
        f"{theme.format_muted(f'Total commands registered: {len(all_cmds)}. Use ')}"
        f"{theme.format_primary('command-info <name>', bold=True)}"
        f"{theme.format_muted(' for details.')}\n"
    )
    return CommandResult.success()


def handle_command_info(context: Any, args: list[str]) -> CommandResult:
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
        return CommandResult.fail()

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
    return CommandResult.success()


def handle_config_export(context: Any, sub_args: list[str]) -> CommandResult:
    """Export configuration to a sanitized JSON file."""
    console = context.console
    theme = context.theme
    config = context.config

    target_arg = sub_args[0] if sub_args else None
    cwd = getattr(context, "cwd", Path.cwd())

    success, msg, dest, summary = export_config(config, target_path=target_arg, cwd=cwd)
    if not success:
        console.print(f"{theme.format_error('Export Failed:')} {escape(msg)}")
        return CommandResult.fail(msg, hint="Choose an unused destination file path or verify directory permissions.")

    console.print(theme.format_success(msg, bold=True))
    console.print(f"\n{theme.format_accent('Included Sections:', bold=True)} {escape(', '.join(summary['included']))}")
    if summary["machine_specific_paths"]:
        console.print(f"{theme.format_warning('Machine-Specific Absolute Paths:', bold=True)}")
        for msp in summary["machine_specific_paths"]:
            console.print(f"  * {escape(msp)}")
    console.print(f"{theme.format_muted('Excluded Items (Privacy):')} {escape(', '.join(summary['excluded']))}")
    console.print(
        f"\n{theme.format_warning('Security Notice:', bold=True)} "
        f"Exported files contain configured folder shortcuts and application paths. "
        f"Only share this file with people you trust.\n"
    )
    return CommandResult.success()


def handle_config_import(context: Any, sub_args: list[str]) -> CommandResult:
    """Import and validate configuration settings from an exported JSON file."""
    console = context.console
    theme = context.theme
    config = context.config

    if not sub_args:
        console.print(f"{theme.format_error('Usage:')} config import <file> [--dry-run] [--overwrite]")
        return CommandResult.fail("Missing import file path", hint="Usage: config import <file> [--dry-run] [--overwrite]")

    dry_run = any(arg.lower() in ("--dry-run", "-n") for arg in sub_args)
    overwrite = any(arg.lower() in ("--overwrite", "-o") for arg in sub_args)
    file_args = [arg for arg in sub_args if not arg.startswith("-")]

    if not file_args:
        console.print(f"{theme.format_error('Error:')} No file path specified for import.")
        return CommandResult.fail("Missing file path", hint="Usage: config import <file> [--dry-run] [--overwrite]")

    raw_path = file_args[0]
    cwd = getattr(context, "cwd", Path.cwd())
    resolved_path = (cwd / Path(raw_path)).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()

    # Load and validate file headers / size / schema
    ok, err, imported_data, warnings = load_and_validate_import_file(resolved_path)
    if not ok:
        console.print(f"{theme.format_error('Import Error:')} {escape(err)}")
        return CommandResult.fail(err)

    for warn in warnings:
        console.print(theme.format_warning(f"Warning: {escape(warn)}"))

    assert imported_data is not None
    # Build preview
    preview = build_import_preview(config, imported_data, context)

    # Display Preview Table
    table = theme.create_table(title="Configuration Import Preview")
    table.add_column("Status", justify="center", style=theme.bold_text_style, no_wrap=True)
    table.add_column("Category", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Item", style=theme.bold_accent_style, no_wrap=True)
    table.add_column("Details", style=theme.text_style, overflow="fold")

    for cat, name, detail in preview["added"]:
        tag = "[ADDED]" if theme.is_plain else theme.format_success("[ADDED]", bold=True)
        table.add_row(tag, escape(cat), escape(name), escape(str(detail)))

    for cat, name, detail in preview["conflicting"]:
        act = "(will replace)" if overwrite else "(will skip without --overwrite)"
        tag = "[CONFLICT]" if theme.is_plain else theme.format_warning("[CONFLICT]", bold=True)
        table.add_row(tag, escape(cat), escape(name), f"{escape(str(detail))} {theme.format_muted(act)}")

    for cat, name, detail in preview["skipped"]:
        tag = "[SKIPPED]" if theme.is_plain else theme.format_error("[SKIPPED]", bold=True)
        table.add_row(tag, escape(cat), escape(name), escape(str(detail)))

    for cat, name, detail in preview["unchanged"]:
        tag = "[SAME]" if theme.is_plain else theme.format_muted("[SAME]")
        table.add_row(tag, escape(cat), escape(name), escape(str(detail)))

    console.print(table)

    # Display App Shortcuts Detail
    if preview["app_shortcuts"]:
        console.print(f"\n{theme.format_warning('Application Shortcuts to Import:', bold=True)}")
        for app_name, app_target in preview["app_shortcuts"]:
            console.print(f"  * {theme.format_primary(escape(app_name), bold=True)} -> {escape(app_target)}")
        console.print(
            f"{theme.format_warning('Security Warning:')} "
            f"Imported application shortcuts will execute programs when typed in the shell. "
            f"These programs are launched when you type their name. "
            f"Only import from sources you trust.\n"
        )

    # Display Workflows Detail with Resolved Targets
    if preview["workflow_steps_detail"]:
        console.print(f"\n{theme.format_primary('Workflow Steps Detail:', bold=True)}")
        for wf_name, step_list in preview["workflow_steps_detail"]:
            console.print(f"  Workflow '{theme.format_accent(escape(wf_name), bold=True)}':")
            for s_info in step_list:
                mark = ""
                if not s_info.get("shortcut_on_pc", True):
                    mark = f" {theme.format_error('[SHORTCUT NOT FOUND ON THIS PC]')}"
                elif not s_info.get("exists_on_pc", True):
                    mark = f" {theme.format_warning('[TARGET NOT FOUND ON THIS PC]')}"
                console.print(f"    - {escape(str(s_info['step']))} ({theme.format_muted(escape(s_info['target']))}){mark}")
        console.print()

    # Dry-run termination
    if dry_run:
        console.print(theme.format_muted("[Dry Run] Preview complete. No changes were applied to configuration."))
        return CommandResult.success()

    # Check if there are any applicable changes
    applicable_changes = len(preview["added"]) + (len(preview["conflicting"]) if overwrite else 0)
    if applicable_changes == 0:
        console.print(theme.format_muted("No new or applicable changes found to import."))
        return CommandResult.success()

    # Confirm general import
    confirm_msg = "Apply imported configuration changes to your MayuriShell setup?"
    if not confirm_prompt(console, confirm_msg, default_yes=False, theme=theme):
        console.print(theme.format_muted("Import cancelled by user."))
        return CommandResult.cancel()

    # Separate confirmation for app shortcuts
    include_apps = False
    if preview["app_shortcuts"]:
        app_confirm_msg = f"Import {len(preview['app_shortcuts'])} application shortcut(s)? (App shortcuts can launch programs)"
        include_apps = confirm_prompt(console, app_confirm_msg, default_yes=False, theme=theme)
        if not include_apps:
            console.print(theme.format_muted("Skipping application shortcuts as requested."))

    # Apply atomically with automatic pre-import backup
    success, apply_msg = apply_imported_config(
        config,
        imported_data,
        preview,
        overwrite=overwrite,
        include_apps=include_apps,
        context=context,
    )

    if not success:
        console.print(f"{theme.format_error('Import Failed:')} {escape(apply_msg)}")
        return CommandResult.fail(apply_msg)

    console.print(theme.format_success(apply_msg, bold=True))
    return CommandResult.success()


def handle_config_backup(context: Any, sub_args: list[str]) -> CommandResult:
    """Create a timestamped backup of config.json."""
    console = context.console
    theme = context.theme
    config = context.config

    success, msg, _ = backup_config(config)
    if success:
        console.print(theme.format_success(msg, bold=True))
        return CommandResult.success()
    else:
        console.print(f"{theme.format_error('Backup Failed:')} {escape(msg)}")
        return CommandResult.fail(msg)


def handle_config_restore(context: Any, sub_args: list[str]) -> CommandResult:
    """List available backups or restore configuration from a backup file."""
    console = context.console
    theme = context.theme
    config = context.config

    if not sub_args:
        # List backups
        backups = list_backups(config)
        if not backups:
            console.print(theme.format_muted("No configuration backups found in backups/."))
            return CommandResult.success()

        table = theme.create_table(title="Available Configuration Backups")
        table.add_column("Backup Name", style=theme.bold_primary_style, no_wrap=True)
        table.add_column("Created / Modified", style=theme.text_style, no_wrap=True)
        table.add_column("Size", justify="right", style=theme.muted_style, no_wrap=True)

        for b in backups:
            table.add_row(escape(b["name"]), escape(b["modified"]), escape(b["size_str"]))

        console.print(table)
        console.print(
            f"{theme.format_muted('Restore a backup with: ')}"
            f"{theme.format_primary('config restore <backup-name>', bold=True)}\n"
        )
        return CommandResult.success()

    backup_name = sub_args[0].strip()

    if "/" in backup_name or "\\" in backup_name or ".." in backup_name:
        err = "Backup name must be a plain file name inside backups/ without directory separators."
        console.print(f"{theme.format_error('Invalid Backup Name:')} {err}")
        return CommandResult.fail(err, hint="Use 'config restore' to list available backup names.")

    # Pre-validate before touching current configuration
    target_backup_file = config.backups_dir / backup_name
    is_safe, err_file = is_safe_regular_file(target_backup_file)
    if not is_safe:
        console.print(f"{theme.format_error('Invalid Backup:')} {escape(err_file)}")
        return CommandResult.fail(err_file, hint="Use 'config restore' to list available backup names.")

    if target_backup_file.resolve().parent != config.backups_dir.resolve():
        err = "Backup file must reside directly in backups/ directory."
        console.print(f"{theme.format_error('Invalid Backup:')} {err}")
        return CommandResult.fail(err)

    try:
        with open(target_backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
    except Exception as exc:
        err = f"Backup file '{backup_name}' is corrupted or invalid JSON: {exc}"
        console.print(f"{theme.format_error('Restore Refused:')} {escape(err)}")
        return CommandResult.fail(err)

    valid_struct, struct_err = validate_backup_data(backup_data)
    if not valid_struct:
        err = f"Backup file '{backup_name}' is corrupt: {struct_err}"
        console.print(f"{theme.format_error('Restore Refused:')} {escape(err)}")
        return CommandResult.fail(err)

    # Show preview of the backup
    theme_val = backup_data.get("theme", "-")
    mascot_val = backup_data.get("mascot", "-")
    apps_cnt = len(backup_data.get("applications", {}))
    folders_cnt = len(backup_data.get("folder_shortcuts", {}))
    web_cnt = len(backup_data.get("websites", {}))
    aliases_cnt = len(backup_data.get("aliases", {}))
    wf_cnt = len(backup_data.get("workflows", {}))

    console.print(
        f"{theme.format_primary('Backup Summary:', bold=True)} '{escape(backup_name)}'\n"
        f"  Theme: {theme_val} | Mascot: {mascot_val}\n"
        f"  Contents: {apps_cnt} apps, {folders_cnt} folders, {web_cnt} websites, {aliases_cnt} aliases, {wf_cnt} workflows\n"
    )

    confirm_msg = f"Restore configuration from '{backup_name}'? Current settings will be backed up first."
    if not confirm_prompt(console, confirm_msg, default_yes=False, theme=theme):
        console.print(theme.format_muted("Restore cancelled by user."))
        return CommandResult.cancel()

    success, msg, _ = restore_config(config, backup_name, context=context)
    if not success:
        console.print(f"{theme.format_error('Restore Failed:')} {escape(msg)}")
        return CommandResult.fail(msg)

    console.print(theme.format_success(msg, bold=True))
    return CommandResult.success()


def handle_config(context: Any, args: list[str]) -> CommandResult:
    """Display configuration locations or manage configuration (export, import, backup, restore)."""
    console = context.console
    theme = context.theme
    config = context.config

    if not args:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=theme.bold_accent_style, justify="right")
        grid.add_column(overflow="fold")
        grid.add_row("Base Directory:", theme.format_text(escape(str(config.base_dir)), bold=True))
        grid.add_row("Config File:", theme.format_primary(escape(str(config.config_path))))
        grid.add_row("History File:", theme.format_primary(escape(str(config.history_path))))
        grid.add_row("Logs Directory:", theme.format_primary(escape(str(config.logs_dir))))
        grid.add_row("Backups Directory:", theme.format_primary(escape(str(config.backups_dir))))

        console.print(theme.create_panel(grid, title="MayuriShell - Configuration Locations"))
        console.print(
            f"{theme.format_muted('Manage configuration with: ')}"
            f"{theme.format_primary('config export', bold=True)}{theme.format_muted(', ')}"
            f"{theme.format_primary('config import', bold=True)}{theme.format_muted(', ')}"
            f"{theme.format_primary('config backup', bold=True)}{theme.format_muted(', ')}"
            f"{theme.format_primary('config restore', bold=True)}\n"
        )
        return CommandResult.success()

    subcmd = args[0].strip().lower()
    sub_args = args[1:]

    if subcmd == "export":
        return handle_config_export(context, sub_args)
    elif subcmd == "import":
        return handle_config_import(context, sub_args)
    elif subcmd == "backup":
        return handle_config_backup(context, sub_args)
    elif subcmd == "restore":
        return handle_config_restore(context, sub_args)
    else:
        err = f"Unknown config subcommand '{args[0]}'."
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        console.print("Valid subcommands: export, import, backup, restore.")
        return CommandResult.fail(err, hint="Usage: config [export|import|backup|restore] [arguments]")


def handle_suggestions(context: Any, args: list[str]) -> CommandResult:
    """Turn smart command suggestions on or off, or display current status."""
    console = context.console
    theme = context.theme
    config = context.config

    if not args:
        enabled = config.get_suggestions_enabled()
        status_str = "on" if enabled else "off"
        max_suggs = config.get_max_suggestions()
        msg = f"Smart command suggestions: {status_str} (max {max_suggs})"
        if theme.is_plain:
            console.print(msg)
        else:
            colored_status = theme.format_success("on") if enabled else theme.format_warning("off")
            console.print(f"Smart command suggestions: {colored_status} {theme.format_muted(f'(max {max_suggs})')}")
        return CommandResult.success()

    mode = args[0].strip().lower()
    if mode in ("on", "off"):
        config.set_suggestions_enabled(mode)
        status_word = "enabled" if mode == "on" else "disabled"
        msg = f"Smart command suggestions {status_word}."
        if theme.is_plain:
            console.print(msg)
        else:
            console.print(theme.format_success(msg, bold=True))
        return CommandResult.success()
    else:
        err = f"Invalid option '{args[0]}'. Use 'suggestions on' or 'suggestions off'."
        if theme.is_plain:
            console.print(f"Error: {err}")
        else:
            console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail(err, hint="Usage: suggestions [on|off]")


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
            description="Manage shell configuration (export, import, backup, restore, locations)",
            handler=handle_config,
            usage="config [export|import|backup|restore] [arguments]",
            category="Customization",
            arg_rules=ArgumentRules(min_args=0, max_args=None),
        )
    )

    registry.register(
        CommandInfo(
            name="suggestions",
            description="Toggle or inspect smart command suggestions (on|off)",
            handler=handle_suggestions,
            usage="suggestions [on|off]",
            category="Customization",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
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
