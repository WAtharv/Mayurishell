"""Application management and launching commands for MayuriShell."""
from __future__ import annotations

from typing import Any

from rich.markup import escape

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
        theme = context.theme
        # Check current target from config in case it was updated
        current_target = context.config.get_applications().get(app_name.lower(), target)
        success = launch_detached(current_target, args)
        if success:
            console.print(f"Launched {escape(app_name)}")
        else:
            console.print(
                f"{theme.format_error('Application not found:')} '{escape(app_name)}' "
                f"(target: {theme.format_muted(escape(current_target))})"
            )
            console.print(
                f"  Please verify it is installed or update its target with: "
                f"{theme.format_primary(f'add-app {app_name} <path>', bold=True)}"
            )
    return handler


def handle_apps(context: Any, args: list[str]) -> None:
    """List configured applications and their resolution status."""
    console = context.console
    theme = context.theme
    apps = context.config.get_applications()

    if not apps:
        console.print(theme.format_muted("No applications configured."))
        return

    table = theme.create_table(
        title="Configured Applications",
    )
    table.add_column("Command", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Target", style=theme.warning_style)
    table.add_column("Status", style=theme.bold_text_style)

    for name, target in sorted(apps.items()):
        if is_uri(target):
            status = theme.format_success("URI Protocol")
        else:
            resolved = find_executable(target)
            if resolved:
                status = theme.format_success("Found")
            else:
                status = theme.format_error("Not Found")
        table.add_row(escape(name), escape(target), status)

    console.print(table)
    console.print(
        f"{theme.format_muted('Launch an app by typing its command name (e.g. ')}"
        f"{theme.format_primary('code', bold=True)}{theme.format_muted(', ')}"
        f"{theme.format_primary('notepad', bold=True)}{theme.format_muted(').')}\n"
    )


def handle_add_app(context: Any, args: list[str]) -> None:
    """Add or update an application shortcut."""
    console = context.console
    theme = context.theme
    name = args[0].strip().lower()
    target = args[1].strip()

    err = check_shortcut_collision(name, "applications", context)
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
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

    console.print(
        f"{theme.format_success('Application shortcut')} "
        f"'{theme.format_primary(escape(name), bold=True)}' "
        f"{theme.format_success('set to')} "
        f"'{theme.format_warning(escape(target))}'."
    )


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
