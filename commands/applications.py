"""Application management and launching commands for MayuriShell."""
from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table

from core.aliases import is_valid_name
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.application_discovery import find_executable, is_uri, launch_detached


def check_shortcut_collision(name: str, current_section: str, context: Any) -> str | None:
    """Verify that a shortcut name is valid and does not collide with builtins or other sections."""
    if not is_valid_name(name):
        return f"Invalid name '{name}'. Names may only contain letters, numbers, and hyphens."

    key = name.lower()
    registry: CommandRegistry = context.registry
    config = context.config

    if registry.has_command(key):
        cmd = registry.get(key)
        if cmd and cmd.category == "Builtins":
            return f"Cannot use '{name}': conflicts with built-in command '{cmd.name}'."

    # Check other sections
    sections = {
        "applications": config.get_applications(),
        "websites": config.get_websites(),
        "folder_shortcuts": config.get_folder_shortcuts(),
        "aliases": config.get_aliases(),
    }

    for sec_name, sec_dict in sections.items():
        if sec_name != current_section and key in sec_dict:
            return f"Cannot use '{name}': already exists in '{sec_name}'."

    return None


def create_app_launcher_handler(app_name: str, target: str):
    """Factory to create a command handler for a specific application shortcut."""
    def handler(context: Any, args: list[str]) -> None:
        console = context.console
        # Check current target from config in case it was updated
        current_target = context.config.get_applications().get(app_name.lower(), target)
        success = launch_detached(current_target, args)
        if success:
            console.print(f"Launched {app_name}")
        else:
            console.print(f"[bold red]Application not found:[/bold red] '{app_name}' (target: [dim]{current_target}[/dim])")
            console.print(f"  Please verify it is installed or update its target with: [bold cyan]add-app {app_name} <path>[/bold cyan]")
    return handler


def handle_apps(context: Any, args: list[str]) -> None:
    """List configured applications and their resolution status."""
    console = context.console
    apps = context.config.get_applications()

    if not apps:
        console.print("[dim]No applications configured.[/dim]")
        return

    table = Table(
        title="[bold magenta]Configured Applications[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
    )
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Target", style="yellow")
    table.add_column("Status", style="bold")

    for name, target in sorted(apps.items()):
        if is_uri(target):
            status = "[green]URI Protocol[/green]"
        else:
            resolved = find_executable(target)
            if resolved:
                status = "[green]Found[/green]"
            else:
                status = "[red]Not Found[/red]"
        table.add_row(name, target, status)

    console.print(table)
    console.print("[dim]Launch an app by typing its command name (e.g. [bold cyan]code[/bold cyan], [bold cyan]notepad[/bold cyan]).[/dim]\n")


def handle_add_app(context: Any, args: list[str]) -> None:
    """Add or update an application shortcut."""
    console = context.console
    name = args[0].strip().lower()
    target = args[1].strip()

    err = check_shortcut_collision(name, "applications", context)
    if err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        return

    context.config.set_shortcut("applications", name, target)
    
    # Register in active command registry
    context.registry.register(
        CommandInfo(
            name=name,
            description=f"Launch application: {name}",
            handler=create_app_launcher_handler(name, target),
            usage=f"{name} [args...]",
            category="Applications",
        )
    )

    console.print(f"[green]Application shortcut '[bold cyan]{name}[/bold cyan]' set to '[yellow]{target}[/yellow]'.[/green]")


def register_application_commands(registry: CommandRegistry, config: Any) -> None:
    """Register 'apps', 'add-app', and all configured application shortcuts."""
    registry.register(
        CommandInfo(
            name="apps",
            description="List configured applications and their status",
            handler=handle_apps,
            usage="apps",
            category="Launchers",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="add-app",
            description="Add or update an application shortcut",
            handler=handle_add_app,
            usage="add-app <name> <path_or_command>",
            category="Customization",
            arg_rules=ArgumentRules(min_args=2, max_args=2),
        )
    )

    # Register individual application shortcuts
    for name, target in config.get_applications().items():
        registry.register(
            CommandInfo(
                name=name.lower(),
                description=f"Launch application: {name}",
                handler=create_app_launcher_handler(name, target),
                usage=f"{name} [args...]",
                category="Applications",
            )
        )
