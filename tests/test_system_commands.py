"""Integration tests for system commands: sysinfo, cpu, memory, disk, uptime."""
from pathlib import Path
from unittest.mock import patch
from rich.console import Console

from commands.system import register_system_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell


def create_system_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to initialize shell with system commands."""
    config = ConfigManager(base_dir=tmp_path / "appdata")
    history = HistoryManager(tmp_path / "appdata" / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_system_commands(registry)

    console = Console(record=True, color_system=None, width=120)
    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        console=console,
        current_dir=tmp_path,
    )
    return shell, console


def test_command_sysinfo(tmp_path: Path) -> None:
    """Test sysinfo command renders system information overview panel."""
    shell, console = create_system_test_shell(tmp_path)

    mock_summary = {
        "os": {"windows_version": "Windows 11 (Build 22631)", "architecture": "64bit"},
        "python": {"version": "3.11.9", "implementation": "CPython"},
        "user_host": {"user": "Mayuri", "hostname": "DESKTOP-PC"},
        "uptime": {"formatted_uptime": "2 days, 4 hrs, 10 mins"},
        "cpu": {"overall_percent": 12.5, "physical_cores": 8, "logical_cores": 16},
        "memory": {"virtual": {"used_formatted": "6.5 GB", "total_formatted": "16.0 GB", "percent": 40.6}},
        "main_disk": {"mountpoint": "C:\\", "used_formatted": "120.0 GB", "total_formatted": "500.0 GB", "percent": 24.0},
    }

    with patch("commands.system.get_sysinfo_summary", return_value=mock_summary):
        shell.run_command_line("sysinfo")
        output = console.export_text()
        assert "System Information" in output
        assert "Windows 11" in output
        assert "Python 3.11.9" in output
        assert "Mayuri @ DESKTOP-PC" in output
        assert "2 days, 4 hrs" in output


def test_command_cpu(tmp_path: Path) -> None:
    """Test cpu command renders overall and per-core statistics."""
    shell, console = create_system_test_shell(tmp_path)

    mock_cpu = {
        "overall_percent": 18.0,
        "physical_cores": 4,
        "logical_cores": 8,
        "frequency": {"current": 3200.0},
        "per_cpu_percent": [10.0, 25.0, 5.0, 30.0],
    }

    with patch("commands.system.get_cpu_info", return_value=mock_cpu):
        shell.run_command_line("cpu")
        output = console.export_text()
        assert "CPU Overview" in output
        assert "18.0%" in output
        assert "Per-Core Utilization" in output
        assert "Core #0" in output


def test_command_memory(tmp_path: Path) -> None:
    """Test memory command displays virtual and swap stats."""
    shell, console = create_system_test_shell(tmp_path)

    mock_mem = {
        "virtual": {"used_formatted": "8.0 GB", "available_formatted": "8.0 GB", "total_formatted": "16.0 GB", "percent": 50.0},
        "swap": {"used_formatted": "1.0 GB", "free_formatted": "3.0 GB", "total_formatted": "4.0 GB", "percent": 25.0},
    }

    with patch("commands.system.get_memory_info", return_value=mock_mem):
        shell.run_command_line("memory")
        output = console.export_text()
        assert "Memory Status" in output
        assert "RAM (Physical)" in output
        assert "16.0 GB" in output
        assert "50.0%" in output


def test_command_disk(tmp_path: Path) -> None:
    """Test disk command displays volume list with GB formatted sizes."""
    shell, console = create_system_test_shell(tmp_path)

    mock_disks = [
        {"mountpoint": "C:\\", "device": "C:", "fstype": "NTFS", "used_formatted": "150.0 GB", "free_formatted": "350.0 GB", "total_formatted": "500.0 GB", "percent": 30.0},
    ]

    with patch("commands.system.get_disk_info", return_value=mock_disks):
        shell.run_command_line("disk")
        output = console.export_text()
        assert "Storage Volumes" in output
        assert "C:\\" in output
        assert "500.0 GB" in output
        assert "30.0%" in output


def test_command_uptime(tmp_path: Path) -> None:
    """Test uptime command displays boot time and duration."""
    shell, console = create_system_test_shell(tmp_path)

    mock_uptime = {
        "boot_time": "2026-10-18 09:00:00",
        "formatted_uptime": "2 days, 4 hrs, 45 mins",
    }

    with patch("commands.system.get_uptime", return_value=mock_uptime):
        shell.run_command_line("uptime")
        output = console.export_text()
        assert "System Uptime" in output
        assert "2026-10-18 09:00:00" in output
        assert "2 days, 4 hrs, 45 mins" in output
