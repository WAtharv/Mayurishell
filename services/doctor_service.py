"""Doctor diagnostic and system health verification service for MayuriShell."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Sequence
import uuid

from core.logging_config import get_logger
from core.version import VERSION
from services.application_discovery import is_startfile_target, is_uri
from services.config_service import get_real_desktop_path
from services.launcher_service import validate_web_url
from services.workflow_service import FORBIDDEN_COMMANDS, parse_raw_step

logger = get_logger()

PATH_CHECK_TIMEOUT_SECONDS = 3.0


@dataclass
class DoctorFinding:
    """Individual system health check finding."""
    category: str  # "apps", "python", "config"
    name: str
    status: str    # "OK", "WARN", "FAIL", "UNKNOWN"
    message: str
    fix: str = ""


def check_path_exists_with_timeout(path: Path, timeout: float = PATH_CHECK_TIMEOUT_SECONDS) -> tuple[bool | None, bool]:
    """Check if path exists with a strict timeout to prevent hangs on slow network drives.
    
    Returns:
        (exists_bool_or_None_if_timeout, is_dir_bool)
    """
    def _check() -> tuple[bool, bool]:
        ex = path.exists()
        is_d = path.is_dir() if ex else False
        return ex, is_d

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_check)
    try:
        res = future.result(timeout=timeout)
        executor.shutdown(wait=False, cancel_futures=True)
        return res
    except FutureTimeoutError:
        executor.shutdown(wait=False, cancel_futures=True)
        return None, False
    except Exception:
        executor.shutdown(wait=False, cancel_futures=True)
        return False, False


def check_winreg_protocol_registered(protocol_name: str) -> str:
    """Check if a protocol URI (e.g. spotify, discord) is registered in Windows Registry.
    
    Returns:
        "OK" if registered, "WARN" if not found, "UNKNOWN" if non-Windows or error.
        Never writes to registry.
    """
    if platform.system() != "Windows":
        return "UNKNOWN"

    clean_proto = protocol_name.rstrip(":").strip().lower()
    if not clean_proto:
        return "UNKNOWN"

    try:
        import winreg  # type: ignore

        # 1. Check HKCU\Software\Classes\<protocol>
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{clean_proto}"):
                return "OK"
        except OSError:
            pass

        # 2. Check HKEY_CLASSES_ROOT\<protocol>
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, clean_proto):
                return "OK"
        except OSError:
            pass

        return "WARN"
    except Exception:
        return "UNKNOWN"


# ============================================================================
# DOCTOR APPS
# ============================================================================

def check_apps_health(context: Any) -> list[DoctorFinding]:
    """Inspect configured applications, folders, websites, and workflows."""
    findings: list[DoctorFinding] = []
    config = getattr(context, "config", None)
    if not config:
        findings.append(DoctorFinding(
            category="apps",
            name="Configuration Context",
            status="FAIL",
            message="No configuration manager available to inspect shortcuts.",
            fix="Run 'main.py' or check your MayuriShell setup.",
        ))
        return findings

    # 1. Configured Application Shortcuts
    apps = config.get_applications()
    for name, target in sorted(apps.items()):
        target_str = str(target).strip()
        t_lower = target_str.lower()

        # Check shell:AppsFolder virtual store targets
        if t_lower.startswith("shell:appsfolder\\"):
            findings.append(DoctorFinding(
                category="apps",
                name=f"App '{name}'",
                status="UNKNOWN",
                message=f"Windows Store virtual shell target cannot be statically verified: {target_str}",
                fix=f"Type '{name}' in shell to test launch.",
            ))
            continue

        # Check Protocol URIs
        if is_uri(target_str):
            proto = target_str.split(":")[0] if ":" in target_str else target_str
            reg_status = check_winreg_protocol_registered(proto)
            if reg_status == "OK":
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"App '{name}'",
                    status="OK",
                    message=f"Protocol URI handler for '{proto}:' is registered in Windows.",
                ))
            elif reg_status == "WARN":
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"App '{name}'",
                    status="WARN",
                    message=f"No registered Windows handler found for protocol '{proto}:'.",
                    fix=f"Ensure application providing '{proto}:' is installed, or update with: add-app {name} <path>",
                ))
            else:
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"App '{name}'",
                    status="UNKNOWN",
                    message=f"Could not verify protocol URI handler for '{proto}:' in registry.",
                    fix=f"Type '{name}' to test launch.",
                ))
            continue

        # Check .bat and .cmd scripts
        if t_lower.endswith((".bat", ".cmd")):
            findings.append(DoctorFinding(
                category="apps",
                name=f"App '{name}'",
                status="WARN",
                message=f"Batch script target '{target_str}' cannot accept user arguments.",
                fix=f"Target direct .exe or wrap in workflow: add-app {name} <path-to-exe>",
            ))
            # Continue checking if file exists
            pass

        # Check file target existence with timeout
        exp_target = os.path.expanduser(os.path.expandvars(target_str))
        p = Path(exp_target)

        # Check if direct file or resolvable on PATH
        if p.is_file():
            findings.append(DoctorFinding(
                category="apps",
                name=f"App '{name}'",
                status="OK",
                message=f"Target executable exists: {exp_target}",
            ))
        else:
            # Check PATH via shutil.which
            which_p = shutil.which(target_str) or shutil.which(f"{target_str}.exe")
            if which_p:
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"App '{name}'",
                    status="OK",
                    message=f"Target resolved on PATH: {which_p}",
                ))
            else:
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"App '{name}'",
                    status="FAIL",
                    message=f"Target executable does not exist: {exp_target}",
                    fix=f"Update target executable with: add-app {name} <path-to-executable>",
                ))

    # 2. Configured Folder Shortcuts
    folders = config.get_folder_shortcuts()
    for name, raw_path in sorted(folders.items()):
        exp_p = os.path.expanduser(os.path.expandvars(str(raw_path)))
        p = Path(exp_p)
        exists, is_dir = check_path_exists_with_timeout(p)

        if exists is None:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Folder '{name}'",
                status="WARN",
                message=f"Directory check timed out (>3s): {exp_p}",
                fix=f"Verify drive or network connection, or update with: add-folder {name} <path>",
            ))
        elif exists and is_dir:
            # Check readability
            readable = os.access(str(p), os.R_OK)
            if readable:
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"Folder '{name}'",
                    status="OK",
                    message=f"Directory exists and is readable: {exp_p}",
                ))
            else:
                findings.append(DoctorFinding(
                    category="apps",
                    name=f"Folder '{name}'",
                    status="WARN",
                    message=f"Directory exists but read access is restricted: {exp_p}",
                    fix=f"Check folder permissions or update with: add-folder {name} <path>",
                ))
        else:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Folder '{name}'",
                status="FAIL",
                message=f"Directory does not exist: {exp_p}",
                fix=f"Update folder shortcut with: add-folder {name} <valid-directory-path>",
            ))

    # 3. Search Directories
    search_dirs = config.get("search_directories", ["~/Desktop", "~/Documents", "~/Downloads"])
    for sd in search_dirs:
        exp_sd = os.path.expanduser(os.path.expandvars(str(sd)))
        sd_path = Path(exp_sd)
        exists, is_dir = check_path_exists_with_timeout(sd_path)
        if exists is None:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Search Dir '{sd}'",
                status="WARN",
                message=f"Search directory check timed out (>3s): {exp_sd}",
                fix="Verify storage availability.",
            ))
        elif exists and is_dir:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Search Dir '{sd}'",
                status="OK",
                message=f"Search directory exists: {exp_sd}",
            ))
        else:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Search Dir '{sd}'",
                status="WARN",
                message=f"Search directory missing: {exp_sd}",
                fix=f"Create folder or update search_directories in config: mkdir {exp_sd}",
            ))

    # 4. Website Shortcuts
    websites = config.get_websites()
    for name, raw_url in sorted(websites.items()):
        valid, norm_or_err = validate_web_url(str(raw_url))
        if valid:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Website '{name}'",
                status="OK",
                message=f"URL template is valid: {norm_or_err}",
            ))
        else:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Website '{name}'",
                status="FAIL",
                message=f"Invalid website URL template: {norm_or_err}",
                fix=f"Update website shortcut with: add-website {name} <valid-url>",
            ))

    # 5. Workflows
    workflows = config.get_workflows()
    for name, wf in sorted(workflows.items()):
        steps = wf.get("steps", []) if isinstance(wf, dict) else []
        all_steps_ok = True
        failed_step_msg = ""

        for step in steps:
            cmd_text, _ = parse_raw_step(step)
            parts = cmd_text.split()
            cmd_first = parts[0].lower() if parts else ""

            if cmd_first in FORBIDDEN_COMMANDS:
                all_steps_ok = False
                failed_step_msg = f"Step '{cmd_text}' contains forbidden command '{cmd_first}'."
                break

            # Verify step command exists in registry or configured shortcuts
            if hasattr(context, "registry") and context.registry.has_command(cmd_first):
                continue
            if cmd_first in apps or cmd_first in folders or cmd_first in websites:
                continue

            all_steps_ok = False
            failed_step_msg = f"Step '{cmd_text}' references unknown command or shortcut '{cmd_first}'."
            break

        if all_steps_ok:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Workflow '{name}'",
                status="OK",
                message=f"All {len(steps)} workflow steps resolve to valid actions.",
            ))
        else:
            findings.append(DoctorFinding(
                category="apps",
                name=f"Workflow '{name}'",
                status="FAIL",
                message=failed_step_msg,
                fix=f"Review workflow steps with: workflow show {name} or workflow validate",
            ))

    return findings


# ============================================================================
# DOCTOR PYTHON
# ============================================================================

def is_windows_store_python_stub(exe_path: str) -> bool:
    """Return True if path points to the 0-byte or redirector Microsoft Store Python stub."""
    norm = exe_path.lower()
    if r"\localappdata\microsoft\windowsapps" in norm or r"\microsoft\windowsapps" in norm:
        # Check if file size is very small (Windows Store stubs are redirectors, typically 0 KB)
        try:
            st = Path(exe_path).stat()
            if st.st_size == 0 or "python" in Path(exe_path).name.lower():
                return True
        except Exception:
            return True
    return False


def check_python_health(context: Any) -> list[DoctorFinding]:
    """Inspect Python interpreters on PATH and execution environment."""
    findings: list[DoctorFinding] = []

    # Check if MayuriShell runs frozen
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        findings.append(DoctorFinding(
            category="python",
            name="Runtime Mode",
            status="OK",
            message=f"MayuriShell is running as a standalone frozen executable (version {VERSION}). Python runtime not required for core shell.",
        ))

    # Discover candidate python commands on PATH
    candidates = ["python", "python3", "py"]
    found_interpreters: list[tuple[str, str]] = []

    for cand in candidates:
        which_path = shutil.which(cand)
        if which_path and (cand, which_path) not in [(c, p) for c, p in found_interpreters]:
            found_interpreters.append((cand, which_path))

    if not found_interpreters:
        status_code = "WARN" if is_frozen else "FAIL"
        findings.append(DoctorFinding(
            category="python",
            name="Python Interpreter",
            status=status_code,
            message="No Python interpreter found on system PATH (python, python3, py).",
            fix="Install Python 3.11+ from https://www.python.org/ or run: add-app python <path-to-python.exe>",
        ))
        return findings

    real_python_count = 0

    for cand_name, exe_path in found_interpreters:
        # Check for Microsoft Store redirector stub
        if is_windows_store_python_stub(exe_path):
            findings.append(DoctorFinding(
                category="python",
                name=f"PATH command '{cand_name}'",
                status="WARN",
                message=f"Microsoft Store app execution stub detected at: {exe_path} (not a real Python installation).",
                fix="Install full Python from https://www.python.org/ and ensure 'Add Python to PATH' is checked.",
            ))
            continue

        # Execute real Python with --version only, timeout 5 seconds, closed streams
        try:
            proc = subprocess.run(
                [exe_path, "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=5.0,
                text=True,
            )
            out = (proc.stdout or proc.stderr or "").strip()
            if proc.returncode == 0:
                real_python_count += 1
                findings.append(DoctorFinding(
                    category="python",
                    name=f"PATH command '{cand_name}'",
                    status="OK",
                    message=f"{out} ({exe_path})",
                ))
            else:
                findings.append(DoctorFinding(
                    category="python",
                    name=f"PATH command '{cand_name}'",
                    status="WARN",
                    message=f"Interpreter at '{exe_path}' exited with code {proc.returncode}.",
                    fix=f"Verify Python installation at '{exe_path}'.",
                ))
        except subprocess.TimeoutExpired:
            findings.append(DoctorFinding(
                category="python",
                name=f"PATH command '{cand_name}'",
                status="WARN",
                message=f"Executing '{exe_path} --version' timed out after 5 seconds.",
                fix="Check if antivirus or drive access is blocking execution.",
            ))
        except Exception as exc:
            findings.append(DoctorFinding(
                category="python",
                name=f"PATH command '{cand_name}'",
                status="WARN",
                message=f"Failed to execute '{exe_path}': {exc}",
                fix="Verify executable permissions.",
            ))

    if real_python_count == 0 and not is_frozen:
        findings.append(DoctorFinding(
            category="python",
            name="Usable Python Runtime",
            status="FAIL",
            message="No functional, non-stub Python installation found on system PATH.",
            fix="Install Python 3.11+ from https://www.python.org/",
        ))

    return findings


# ============================================================================
# DOCTOR CONFIG
# ============================================================================

def probe_write_access(directory: Path) -> tuple[bool, str]:
    """Test write and delete access in directory using a unique temporary probe file."""
    if not directory.exists():
        return False, f"Directory does not exist: {directory}"

    probe_id = uuid.uuid4().hex[:12]
    probe_file = directory / f".probe_{probe_id}.tmp"

    try:
        probe_file.write_text("probe", encoding="utf-8")
        return True, ""
    except Exception as exc:
        return False, f"Write access test failed: {exc}"
    finally:
        try:
            if probe_file.exists():
                probe_file.unlink()
        except Exception:
            pass


def check_config_health(context: Any) -> list[DoctorFinding]:
    """Inspect configuration files, history, directories, and permissions."""
    findings: list[DoctorFinding] = []
    config = getattr(context, "config", None)
    if not config:
        findings.append(DoctorFinding(
            category="config",
            name="Configuration Context",
            status="FAIL",
            message="Configuration manager is unavailable.",
            fix="Run 'main.py' or check your MayuriShell setup.",
        ))
        return findings

    cfg_file = config.config_path

    # 1. Config file existence & JSON validation
    if not cfg_file.exists():
        findings.append(DoctorFinding(
            category="config",
            name="Config File",
            status="WARN",
            message=f"config.json not found at '{cfg_file}'. Shell is operating with in-memory defaults.",
            fix="Save settings or create a backup with: config backup",
        ))
    else:
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            if isinstance(parsed, dict):
                findings.append(DoctorFinding(
                    category="config",
                    name="Config File",
                    status="OK",
                    message=f"config.json exists, parses cleanly, and contains valid configuration.",
                ))
            else:
                findings.append(DoctorFinding(
                    category="config",
                    name="Config File",
                    status="FAIL",
                    message="config.json root element is not an object.",
                    fix="Restore a valid backup with: config restore <name>",
                ))
        except Exception as exc:
            findings.append(DoctorFinding(
                category="config",
                name="Config File",
                status="FAIL",
                message=f"config.json is corrupted: {exc}",
                fix="Restore a valid backup with: config restore <name>",
            ))

    # 2. History file existence & validation
    hist_file = config.history_path
    if not hist_file.exists():
        findings.append(DoctorFinding(
            category="config",
            name="History File",
            status="OK",
            message="history.json has not been created yet (created after running commands).",
        ))
    else:
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                hist_data = json.load(f)
            if isinstance(hist_data, list):
                findings.append(DoctorFinding(
                    category="config",
                    name="History File",
                    status="OK",
                    message=f"history.json exists and contains {len(hist_data)} stored command entries.",
                ))
            else:
                findings.append(DoctorFinding(
                    category="config",
                    name="History File",
                    status="WARN",
                    message="history.json root element is not an array.",
                    fix="Clear corrupted history with: history clear",
                ))
        except Exception as exc:
            findings.append(DoctorFinding(
                category="config",
                name="History File",
                status="WARN",
                message=f"history.json is unparseable: {exc}",
                fix="Clear corrupted history with: history clear",
            ))

    # 2b. Undo journal existence and validity check (never prints file paths or names)
    journal_file = config.base_dir / "undo_journal.json"
    if journal_file.exists():
        try:
            with open(journal_file, "r", encoding="utf-8") as f:
                j_data = json.load(f)
            if isinstance(j_data, dict) and "operations" in j_data:
                op_count = len(j_data.get("operations", []))
                f_size = journal_file.stat().st_size
                findings.append(DoctorFinding(
                    category="config",
                    name="Undo Journal",
                    status="OK",
                    message=f"undo_journal.json exists, parses cleanly ({op_count} tracked operations, {f_size} bytes).",
                ))
            else:
                findings.append(DoctorFinding(
                    category="config",
                    name="Undo Journal",
                    status="WARN",
                    message="undo_journal.json root element is invalid.",
                    fix="Corrupted journal will automatically backup on next undo command.",
                ))
        except Exception as exc:
            findings.append(DoctorFinding(
                category="config",
                name="Undo Journal",
                status="WARN",
                message=f"undo_journal.json is unparseable: {exc}",
                fix="Corrupted journal will automatically backup on next undo command.",
            ))

    # 3. User Data, Logs, and Backups Folder Writable Probes
    dirs_to_probe = [

        ("Base Data Directory", config.base_dir),
        ("Logs Directory", config.logs_dir),
        ("Backups Directory", config.backups_dir),
    ]

    for label, dir_p in dirs_to_probe:
        ok, err_msg = probe_write_access(dir_p)
        if ok:
            findings.append(DoctorFinding(
                category="config",
                name=label,
                status="OK",
                message=f"Directory is accessible and writable: {dir_p}",
            ))
        else:
            findings.append(DoctorFinding(
                category="config",
                name=label,
                status="FAIL",
                message=f"Directory write check failed: {err_msg}",
                fix=f"Check folder write permissions for: {dir_p}",
            ))

    # 4. Desktop Folder Writable Probe (for diagnostics & config exports)
    desktop_p = get_real_desktop_path()
    dt_ok, dt_err = probe_write_access(desktop_p)
    if dt_ok:
        findings.append(DoctorFinding(
            category="config",
            name="Desktop Folder",
            status="OK",
            message=f"Desktop directory is writable for exports: {desktop_p}",
        ))
    else:
        findings.append(DoctorFinding(
            category="config",
            name="Desktop Folder",
            status="WARN",
            message=f"Desktop is not directly writable ({dt_err}). Exports will fall back to home directory.",
            fix="Verify Desktop permissions or OneDrive sync status.",
        ))

    # 5. Count Backups
    backups_dir = config.backups_dir
    try:
        backup_files = [p for p in backups_dir.glob("*.json") if p.is_file()] if backups_dir.exists() else []
        count = len(backup_files)
        if count == 0:
            findings.append(DoctorFinding(
                category="config",
                name="Configuration Backups",
                status="WARN",
                message="No configuration backups found in backups/.",
                fix="Create a snapshot backup of your setup with: config backup",
            ))
        elif count > 50:
            findings.append(DoctorFinding(
                category="config",
                name="Configuration Backups",
                status="WARN",
                message=f"{count} backup files found in backups/. High count may slow down backup listings.",
                fix="Consider removing older backup files from backups/.",
            ))
        else:
            findings.append(DoctorFinding(
                category="config",
                name="Configuration Backups",
                status="OK",
                message=f"{count} backup snapshot(s) safely stored in backups/.",
            ))
    except Exception as exc:
        findings.append(DoctorFinding(
            category="config",
            name="Configuration Backups",
            status="WARN",
            message=f"Could not inspect backups folder: {exc}",
        ))

    return findings


def check_git_availability() -> DoctorFinding:
    """Inspect Git executable availability on PATH and test with --version through hardened runner."""
    from services.git_service import find_git_executable, run_hardened_git
    git_bin = find_git_executable()
    if not git_bin:
        return DoctorFinding(
            category="git",
            name="Git Version Control",
            status="WARN",
            message="Git executable not found on PATH or standard install paths.",
            fix="Install Git for Windows from https://git-scm.com/download/win",
        )

    res = run_hardened_git(["--version"], cwd=Path.home())
    if res.success and res.stdout.strip():
        ver_str = res.stdout.strip()
        return DoctorFinding(
            category="git",
            name="Git Version Control",
            status="OK",
            message=f"{ver_str} ({git_bin})",
        )

    return DoctorFinding(
        category="git",
        name="Git Version Control",
        status="WARN",
        message=f"Git detected at '{git_bin}' but '--version' exited with code {res.returncode}.",
        fix="Verify your Git installation.",
    )


# ============================================================================
# AGGREGATOR
# ============================================================================

def run_doctor(category: str = "all", context: Any = None) -> tuple[list[DoctorFinding], dict[str, int]]:
    """Run diagnostics for 'apps', 'python', 'config', or 'all'.
    
    Returns:
        (findings_list, summary_counts_dict)
    """
    clean_cat = category.strip().lower()
    findings: list[DoctorFinding] = []

    if clean_cat in ("apps", "all"):
        findings.extend(check_apps_health(context))
        findings.append(check_git_availability())
    if clean_cat in ("python", "all"):
        findings.extend(check_python_health(context))
    if clean_cat in ("config", "all"):
        findings.extend(check_config_health(context))

    counts = {
        "OK": sum(1 for f in findings if f.status == "OK"),
        "WARN": sum(1 for f in findings if f.status == "WARN"),
        "FAIL": sum(1 for f in findings if f.status == "FAIL"),
        "UNKNOWN": sum(1 for f in findings if f.status == "UNKNOWN"),
    }

    # Privacy logging: log only summary counts, never paths or targets
    logger.info("Doctor executed: category=%s, OK=%d, WARN=%d, FAIL=%d, UNKNOWN=%d",
                clean_cat, counts["OK"], counts["WARN"], counts["FAIL"], counts["UNKNOWN"])

    return findings, counts
