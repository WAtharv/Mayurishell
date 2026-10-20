"""Website launcher commands and shortcuts for MayuriShell."""
from __future__ import annotations

from typing import Any

from rich.table import Table

from commands.applications import check_shortcut_collision
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.launcher_service import launch_website, validate_web_url


def create_website_launcher_handler(site_name: str, raw_url: str):
    """Factory to create a command handler for a website shortcut."""
    def handler(context: Any, args: list[str]) -> None:
        console = context.console
        current_url = context.config.get_websites().get(site_name.lower(), raw_url)
        success, msg = launch_website(current_url)
        if success:
            console.print(f"[bold green]Opening[/bold green] [bold cyan]{site_name}[/bold cyan] ([dim]{current_url}[/dim])")
        else:
            console.print(f"[bold red]Failed to open website:[/bold red] {msg}")
    return handler


def handle_websites(context: Any, args: list[str]) -> None:
    """List configured websites."""
    console = context.console
    sites = context.config.get_websites()

    if not sites:
        console.print("[dim]No websites configured.[/dim]")
        return

    table = Table(
        title="[bold magenta]Configured Websites[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
    )
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("URL", style="yellow")

    for name, url in sorted(sites.items()):
        table.add_row(name, url)

    console.print(table)
    console.print("[dim]Open a website by typing its command name (e.g. [bold cyan]youtube[/bold cyan], [bold cyan]github[/bold cyan]).[/dim]\n")


def handle_add_website(context: Any, args: list[str]) -> None:
    """Add or update a website shortcut."""
    console = context.console
    name = args[0].strip().lower()
    raw_url = args[1].strip()

    # Validate name
    err = check_shortcut_collision(name, "websites", context)
    if err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        return

    # Validate URL (must be http or https)
    valid, norm_url_or_err = validate_web_url(raw_url)
    if not valid:
        console.print(f"[bold red]Invalid URL:[/bold red] {norm_url_or_err}")
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

    console.print(f"[green]Website shortcut '[bold cyan]{name}[/bold cyan]' set to '[yellow]{norm_url_or_err}[/yellow]'.[/green]")


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
