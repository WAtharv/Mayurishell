"""System monitoring commands: sysinfo, cpu, memory, disk, uptime."""
from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.system_service import (
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_sysinfo_summary,
    get_uptime,
)


def handle_sysinfo(context: Any, args: list[str]) -> None:
    """Display comprehensive system overview summary."""
    console = context.console
    data = get_sysinfo_summary()

    os_info = data.get("os", {})
    py_info = data.get("python", {})
    user_host = data.get("user_host", {})
    uptime = data.get("uptime", {})
    cpu = data.get("cpu", {})
    memory = data.get("memory", {}).get("virtual", {})
    main_disk = data.get("main_disk")

    table = Table.grid(padding=(0, 2))
    table.add_column("Key", style="bold cyan", justify="right")
    table.add_column("Value", style="white")

    # System & Platform
    table.add_row("Operating System:", f"{os_info.get('windows_version', os_info.get('system', 'Windows'))} ({os_info.get('architecture', '64-bit')})")
    table.add_row("Python Runtime:", f"Python {py_info.get('version', '3.11')} ({py_info.get('implementation', 'CPython')})")
    table.add_row("User / Hostname:", f"{user_host.get('user', 'User')} @ {user_host.get('hostname', 'localhost')}")
    table.add_row("System Uptime:", uptime.get("formatted_uptime", "Unavailable"))

    # Hardware stats
    cpu_cores = f"{cpu.get('physical_cores', 0)} physical, {cpu.get('logical_cores', 0)} logical cores"
    cpu_str = f"{cpu.get('overall_percent', 0.0)}% ({cpu_cores})"
    table.add_row("CPU Utilization:", cpu_str)

    ram_str = f"{memory.get('used_formatted', '0 GB')} used / {memory.get('total_formatted', '0 GB')} total ({memory.get('percent', 0.0)}%)"
    table.add_row("RAM Usage:", ram_str)

    if main_disk:
        disk_str = f"{main_disk.get('mountpoint', 'C:')} - {main_disk.get('used_formatted', '0 GB')} used / {main_disk.get('total_formatted', '0 GB')} ({main_disk.get('percent', 0.0)}%)"
        table.add_row("Primary Storage:", disk_str)

    panel = Panel(
        table,
        title="[bold magenta]System Information[/bold magenta]",
        border_style="cyan",
        expand=False,
    )
    console.print(panel)


def handle_cpu(context: Any, args: list[str]) -> None:
    """Display detailed CPU utilization, core counts, and clock frequencies."""
    console = context.console
    cpu = get_cpu_info()

    # Overview table
    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_column("Key", style="bold cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Overall Utilization:", f"[bold yellow]{cpu.get('overall_percent', 0.0)}%[/bold yellow]")
    summary_table.add_row("Physical Cores:", str(cpu.get("physical_cores", "N/A")))
    summary_table.add_row("Logical Processors:", str(cpu.get("logical_cores", "N/A")))

    freq = cpu.get("frequency", {})
    if freq and freq.get("current"):
        summary_table.add_row("Current Clock:", f"{freq['current']:.0f} MHz")

    panel = Panel(summary_table, title="[bold magenta]CPU Overview[/bold magenta]", border_style="cyan", expand=False)
    console.print(panel)

    # Per-core breakdown table
    per_cpu = cpu.get("per_cpu_percent", [])
    if per_cpu:
        core_table = Table(title="Per-Core Utilization", border_style="purple", header_style="bold cyan")
        core_table.add_column("Core", justify="center", style="dim")
        core_table.add_column("Utilization", justify="right", style="yellow")
        core_table.add_column("Status", style="white")

        for idx, pct in enumerate(per_cpu):
            if pct > 80:
                status = "[bold red]High[/bold red]"
            elif pct > 50:
                status = "[yellow]Moderate[/yellow]"
            else:
                status = "[green]Normal[/green]"
            core_table.add_row(f"Core #{idx}", f"{pct:.1f}%", status)

        console.print(core_table)


