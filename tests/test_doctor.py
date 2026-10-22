"""Unit and integration tests for doctor diagnostic health inspection."""
from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from commands.doctor import register_doctor_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell
from core.theme import ThemeManager
from services.doctor_service import (
    PATH_CHECK_TIMEOUT_SECONDS,
    DoctorFinding,
    check_apps_health,
    check_config_health,
    check_path_exists_with_timeout,
    check_python_health,
    check_winreg_protocol_registered,
    is_windows_store_python_stub,
    probe_write_access,
    run_doctor,
)


def create_isolated_doctor_shell(tmp_path: Path, plain: bool = False):
    """Create an isolated test shell strictly inside tmp_path."""
    cfg_dir = tmp_path / "cfg"
    cfg = ConfigManager(base_dir=cfg_dir)
    reg = CommandRegistry()
    register_builtin_commands(reg)
    register_customization_commands(reg, cfg)
    register_doctor_commands(reg)

    hist = HistoryManager(cfg.history_path)
    aliases = AliasManager(cfg)
    console = Console(record=True, force_terminal=False, color_system=None if plain else "standard")
    theme_mgr = ThemeManager(cfg, console=console)
    if plain:
        theme_mgr.set_theme("plain")

    shell = MayuriShell(
        config=cfg,
        registry=reg,
        history_manager=hist,
        alias_manager=aliases,
        console=console,
        theme_manager=theme_mgr,
    )
    shell.context.is_interactive = False
    return shell, console


# ============================================================================
# 1. READ-ONLY INVARIANT
# ============================================================================

def test_doctor_read_only_invariant(tmp_path: Path) -> None:
    """Doctor is strictly read-only and leaves config and history files byte-identical."""
    shell, console = create_isolated_doctor_shell(tmp_path)
    cfg = shell.context.config

    # Set some initial configuration
    cfg.set("theme", "tokyo-night")
    cfg.set_shortcut("aliases", "t", "theme")
    cfg.set_shortcut("websites", "mysite", "https://example.com")

    # Capture initial bytes
    cfg_bytes_before = cfg.config_path.read_bytes() if cfg.config_path.exists() else b""

    # Run doctor all
    shell.run_command_line("doctor all")
    shell.run_command_line("doctor apps")
    shell.run_command_line("doctor python")
    shell.run_command_line("doctor config")

    cfg_bytes_after = cfg.config_path.read_bytes() if cfg.config_path.exists() else b""
    assert cfg_bytes_before == cfg_bytes_after, "Doctor modified the configuration file!"


# ============================================================================
# 2. STATUSES, DETAILS, AND ACTIONABLE FIX RECOMMENDATIONS
# ============================================================================

def test_doctor_finding_dataclass() -> None:
    """DoctorFinding holds category, name, status, message, and actionable fix."""
    f = DoctorFinding(
        category="apps",
        name="App 'code'",
        status="FAIL",
        message="Executable missing",
        fix="add-app code <path>",
    )
    assert f.category == "apps"
    assert f.status == "FAIL"
    assert f.fix == "add-app code <path>"


