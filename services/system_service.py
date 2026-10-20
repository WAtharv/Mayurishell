"""System monitoring and process management service for MayuriShell."""
from __future__ import annotations

import datetime
import getpass
import os
from pathlib import Path
import platform
import socket
import sys
import time
from typing import Any

import psutil

from core.logging_config import get_logger

logger = get_logger()

# Protected system processes that MayuriShell refuses to kill under any circumstances
PROTECTED_PROCESS_NAMES = {
    "system",
    "system idle process",
    "smss",
    "smss.exe",
    "csrss",
    "csrss.exe",
    "wininit",
    "wininit.exe",
    "winlogon",
    "winlogon.exe",
    "services",
    "services.exe",
    "lsass",
    "lsass.exe",
    "svchost",
    "svchost.exe",
    "explorer",
    "explorer.exe",
    "dwm",
    "dwm.exe",
    "registry",
    "memory compression",
}


def get_current_user_name() -> str:
    """Get the normalized username of the current user."""
    try:
        user = getpass.getuser().lower()
        # Handle DOMAIN\user format
        if "\\" in user:
            user = user.split("\\")[-1]
        return user
    except Exception:
        return ""


def get_ancestor_pids() -> set[int]:
    """Retrieve the set of all ancestor process PIDs of MayuriShell (parent, grandparent, etc.)."""
    ancestors: set[int] = set()
    try:
        curr = psutil.Process(os.getpid())
        while curr:
            try:
                parent = curr.parent()
                if not parent or parent.pid in ancestors:
                    break
                ancestors.add(parent.pid)
                curr = parent
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                break
    except Exception:
        pass
    return ancestors


def format_bytes_gb(byte_count: int | float) -> str:
    """Format bytes into GB with one decimal place."""
    gb = byte_count / (1024**3)
    return f"{gb:.1f} GB"


def format_bytes_mb_or_gb(byte_count: int | float) -> str:
    """Format bytes into MB or GB depending on magnitude."""
    mb = byte_count / (1024**2)
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.1f} MB"


def format_duration(seconds: float) -> str:
    """Format seconds into 'X days, Y hours, Z minutes'."""
    td = datetime.timedelta(seconds=int(seconds))
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0 or days > 0:
        parts.append(f"{hours} hr{'s' if hours != 1 else ''}")
    parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    return ", ".join(parts)


# --- System Metric Inspection ---

def get_os_info() -> dict[str, str]:
    """Gather operating system and platform details."""
    try:
        win_ver = platform.win32_ver()
        win_str = f"Windows {win_ver[0]} (Build {win_ver[1]} {win_ver[2]})" if win_ver[0] else platform.platform()
    except Exception:
        win_str = platform.platform()

    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "windows_version": win_str,
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
    }


def get_python_info() -> dict[str, str]:
    """Gather Python runtime details."""
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
    }


def get_user_and_host() -> dict[str, str]:
    """Gather user and hostname details."""
    try:
        user = getpass.getuser()
    except Exception:
        user = "Unknown"

    try:
        host = platform.node() or socket.gethostname()
    except Exception:
        host = "Unknown"

    return {"user": user, "hostname": host}


def get_uptime() -> dict[str, Any]:
    """Gather boot time and system uptime."""
    try:
        boot_timestamp = psutil.boot_time()
        boot_dt = datetime.datetime.fromtimestamp(boot_timestamp)
        now = datetime.datetime.now()
        uptime_seconds = (now - boot_dt).total_seconds()
        return {
            "boot_time": boot_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": uptime_seconds,
            "formatted_uptime": format_duration(uptime_seconds),
        }
    except Exception as exc:
        logger.warning("Failed to retrieve uptime: %s", exc)
        return {
            "boot_time": "Unavailable",
            "uptime_seconds": 0.0,
            "formatted_uptime": "Unavailable",
        }


def get_cpu_info() -> dict[str, Any]:
    """Gather CPU utilization, core counts, and frequencies."""
    try:
        overall_usage = psutil.cpu_percent(interval=0.1)
    except Exception:
        overall_usage = 0.0

    try:
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
    except Exception:
        per_cpu = []

    try:
        physical_cores = psutil.cpu_count(logical=False) or 0
    except Exception:
        physical_cores = 0

    try:
        logical_cores = psutil.cpu_count(logical=True) or 0
    except Exception:
        logical_cores = 0

    freq_info: dict[str, float] = {}
    try:
        freq = psutil.cpu_freq()
        if freq:
            freq_info = {
                "current": freq.current,
                "min": freq.min,
                "max": freq.max,
            }
    except Exception:
        pass

    return {
        "overall_percent": overall_usage,
        "per_cpu_percent": per_cpu,
        "physical_cores": physical_cores,
        "logical_cores": logical_cores,
        "frequency": freq_info,
    }


