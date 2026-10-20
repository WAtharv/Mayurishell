"""Process inspection and management commands: processes, process find, process info, process kill."""
from __future__ import annotations

import re
from typing import Any

from rich.panel import Panel
from rich.table import Table

from commands.files import confirm_prompt
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.system_service import (
    find_processes,
    get_process_detail,
    is_protected_process,
    kill_process_guarded,
    list_processes,
)


def parse_pid(raw_pid: str) -> tuple[int | None, str]:
    """Validate and parse a raw PID string.
    
    Rejects non-numeric strings, negative numbers, and wildcards.
    """
    if any(ch in raw_pid for ch in ("*", "?", "%")):
        return None, "Wildcards are not allowed in PID. Please specify an exact numeric PID."

    if raw_pid.startswith("-"):
        return None, f"Invalid PID '{raw_pid}': PID must be a positive integer."

    if not raw_pid.isdigit():
        return None, f"Invalid PID '{raw_pid}': PID must be a positive number, not a name or text."

    pid = int(raw_pid)
    return pid, ""


def handle_processes(context: Any, args: list[str]) -> None:
    """List running processes with CPU % and Working Set memory.
    
    Usage: processes [--sort cpu|memory|name] [--limit N]
    """
    console = context.console
    sort_by = "memory"
    limit = 20

    i = 0
    while i < len(args):
        arg = args[i].lower()
        if arg in ("--sort", "-s") and i + 1 < len(args):
            sort_val = args[i + 1].lower()
            if sort_val in ("cpu", "memory", "name"):
                sort_by = sort_val
            else:
                console.print(f"[bold red]Invalid sort option '{args[i + 1]}'.[/bold red] Choose from: cpu, memory, name.")
                return
            i += 2
        elif arg.startswith("--sort="):
            sort_val = arg.split("=", 1)[1].lower()
            if sort_val in ("cpu", "memory", "name"):
                sort_by = sort_val
            else:
                console.print(f"[bold red]Invalid sort option '{sort_val}'.[/bold red] Choose from: cpu, memory, name.")
                return
            i += 1
        elif arg in ("--limit", "-l", "-n") and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit <= 0:
                    raise ValueError
            except ValueError:
                console.print(f"[bold red]Invalid limit '{args[i + 1]}'.[/bold red] Must be a positive integer.")
                return
            i += 2
        elif arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
                if limit <= 0:
                    raise ValueError
            except ValueError:
                console.print(f"[bold red]Invalid limit value.[/bold red] Must be a positive integer.")
                return
            i += 1
        else:
            i += 1

    console.print(f"[dim]Collecting process statistics (sampling CPU)...[/dim]")
    procs = list_processes(sort_by=sort_by, limit=limit)

    table = Table(
        title=f"[bold magenta]Running Processes (Top {len(procs)} by {sort_by.capitalize()})[/bold magenta]",
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("PID", justify="right", style="dim", no_wrap=True)
    table.add_column("Name", style="bold white", max_width=35, overflow="ellipsis", no_wrap=True)
    table.add_column("CPU %", justify="right", style="yellow", no_wrap=True)
    table.add_column("Memory (Working Set)", justify="right", style="green", no_wrap=True)
    table.add_column("User", style="dim cyan", max_width=25, overflow="ellipsis", no_wrap=True)

    for p in procs:
        cpu_val = p.get("cpu_percent", 0.0)
        cpu_str = f"[bold yellow]{cpu_val:.1f}%[/bold yellow]" if cpu_val > 0.0 else f"{cpu_val:.1f}%"
        table.add_row(
            str(p.get("pid", "")),
            p.get("name", ""),
            cpu_str,
            p.get("memory_formatted", ""),
            p.get("username", ""),
        )

    console.print(table)


def handle_process_find(context: Any, args: list[str]) -> None:
    """Search for running processes by partial, case-insensitive name match."""
    console = context.console
    if not args:
        console.print("[bold red]Usage:[/bold red] process find <name>")
        return

    query = args[0].strip()
    matches = find_processes(query)

    if not matches:
        console.print(f"[dim]No running processes found matching '{query}'.[/dim]")
        return

    table = Table(
        title=f"[bold magenta]Processes Matching '{query}' ({len(matches)} found)[/bold magenta]",
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("PID", justify="right", style="dim", no_wrap=True)
    table.add_column("Name", style="bold white", max_width=35, overflow="ellipsis", no_wrap=True)
    table.add_column("Memory (Working Set)", justify="right", style="green", no_wrap=True)
    table.add_column("User", style="dim cyan", max_width=25, overflow="ellipsis", no_wrap=True)

    for p in matches:
        table.add_row(
            str(p.get("pid", "")),
            p.get("name", ""),
            p.get("memory_formatted", ""),
            p.get("username", ""),
        )

    console.print(table)


def handle_process_info(context: Any, args: list[str]) -> None:
    """Inspect a single process by PID without exposing cmdline or environment variables."""
    console = context.console
    if not args:
        console.print("[bold red]Usage:[/bold red] process info <pid>")
        return

    pid, err = parse_pid(args[0])
    if err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        return

    info = get_process_detail(pid)
    if not info:
        console.print(f"[bold red]Error:[/bold red] Process with PID {pid} was not found (it may have exited).")
        return

    grid = Table.grid(padding=(0, 2))
    grid.add_column("Field", style="bold cyan", justify="right")
    grid.add_column("Value", style="white")

    grid.add_row("Process Name:", info.get("name", ""))
    grid.add_row("PID:", str(info.get("pid", "")))
    grid.add_row("Status:", info.get("status", ""))
    grid.add_row("User:", info.get("user", ""))
    grid.add_row("Executable Path:", info.get("exe", ""))
    grid.add_row("Thread Count:", str(info.get("threads", 0)))
    grid.add_row("CPU Utilization:", f"{info.get('cpu_percent', 0.0):.1f}%")
    grid.add_row("Memory (Working Set):", info.get("memory_rss_formatted", "0 MB"))
    grid.add_row("Memory (Virtual / VMS):", info.get("memory_vms_formatted", "0 MB"))
    grid.add_row("Start Time:", info.get("start_time", "Unavailable"))
    grid.add_row("Parent PID:", str(info.get("ppid") if info.get("ppid") is not None else "N/A"))

    panel = Panel(grid, title=f"[bold magenta]Process Details: {info.get('name', '')} (PID {pid})[/bold magenta]", border_style="cyan", expand=False)
    console.print(panel)


def handle_process_kill(context: Any, args: list[str]) -> None:
    """Safely terminate or kill a process by PID with confirmation and protection guards."""
    console = context.console
    force = "--force" in args or "-f" in args
    clean_args = [a for a in args if a not in ("--force", "-f")]

    if not clean_args:
        console.print("[bold red]Usage:[/bold red] process kill <pid> [--force]")
        return

    if len(clean_args) > 1:
        console.print("[bold red]Error:[/bold red] Process kill accepts only one PID at a time. No multiple or wildcard kills.")
        return

    raw_pid = clean_args[0]
    pid, err = parse_pid(raw_pid)
    if err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        return

    # Check protected status first
    is_prot, reason = is_protected_process(pid)
    if is_prot:
        console.print(f"[bold red]Action Refused:[/bold red] {reason}")
        return

    # Fetch metadata for confirmation
    detail = get_process_detail(pid)
    if not detail:
        console.print(f"[bold red]Error:[/bold red] Process with PID {pid} not found (may have already exited).")
        return

    pname = detail.get("name", f"PID {pid}")
    create_time = detail.get("create_time", 0.0)

    # Prompt user with (y/N)
    if force:
        msg = f"[bold red]Are you sure you want to FORCE KILL process '{pname}' (PID {pid})? This cannot be undone and may cause data loss.[/bold red]"
    else:
        msg = f"Are you sure you want to terminate process '{pname}' (PID {pid})?"

    confirmed = confirm_prompt(console, msg, default_yes=False)
    if not confirmed:
        console.print("[dim]Process termination cancelled by user.[/dim]")
        return

    # Execute guarded kill with PID recycling check
    success, res_msg = kill_process_guarded(
        pid,
        force=force,
        expected_name=pname,
        expected_create_time=create_time,
    )

    if success:
        console.print(f"[bold green]Success:[/bold green] {res_msg}")
    else:
        console.print(f"[bold red]Failed:[/bold red] {res_msg}")


def handle_process_dispatcher(context: Any, args: list[str]) -> None:
    """Dispatcher command routing 'process find', 'process info', 'process kill', and 'process list'."""
    console = context.console
    if not args:
        console.print(
            "[bold cyan]MayuriShell Process Management[/bold cyan]\n"
            "Usage:\n"
            "  [bold white]processes[/bold white] [--sort cpu|memory|name] [--limit N]  - List active processes\n"
            "  [bold white]process find <name>[/bold white]                           - Search processes by name\n"
            "  [bold white]process info <pid>[/bold white]                            - Display details for a PID\n"
            "  [bold white]process kill <pid> [--force][/bold white]                  - Terminate process by PID\n"
        )
        return

    subcmd = args[0].lower()
    sub_args = args[1:]

    if subcmd == "find":
        handle_process_find(context, sub_args)
    elif subcmd == "info":
        handle_process_info(context, sub_args)
    elif subcmd == "kill":
        handle_process_kill(context, sub_args)
    elif subcmd in ("list", "ls"):
        handle_processes(context, sub_args)
    else:
        console.print(f"[bold red]Unknown process subcommand '{subcmd}'.[/bold red] Valid subcommands: find, info, kill, list.")


def register_process_commands(registry: CommandRegistry) -> None:
    """Register all process management commands in the CommandRegistry."""
    registry.register(
        CommandInfo(
            name="processes",
            description="List running processes with CPU and Working Set memory usage",
            handler=handle_processes,
            usage="processes [--sort cpu|memory|name] [--limit N]",
            category="Processes",
            arg_rules=ArgumentRules(min_args=0, max_args=4),
        )
    )
    registry.register(
        CommandInfo(
            name="process",
            description="Process management tools (find, info, kill, list)",
            handler=handle_process_dispatcher,
            usage="process <find|info|kill|list> [arguments]",
            category="Processes",
            arg_rules=ArgumentRules(min_args=0, max_args=5),
        )
    )
