"""Tests for workflow service, command validation, allowlists, and execution."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.workflows import (
    handle_workflow,
    handle_workflow_add,
    handle_workflow_list,
    handle_workflow_remove,
    handle_workflow_run,
    handle_workflow_show,
    handle_workflow_validate,
)
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from core.shell import ShellContext
from services.workflow_service import (
    MAX_WORKFLOW_STEPS,
    resolve_step,
    validate_workflow,
)


@pytest.fixture
def wf_context(tmp_path: Path):
    """Create test shell context with mock apps and websites."""
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    config = ConfigManager(base_dir=appdata)

    # Configure some shortcuts
    config.set_shortcut("websites", "github", "https://github.com")
    config.set_shortcut("websites", "youtube", "https://youtube.com")
    config.set_shortcut("folder_shortcuts", "projects", str(tmp_path / "projects"))
    config.set_shortcut("applications", "notepad", "notepad.exe")

    registry = CommandRegistry()
    from commands.files import register_file_commands
    register_file_commands(registry)
    history = MagicMock()
    console = Console(record=True, width=120)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = ShellContext(
        config=config,
        registry=registry,
        history_manager=history,
        console=console,
        current_dir=work_dir,
    )
    return ctx


def test_workflow_allowlist_and_blocked_commands(wf_context: ShellContext):
    """Test that safe commands pass and dangerous/blocked commands fail allowlist check."""
    # Safe allowlisted commands
    safe_steps = [
        "github",
        "youtube",
        "projects",
        "notepad",
        "pwd",
        "sysinfo",
        "cd .",
        "ls .",
        "organize downloads --dry-run",
    ]
    for st in safe_steps:
        step_obj, err = resolve_step(st, wf_context)
        assert err is None, f"Expected '{st}' to pass allowlist, got error: {err}"
        assert step_obj is not None

    # Blocked commands
    blocked_steps = [
        "delete file.txt",
        "kill 1234",
        "move file.txt dir/",
        "rename a.txt b.txt",
        "copy a.txt b.txt",
        "alias foo bar",
        "config get display.theme",
        "workflow run other_wf",
        "organize downloads",  # organize without --dry-run is forbidden!
    ]
    for st in blocked_steps:
        step_obj, err = resolve_step(st, wf_context)
        assert step_obj is None, f"Expected '{st}' to be blocked"
        assert err is not None


def test_workflow_resolves_aliases_before_allowlist(wf_context: ShellContext):
    """Requirement 3: Resolve aliases BEFORE allowlist check."""
    alias_mgr = wf_context.alias_manager
    alias_mgr.add_alias("gh", "github")
    alias_mgr.add_alias("rm", "delete")

    # Safe alias 'gh' -> 'github' (website) should pass
    step_obj, err = resolve_step("gh", wf_context)
    assert err is None
    assert step_obj is not None
    assert step_obj.command == "github"
    assert "https://github.com" in step_obj.resolved_target

    # Dangerous alias 'rm' -> 'delete' should be rejected
    step_obj, err = resolve_step("rm file.txt", wf_context)
    assert step_obj is None
    assert "forbidden" in err


def test_workflow_open_refuses_executables(wf_context: ShellContext, tmp_path: Path):
    """Requirement 3: 'open' inside a workflow must refuse executable/script types."""
    # Plain text file -> permitted
    doc_file = tmp_path / "work" / "readme.txt"
    doc_file.write_text("hello")
    step_obj, err = resolve_step("open readme.txt", wf_context)
    assert err is None
    assert step_obj is not None

    # Executable / script files -> forbidden
    for bad_ext in [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".js", ".lnk"]:
        bad_file = tmp_path / "work" / f"app{bad_ext}"
        bad_file.write_text("malicious")
        step_obj, err = resolve_step(f"open app{bad_ext}", wf_context)
        assert step_obj is None
        assert "refuses executable/script types" in err


def test_workflow_optional_prefix(wf_context: ShellContext):
    """Test that '?' prefix marks a step optional."""
    step_obj, err = resolve_step("? open readme.txt", wf_context)
    assert err is None
    assert step_obj.optional is True
    assert step_obj.command == "open"

    step_obj2, err2 = resolve_step("?github", wf_context)
    assert err2 is None
    assert step_obj2.optional is True
    assert step_obj2.command == "github"

    step_obj3, err3 = resolve_step("github", wf_context)
    assert err3 is None
    assert step_obj3.optional is False


def test_workflow_step_limit_20(wf_context: ShellContext):
    """Test maximum 20 steps restriction."""
    valid_data = {"description": "test", "steps": ["github"] * 20}
    wf_def, errs = validate_workflow("twenty", valid_data, wf_context)
    assert wf_def is not None
    assert not errs

    too_many_data = {"description": "test", "steps": ["github"] * 21}
    wf_def, errs = validate_workflow("toomany", too_many_data, wf_context)
    assert wf_def is None
    assert any("exceeding maximum" in e for e in errs)


def test_workflow_run_dry_run_shows_plan(wf_context: ShellContext):
    """Test workflow run --dry-run prints plan with resolved targets and stops without execution."""
    wf_context.config.set_workflow("dev", {
        "description": "Dev setup",
        "steps": ["github", "projects", "? pwd"],
    })

    with patch("services.launcher_service.webbrowser.open") as mock_web:
        handle_workflow_run(wf_context, "dev", dry_run=True)
        mock_web.assert_not_called()

    out = wf_context.console.export_text()
    assert "Workflow Plan: dev" in out
    assert "https://github.com" in out
    assert "[Dry Run]" in out


def test_workflow_run_stops_on_first_error_unless_optional(wf_context: ShellContext):
    """Test that workflow halts on first non-optional failure and continues on optional failure."""
    wf_context.config.set_workflow("mixed", {
        "description": "Mixed workflow",
        "steps": [
            "? open non_existent_optional_file.txt",  # optional failure -> continues
            "github",  # success
        ],
    })

    with patch("commands.workflows.confirm_prompt", return_value=True), \
         patch("services.launcher_service.webbrowser.open", return_value=True) as mock_web:
        handle_workflow_run(wf_context, "mixed", dry_run=False)
        mock_web.assert_called_once()

    out = wf_context.console.export_text()
    assert "optional step skipped" in out
    assert "Workflow completed successfully" in out


def test_workflow_add_show_remove_validate(wf_context: ShellContext):
    """Test workflow CRUD and validate commands."""
    # 1. Add workflow
    handle_workflow_add(wf_context, "morning", ["github", "youtube"])
    out = wf_context.console.export_text()
    assert "Workflow added successfully" in out
    assert "morning" in wf_context.config.get_workflows()

    # 2. Show workflow
    handle_workflow_show(wf_context, "morning")
    out_show = wf_context.console.export_text()
    assert "Workflow: morning" in out_show
    assert "https://github.com" in out_show

    # 3. Validate workflows
    handle_workflow_validate(wf_context)
    out_val = wf_context.console.export_text()
    assert "VALID" in out_val

    # 4. Remove workflow
    handle_workflow_remove(wf_context, "morning")
    assert "morning" not in wf_context.config.get_workflows()
