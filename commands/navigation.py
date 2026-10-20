"""Folder shortcuts and navigation commands for MayuriShell."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from rich.table import Table

from commands.applications import check_shortcut_collision
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.launcher_service import launch_folder


def create_folder_launcher_handler(folder_name: str, raw_path: str):
    """Factory to create a command handler for a folder shortcut."""
    def handler(context: Any, args: list[str]) -> None:
        console = context.console
        current_path = context.config.get_folder_shortcuts().get(folder_name.lower(), raw_path)
        success, msg, expanded_path = launch_folder(current_path)
        if success:
            console.print(f"[bold green]Opened folder[/bold green] [bold cyan]{folder_name}[/bold cyan] ([dim]{expanded_path}[/dim])")
        else:
            console.print(f"[bold red]Folder error for '{folder_name}':[/bold red] {msg}")
            console.print(f"  Update this shortcut to an existing directory using: [bold cyan]add-folder {folder_name} <path>[/bold cyan]")
    return handler


def handle_add_folder(context: Any, args: list[str]) -> None:
    """Add or update a folder shortcut."""
    console = context.console
    name = args[0].strip().lower()
    raw_path = args[1].strip()

    # Validate name
    err = check_shortcut_collision(name, "folder_shortcuts", context)
    if err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        return

    # Path expansion and check
    expanded = Path(os.path.expanduser(os.path.expandvars(raw_path))).resolve()
    if not expanded.exists():
        console.print(f"[bold yellow]Warning:[/bold yellow] Target folder '{expanded}' does not currently exist.")

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

    console.print(f"[green]Folder shortcut '[bold cyan]{name}[/bold cyan]' set to '[yellow]{raw_path}[/yellow]'.[/green]")


def register_navigation_commands(registry: CommandRegistry, config: Any) -> None:
    """Register 'add-folder' and all configured folder shortcuts."""
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
