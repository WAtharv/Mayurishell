"""File operations commands for MayuriShell: open, mkdir, touch, copy, move, rename, delete, info."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from rich.panel import Panel
from rich.table import Table

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


def confirm_prompt(console: Any, prompt_msg: str, default_yes: bool = False) -> bool:
    """Ask user for yes/no confirmation. Default answer is No (y/N)."""
    tag = "(Y/n)" if default_yes else "(y/N)"
    console.print(f"{prompt_msg} [bold cyan]{tag}[/bold cyan] ", end="")
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


def handle_open(context: Any, args: list[str]) -> None:
    """Open a file with its default application."""
    console = context.console
    raw_path = args[0]
    target, _ = context.resolve_path(raw_path)

    if not target.exists():
        console.print(f"[bold red]File not found:[/bold red] '{target}'")
        return

    if target.is_dir():
        console.print(f"[bold yellow]Path is a directory.[/bold yellow] Use [bold cyan]cd '{target.name}'[/bold cyan] to navigate or its folder shortcut to open in Explorer.")
        return

    # Check for executable or script extensions
    ext = target.suffix.lower()
    if ext in EXECUTABLE_EXTENSIONS:
        console.print(f"[bold yellow]Security Warning:[/bold yellow] '{target.name}' is an executable or script ({ext}).")
        confirmed = confirm_prompt(
            console,
            "Do you want to run it?",
            default_yes=False,
        )
        if not confirmed:
            console.print("[dim]Execution cancelled by user.[/dim]")
            return

    try:
        if hasattr(os, "startfile"):
            os.startfile(str(target))
        else:
            import webbrowser
            webbrowser.open(target.as_uri())
        console.print(f"[green]Opened[/green] [bold cyan]{target.name}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Failed to open file:[/bold red] {exc}")


def handle_mkdir(context: Any, args: list[str]) -> None:
    """Create a new directory."""
    console = context.console
    target, _ = context.resolve_path(args[0])

    try:
        create_directory(target)
        console.print(f"[green]Created directory:[/green] [bold cyan]{target}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Error creating directory:[/bold red] {exc}")


def handle_touch(context: Any, args: list[str]) -> None:
    """Create an empty file or update its timestamp."""
    console = context.console
    target, _ = context.resolve_path(args[0])

    try:
        create_file(target)
        console.print(f"[green]Created/updated file:[/green] [bold cyan]{target}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Error touching file:[/bold red] {exc}")


def handle_copy(context: Any, args: list[str]) -> None:
    """Copy a file or directory."""
    console = context.console
    auto_yes = "-y" in args or "--yes" in args
    clean_args = [a for a in args if a not in ("-y", "--yes")]

    if len(clean_args) < 2:
        console.print("[bold red]Usage:[/bold red] copy <source> <destination>")
        return

    src, _ = context.resolve_path(clean_args[0])
    dst, _ = context.resolve_path(clean_args[1])

    if not src.exists():
        console.print(f"[bold red]Source not found:[/bold red] '{src}'")
        return

    # Check overwrite if dst exists
    check_target = dst / src.name if dst.is_dir() else dst
    overwrite = False
    if check_target.exists():
        if not auto_yes:
            confirmed = confirm_prompt(
                console,
                f"Target '{check_target.name}' already exists. Overwrite?",
                default_yes=False,
            )
            if not confirmed:
                console.print("[dim]Copy cancelled.[/dim]")
                return
        overwrite = True

    try:
        result = copy_path(src, dst, overwrite=overwrite)
        console.print(f"[green]Copied[/green] [bold cyan]{src.name}[/bold cyan] -> [bold cyan]{result}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Copy failed:[/bold red] {exc}")


def handle_move(context: Any, args: list[str]) -> None:
    """Move a file or directory."""
    console = context.console
    auto_yes = "-y" in args or "--yes" in args
    clean_args = [a for a in args if a not in ("-y", "--yes")]

    if len(clean_args) < 2:
        console.print("[bold red]Usage:[/bold red] move <source> <destination>")
        return

    src, _ = context.resolve_path(clean_args[0])
    dst, _ = context.resolve_path(clean_args[1])

    if not src.exists():
        console.print(f"[bold red]Source not found:[/bold red] '{src}'")
        return

    check_target = dst / src.name if dst.is_dir() else dst
    overwrite = False
    if check_target.exists():
        if not auto_yes:
            confirmed = confirm_prompt(
                console,
                f"Target '{check_target.name}' already exists. Overwrite?",
                default_yes=False,
            )
            if not confirmed:
                console.print("[dim]Move cancelled.[/dim]")
                return
        overwrite = True

    try:
        result = move_path(src, dst, overwrite=overwrite)
        console.print(f"[green]Moved[/green] [bold cyan]{src.name}[/bold cyan] -> [bold cyan]{result}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Move failed:[/bold red] {exc}")


def handle_rename(context: Any, args: list[str]) -> None:
    """Rename a file or folder in place."""
    console = context.console
    auto_yes = "-y" in args or "--yes" in args
    clean_args = [a for a in args if a not in ("-y", "--yes")]

    if len(clean_args) < 2:
        console.print("[bold red]Usage:[/bold red] rename <target> <new_name>")
        return

    src, _ = context.resolve_path(clean_args[0])
    new_name = clean_args[1]

    # Rejection of path separators
    if "/" in new_name or "\\" in new_name:
        console.print("[bold red]Error:[/bold red] New name must be a plain filename with no path separators. Use 'move' to relocate items.")
        return

    if not src.exists():
        console.print(f"[bold red]Target not found:[/bold red] '{src}'")
        return

    target_dst = src.parent / new_name
    overwrite = False
    if target_dst.exists():
        if not auto_yes:
            confirmed = confirm_prompt(
                console,
                f"Target '{new_name}' already exists. Overwrite?",
                default_yes=False,
            )
            if not confirmed:
                console.print("[dim]Rename cancelled.[/dim]")
                return
        overwrite = True

    try:
        result = rename_path(src, new_name, overwrite=overwrite)
        console.print(f"[green]Renamed[/green] [bold cyan]{src.name}[/bold cyan] -> [bold cyan]{result.name}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Rename failed:[/bold red] {exc}")


def handle_delete(context: Any, args: list[str]) -> None:
    """Safely delete a file or directory by sending to the Recycle Bin.
    
    Refuses protected paths. Requires -r for directories. Default confirmation is No.
    """
    console = context.console
    recursive = "-r" in args or "--recursive" in args
    auto_yes = "-y" in args or "--yes" in args
    targets = [a for a in args if a not in ("-r", "--recursive", "-y", "--yes")]

    if not targets:
        console.print("[bold red]Usage:[/bold red] delete [-r] <target>")
        return

    # Check for wildcards
    if len(targets) > 1:
        console.print("[bold red]Error:[/bold red] Delete accepts only one explicit target at a time. No bulk/multiple deletion.")
        return

    raw_target = targets[0]
    if any(ch in raw_target for ch in ("*", "?")):
        console.print("[bold red]Error:[/bold red] Wildcards are not allowed in delete. Specify an exact file or folder.")
        return

    target_path, _ = context.resolve_path(raw_target)
    if not target_path.exists():
        console.print(f"[bold red]Target not found:[/bold red] '{target_path}'")
        return

    # Check protected path constraints
    project_root = Path(__file__).parent.parent.resolve()
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
        console.print(f"[bold red]Deletion refused:[/bold red] {reason}")
        return

    # Directory requires -r
    if target_path.is_dir() and not recursive:
        console.print(f"[bold red]Error:[/bold red] '{target_path.name}' is a directory. Use [bold cyan]delete -r <directory>[/bold cyan] to delete.")
        return

    # Check network / removable drive warning
    if is_network_or_removable(target_path):
        console.print("[bold yellow]Warning:[/bold yellow] Target is on a network or removable drive. Windows may permanently delete it instead of using the Recycle Bin.")

    # Confirmation prompt (default is No)
    if not auto_yes:
        if target_path.is_dir():
            msg = f"[bold red]Are you sure you want to recursively delete directory '{target_path.name}' and all its contents?[/bold red]"
        else:
            msg = f"Are you sure you want to delete '{target_path.name}'?"

        confirmed = confirm_prompt(console, msg, default_yes=False)
        if not confirmed:
            console.print("[dim]Deletion cancelled.[/dim]")
            return

    try:
        recycle_path(target_path, recursive=recursive)
        console.print(f"[green]Sent to Recycle Bin:[/green] [bold cyan]{target_path.name}[/bold cyan]")
    except Exception as exc:
        console.print(f"[bold red]Delete failed:[/bold red] {exc}")


def handle_info(context: Any, args: list[str]) -> None:
    """Display comprehensive information about a file or directory."""
    console = context.console
    raw_path = args[0]
    target, _ = context.resolve_path(raw_path)

    try:
        data = get_path_info(target)
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        return

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()

    grid.add_row("Name:", f"[bold cyan]{data['name']}[/bold cyan]")
    grid.add_row("Type:", f"[green]{data['type']}[/green]")
    grid.add_row("Full Path:", str(data["path"]))
    grid.add_row("Size / Items:", str(data["size_formatted"]))
    grid.add_row("Created:", str(data["created"]))
    grid.add_row("Modified:", str(data["modified"]))

    console.print(Panel(grid, title=f"[bold pink1]Item Info: {data['name']}[/bold pink1]", border_style="magenta"))


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