def get_memory_info() -> dict[str, Any]:
    """Gather virtual memory and swap statistics."""
    try:
        vmem = psutil.virtual_memory()
        virtual = {
            "total": vmem.total,
            "available": vmem.available,
            "used": vmem.used,
            "percent": vmem.percent,
            "total_formatted": format_bytes_gb(vmem.total),
            "available_formatted": format_bytes_gb(vmem.available),
            "used_formatted": format_bytes_gb(vmem.used),
        }
    except Exception as exc:
        logger.warning("Failed to retrieve virtual memory: %s", exc)
        virtual = {"total": 0, "available": 0, "used": 0, "percent": 0.0, "total_formatted": "0 GB", "available_formatted": "0 GB", "used_formatted": "0 GB"}

    try:
        smem = psutil.swap_memory()
        swap = {
            "total": smem.total,
            "used": smem.used,
            "free": smem.free,
            "percent": smem.percent,
            "total_formatted": format_bytes_gb(smem.total),
            "used_formatted": format_bytes_gb(smem.used),
            "free_formatted": format_bytes_gb(smem.free),
        }
    except Exception:
        swap = {"total": 0, "used": 0, "free": 0, "percent": 0.0, "total_formatted": "0 GB", "used_formatted": "0 GB", "free_formatted": "0 GB"}

    return {"virtual": virtual, "swap": swap}


def get_disk_info() -> list[dict[str, Any]]:
    """Gather partition usage, skipping unready drives (empty CD / card readers)."""
    disks: list[dict[str, Any]] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception as exc:
        logger.warning("Failed to list disk partitions: %s", exc)
        return disks

    for part in partitions:
        try:
            # Skip unready devices or drives that raise permission/OS errors
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
                "total_formatted": format_bytes_gb(usage.total),
                "used_formatted": format_bytes_gb(usage.used),
                "free_formatted": format_bytes_gb(usage.free),
            })
        except (PermissionError, OSError):
            # Not ready, empty optical drive, or inaccessible volume
            continue
        except Exception as exc:
            logger.debug("Skipping drive %s due to error: %s", part.mountpoint, exc)
            continue

    return disks


def get_sysinfo_summary() -> dict[str, Any]:
    """Compile aggregated system information overview for sysinfo."""
    os_info = get_os_info()
    py_info = get_python_info()
    user_host = get_user_and_host()
    uptime = get_uptime()
    cpu = get_cpu_info()
    memory = get_memory_info()
    disks = get_disk_info()

    # Get primary drive (usually C:\ or mountpoint /)
    main_disk = disks[0] if disks else None

    return {
        "os": os_info,
        "python": py_info,
        "user_host": user_host,
        "uptime": uptime,
        "cpu": cpu,
        "memory": memory,
        "disks": disks,
        "main_disk": main_disk,
    }


# --- Process Management & Safety ---

def is_protected_process(proc_or_pid: int | psutil.Process, proc_name: str | None = None) -> tuple[bool, str]:
    """Determine whether a process is protected and cannot be killed.
    
    Refuses:
      - PIDs 0 and 4
      - MayuriShell itself (os.getpid())
      - The entire ancestor process chain (parent, grandparent, etc.)
      - Critical Windows system process names
      - Processes owned by another user or the system
    """
    if isinstance(proc_or_pid, int):
        pid = proc_or_pid
        try:
            proc = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc = None
    else:
        proc = proc_or_pid
        pid = proc.pid

    # 1. PIDs 0 and 4 (System Idle and System kernel)
    if pid in (0, 4):
        return True, f"Refusing to kill critical Windows kernel process (PID {pid})."

    # 2. MayuriShell itself
    my_pid = os.getpid()
    if pid == my_pid:
        return True, "Refusing to kill MayuriShell itself."

    # 3. MayuriShell ancestor chain (parent terminal, PowerShell, cmd, etc.)
    ancestor_pids = get_ancestor_pids()
    if pid in ancestor_pids:
        return True, f"Refusing to kill MayuriShell ancestor terminal process (PID {pid})."

    # Resolve name and username
    name = proc_name or ""
    username = ""
    if proc:
        try:
            if not name:
                name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            username = proc.username() or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            username = ""

    # 4. Critical Windows system process names
    clean_name = name.lower()
    base_name = clean_name[:-4] if clean_name.endswith(".exe") else clean_name
    if clean_name in PROTECTED_PROCESS_NAMES or base_name in PROTECTED_PROCESS_NAMES:
        return True, f"Refusing to kill protected Windows system process '{name}' (PID {pid})."

    # 5. Process ownership check
    if username:
        norm_proc_user = username.lower().split("\\")[-1]
        current_user = get_current_user_name()
        if current_user and norm_proc_user != current_user:
            return True, f"Refusing to kill process '{name}' (PID {pid}): owned by another user or the system ({username})."

    return False, ""


