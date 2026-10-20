"""Process inspection and management commands: processes, process find, process info, process kill."""
from __future__ import annotations

from typing import Any

from rich.markup import escape
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
    theme = context.theme
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
                console.print(f"{theme.format_error('Invalid sort option:')} '{escape(args[i + 1])}'. Choose from: cpu, memory, name.")
                return
            i += 2
        elif arg.startswith("--sort="):
            sort_val = arg.split("=", 1)[1].lower()
            if sort_val in ("cpu", "memory", "name"):
                sort_by = sort_val
            else:
                console.print(f"{theme.format_error('Invalid sort option:')} '{escape(sort_val)}'. Choose from: cpu, memory, name.")
                return
            i += 1
        elif arg in ("--limit", "-l", "-n") and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit <= 0:
                    raise ValueError
            except ValueError:
                console.print(f"{theme.format_error('Invalid limit:')} '{escape(args[i + 1])}'. Must be a positive integer.")
                return
            i += 2
        elif arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
                if limit <= 0:
                    raise ValueError
            except ValueError:
                console.print(f"{theme.format_error('Invalid limit value.')} Must be a positive integer.")
                return
            i += 1
        else:
            i += 1

    console.print(theme.format_muted("Collecting process statistics (sampling CPU)..."))
    procs = list_processes(sort_by=sort_by, limit=limit)

    table = theme.create_table(
        title=f"Running Processes (Top {len(procs)} by {sort_by.capitalize()})",
    )
    table.add_column("PID", justify="right", style=theme.muted_style, no_wrap=True)
    table.add_column("Name", style=theme.bold_text_style, max_width=35, overflow=theme.overflow, no_wrap=True)
    table.add_column("CPU %", justify="right", style=theme.warning_style, no_wrap=True)
    table.add_column("Memory (Working Set)", justify="right", style=theme.success_style, no_wrap=True)
    table.add_column("User", style=theme.muted_style, max_width=25, overflow=theme.overflow, no_wrap=True)

    for p in procs:
        cpu_val = p.get("cpu_percent", 0.0)
        cpu_str = theme.format_warning(f"{cpu_val:.1f}%", bold=True) if cpu_val > 0.0 else f"{cpu_val:.1f}%"
        table.add_row(
            escape(str(p.get("pid", ""))),
            escape(str(p.get("name", ""))),
            cpu_str,
            escape(str(p.get("memory_formatted", ""))),
            escape(str(p.get("username", ""))),
        )

    console.print(table)


def handle_process_find(context: Any, args: list[str]) -> None:
    """Search for running processes by partial, case-insensitive name match."""
    console = context.console
    theme = context.theme
    if not args:
        console.print(f"{theme.format_error('Usage:')} process find <name>")
        return

    query = args[0].strip()
    matches = find_processes(query)

    if not matches:
        console.print(theme.format_muted(f"No running processes found matching '{escape(query)}'."))
        return

    table = theme.create_table(
        title=f"Processes Matching '{escape(query)}' ({len(matches)} found)",
    )
    table.add_column("PID", justify="right", style=theme.muted_style, no_wrap=True)
    table.add_column("Name", style=theme.bold_text_style, max_width=35, overflow=theme.overflow, no_wrap=True)
    table.add_column("Memory (Working Set)", justify="right", style=theme.success_style, no_wrap=True)
    table.add_column("User", style=theme.muted_style, max_width=25, overflow=theme.overflow, no_wrap=True)

    for p in matches:
        table.add_row(
            escape(str(p.get("pid", ""))),
            escape(str(p.get("name", ""))),
            escape(str(p.get("memory_formatted", ""))),
            escape(str(p.get("username", ""))),
        )

    console.print(table)