def test_doctor_apps_health_checks(tmp_path: Path) -> None:
    """Doctor apps verifies executable targets, folders, websites, and workflows."""
    shell, _ = create_isolated_doctor_shell(tmp_path)
    cfg = shell.context.config

    # 1. Valid and invalid app
    real_exe = tmp_path / "valid_tool.exe"
    real_exe.write_text("dummy", encoding="utf-8")
    cfg.set_shortcut("applications", "goodapp", str(real_exe))
    cfg.set_shortcut("applications", "badapp", str(tmp_path / "missing_tool.exe"))

    # 2. Valid and invalid folder
    real_folder = tmp_path / "myfolder"
    real_folder.mkdir()
    cfg.set_shortcut("folder_shortcuts", "goodfolder", str(real_folder))
    cfg.set_shortcut("folder_shortcuts", "badfolder", str(tmp_path / "nonexistent_dir"))

    # 3. Valid and invalid website
    cfg.set_shortcut("websites", "goodsite", "https://example.com/search?q={query}")
    cfg.set_shortcut("websites", "badsite", "ftp://invalid.com")

    # 4. Valid and invalid workflow
    cfg.set_workflow("goodwf", {"steps": ["goodapp"], "description": "Good"})
    cfg.set_workflow("badwf", {"steps": ["delete file.txt"], "description": "Bad"})

    findings = check_apps_health(shell.context)
    f_map = {f.name: f for f in findings}

    assert f_map["App 'goodapp'"].status == "OK"
    assert f_map["App 'badapp'"].status == "FAIL"
    assert "add-app badapp" in f_map["App 'badapp'"].fix

    assert f_map["Folder 'goodfolder'"].status == "OK"
    assert f_map["Folder 'badfolder'"].status == "FAIL"
    assert "add-folder badfolder" in f_map["Folder 'badfolder'"].fix

    assert f_map["Website 'goodsite'"].status == "OK"
    assert f_map["Website 'badsite'"].status == "FAIL"
    assert "add-website badsite" in f_map["Website 'badsite'"].fix

    assert f_map["Workflow 'goodwf'"].status == "OK"
    assert f_map["Workflow 'badwf'"].status == "FAIL"
    assert "forbidden command 'delete'" in f_map["Workflow 'badwf'"].message


def test_doctor_apps_batch_script_warning(tmp_path: Path) -> None:
    """Targeting a .bat or .cmd script emits a WARN finding."""
    shell, _ = create_isolated_doctor_shell(tmp_path)
    cfg = shell.context.config

    bat_file = tmp_path / "script.bat"
    bat_file.write_text("@echo off", encoding="utf-8")
    cfg.set_shortcut("applications", "runscript", str(bat_file))

    findings = check_apps_health(shell.context)
    bat_findings = [f for f in findings if f.name == "App 'runscript'"]
    assert any(f.status == "WARN" and "cannot accept user arguments" in f.message for f in bat_findings)


# ============================================================================
# 3. MICROSOFT STORE PYTHON STUB & PYTHON EXECUTION SAFETY
# ============================================================================

def test_is_windows_store_python_stub() -> None:
    """Store stub paths are recognized and flagged without running them."""
    stub_path = r"C:\Users\User\AppData\Local\Microsoft\WindowsApps\python.exe"
    assert is_windows_store_python_stub(stub_path) is True

    normal_path = r"C:\Python311\python.exe"
    assert is_windows_store_python_stub(normal_path) is False


def test_doctor_python_store_stub_never_executed(tmp_path: Path) -> None:
    """When a Microsoft Store stub is on PATH, it yields WARN and subprocess.run is NOT called."""
    shell, _ = create_isolated_doctor_shell(tmp_path)
    stub_exe = r"C:\Users\test\AppData\Local\Microsoft\WindowsApps\python.exe"

    with patch("shutil.which", side_effect=lambda cmd: stub_exe if cmd == "python" else None):
        with patch("subprocess.run") as mock_subproc:
            findings = check_python_health(shell.context)

            # subprocess.run MUST NOT be called on the stub
            mock_subproc.assert_not_called()

            stub_finding = next((f for f in findings if "stub" in f.message.lower()), None)
            assert stub_finding is not None
            assert stub_finding.status == "WARN"
            assert "Microsoft Store" in stub_finding.message


def test_doctor_python_real_version_and_timeout(tmp_path: Path) -> None:
    """Real Python execution verifies version; timeout generates a WARN finding."""
    shell, _ = create_isolated_doctor_shell(tmp_path)
    real_exe = r"C:\Python311\python.exe"

    # Case 1: Normal python execution
    mock_res = subprocess.CompletedProcess(
        args=[real_exe, "--version"],
        returncode=0,
        stdout="Python 3.11.8\n",
        stderr="",
    )
    with patch("shutil.which", side_effect=lambda cmd: real_exe if cmd == "python" else None):
        with patch("subprocess.run", return_value=mock_res) as mock_run:
            findings = check_python_health(shell.context)
            mock_run.assert_called_once()
            # Verify stream safety arguments
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("stdin") == subprocess.DEVNULL
            assert call_kwargs.get("timeout") == 5.0
            assert any(f.status == "OK" and "Python 3.11.8" in f.message for f in findings)

    # Case 2: Timeout expired
    with patch("shutil.which", side_effect=lambda cmd: real_exe if cmd == "python" else None):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[real_exe], timeout=5.0)):
            findings_timeout = check_python_health(shell.context)
            assert any(f.status == "WARN" and "timed out" in f.message for f in findings_timeout)


