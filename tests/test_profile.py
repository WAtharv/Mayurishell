"""Comprehensive test suite for Stage 11 Workflow Profiles.

Tests profile list, show, run, dry-run, optional step continuation, non-optional
halt, name validation, interactive editor actions, non-interactive refusal,
privacy (no editor lines in history/logs), and one-time profile seeding.
"""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

from core.config_manager import ConfigManager, DEFAULT_CONFIG, SEEDED_PROFILES
from core.executor import CommandExecutor
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import ShellContext
from core.theme import ThemeManager
from rich.console import Console

from commands.profile import handle_profile, register_profile_commands
from services.workflow_service import resolve_step, FORBIDDEN_COMMANDS


@pytest.fixture
def profile_context(tmp_path: Path):
    """Provide an isolated ShellContext for profile testing."""
    config_dir = tmp_path / "config"
    work_dir = tmp_path / "work"
    config_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    config_mgr = ConfigManager(base_dir=config_dir)
    registry = CommandRegistry()
    register_profile_commands(registry)

    # Register some dummy commands for testing
    from commands.builtins import register_builtin_commands
    from commands.system import register_system_commands
    register_builtin_commands(registry)
    register_system_commands(registry)


    console = Console(force_terminal=False, color_system=None)
    theme_mgr = ThemeManager(config_mgr, console=console)
    history_mgr = HistoryManager(config_mgr.history_path)

    ctx = ShellContext(
        config=config_mgr,
        registry=registry,
        history_manager=history_mgr,
        console=console,
        theme_manager=theme_mgr,
    )
    ctx.current_dir = work_dir
    ctx.is_interactive = False
    return ctx


# ============================================================================
# 1. PROFILE SEEDING
# ============================================================================

def test_profile_seeding_on_first_load(tmp_path: Path):
    """Default profiles (coding, study, gaming) are seeded and preferences.profiles_seeded is set."""
    config_dir = tmp_path / "config"
    config_mgr = ConfigManager(base_dir=config_dir)

    wfs = config_mgr.get_workflows()
    assert "coding" in wfs
    assert "study" in wfs
    assert "gaming" in wfs
    assert config_mgr.get("preferences.profiles_seeded") is True


