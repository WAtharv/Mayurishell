"""Folder shortcuts and navigation commands for MayuriShell: pwd, ls, cd, add-folder."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from rich.markup import escape

from commands.applications import check_shortcut_collision
from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.file_service import list_directory
from services.launcher_service import launch_folder


def handle_pwd(context: Any, args: list[str]) -> CommandResult:
    """Print the current working directory."""
    theme = context.theme
    context.console.print(theme.format_primary(escape(str(context.current_dir)), bold=True))
    return CommandResult.success()


def handle_cd(context: Any, args: list[str]) -> CommandResult:
    r"""Change the shell's current working directory.
    
    Accepts relative paths, '..', drive letters (D:\), '~', and folder shortcuts.
    If an argument matches both a local folder and a shortcut, the local folder takes precedence.
    """
    console = context.console
    theme = context.theme
    raw_target = args[0] if args else "~"

    target_path, note = context.resolve_path(raw_target)
    if note:
        console.print(theme.format_muted(escape(note)))

    if not target_path.exists():
        console.print(f"{theme.format_error('Directory not found:')} '{escape(str(target_path))}'")
        return CommandResult.fail("Directory not found", hint="Use 'add-folder <name> <path>' to create a folder shortcut, or 'cd' to navigate.")

    if not target_path.is_dir():
        console.print(f"{theme.format_error('Not a directory:')} '{escape(str(target_path))}'")
        return CommandResult.fail()

    context.current_dir = target_path.resolve()
    return CommandResult.success()


def handle_ls(context: Any, args: list[str]) -> None:
    """List directory contents with file metadata and extension/pattern filtering."""
    console = context.console
    theme = context.theme
    current_dir = context.current_dir

    show_hidden = False
    target_dir = current_dir
    pattern: str | None = None

    filtered_args: list[str] = []
    for arg in args:
        if arg in ("-a", "--all"):
            show_hidden = True
        else:
            filtered_args.append(arg)

    if filtered_args:
        first = filtered_args[0]
        # Check if first is a pattern (contains * or ?)
        if any(ch in first for ch in ("*", "?")):
            pattern = first
        else:
            cand_path, _ = context.resolve_path(first)
            if cand_path.is_dir():
                target_dir = cand_path
                if len(filtered_args) > 1:
                    pattern = filtered_args[1]
            elif cand_path.is_file():
                # Single file display
                target_dir = cand_path.parent
                pattern = cand_path.name
            else:
                # Treat as pattern if non-existent
                pattern = first

    try:
        items = list_directory(target_dir, pattern=pattern, show_hidden=show_hidden)
    except Exception as exc:
        console.print(f"{theme.format_error('Error listing directory:')} {escape(str(exc))}")
        return CommandResult.fail()

    table = theme.create_table(
        title=f"Directory: {escape(str(target_dir))}",
    )
    table.add_column("Type", style=theme.accent_style, no_wrap=True)
    table.add_column("Name", style=theme.bold_text_style, max_width=45, overflow=theme.overflow, no_wrap=True)
    table.add_column("Size", justify="right", style=theme.warning_style, no_wrap=True)
    table.add_column("Modified Date", style=theme.muted_style, no_wrap=True)

    dir_count = 0
    file_count = 0
    MAX_NAME_WIDTH = 40

    for item in items:
        display_name = item.name
        if len(display_name) > MAX_NAME_WIDTH:
            display_name = display_name[: MAX_NAME_WIDTH - 3] + "..."

        esc_display_name = escape(display_name)
        if item.is_dir:
            type_str = theme.format_accent("<DIR>", bold=True)
            name_str = theme.format_primary(f"{esc_display_name}/", bold=True)
            dir_count += 1
        else:
            type_str = theme.format_muted("FILE")
            name_str = esc_display_name
            file_count += 1

        if item.is_hidden:
            name_str = theme.format_muted(name_str)

        table.add_row(type_str, name_str, escape(item.formatted_size), escape(item.formatted_mtime))

    console.print(table)
    console.print(f"{theme.format_muted(f'{dir_count} directories, {file_count} files')}\n")
    return CommandResult.success()


def create_folder_launcher_handler(folder_name: str, raw_path: str):
    """Factory to create a command handler for opening a folder shortcut in File Explorer."""
    def handler(context: Any, args: list[str]) -> CommandResult:
        console = context.console
        theme = context.theme
        current_path = context.config.get_folder_shortcuts().get(folder_name.lower(), raw_path)
        success, msg, expanded_path = launch_folder(current_path)
        if success:
            console.print(
                f"{theme.format_success('Opened folder', bold=True)} "
                f"{theme.format_primary(escape(folder_name), bold=True)} "
                f"({theme.format_muted(escape(str(expanded_path)))})"
            )
            return CommandResult.success()
        else:
            err_prefix = theme.format_error(f"Folder error for '{escape(folder_name)}':")
            console.print(f"{err_prefix} {escape(msg)}")
            console.print(
                f"  Update this shortcut to an existing directory using: "
                f"{theme.format_primary(f'add-folder {folder_name} <path>', bold=True)}"
            )
            return CommandResult.fail(msg, hint="Use 'add-folder <name> <path>' to create a folder shortcut, or 'cd' to navigate.")
    return handler


def handle_add_folder(context: Any, args: list[str]) -> CommandResult:
    """Add or update a folder shortcut."""
    console = context.console
    theme = context.theme
    name = args[0].strip().lower()
    raw_path = args[1].strip()

    # Validate name
    err = check_shortcut_collision(name, "folder_shortcuts", context)
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail(err, hint="Names must be alphanumeric without spaces and cannot collide with existing commands.")

    # Path expansion and check
    expanded = Path(os.path.expanduser(os.path.expandvars(raw_path))).resolve()
    if not expanded.exists():
        console.print(f"{theme.format_warning('Warning:', bold=True)} Target folder '{escape(str(expanded))}' does not currently exist.")

    context.config.set_shortcut("folder_shortcuts", name, raw_path)

    # Register in command registry
    context.registry.register(
        CommandInfo(
            name=name,
            description=f"Open folder in File Explorer: {raw_path}",
            handler=create_folder_launcher_handler(name, raw_path),
            usage=name,
            category="Folders",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    console.print(
        f"{theme.format_success('Folder shortcut')} "
        f"'{theme.format_primary(escape(name), bold=True)}' "
        f"{theme.format_success('set to')} "
        f"'{theme.format_warning(escape(raw_path))}'."
    )
    return CommandResult.success()


def register_navigation_commands(registry: CommandRegistry, config: Any) -> None:
    """Register navigation commands (pwd, cd, ls, add-folder) and folder shortcuts."""
    registry.register(
        CommandInfo(
            name="pwd",
            description="Print current working directory",
            handler=handle_pwd,
            usage="pwd",
            category="Navigation",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="cd",
            description="Change working directory (supports ~, .., drive letters, and shortcuts)",
            handler=handle_cd,
            usage="cd [path|shortcut]",
            category="Navigation",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="ls",
            description="List directory contents with size, date, and extension filter",
            handler=handle_ls,
            usage="ls [-a] [path] [pattern]",
            category="Navigation",
            arg_rules=ArgumentRules(min_args=0, max_args=3),
        )
    )

    registry.register(
        CommandInfo(
            name="add-folder",
            description="Add or update a folder shortcut that opens in File Explorer",
            handler=handle_add_folder,
            usage="add-folder <name> <path>",
            category="Customization",
            arg_rules=ArgumentRules(min_args=2, max_args=2),
        )
    )

    # Register individual folder shortcuts
    for name, path_str in config.get_folder_shortcuts().items():
        registry.register(
            CommandInfo(
                name=name.lower(),
                description=f"Open folder in File Explorer: {path_str}",
                handler=create_folder_launcher_handler(name, path_str),
                usage=name,
                category="Folders",
                arg_rules=ArgumentRules(min_args=0, max_args=0),
            )
        )