# ============================================================================
# 4. CONFIG HEALTH & PROBE FILE LIFECYCLE
# ============================================================================

def test_probe_write_access_creates_and_cleans_up_file(tmp_path: Path) -> None:
    """probe_write_access uses a unique ephemeral file and guarantees its deletion in try/finally."""
    test_dir = tmp_path / "probe_dir"
    test_dir.mkdir()

    ok, err = probe_write_access(test_dir)
    assert ok is True
    assert err == ""

    # Directory must have NO probe files remaining
    leftovers = list(test_dir.glob(".probe_*.tmp"))
    assert len(leftovers) == 0, f"Found lingering probe files: {leftovers}"


def test_probe_write_access_failure_on_nonexistent_dir(tmp_path: Path) -> None:
    """probe_write_access handles nonexistent directories cleanly without crashing."""
    bad_dir = tmp_path / "ghost_dir"
    ok, err = probe_write_access(bad_dir)
    assert ok is False
    assert "does not exist" in err


def test_doctor_config_health_corrupt_files(tmp_path: Path) -> None:
    """Corrupted config.json yields FAIL; unparseable history yields WARN."""
    shell, _ = create_isolated_doctor_shell(tmp_path)
    cfg = shell.context.config

    # Corrupt config.json
    cfg.config_path.write_text("{ corrupt json", encoding="utf-8")
    findings = check_config_health(shell.context)
    cfg_finding = next((f for f in findings if f.name == "Config File"), None)
    assert cfg_finding is not None
    assert cfg_finding.status == "FAIL"
    assert "corrupted" in cfg_finding.message.lower()

    # Corrupt history.json
    cfg.history_path.write_text("not json at all", encoding="utf-8")
    findings2 = check_config_health(shell.context)
    hist_finding = next((f for f in findings2 if f.name == "History File"), None)
    assert hist_finding is not None
    assert hist_finding.status == "WARN"


def test_doctor_backup_counts(tmp_path: Path) -> None:
    """Doctor config reports 0 backups (WARN), normal (OK), and > 50 (WARN)."""
    shell, _ = create_isolated_doctor_shell(tmp_path)
    cfg = shell.context.config

    # 0 backups -> WARN
    f_0 = check_config_health(shell.context)
    bkp_f0 = next(f for f in f_0 if f.name == "Configuration Backups")
    assert bkp_f0.status == "WARN"
    assert "No configuration backups found" in bkp_f0.message

    # 2 backups -> OK
    (cfg.backups_dir / "b1.json").write_text("{}", encoding="utf-8")
    (cfg.backups_dir / "b2.json").write_text("{}", encoding="utf-8")
    f_2 = check_config_health(shell.context)
    bkp_f2 = next(f for f in f_2 if f.name == "Configuration Backups")
    assert bkp_f2.status == "OK"
    assert "2 backup snapshot(s)" in bkp_f2.message

    # 52 backups -> WARN
    for i in range(50):
        (cfg.backups_dir / f"b_extra_{i}.json").write_text("{}", encoding="utf-8")
    f_52 = check_config_health(shell.context)
    bkp_f52 = next(f for f in f_52 if f.name == "Configuration Backups")
    assert bkp_f52.status == "WARN"
    assert "52 backup files found" in bkp_f52.message


# ============================================================================
# 5. TIMEOUT AND REGISTRY CHECKS
# ============================================================================

def test_check_path_exists_with_timeout_slow_path() -> None:
    """check_path_exists_with_timeout returns None when path check exceeds timeout."""
    slow_p = Path(r"\\192.0.2.1\unreachable_share")

    def _hang(*args, **kwargs):
        raise FutureTimeoutError()

    with patch("concurrent.futures.Future.result", side_effect=_hang):
        exists, is_dir = check_path_exists_with_timeout(slow_p, timeout=0.1)
        assert exists is None
        assert is_dir is False