def test_seeded_profiles_never_replace_existing_workflow(tmp_path: Path):
    """If user already has a workflow named 'coding', seeding skips it and preserves user's workflow."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = config_dir / "config.json"

    # Pre-populate custom config with user's own coding workflow
    custom_cfg = copy.deepcopy(DEFAULT_CONFIG)
    custom_cfg["workflows"]["coding"] = {
        "description": "User's Custom Coding Workflow",
        "steps": ["github"],
    }
    custom_cfg["preferences"]["profiles_seeded"] = False
    cfg_file.write_text(json.dumps(custom_cfg), encoding="utf-8")

    # Load config manager
    config_mgr = ConfigManager(base_dir=config_dir)
    coding_wf = config_mgr.get_workflow("coding")
    assert coding_wf["description"] == "User's Custom Coding Workflow"
    assert config_mgr.get("preferences.profiles_seeded") is True


def test_deleted_seeded_profile_never_reseeds(tmp_path: Path):
    """If user removes a seeded profile, subsequent reloads do NOT reseed it."""
    config_dir = tmp_path / "config"
    config_mgr = ConfigManager(base_dir=config_dir)

    # User removes 'gaming'
    config_mgr.remove_workflow("gaming")
    assert "gaming" not in config_mgr.get_workflows()

    # Re-initialize config manager (simulating shell restart)
    reloaded_mgr = ConfigManager(base_dir=config_dir)
    assert "gaming" not in reloaded_mgr.get_workflows()


# ============================================================================
# 2. PROFILE LIST & SHOW
# ============================================================================

def test_profile_list_and_show(profile_context: ShellContext):
    """'profile list' and 'profile show <name>' display clean metadata."""
    res_list = handle_profile(profile_context, ["list"])
    assert res_list.ok

    res_show = handle_profile(profile_context, ["show", "coding"])
    assert res_show.ok

    res_missing = handle_profile(profile_context, ["show", "nonexistent"])
    assert not res_missing.ok


# ============================================================================
# 3. PROFILE EXECUTION: PLAN, DRY-RUN, AND CONFIRMATION
# ============================================================================

def test_profile_dry_run_executes_no_steps(profile_context: ShellContext):
    """'profile <name> --dry-run' previews steps without launching any actions."""
    with patch("services.workflow_service.execute_workflow_step") as mock_exec:
        res = handle_profile(profile_context, ["coding", "--dry-run"])
        assert res.ok
        mock_exec.assert_not_called()


def test_profile_run_confirmation_aborted(profile_context: ShellContext):
    """If user declines confirmation prompt (y/N), execution is cancelled."""
    with patch("commands.profile.confirm_prompt", return_value=False):
        with patch("commands.profile.execute_workflow_step") as mock_exec:
            res = handle_profile(profile_context, ["coding"])
            assert res.cancelled is True
            mock_exec.assert_not_called()


def test_profile_run_confirmation_accepted(profile_context: ShellContext):
    """If user confirms, steps execute sequentially."""
    with patch("commands.profile.confirm_prompt", return_value=True):
        with patch("commands.profile.execute_workflow_step", return_value=(True, "Success")):
            res = handle_profile(profile_context, ["coding"])
            assert res.ok


# ============================================================================
# 4. OPTIONAL VS NON-OPTIONAL STEP FAILURE BEHAVIOR
# ============================================================================

def test_profile_optional_step_failure_continues(profile_context: ShellContext):
    """Optional step starting with '?' warns on error but continues execution."""
    profile_context.config.set_workflow(
        "test_opt",
        {
            "description": "Optional step test",
            "steps": ["? non_existent_shortcut", "sysinfo"],
        },
    )

    executed: list[str] = []

    def mock_step(step, ctx):
        executed.append(step.command)
        if step.command == "sysinfo":
            return True, "Executed sysinfo"
        return False, "Failed"

    with patch("commands.profile.confirm_prompt", return_value=True):
        with patch("commands.profile.execute_workflow_step", side_effect=mock_step):
            res = handle_profile(profile_context, ["test_opt"])
            assert res.ok
            # The second step sysinfo was executed even though first failed
            assert "sysinfo" in executed



def test_profile_non_optional_step_failure_halts(profile_context: ShellContext):
    """Non-optional step failure immediately halts execution and fails."""
    profile_context.config.set_workflow(
        "test_halt",
        {
            "description": "Non-optional step test",
            "steps": ["non_existent_shortcut", "sysinfo"],
        },
    )

    executed: list[str] = []

    def mock_step(step, ctx):
        executed.append(step.command)
        return False, "Failed"

    with patch("commands.profile.confirm_prompt", return_value=True):
        with patch("commands.profile.execute_workflow_step", side_effect=mock_step):
            res = handle_profile(profile_context, ["test_halt"])

            assert not res.ok
            # sysinfo should NEVER have been executed
            assert "sysinfo" not in executed


# ============================================================================
# 5. PROFILE REMOVE & BACKUP
# ============================================================================

def test_profile_remove_creates_backup(profile_context: ShellContext):
    """Removing a profile creates a config backup and removes from workflows."""
    assert "gaming" in profile_context.config.get_workflows()

    with patch("commands.profile.confirm_prompt", return_value=True):
        res = handle_profile(profile_context, ["remove", "gaming"])
        assert res.ok

    assert "gaming" not in profile_context.config.get_workflows()
    backups = list(profile_context.config.backups_dir.glob("config_profile_remove_*.json"))
    assert len(backups) == 1


# ============================================================================
# 6. NAME VALIDATION & NON-INTERACTIVE REFUSAL
# ============================================================================

def test_profile_name_validation(profile_context: ShellContext):
    """Names with spaces, special characters, or reserved words are refused."""
    with patch("sys.stdin.isatty", return_value=True):
        # Reserved name
        res = handle_profile(profile_context, ["new", "list"])
        assert not res.ok

        # Invalid characters
        res = handle_profile(profile_context, ["new", "my profile!"])
        assert not res.ok

        # Over 30 characters
        res = handle_profile(profile_context, ["new", "a" * 35])
        assert not res.ok


def test_profile_new_and_edit_refuse_non_interactive(profile_context: ShellContext):
    """When sys.stdin.isatty() is False, interactive creation/editing is refused."""
    with patch("sys.stdin.isatty", return_value=False):
        res_new = handle_profile(profile_context, ["new", "fresh"])
        assert not res_new.ok
        assert "Non-interactive mode" in (res_new.message or "")

        res_edit = handle_profile(profile_context, ["edit", "coding"])
        assert not res_edit.ok
        assert "Non-interactive mode" in (res_edit.message or "")


# ============================================================================
# 7. INTERACTIVE PROFILE EDITOR ACTIONS
# ============================================================================

def test_interactive_profile_editor_scripted(profile_context: ShellContext):
    """Scripted inputs (add, desc, optional, move, remove, save) work cleanly."""
    inputs = [
        "desc My Custom Test Profile",
        "add github",
        "add sysinfo",
        "optional 2",
        "add pwd",
        "move 3 1",  # Move pwd to first
        "remove 2",  # Remove second
        "save",
    ]

    with patch("sys.stdin.isatty", return_value=True):
        with patch("commands.profile.input", side_effect=inputs):
            with patch("commands.profile.confirm_prompt", return_value=True):
                res = handle_profile(profile_context, ["new", "testflow"])
                assert res.ok

    wf = profile_context.config.get_workflow("testflow")
    assert wf is not None
    assert wf["description"] == "My Custom Test Profile"
    assert len(wf["steps"]) == 2


def test_profile_editor_rejects_control_characters_and_forbidden_commands(profile_context: ShellContext):
    """Control characters and forbidden nested commands (undo, delete, kill) are refused."""
    inputs = [
        "add delete file.txt",      # Forbidden command
        "add undo",                 # Forbidden command
        "add \x01\x02badcontrol",   # Control characters
        "cancel",
    ]

    with patch("sys.stdin.isatty", return_value=True):
        with patch("commands.profile.input", side_effect=inputs):
            with patch("commands.profile.confirm_prompt", return_value=True):
                res = handle_profile(profile_context, ["new", "safe_flow"])
                assert not res.ok


def test_profile_editor_lines_never_logged_or_added_to_history(profile_context: ShellContext):
    """Editor commands (add, remove, save, etc.) never enter history.json."""
    initial_history_len = len(profile_context.history_manager.get_all())

    inputs = [
        "add github",
        "save",
    ]

    with patch("sys.stdin.isatty", return_value=True):
        with patch("commands.profile.input", side_effect=inputs):
            with patch("commands.profile.confirm_prompt", return_value=True):
                handle_profile(profile_context, ["new", "historycheck"])

    # History manager count must be unchanged by editor inputs
    assert len(profile_context.history_manager.get_all()) == initial_history_len
