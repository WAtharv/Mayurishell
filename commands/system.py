"""System monitoring commands: sysinfo, cpu, memory, disk, uptime."""
from __future__ import annotations

from typing import Any

from rich.markup import escape
from rich.table import Table

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
    theme = context.theme
    data = get_sysinfo_summary()

    os_info = data.get("os", {})
    py_info = data.get("python", {})
    user_host = data.get("user_host", {})
    uptime = data.get("uptime", {})
    cpu = data.get("cpu", {})
    memory = data.get("memory", {}).get("virtual", {})
    main_disk = data.get("main_disk")

    table = Table.grid(padding=(0, 2))
    table.add_column("Key", style=theme.bold_primary_style, justify="right")
    table.add_column("Value", style=theme.text_style, overflow="fold")

    # System & Platform
    table.add_row(
        "Operating System:",
        escape(f"{os_info.get('windows_version', os_info.get('system', 'Windows'))} ({os_info.get('architecture', '64-bit')})"),
    )
    table.add_row(
        "Python Runtime:",
        escape(f"Python {py_info.get('version', '3.11')} ({py_info.get('implementation', 'CPython')})"),
    )
    table.add_row(
        "User / Hostname:",
        escape(f"{user_host.get('user', 'User')} @ {user_host.get('hostname', 'localhost')}"),
    )
    table.add_row("System Uptime:", escape(str(uptime.get("formatted_uptime", "Unavailable"))))

    # Hardware stats
    cpu_cores = f"{cpu.get('physical_cores', 0)} physical, {cpu.get('logical_cores', 0)} logical cores"
    cpu_str = f"{cpu.get('overall_percent', 0.0)}% ({cpu_cores})"
    table.add_row("CPU Utilization:", escape(cpu_str))

    ram_str = f"{memory.get('used_formatted', '0 GB')} used / {memory.get('total_formatted', '0 GB')} total ({memory.get('percent', 0.0)}%)"
    table.add_row("RAM Usage:", escape(ram_str))

    if main_disk:
        disk_str = f"{main_disk.get('mountpoint', 'C:')} - {main_disk.get('used_formatted', '0 GB')} used / {main_disk.get('total_formatted', '0 GB')} ({main_disk.get('percent', 0.0)}%)"
        table.add_row("Primary Storage:", escape(disk_str))

    panel = theme.create_panel(
        table,
        title="System Information",
        expand=False,
    )
    console.print(panel)


def handle_cpu(context: Any, args: list[str]) -> None:
    """Display detailed CPU utilization, core counts, and clock frequencies."""
    console = context.console
    theme = context.theme
    cpu = get_cpu_info()

    # Overview table
    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_column("Key", style=theme.bold_primary_style)
    summary_table.add_column("Value", style=theme.text_style, overflow="fold")

    summary_table.add_row("Overall Utilization:", theme.format_warning(f"{cpu.get('overall_percent', 0.0)}%", bold=True))
    summary_table.add_row("Physical Cores:", str(cpu.get("physical_cores", "N/A")))
    summary_table.add_row("Logical Processors:", str(cpu.get("logical_cores", "N/A")))

    freq = cpu.get("frequency", {})
    if freq and freq.get("current"):
        summary_table.add_row("Current Clock:", f"{freq['current']:.0f} MHz")

    panel = theme.create_panel(summary_table, title="CPU Overview", expand=False)
    console.print(panel)

    # Per-core breakdown table
    per_cpu = cpu.get("per_cpu_percent", [])
    if per_cpu:
        core_table = theme.create_table(title="Per-Core Utilization")
        core_table.add_column("Core", justify="center", style=theme.muted_style)
        core_table.add_column("Utilization", justify="right", style=theme.warning_style)
        core_table.add_column("Status", style=theme.text_style)

        for idx, pct in enumerate(per_cpu):
            if pct > 80:
                status = theme.format_error("High", bold=True)
            elif pct > 50:
                status = theme.format_warning("Moderate")
            else:
                status = theme.format_success("Normal")
            core_table.add_row(f"Core #{idx}", f"{pct:.1f}%", status)

        console.print(core_table)


def handle_memory(context: Any, args: list[str]) -> None:
    """Display detailed virtual memory and swap statistics."""
    console = context.console
    theme = context.theme
    mem = get_memory_info()
    vmem = mem.get("virtual", {})
    swap = mem.get("swap", {})

    table = theme.create_table(title="Memory Status")
    table.add_column("Type", style=theme.bold_text_style)
    table.add_column("Used", justify="right", style=theme.warning_style)
    table.add_column("Available / Free", justify="right", style=theme.success_style)
    table.add_column("Total", justify="right", style=theme.muted_style)
    table.add_column("Usage %", justify="right", style=theme.bold_primary_style)

    table.add_row(
        "RAM (Physical)",
        escape(str(vmem.get("used_formatted", "0 GB"))),
        escape(str(vmem.get("available_formatted", "0 GB"))),
        escape(str(vmem.get("total_formatted", "0 GB"))),
        f"{vmem.get('percent', 0.0):.1f}%",
    )
    table.add_row(
        "Swap / Pagefile",
        escape(str(swap.get("used_formatted", "0 GB"))),
        escape(str(swap.get("free_formatted", "0 GB"))),
        escape(str(swap.get("total_formatted", "0 GB"))),
        f"{swap.get('percent', 0.0):.1f}%",
    )
    console.print(table)


def handle_disk(context: Any, args: list[str]) -> None:
    """Display disk partition usage, skipping unready drives."""
    console = context.console
    theme = context.theme
    disks = get_disk_info()

    if not disks:
        console.print(theme.format_warning("No ready disk volumes detected.", bold=True))
        return

    table = theme.create_table(title="Storage Volumes")
    table.add_column("Drive", style=theme.bold_text_style)
    table.add_column("Filesystem", style=theme.muted_style)
    table.add_column("Used", justify="right", style=theme.warning_style)
    table.add_column("Free", justify="right", style=theme.success_style)
    table.add_column("Total", justify="right", style=theme.muted_style)
    table.add_column("Usage %", justify="right", style=theme.bold_primary_style)

    for d in disks:
        pct = d.get("percent", 0.0)
        if pct >= 90:
            pct_str = theme.format_error(f"{pct:.1f}%")
        elif pct >= 75:
            pct_str = theme.format_warning(f"{pct:.1f}%")
        else:
            pct_str = theme.format_success(f"{pct:.1f}%")

        table.add_row(
            escape(f"{d.get('mountpoint', '')} ({d.get('device', '')})"),
            escape(str(d.get("fstype", "NTFS"))),
            escape(str(d.get("used_formatted", "0 GB"))),
            escape(str(d.get("free_formatted", "0 GB"))),
            escape(str(d.get("total_formatted", "0 GB"))),
            pct_str,
        )

    console.print(table)


def handle_uptime(context: Any, args: list[str]) -> None:
    """Display system boot timestamp and elapsed running duration."""
    console = context.console
    theme = context.theme
    uptime = get_uptime()

    table = Table.grid(padding=(0, 2))
    table.add_column("Key", style=theme.bold_primary_style)
    table.add_column("Value", style=theme.text_style, overflow="fold")

    table.add_row("Boot Timestamp:", escape(str(uptime.get("boot_time", "Unavailable"))))
    table.add_row(
        "Active Uptime:",
        theme.format_success(escape(str(uptime.get("formatted_uptime", "Unavailable"))), bold=True),
    )

    panel = theme.create_panel(table, title="System Uptime", expand=False)
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