def list_processes(sort_by: str = "memory", limit: int = 20) -> list[dict[str, Any]]:
    """List running processes with CPU % and Working Set memory.
    
    Primes CPU measurement with a 0.3s sleep for accurate readings.
    """
    # 1. Prime psutil cpu_percent for all processes
    active_procs: list[psutil.Process] = []
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
            active_procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # 2. Wait 0.3 seconds to obtain an accurate CPU interval
    time.sleep(0.3)

    results: list[dict[str, Any]] = []
    for p in active_procs:
        try:
            cpu = p.cpu_percent(None)
            mem_info = p.memory_info()
            rss = mem_info.rss  # Working Set in bytes
            name = p.name()
            username = ""
            try:
                username = p.username() or ""
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                username = "<access-denied>"

            results.append({
                "pid": p.pid,
                "name": name,
                "cpu_percent": cpu,
                "memory_rss": rss,
                "memory_formatted": format_bytes_mb_or_gb(rss),
                "username": username,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # 3. Sort
    sort_key = sort_by.lower()
    if sort_key == "cpu":
        results.sort(key=lambda x: x["cpu_percent"], reverse=True)
    elif sort_key == "name":
        results.sort(key=lambda x: x["name"].lower())
    else:  # memory default
        results.sort(key=lambda x: x["memory_rss"], reverse=True)

    return results[:limit]


def find_processes(query: str) -> list[dict[str, Any]]:
    """Find processes by partial, case-insensitive name match."""
    q = query.lower()
    matches: list[dict[str, Any]] = []

    for p in psutil.process_iter(["pid", "name", "memory_info", "username"]):
        try:
            name = p.info.get("name") or ""
            if q in name.lower():
                mem_info = p.info.get("memory_info")
                rss = mem_info.rss if mem_info else 0
                matches.append({
                    "pid": p.info["pid"],
                    "name": name,
                    "memory_rss": rss,
                    "memory_formatted": format_bytes_mb_or_gb(rss),
                    "username": p.info.get("username") or "",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    matches.sort(key=lambda x: x["memory_rss"], reverse=True)
    return matches


def get_process_detail(pid: int) -> dict[str, Any] | None:
    """Retrieve detailed process metadata without exposing cmdline or environment variables."""
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            name = proc.name()
            status = proc.status()
            create_time = proc.create_time()
            start_time_str = datetime.datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")

            try:
                exe = proc.exe() or "Unavailable"
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                exe = "<Access Denied>"

            try:
                username = proc.username() or "Unavailable"
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                username = "<Access Denied>"

            try:
                num_threads = proc.num_threads()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                num_threads = 0

            try:
                cpu = proc.cpu_percent(interval=0.05)
            except Exception:
                cpu = 0.0

            try:
                mem_info = proc.memory_info()
                rss = mem_info.rss
                vms = mem_info.vms
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                rss = 0
                vms = 0

            try:
                ppid = proc.ppid()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                ppid = None

            return {
                "pid": pid,
                "name": name,
                "status": status,
                "user": username,
                "exe": exe,
                "threads": num_threads,
                "cpu_percent": cpu,
                "memory_rss": rss,
                "memory_vms": vms,
                "memory_rss_formatted": format_bytes_mb_or_gb(rss),
                "memory_vms_formatted": format_bytes_mb_or_gb(vms),
                "start_time": start_time_str,
                "create_time": create_time,
                "ppid": ppid,
            }
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied:
        return {
            "pid": pid,
            "name": f"PID {pid}",
            "status": "Access Denied",
            "user": "<Access Denied>",
            "exe": "<Access Denied>",
            "threads": 0,
            "cpu_percent": 0.0,
            "memory_rss": 0,
            "memory_vms": 0,
            "memory_rss_formatted": "Unavailable",
            "memory_vms_formatted": "Unavailable",
            "start_time": "Unavailable",
            "create_time": 0.0,
            "ppid": None,
        }


def kill_process_guarded(
    pid: int,
    force: bool = False,
    expected_name: str | None = None,
    expected_create_time: float | None = None,
) -> tuple[bool, str]:
    """Safely terminate or kill a process with verification and ancestor guards.
    
    Logs only 'name + PID + result', never command lines.
    """
    # 1. Existence and initial inspection
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        msg = f"Process with PID {pid} not found (may have already exited)."
        logger.info("Process kill: name='<unknown>', PID=%d, force=%s, result='not_found'", pid, force)
        return False, msg
    except psutil.AccessDenied:
        msg = f"Access denied: Windows permissions prevent inspecting PID {pid}. MayuriShell does not elevate."
        logger.info("Process kill: name='<access_denied>', PID=%d, force=%s, result='access_denied'", pid, force)
        return False, msg

    # 2. Check protected status
    is_prot, reason = is_protected_process(proc)
    if is_prot:
        logger.info("Process kill: name='%s', PID=%d, force=%s, result='refused_protected'", proc.name(), pid, force)
        return False, reason

    # 3. PID recycling guard: re-check name and create_time after confirmation
    try:
        current_name = proc.name()
        current_create_time = proc.create_time()

        if expected_name is not None and current_name.lower() != expected_name.lower():
            msg = f"Aborted: Process identity changed. Target was '{expected_name}', but PID {pid} is now '{current_name}'."
            logger.info("Process kill: name='%s', PID=%d, force=%s, result='identity_changed'", current_name, pid, force)
            return False, msg

        if expected_create_time is not None and abs(current_create_time - expected_create_time) > 0.5:
            msg = f"Aborted: PID {pid} was recycled with a new creation timestamp."
            logger.info("Process kill: name='%s', PID=%d, force=%s, result='pid_recycled'", current_name, pid, force)
            return False, msg
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        msg = f"Failed to verify process identity before termination: {exc}"
        logger.info("Process kill: name='<error>', PID=%d, force=%s, result='verify_failed'", pid, force)
        return False, msg

    pname = current_name

    # 4. Terminate or Kill
    try:
        if force:
            proc.kill()
            try:
                proc.wait(timeout=3.0)
                result_msg = f"Forcefully killed process '{pname}' (PID {pid})."
                logger.info("Process kill: name='%s', PID=%d, force=True, result='force_killed'", pname, pid)
                return True, result_msg
            except psutil.TimeoutExpired:
                result_msg = f"Sent force kill to process '{pname}' (PID {pid}), but it did not exit within 3 seconds."
                logger.info("Process kill: name='%s', PID=%d, force=True, result='timeout_after_kill'", pname, pid)
                return False, result_msg
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
                result_msg = f"Terminated process '{pname}' (PID {pid})."
                logger.info("Process kill: name='%s', PID=%d, force=False, result='terminated'", pname, pid)
                return True, result_msg
            except psutil.TimeoutExpired:
                result_msg = f"Sent termination signal to process '{pname}' (PID {pid}), but it is still running after 3 seconds. Use --force to kill."
                logger.info("Process kill: name='%s', PID=%d, force=False, result='still_running'", pname, pid)
                return False, result_msg

    except psutil.NoSuchProcess:
        result_msg = f"Process '{pname}' (PID {pid}) has already exited."
        logger.info("Process kill: name='%s', PID=%d, force=%s, result='already_exited'", pname, pid, force)
        return True, result_msg
    except psutil.AccessDenied:
        result_msg = f"Access denied: Windows permissions prevent terminating process '{pname}' (PID {pid}). MayuriShell does not elevate or bypass system security."
        logger.info("Process kill: name='%s', PID=%d, force=%s, result='access_denied'", pname, pid, force)
        return False, result_msg
    except Exception as exc:
        result_msg = f"Error terminating process '{pname}' (PID {pid}): {exc}"
        logger.error("Process kill failed: name='%s', PID=%d, force=%s, error=%s", pname, pid, force, exc)
        return False, result_msg
