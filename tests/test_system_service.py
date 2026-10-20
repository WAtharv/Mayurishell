"""Unit tests for services/system_service.py with complete psutil mocking.
No test may kill or terminate a real process.
"""
from collections import namedtuple
import os
from unittest.mock import MagicMock, patch

import psutil
import pytest

from services.system_service import (
    find_processes,
    format_bytes_gb,
    format_bytes_mb_or_gb,
    format_duration,
    get_ancestor_pids,
    get_cpu_info,
    get_disk_info,
    get_memory_info,
    get_os_info,
    get_process_detail,
    get_python_info,
    get_sysinfo_summary,
    get_uptime,
    is_protected_process,
    kill_process_guarded,
    list_processes,
)


def test_format_helpers() -> None:
    """Test format helpers for bytes and durations."""
    assert format_bytes_gb(1024**3 * 5) == "5.0 GB"
    assert format_bytes_mb_or_gb(1024**2 * 100) == "100.0 MB"
    assert format_bytes_mb_or_gb(1024**3 * 2) == "2.0 GB"
    assert "day" in format_duration(86400 * 2 + 3600)


def test_system_info_metrics() -> None:
    """Test system info metrics retrieval."""
    os_info = get_os_info()
    assert "system" in os_info
    assert "architecture" in os_info

    py_info = get_python_info()
    assert "version" in py_info
    assert "implementation" in py_info

    with patch("psutil.boot_time", return_value=1700000000.0):
        uptime = get_uptime()
        assert "boot_time" in uptime
        assert uptime["uptime_seconds"] > 0

    with patch("psutil.cpu_percent", return_value=15.5), \
         patch("psutil.cpu_count", side_effect=[4, 8]), \
         patch("psutil.cpu_freq", return_value=None):
        cpu = get_cpu_info()
        assert cpu["overall_percent"] == 15.5
        assert cpu["physical_cores"] == 4
        assert cpu["logical_cores"] == 8

    vmem_mock = namedtuple("VMem", ["total", "available", "used", "percent"])(16 * 1024**3, 8 * 1024**3, 8 * 1024**3, 50.0)
    swap_mock = namedtuple("Swap", ["total", "used", "free", "percent"])(4 * 1024**3, 1 * 1024**3, 3 * 1024**3, 25.0)
    with patch("psutil.virtual_memory", return_value=vmem_mock), \
         patch("psutil.swap_memory", return_value=swap_mock):
        mem = get_memory_info()
        assert mem["virtual"]["percent"] == 50.0
        assert mem["swap"]["percent"] == 25.0


def test_disk_info_skips_unready_drives() -> None:
    """Test disk info skips optical drives / unready volumes raising OSError."""
    part1 = namedtuple("Partition", ["device", "mountpoint", "fstype"])("C:", "C:\\", "NTFS")
    part2 = namedtuple("Partition", ["device", "mountpoint", "fstype"])("D:", "D:\\", "CDFS")
    usage1 = namedtuple("Usage", ["total", "used", "free", "percent"])(100 * 1024**3, 40 * 1024**3, 60 * 1024**3, 40.0)

    def mock_usage(mount: str):
        if "D:" in mount:
            raise OSError("Drive not ready")
        return usage1

    with patch("psutil.disk_partitions", return_value=[part1, part2]), \
         patch("psutil.disk_usage", side_effect=mock_usage):
        disks = get_disk_info()
        assert len(disks) == 1
        assert disks[0]["mountpoint"] == "C:\\"
        assert disks[0]["total_formatted"] == "100.0 GB"


def test_protected_processes() -> None:
    """Test refusal of critical system PIDs, ancestors, and foreign-user processes."""
    # PID 0 and 4
    is_prot0, reason0 = is_protected_process(0)
    assert is_prot0 is True
    assert "kernel process" in reason0

    is_prot4, reason4 = is_protected_process(4)
    assert is_prot4 is True
    assert "kernel process" in reason4

    # Shell itself
    my_pid = os.getpid()
    is_self, reason_self = is_protected_process(my_pid)
    assert is_self is True
    assert "itself" in reason_self

    # Ancestor terminal process
    with patch("services.system_service.get_ancestor_pids", return_value={9999}):
        is_anc, reason_anc = is_protected_process(9999)
        assert is_anc is True
        assert "ancestor terminal" in reason_anc

    # System process name
    mock_explorer = MagicMock()
    mock_explorer.pid = 1234
    mock_explorer.name.return_value = "explorer.exe"
    mock_explorer.username.return_value = "DOMAIN\\Mayuri"
    with patch("services.system_service.get_current_user_name", return_value="mayuri"):
        is_exp, reason_exp = is_protected_process(mock_explorer)
        assert is_exp is True
        assert "protected Windows system process" in reason_exp

    # Foreign user / System owned process
    mock_foreign = MagicMock()
    mock_foreign.pid = 5678
    mock_foreign.name.return_value = "other_app.exe"
    mock_foreign.username.return_value = "NT AUTHORITY\\SYSTEM"
    with patch("services.system_service.get_current_user_name", return_value="mayuri"):
        is_foreign, reason_foreign = is_protected_process(mock_foreign)
        assert is_foreign is True
        assert "owned by another user or the system" in reason_foreign


