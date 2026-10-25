"""File operations commands for MayuriShell: open, mkdir, touch, copy, move, rename, delete, info."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.file_service import (
    EXECUTABLE_EXTENSIONS,
    copy_path,
    create_directory,
    create_file,
    get_path_info,
    is_network_or_removable,
    is_protected_path,
    move_path,
    recycle_path,
    rename_path,
)
from services.undo_service import (
    finish_journal_operation,
    mark_item_done,
    record_pending_item,
    start_journal_operation,
)



def confirm_prompt(console: Any, prompt_msg: str, default_yes: bool = False, theme: Any = None) -> bool:
    """Ask user for yes/no confirmation. Default answer is No (y/N)."""
    tag = "(Y/n)" if default_yes else "(y/N)"
    tag_str = theme.format_primary(tag, bold=True) if theme else tag
    console.print(f"{prompt_msg} {tag_str} ", end="")
    if not sys.stdin.isatty():
        console.print()
        return default_yes
    try:
        ans = input().strip().lower()
        if not ans:
            return default_yes
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def handle_open(context: Any, args: list[str]) -> CommandResult:
    """Open a file with its default application."""
    console = context.console
    theme = context.theme
    raw_path = args[0]
    target, _ = context.resolve_path(raw_path)

    if not target.exists():
        console.print(f"{theme.format_error('File not found:')} '{escape(str(target))}'")
        return CommandResult.fail()

    if target.is_dir():
        cd_cmd = theme.format_primary(f"cd '{target.name}'", bold=True)
        console.print(
            f"{theme.format_warning('Path is a directory.', bold=True)} "
            f"Use {cd_cmd} to navigate or its folder shortcut to open in Explorer."
        )
        return CommandResult.fail()

    # Check for executable or script extensions
    ext = target.suffix.lower()
    if ext in EXECUTABLE_EXTENSIONS:
        console.print(
            f"{theme.format_warning('Security Warning:', bold=True)} "
            f"'{escape(target.name)}' is an executable or script ({escape(ext)})."
        )
        confirmed = confirm_prompt(
            console,
            "Do you want to run it?",
            default_yes=False,
            theme=theme,
        )
        if not confirmed:
            console.print(theme.format_muted("Execution cancelled by user."))
            return CommandResult.cancel()

    try:
        if hasattr(os, "startfile"):
            os.startfile(str(target))
        else:
            import webbrowser
            webbrowser.open(target.as_uri())
        console.print(f"{theme.format_success('Opened')} {theme.format_primary(escape(target.name), bold=True)}")
        return CommandResult.success()
    except Exception as exc:
        console.print(f"{theme.format_error('Failed to open file:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_mkdir(context: Any, args: list[str]) -> CommandResult:
    """Create a new directory."""
    console = context.console
    theme = context.theme
    target, _ = context.resolve_path(args[0])

    try:
        create_directory(target)
        console.print(f"{theme.format_success('Created directory:')} {theme.format_primary(escape(str(target)), bold=True)}")
        return CommandResult.success()
    except Exception as exc:
        console.print(f"{theme.format_error('Error creating directory:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_touch(context: Any, args: list[str]) -> CommandResult:
    """Create an empty file or update its timestamp."""
    console = context.console
    theme = context.theme
    target, _ = context.resolve_path(args[0])

    try:
        create_file(target)
        console.print(f"{theme.format_success('Created/updated file:')} {theme.format_primary(escape(str(target)), bold=True)}")
        return CommandResult.success()
    except Exception as exc:
        console.print(f"{theme.format_error('Error touching file:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_copy(context: Any, args: list[str]) -> CommandResult:
    """Copy a file or directory."""
    console = context.console
    theme = context.theme
    auto_yes = "-y" in args or "--yes" in args
    clean_args = [a for a in args if a not in ("-y", "--yes")]

    if len(clean_args) < 2:
        console.print(f"{theme.format_error('Usage:')} copy <source> <destination>")
        return CommandResult.fail()

    src, _ = context.resolve_path(clean_args[0])
    dst, _ = context.resolve_path(clean_args[1])

    if not src.exists():
        console.print(f"{theme.format_error('Source not found:')} '{escape(str(src))}'")
        return CommandResult.fail()

    # Check overwrite if dst exists
    check_target = dst / src.name if dst.is_dir() else dst
    overwrite = False
    if check_target.exists():
        if not auto_yes:
            confirmed = confirm_prompt(
                console,
                f"Target '{escape(check_target.name)}' already exists. Overwrite?",
                default_yes=False,
                theme=theme,
            )
            if not confirmed:
                console.print(theme.format_muted("Copy cancelled."))
                return CommandResult.cancel()
        overwrite = True

    try:
        result = copy_path(src, dst, overwrite=overwrite)
        console.print(
            f"{theme.format_success('Copied')} {theme.format_primary(escape(src.name), bold=True)} -> "
            f"{theme.format_primary(escape(str(result)), bold=True)}"
        )
        return CommandResult.success()
    except Exception as exc:
        console.print(f"{theme.format_error('Copy failed:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_move(context: Any, args: list[str]) -> CommandResult:
    """Move a file or directory."""
    console = context.console
    theme = context.theme
    auto_yes = "-y" in args or "--yes" in args
    clean_args = [a for a in args if a not in ("-y", "--yes")]

    if len(clean_args) < 2:
        console.print(f"{theme.format_error('Usage:')} move <source> <destination>")
        return CommandResult.fail()

    src, _ = context.resolve_path(clean_args[0])
    dst, _ = context.resolve_path(clean_args[1])

    if not src.exists():
        console.print(f"{theme.format_error('Source not found:')} '{escape(str(src))}'")
        return CommandResult.fail()

    check_target = dst / src.name if dst.is_dir() else dst
    overwrite = False
    if check_target.exists():
        if not auto_yes:
            confirmed = confirm_prompt(
                console,
                f"Target '{escape(check_target.name)}' already exists. Overwrite?",
                default_yes=False,
                theme=theme,
            )
            if not confirmed:
                console.print(theme.format_muted("Move cancelled."))
                return CommandResult.cancel()
        overwrite = True

    base_dir = context.config.base_dir
    op_id = start_journal_operation(base_dir, "move")
    record_pending_item(
        base_dir,
        op_id,
        src,
        check_target,
        kind="folder" if src.is_dir() else "file",
    )

    try:
        result = move_path(src, dst, overwrite=overwrite)
        mark_item_done(base_dir, op_id, result)
        finish_journal_operation(base_dir, op_id, status="done")
        console.print(
            f"{theme.format_success('Moved')} {theme.format_primary(escape(src.name), bold=True)} -> "
            f"{theme.format_primary(escape(str(result)), bold=True)}"
        )
        return CommandResult.success()
    except Exception as exc:
        finish_journal_operation(base_dir, op_id, status="failed")
        console.print(f"{theme.format_error('Move failed:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_rename(context: Any, args: list[str]) -> CommandResult:
    """Rename a file or folder in place."""
    console = context.console
    theme = context.theme
    auto_yes = "-y" in args or "--yes" in args
    clean_args = [a for a in args if a not in ("-y", "--yes")]

    if len(clean_args) < 2:
        console.print(f"{theme.format_error('Usage:')} rename <target> <new_name>")
        return CommandResult.fail()

    src, _ = context.resolve_path(clean_args[0])
    new_name = clean_args[1]

    # Rejection of path separators
    if "/" in new_name or "\\" in new_name:
        console.print(
            f"{theme.format_error('Error:')} New name must be a plain filename with no path separators. "
            f"Use 'move' to relocate items."
        )
        return CommandResult.fail()

    if not src.exists():
        console.print(f"{theme.format_error('Target not found:')} '{escape(str(src))}'")
        return CommandResult.fail()

    target_dst = src.parent / new_name
    overwrite = False
    if target_dst.exists():
        if not auto_yes:
            confirmed = confirm_prompt(
                console,
                f"Target '{escape(new_name)}' already exists. Overwrite?",
                default_yes=False,
                theme=theme,
            )
            if not confirmed:
                console.print(theme.format_muted("Rename cancelled."))
                return CommandResult.cancel()
        overwrite = True

    base_dir = context.config.base_dir
    op_id = start_journal_operation(base_dir, "rename")
    record_pending_item(
        base_dir,
        op_id,
        src,
        target_dst,
        kind="folder" if src.is_dir() else "file",
    )

    try:
        result = rename_path(src, new_name, overwrite=overwrite)
        mark_item_done(base_dir, op_id, result)
        finish_journal_operation(base_dir, op_id, status="done")
        console.print(
            f"{theme.format_success('Renamed')} {theme.format_primary(escape(src.name), bold=True)} -> "
            f"{theme.format_primary(escape(result.name), bold=True)}"
        )
        return CommandResult.success()
    except Exception as exc:
        finish_journal_operation(base_dir, op_id, status="failed")
        console.print(f"{theme.format_error('Rename failed:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_delete(context: Any, args: list[str]) -> CommandResult:
    """Safely delete a file or directory by sending to the Recycle Bin.
    
    Refuses protected paths. Requires -r for directories. Default confirmation is No.
    """
    console = context.console
    theme = context.theme
    recursive = "-r" in args or "--recursive" in args
    auto_yes = "-y" in args or "--yes" in args
    targets = [a for a in args if a not in ("-r", "--recursive", "-y", "--yes")]

    if not targets:
        console.print(f"{theme.format_error('Usage:')} delete [-r] <target>")
        return CommandResult.fail()

    # Check for wildcards
    if len(targets) > 1:
        console.print(f"{theme.format_error('Error:')} Delete accepts only one explicit target at a time. No bulk/multiple deletion.")
        return CommandResult.fail()

    raw_target = targets[0]
    if any(ch in raw_target for ch in ("*", "?")):
        console.print(f"{theme.format_error('Error:')} Wildcards are not allowed in delete. Specify an exact file or folder.")
        return CommandResult.fail(hint="Wildcard deletion is refused for safety. Specify exact file names.")

    target_path, _ = context.resolve_path(raw_target)
    if not target_path.exists():
        console.print(f"{theme.format_error('Target not found:')} '{escape(str(target_path))}'")
        return CommandResult.fail()

    # Check protected path constraints
    from core.paths import get_app_root
    project_root = get_app_root().resolve()
    appdata_dir = context.config.base_dir.resolve()
    shortcuts = context.config.get_folder_shortcuts()

    is_prot, reason = is_protected_path(
        target_path,
        current_dir=context.current_dir,
        appdata_dir=appdata_dir,
        project_root=project_root,
        folder_shortcuts=shortcuts,
    )
    if is_prot:
        console.print(f"{theme.format_error('Deletion refused:')} {escape(reason)}")
        return CommandResult.fail(reason, hint="Target path is protected for system stability.")

    # Directory requires -r
    if target_path.is_dir() and not recursive:
        console.print(
            f"{theme.format_error('Error:')} '{escape(target_path.name)}' is a directory. "
            f"Use {theme.format_primary('delete -r <directory>', bold=True)} to delete."
        )
        return CommandResult.fail()

    # Check network / removable drive warning
    if is_network_or_removable(target_path):
        console.print(
            f"{theme.format_warning('Warning:', bold=True)} Target is on a network or removable drive. "
            f"Windows may permanently delete it instead of using the Recycle Bin."
        )

    # Confirmation prompt (default is No)
    if not auto_yes:
        if target_path.is_dir():
            msg = theme.format_error(
                f"Are you sure you want to recursively delete directory '{escape(target_path.name)}' and all its contents? (Restore deleted files from the Recycle Bin.)",
                bold=True,
            )
        else:
            msg = f"Are you sure you want to delete '{escape(target_path.name)}'? (Restore deleted files from the Recycle Bin.)"

        confirmed = confirm_prompt(console, msg, default_yes=False, theme=theme)
        if not confirmed:
            console.print(theme.format_muted("Deletion cancelled."))
            return CommandResult.cancel()

    try:
        recycle_path(target_path, recursive=recursive)
        console.print(
            f"{theme.format_success('Sent to Recycle Bin:')} {theme.format_primary(escape(target_path.name), bold=True)}\n"
            f"{theme.format_muted('Restore deleted files from the Recycle Bin.')}"
        )
        return CommandResult.success()
    except Exception as exc:
        console.print(f"{theme.format_error('Delete failed:')} {escape(str(exc))}")
        return CommandResult.fail()


def handle_info(context: Any, args: list[str]) -> CommandResult:
    """Display comprehensive information about a file or directory."""
    console = context.console
    theme = context.theme
    raw_path = args[0]
    target, _ = context.resolve_path(raw_path)

    try:
        data = get_path_info(target)
    except Exception as exc:
        console.print(f"{theme.format_error('Error:')} {escape(str(exc))}")
        return CommandResult.fail()

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=theme.bold_accent_style, justify="right")
    grid.add_column(overflow="fold")

    grid.add_row("Name:", theme.format_primary(escape(str(data['name'])), bold=True))
    grid.add_row("Type:", theme.format_success(escape(str(data['type']))))
    grid.add_row("Full Path:", escape(str(data["path"])))
    grid.add_row("Size / Items:", escape(str(data["size_formatted"])))
    grid.add_row("Created:", escape(str(data["created"])))
    grid.add_row("Modified:", escape(str(data["modified"])))

    console.print(theme.create_panel(grid, title=f"Item Info: {escape(str(data['name']))}"))
    return CommandResult.success()


def register_file_commands(registry: CommandRegistry) -> None:
    """Register file operations commands."""
    registry.register(
        CommandInfo(
            name="open",
            description="Open a file with its default application",
            handler=handle_open,
            usage="open <file>",
            category="Files",
            arg_rules=ArgumentRules(min_args=1, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="mkdir",
            description="Create a new directory",
            handler=handle_mkdir,
            usage="mkdir <folder>",
            category="Files",
            arg_rules=ArgumentRules(min_args=1, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="touch",
            description="Create a new empty file or update timestamp",
            handler=handle_touch,
            usage="touch <file>",
            category="Files",
            arg_rules=ArgumentRules(min_args=1, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="copy",
            description="Copy a file or directory with overwrite protection",
            handler=handle_copy,
            usage="copy [-y] <source> <destination>",
            category="Files",
            arg_rules=ArgumentRules(min_args=2, max_args=3),
        )
    )

    registry.register(
        CommandInfo(
            name="move",
            description="Move a file or directory with overwrite protection",
            handler=handle_move,
            usage="move [-y] <source> <destination>",
            category="Files",
            arg_rules=ArgumentRules(min_args=2, max_args=3),
        )
    )

    registry.register(
        CommandInfo(
            name="rename",
            description="Rename a file or folder in place (plain name only)",
            handler=handle_rename,
            usage="rename [-y] <target> <new_name>",
            category="Files",
            arg_rules=ArgumentRules(min_args=2, max_args=3),
        )
    )

    registry.register(
        CommandInfo(
            name="delete",
            description="Safely delete file or directory to Recycle Bin",
            handler=handle_delete,
            usage="delete [-r] [-y] <target>",
            category="Files",
            arg_rules=ArgumentRules(min_args=1, max_args=3),
        )
    )

    registry.register(
        CommandInfo(
            name="info",
            description="Display detailed metadata about a file or folder",
            handler=handle_info,
            usage="info <path>",
            category="Files",
            arg_rules=ArgumentRules(min_args=1, max_args=1),
        )
    )
