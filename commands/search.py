"""Search commands for MayuriShell: find."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from rich.table import Table

from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.file_service import format_bytes, search_files


def handle_find(context: Any, args: list[str]) -> None:
    """Search for files in configured search directories."""
    console = context.console
    config = context.config

    if not args:
        console.print("[bold red]Usage:[/bold red] find <pattern_or_name> [--ext <extension>] [--limit <number>]")
        return

    # Parse arguments
    query_parts: list[str] = []
    extension: str | None = None
    limit = 100

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--ext" and i + 1 < len(args):
            extension = args[i + 1]
            i += 2
        elif arg == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            query_parts.append(arg)
            i += 1

    query = " ".join(query_parts).strip()
    if not query and not extension:
        console.print("[bold red]Error:[/bold red] Please provide a search query or an extension.")
        return

    # Gather search roots from config
    raw_search_dirs = config.get("search_directories", ["~/Desktop", "~/Documents", "~/Downloads"])
    search_roots = [
        Path(os.path.expanduser(os.path.expandvars(d))).resolve()
        for d in raw_search_dirs
    ]

    # Gather excluded directories from config
    raw_excluded = config.get("excluded_directories", [".git", "node_modules", ".venv", "__pycache__", "AppData"])
    excluded_set = set(raw_excluded)

    console.print(f"[dim]Searching for '{query or f'*.{extension}'}' in {len(search_roots)} configured directories... (Ctrl+C to cancel)[/dim]")

    try:
        matches, skipped_count, hit_limit = search_files(
            search_roots=search_roots,
            query=query if query else f"*.{extension}",
            extension=extension,
            excluded_names=excluded_set,
            limit=limit,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Search cancelled by user.[/yellow]")
        return

    if not matches:
        console.print(f"[dim]No matching files found for '{query}'.[/dim]")
        if skipped_count > 0:
            console.print(f"[dim]{skipped_count} folder(s) skipped due to permission restrictions.[/dim]")
        return

    table = Table(
        title=f"[bold magenta]Search Results ({len(matches)} matches)[/bold magenta]",
        border_style="purple",
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("Filename", style="bold cyan")
    table.add_column("Location", style="yellow")
    table.add_column("Size", justify="right", style="green", no_wrap=True)

    for idx, path in enumerate(matches, start=1):
        try:
            size_str = format_bytes(path.stat().st_size)
        except OSError:
            size_str = "-"
        table.add_row(str(idx), path.name, str(path.parent), size_str)

    console.print(table)

    # Status notifications
    if hit_limit:
        console.print(f"[bold yellow]Result limit reached (capped at {limit} items). Refine search or use --limit to view more.[/bold yellow]")
    if skipped_count > 0:
        console.print(f"[dim]{skipped_count} folder(s) skipped due to permission restrictions.[/dim]")
    console.print()


def register_search_commands(registry: CommandRegistry) -> None:
    """Register search commands."""
    registry.register(
        CommandInfo(
            name="find",
            description="Search for files in configured directories",
            handler=handle_find,
            usage="find <query> [--ext <extension>] [--limit <number>]",
            category="Search",
            arg_rules=ArgumentRules(min_args=1),
        )
    )