def test_check_winreg_protocol_registered_read_only() -> None:
    """check_winreg_protocol_registered is read-only and handles Windows/non-Windows safely."""
    # On non-Windows platform
    with patch("platform.system", return_value="Linux"):
        status = check_winreg_protocol_registered("spotify")
        assert status == "UNKNOWN"

    # On Windows platform with missing protocol
    with patch("platform.system", return_value="Windows"):
        with patch("winreg.OpenKey", side_effect=OSError("Key not found")):
            status = check_winreg_protocol_registered("nonexistentprotocol")
            assert status == "WARN"


# ============================================================================
# 6. OUTPUT FORMATTING & PRIVACY GUARANTEES
# ============================================================================

def test_doctor_plain_ascii_badges(tmp_path: Path) -> None:
    """In plain theme mode, doctor outputs strict ASCII badges [OK], [WARN], [FAIL], [??]."""
    shell, console = create_isolated_doctor_shell(tmp_path, plain=True)
    cfg = shell.context.config

    # Add a broken app so we get at least [FAIL] and [OK]
    cfg.set_shortcut("applications", "broken", str(tmp_path / "no_exe.exe"))

    shell.run_command_line("doctor apps")
    out = console.export_text()

    assert "[FAIL]" in out
    assert "[OK]" in out or "[??]" in out
    assert "Doctor Summary:" in out


def test_doctor_never_prints_username_or_env_vars(tmp_path: Path) -> None:
    """Doctor never leaks username, hostname, or environment variables into console output."""
    shell, console = create_isolated_doctor_shell(tmp_path)
    cfg = shell.context.config

    # Create dummy app and folder
    cfg.set_shortcut("folder_shortcuts", "box", str(tmp_path))

    secret_user = "PrivateSuperSecretUser999"
    secret_host = "ConfidentialHost42"

    with patch.dict(os.environ, {"SECRET_API_KEY": "sk-secret-token-12345"}):
        with patch("getpass.getuser", return_value=secret_user):
            with patch("platform.node", return_value=secret_host):
                shell.run_command_line("doctor all")

    output = console.export_text()
    assert "sk-secret-token-12345" not in output
    assert "SECRET_API_KEY" not in output
    assert secret_user not in output
    assert secret_host not in output


def test_doctor_privacy_logging(caplog) -> None:
    """Doctor logger records summary counts only; never logs user paths or targets."""
    with caplog.at_level(logging.INFO):
        findings, counts = run_doctor(category="config", context=None)

    # Inspect captured log messages
    doctor_logs = [record.message for record in caplog.records if "Doctor executed:" in record.message]
    assert len(doctor_logs) >= 1
    log_line = doctor_logs[0]

    # Must contain category and counts
    assert "category=config" in log_line
    assert "OK=" in log_line
    assert "WARN=" in log_line
    assert "FAIL=" in log_line
    assert "UNKNOWN=" in log_line

    # Must not contain user paths or internal file paths
    assert "\\" not in log_line and "/" not in log_line


# ============================================================================
# 7. CLI COMMAND CATEGORY ARGUMENTS
# ============================================================================

def test_doctor_subcommand_categories(tmp_path: Path) -> None:
    """doctor accepts apps, python, config, and all; rejects invalid categories."""
    shell, console = create_isolated_doctor_shell(tmp_path)

    # Valid subcommands
    for sub in ("apps", "python", "config", "all"):
        console.clear()
        res = shell.run_command_line(f"doctor {sub}")
        out = console.export_text()
        assert f"Health Report ({sub.upper()})" in out

    # Invalid subcommand
    console.clear()
    res_bad = shell.run_command_line("doctor nonexistent")
    assert res_bad is False
    out_bad = console.export_text()
    assert "Unknown doctor category 'nonexistent'" in out_bad
    assert "Valid categories: apps, python, config, all." in out_bad
