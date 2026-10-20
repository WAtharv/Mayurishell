"""Website launcher commands and shortcuts for MayuriShell."""
from __future__ import annotations

from typing import Any

from rich.markup import escape

from commands.applications import check_shortcut_collision
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.launcher_service import launch_website, validate_web_url


def create_website_launcher_handler(site_name: str, raw_url: str):
    """Factory to create a command handler for a website shortcut."""
    def handler(context: Any, args: list[str]) -> None:
        console = context.console
        theme = context.theme
        current_url = context.config.get_websites().get(site_name.lower(), raw_url)
        success, msg = launch_website(current_url)
        if success:
            console.print(
                f"{theme.format_success('Opening', bold=True)} "
                f"{theme.format_primary(escape(site_name), bold=True)} "
                f"({theme.format_muted(escape(current_url))})"
            )
        else:
            console.print(f"{theme.format_error('Failed to open website:')} {escape(msg)}")
    return handler


def handle_websites(context: Any, args: list[str]) -> None:
    """List configured websites."""
    console = context.console
    theme = context.theme
    sites = context.config.get_websites()

    if not sites:
        console.print(theme.format_muted("No websites configured."))
        return

    table = theme.create_table(
        title="Configured Websites",
    )
    table.add_column("Command", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("URL", style=theme.warning_style)

    for name, url in sorted(sites.items()):
        table.add_row(escape(name), escape(url))

    console.print(table)
    console.print(
        f"{theme.format_muted('Open a website by typing its command name (e.g. ')}"
        f"{theme.format_primary('youtube', bold=True)}{theme.format_muted(', ')}"
        f"{theme.format_primary('github', bold=True)}{theme.format_muted(').')}\n"
    )


def handle_add_website(context: Any, args: list[str]) -> None:
    """Add or update a website shortcut."""
    console = context.console
    theme = context.theme
    name = args[0].strip().lower()
    raw_url = args[1].strip()

    # Validate name
    err = check_shortcut_collision(name, "websites", context)
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return

    # Validate URL (must be http or https)
    valid, norm_url_or_err = validate_web_url(raw_url)
    if not valid:
        console.print(f"{theme.format_error('Invalid URL:')} {escape(norm_url_or_err)}")
        return

    context.config.set_shortcut("websites", name, norm_url_or_err)

    # Register in active command registry
    context.registry.register(
        CommandInfo(
            name=name,
            description=f"Open website: {norm_url_or_err}",
            handler=create_website_launcher_handler(name, norm_url_or_err),
            usage=name,
            category="Websites",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    console.print(
        f"{theme.format_success('Website shortcut')} "
        f"'{theme.format_primary(escape(name), bold=True)}' "
        f"{theme.format_success('set to')} "
        f"'{theme.format_warning(escape(norm_url_or_err))}'."
    )


def register_website_commands(registry: CommandRegistry, config: Any) -> None:
    """Register 'websites', 'add-website', and all configured website shortcuts."""
    registry.register(
        CommandInfo(
            name="websites",
            description="List configured website shortcuts",
            handler=handle_websites,
            usage="websites",
            category="Launchers",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="add-website",
            description="Add or update a website shortcut",
            handler=handle_add_website,
            usage="add-website <name> <url>",
            category="Customization",
            arg_rules=ArgumentRules(min_args=2, max_args=2),
        )
    )

    # Register individual website shortcuts
    for name, url in config.get_websites().items():
        registry.register(
            CommandInfo(
                name=name.lower(),
                description=f"Open website: {url}",
                handler=create_website_launcher_handler(name, url),
                usage=name,
                category="Websites",
                arg_rules=ArgumentRules(min_args=0, max_args=0),
            )
        )