def test_list_and_find_processes() -> None:
    """Test list_processes sorting and find_processes filtering."""
    p1 = MagicMock()
    p1.pid = 101
    p1.name.return_value = "notepad.exe"
    p1.cpu_percent.return_value = 2.5
    p1.memory_info.return_value = namedtuple("Mem", ["rss"])(50 * 1024**2)
    p1.username.return_value = "Mayuri"

    p2 = MagicMock()
    p2.pid = 102
    p2.name.return_value = "code.exe"
    p2.cpu_percent.return_value = 10.0
    p2.memory_info.return_value = namedtuple("Mem", ["rss"])(300 * 1024**2)
    p2.username.return_value = "Mayuri"

    with patch("psutil.process_iter", return_value=[p1, p2]), \
         patch("time.sleep", return_value=None):
        by_mem = list_processes(sort_by="memory", limit=10)
        assert by_mem[0]["name"] == "code.exe"
        assert by_mem[1]["name"] == "notepad.exe"

        by_cpu = list_processes(sort_by="cpu", limit=10)
        assert by_cpu[0]["name"] == "code.exe"

    # Test find_processes
    proc_info_list = [
        MagicMock(info={"pid": 101, "name": "notepad.exe", "memory_info": namedtuple("Mem", ["rss"])(50 * 1024**2), "username": "Mayuri"}),
        MagicMock(info={"pid": 102, "name": "code.exe", "memory_info": namedtuple("Mem", ["rss"])(300 * 1024**2), "username": "Mayuri"}),
    ]
    with patch("psutil.process_iter", return_value=proc_info_list):
        matches = find_processes("note")
        assert len(matches) == 1
        assert matches[0]["name"] == "notepad.exe"


def test_process_detail_never_exposes_cmdline_or_env() -> None:
    """Test get_process_detail provides required fields and omits cmdline/env."""
    mock_p = MagicMock()
    mock_p.pid = 555
    mock_p.name.return_value = "worker.exe"
    mock_p.status.return_value = "running"
    mock_p.create_time.return_value = 1700000000.0
    mock_p.exe.return_value = "C:\\Tools\\worker.exe"
    mock_p.username.return_value = "Mayuri"
    mock_p.num_threads.return_value = 4
    mock_p.cpu_percent.return_value = 1.0
    mock_p.memory_info.return_value = namedtuple("Mem", ["rss", "vms"])(64 * 1024**2, 128 * 1024**2)
    mock_p.ppid.return_value = 100

    with patch("psutil.Process", return_value=mock_p):
        detail = get_process_detail(555)
        assert detail is not None
        assert detail["name"] == "worker.exe"
        assert detail["exe"] == "C:\\Tools\\worker.exe"
        assert "cmdline" not in detail
        assert "environ" not in detail
        assert "env" not in detail


def test_kill_process_guarded_recheck_identity() -> None:
    """Test guarded kill aborts if process identity (name or create_time) changed."""
    mock_p = MagicMock()
    mock_p.pid = 777
    mock_p.name.return_value = "new_process.exe"
    mock_p.create_time.return_value = 1700000000.0

    with patch("psutil.Process", return_value=mock_p), \
         patch("services.system_service.is_protected_process", return_value=(False, "")):
        success, msg = kill_process_guarded(
            pid=777,
            force=False,
            expected_name="old_target.exe",
            expected_create_time=1700000000.0,
        )
        assert success is False
        assert "identity changed" in msg
        mock_p.terminate.assert_not_called()
        mock_p.kill.assert_not_called()


def test_kill_process_guarded_terminate_and_force() -> None:
    """Test terminate and force kill flows with wait up to 3 seconds."""
    mock_p = MagicMock()
    mock_p.pid = 888
    mock_p.name.return_value = "test_target.exe"
    mock_p.create_time.return_value = 1700000000.0

    with patch("psutil.Process", return_value=mock_p), \
         patch("services.system_service.is_protected_process", return_value=(False, "")):
        # Normal terminate
        mock_p.wait.return_value = None
        success, msg = kill_process_guarded(888, force=False, expected_name="test_target.exe", expected_create_time=1700000000.0)
        assert success is True
        mock_p.terminate.assert_called_once()
        mock_p.wait.assert_called_with(timeout=3.0)

        # Force kill
        mock_p.reset_mock()
        success_force, msg_force = kill_process_guarded(888, force=True, expected_name="test_target.exe", expected_create_time=1700000000.0)
        assert success_force is True
        mock_p.kill.assert_called_once()
        mock_p.wait.assert_called_with(timeout=3.0)


def test_kill_process_access_denied() -> None:
    """Test AccessDenied is handled cleanly without crashing."""
    mock_p = MagicMock()
    mock_p.pid = 999
    mock_p.name.return_value = "system_protected.exe"
    mock_p.create_time.return_value = 1700000000.0
    mock_p.terminate.side_effect = psutil.AccessDenied()

    with patch("psutil.Process", return_value=mock_p), \
         patch("services.system_service.is_protected_process", return_value=(False, "")):
        success, msg = kill_process_guarded(999, force=False, expected_name="system_protected.exe", expected_create_time=1700000000.0)
        assert success is False
        assert "Access denied" in msg