def handle_process_info(context: Any, args: list[str]) -> None:
    """Inspect a single process by PID without exposing cmdline or environment variables."""
    console = context.console
    theme = context.theme
    if not args:
        console.print(f"{theme.format_error('Usage:')} process info <pid>")
        return

    pid, err = parse_pid(args[0])
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return

    info = get_process_detail(pid)
    if not info:
        console.print(f"{theme.format_error('Error:')} Process with PID {pid} was not found (it may have exited).")
        return

    grid = Table.grid(padding=(0, 2))
    grid.add_column("Field", style=theme.bold_primary_style, justify="right")
    grid.add_column("Value", style=theme.text_style, overflow="fold")

    grid.add_row("Process Name:", escape(str(info.get("name", ""))))
    grid.add_row("PID:", escape(str(info.get("pid", ""))))
    grid.add_row("Status:", escape(str(info.get("status", ""))))
    grid.add_row("User:", escape(str(info.get("user", ""))))
    grid.add_row("Executable Path:", escape(str(info.get("exe", ""))))
    grid.add_row("Thread Count:", escape(str(info.get("threads", 0))))
    grid.add_row("CPU Utilization:", f"{info.get('cpu_percent', 0.0):.1f}%")
    grid.add_row("Memory (Working Set):", escape(str(info.get("memory_rss_formatted", "0 MB"))))
    grid.add_row("Memory (Virtual / VMS):", escape(str(info.get("memory_vms_formatted", "0 MB"))))
    grid.add_row("Start Time:", escape(str(info.get("start_time", "Unavailable"))))
    grid.add_row("Parent PID:", escape(str(info.get("ppid") if info.get("ppid") is not None else "N/A")))

    panel = theme.create_panel(grid, title=f"Process Details: {escape(info.get('name', ''))} (PID {pid})", expand=False)
    console.print(panel)


def handle_process_kill(context: Any, args: list[str]) -> None:
    """Safely terminate or kill a process by PID with confirmation and protection guards."""
    console = context.console
    theme = context.theme
    force = "--force" in args or "-f" in args
    clean_args = [a for a in args if a not in ("--force", "-f")]

    if not clean_args:
        console.print(f"{theme.format_error('Usage:')} process kill <pid> [--force]")
        return

    if len(clean_args) > 1:
        console.print(f"{theme.format_error('Error:')} Process kill accepts only one PID at a time. No multiple or wildcard kills.")
        return

    raw_pid = clean_args[0]
    pid, err = parse_pid(raw_pid)
    if err:
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return

    # Check protected status first
    is_prot, reason = is_protected_process(pid)
    if is_prot:
        console.print(f"{theme.format_error('Action Refused:')} {escape(reason)}")
        return

    # Fetch metadata for confirmation
    detail = get_process_detail(pid)
    if not detail:
        console.print(f"{theme.format_error('Error:')} Process with PID {pid} not found (may have already exited).")
        return

    pname = detail.get("name", f"PID {pid}")
    create_time = detail.get("create_time", 0.0)

    # Prompt user with (y/N)
    if force:
        msg = theme.format_error(
            f"Are you sure you want to FORCE KILL process '{escape(pname)}' (PID {pid})? This cannot be undone and may cause data loss.",
            bold=True,
        )
    else:
        msg = f"Are you sure you want to terminate process '{escape(pname)}' (PID {pid})?"

    confirmed = confirm_prompt(console, msg, default_yes=False, theme=theme)
    if not confirmed:
        console.print(theme.format_muted("Process termination cancelled by user."))
        return

    # Execute guarded kill with PID recycling check
    success, res_msg = kill_process_guarded(
        pid,
        force=force,
        expected_name=pname,
        expected_create_time=create_time,
    )

    if success:
        console.print(f"{theme.format_success('Success:', bold=True)} {escape(res_msg)}")
    else:
        console.print(f"{theme.format_error('Failed:', bold=True)} {escape(res_msg)}")


def handle_process_dispatcher(context: Any, args: list[str]) -> None:
    """Dispatcher command routing 'process find', 'process info', 'process kill', and 'process list'."""
    console = context.console
    theme = context.theme
    if not args:
        console.print(
            f"{theme.format_primary('MayuriShell Process Management', bold=True)}\n"
            f"Usage:\n"
            f"  {theme.format_text('processes', bold=True)} [--sort cpu|memory|name] [--limit N]  - List active processes\n"
            f"  {theme.format_text('process find <name>', bold=True)}                           - Search processes by name\n"
            f"  {theme.format_text('process info <pid>', bold=True)}                            - Display details for a PID\n"
            f"  {theme.format_text('process kill <pid> [--force]', bold=True)}                  - Terminate process by PID\n"
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
        err_msg = theme.format_error(f"Unknown process subcommand '{escape(subcmd)}'.")
        console.print(
            f"{err_msg} "
            f"Valid subcommands: find, info, kill, list."
        )


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