def handle_memory(context: Any, args: list[str]) -> None:
    """Display detailed virtual memory and swap statistics."""
    console = context.console
    mem = get_memory_info()
    vmem = mem.get("virtual", {})
    swap = mem.get("swap", {})

    table = Table(title="[bold magenta]Memory Status[/bold magenta]", border_style="cyan", header_style="bold cyan")
    table.add_column("Type", style="bold white")
    table.add_column("Used", justify="right", style="yellow")
    table.add_column("Available / Free", justify="right", style="green")
    table.add_column("Total", justify="right", style="dim cyan")
    table.add_column("Usage %", justify="right", style="bold magenta")

    table.add_row(
        "RAM (Physical)",
        vmem.get("used_formatted", "0 GB"),
        vmem.get("available_formatted", "0 GB"),
        vmem.get("total_formatted", "0 GB"),
        f"{vmem.get('percent', 0.0):.1f}%",
    )
    table.add_row(
        "Swap / Pagefile",
        swap.get("used_formatted", "0 GB"),
        swap.get("free_formatted", "0 GB"),
        swap.get("total_formatted", "0 GB"),
        f"{swap.get('percent', 0.0):.1f}%",
    )
    console.print(table)


def handle_disk(context: Any, args: list[str]) -> None:
    """Display disk partition usage, skipping unready drives."""
    console = context.console
    disks = get_disk_info()

    if not disks:
        console.print("[bold yellow]No ready disk volumes detected.[/bold yellow]")
        return

    table = Table(title="[bold magenta]Storage Volumes[/bold magenta]", border_style="cyan", header_style="bold cyan")
    table.add_column("Drive", style="bold white")
    table.add_column("Filesystem", style="dim")
    table.add_column("Used", justify="right", style="yellow")
    table.add_column("Free", justify="right", style="green")
    table.add_column("Total", justify="right", style="dim cyan")
    table.add_column("Usage %", justify="right", style="bold magenta")

    for d in disks:
        pct = d.get("percent", 0.0)
        pct_color = "red" if pct >= 90 else ("yellow" if pct >= 75 else "green")
        table.add_row(
            f"{d.get('mountpoint', '')} ({d.get('device', '')})",
            d.get("fstype", "NTFS"),
            d.get("used_formatted", "0 GB"),
            d.get("free_formatted", "0 GB"),
            d.get("total_formatted", "0 GB"),
            f"[{pct_color}]{pct:.1f}%[/{pct_color}]",
        )

    console.print(table)


def handle_uptime(context: Any, args: list[str]) -> None:
    """Display system boot timestamp and elapsed running duration."""
    console = context.console
    uptime = get_uptime()

    table = Table.grid(padding=(0, 2))
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Boot Timestamp:", uptime.get("boot_time", "Unavailable"))
    table.add_row("Active Uptime:", f"[bold green]{uptime.get('formatted_uptime', 'Unavailable')}[/bold green]")

    panel = Panel(table, title="[bold magenta]System Uptime[/bold magenta]", border_style="cyan", expand=False)
    console.print(panel)


def register_system_commands(registry: CommandRegistry) -> None:
    """Register all system inspection commands in the CommandRegistry."""
    registry.register(
        CommandInfo(
            name="sysinfo",
            description="Display comprehensive system overview summary",
            handler=handle_sysinfo,
            usage="sysinfo",
            category="System",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
    registry.register(
        CommandInfo(
            name="cpu",
            description="Display detailed CPU utilization and core statistics",
            handler=handle_cpu,
            usage="cpu",
            category="System",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
    registry.register(
        CommandInfo(
            name="memory",
            description="Display RAM and swap file statistics",
            handler=handle_memory,
            usage="memory",
            category="System",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
    registry.register(
        CommandInfo(
            name="disk",
            description="Display storage drive usage and capacity in GB",
            handler=handle_disk,
            usage="disk",
            category="System",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
    registry.register(
        CommandInfo(
            name="uptime",
            description="Display system boot timestamp and uptime",
            handler=handle_uptime,
            usage="uptime",
            category="System",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
