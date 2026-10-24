"""Project commands for MayuriShell: project info, tree, env, and doctor.

Inspects project architecture, virtual environments, stacks, and health.
All commands are strictly read-only.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any

from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.doctor_service import is_windows_store_python_stub
from services.project_service import (
    build_project_tree,
    detect_project_kinds,
    find_project_root,
    find_venv_directory,
    get_project_info,
    is_drive_root,
    render_tree_lines,
    run_project_doctor_checks,
)


def handle_project_info(context: Any, root: Path) -> CommandResult:
    """Display high-level project summary."""
    console = context.console
    theme = context.theme

    info = get_project_info(root)

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=theme.bold_accent_style, justify="right")
    grid.add_column(overflow="fold")

    grid.add_row("Project Name:", theme.format_primary(escape(info.name), bold=True))
    grid.add_row("Root Directory:", theme.format_muted(escape(str(info.root))))
    
    kinds_str = ", ".join(info.kinds) if info.kinds else "generic"
    grid.add_row("Detected Stack:", theme.format_accent(escape(kinds_str)))

    git_str = "Yes (.git detected)" if info.is_git else "No (untracked)"
    grid.add_row("Git Repository:", theme.format_success(git_str) if info.is_git else theme.format_warning(git_str))

    grid.add_row("Python Files:", f"{info.python_files_count} files (capped scan)")
    
    tests_str = "Yes (tests/ directory found)" if info.has_tests else "No (tests/ missing)"
    grid.add_row("Test Suite:", theme.format_success(tests_str) if info.has_tests else theme.format_warning(tests_str))

    readme_str = "Yes (README found)" if info.has_readme else "No (README missing)"
    grid.add_row("Documentation:", theme.format_success(readme_str) if info.has_readme else theme.format_warning(readme_str))

    grid.add_row("Dependencies:", f"{info.dependency_count} declared packages")

    console.print(theme.create_panel(grid, title=f"Project Info: {escape(info.name)}"))
    return CommandResult.success()


def handle_project_tree(context: Any, root: Path, sub_args: list[str]) -> CommandResult:
    """Render project directory hierarchy with depth limits, budget, and skip rules."""
    console = context.console
    theme = context.theme

    # Parse arguments
    depth = 3
    show_all = False
    target_path = root

    idx = 0
    while idx < len(sub_args):
        arg = sub_args[idx]
        if arg in ("--all", "-a"):
            show_all = True
            idx += 1
        elif arg == "--depth":
            if idx + 1 < len(sub_args):
                try:
                    depth = max(1, min(int(sub_args[idx + 1]), 10))
                    idx += 2
                except ValueError:
                    idx += 1
            else:
                idx += 1
        elif arg.startswith("--depth="):
            try:
                depth = max(1, min(int(arg.split("=", 1)[1]), 10))
            except ValueError:
                pass
            idx += 1
        elif not arg.startswith("-"):
            # Target path specified
            candidate = (context.current_dir / arg).resolve()
            target_path = candidate
            idx += 1
        else:
            idx += 1

    # Security check: refuse filesystem drive roots and home directory as tree root
    if is_drive_root(target_path):
        err = "Refusing to render drive root as project tree."
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail(err, hint="Specify a project folder or subfolder.")

    try:
        home_dir = Path.home().resolve()
        if target_path == home_dir:
            err = "Refusing to render user home directory as project tree."
            console.print(f"{theme.format_error('Error:')} {escape(err)}")
            return CommandResult.fail(err, hint="Navigate to a project directory first.")
    except Exception:
        pass

    if not target_path.exists() or not target_path.is_dir():
        err = f"Directory not found: {target_path}"
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail(err, hint="Provide an existing directory path.")

    # Build tree
    root_node, total_entries, hit_limit = build_project_tree(
        target_path,
        depth=depth,
        show_all=show_all,
    )

    lines = render_tree_lines(root_node, is_plain=theme.is_plain)
    for line in lines:
        if theme.is_plain:
            console.print(line)
        else:
            if line.endswith("/"):
                console.print(theme.format_primary(line, bold=True))
            elif "[symlink]" in line or "[skipped]" in line:
                console.print(theme.format_muted(line))
            else:
                console.print(line)

    if hit_limit:
        console.print(
            f"\n{theme.format_warning('Note:')} Output capped (hit limit of 300 entries or 3-second budget)."
        )

    return CommandResult.success()


def handle_project_env(context: Any, root: Path) -> CommandResult:
    """Inspect Python virtual environment and activation commands."""
    console = context.console
    theme = context.theme

    kinds = detect_project_kinds(root)
    if "python" not in kinds:
        err = "Project environment inspection is only available for Python projects."
        console.print(f"{theme.format_warning('Notice:')} {escape(err)}")
        return CommandResult.fail(err, hint="Use 'create-project' to scaffold a Python project.")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=theme.bold_accent_style, justify="right")
    grid.add_column(overflow="fold")

    venv_data = find_venv_directory(root)
    if venv_data:
        v_name, v_path, v_cfg = venv_data
        py_ver = v_cfg.get("version", "unknown")
        py_home = v_cfg.get("home", "unknown")
        grid.add_row("Virtual Environment:", theme.format_success(f"{v_name} (Python {py_ver})"))
        grid.add_row("Base Interpreter:", theme.format_muted(escape(py_home)))
        grid.add_row("PowerShell Activate:", theme.format_accent(rf".\{v_name}\Scripts\Activate.ps1"))
        grid.add_row("Command Prompt Activate:", theme.format_accent(rf".\{v_name}\Scripts\activate.bat"))
    else:
        grid.add_row("Virtual Environment:", theme.format_warning("None detected (.venv, venv, env)"))
        grid.add_row("Setup Recommendation:", "python -m venv .venv")

    # Check real python on PATH (reusing doctor logic)
    candidates = ["python", "python3", "py"]
    found_real = False
    real_path = ""
    for cand in candidates:
        which_path = shutil.which(cand)
        if which_path and not is_windows_store_python_stub(which_path):
            found_real = True
            real_path = which_path
            break

    if found_real:
        grid.add_row("System Python on PATH:", theme.format_success(f"Available ({real_path})"))
    else:
        grid.add_row("System Python on PATH:", theme.format_warning("No full Python interpreter found on PATH"))

    # Check requirements files found
    req_files = []
    for fn in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "Pipfile", "environment.yml"):
        if (root / fn).is_file():
            req_files.append(fn)

    if req_files:
        grid.add_row("Requirements Files:", ", ".join(req_files))
    else:
        grid.add_row("Requirements Files:", theme.format_muted("None found"))

    # Check .env existence ONLY (NEVER read or print values)
    has_env = (root / ".env").is_file()
    if has_env:
        grid.add_row("Environment Secrets:", theme.format_warning(".env file found (values never read or logged)"))
    else:
        grid.add_row("Environment Secrets:", theme.format_muted("No .env file found in root"))

    console.print(theme.create_panel(grid, title=f"Python Environment: {escape(root.name)}"))
    return CommandResult.success()


def handle_project_doctor(context: Any, root: Path) -> CommandResult:
    """Run non-destructive diagnostic checks on the project root."""
    console = context.console
    theme = context.theme

    checks = run_project_doctor_checks(root)

    table = Table(box=None, padding=(0, 1), show_header=True)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Check", style=theme.bold_accent_style)
    table.add_column("Message", overflow="fold")
    table.add_column("Fix Suggestion", style=theme.muted_style, overflow="fold")

    any_fail = False

    for c in checks:
        if theme.is_plain:
            if c.status == "OK":
                status_disp = "[OK]"
            elif c.status == "WARN":
                status_disp = "[WARN]"
            elif c.status == "FAIL":
                status_disp = "[FAIL]"
                any_fail = True
            else:
                status_disp = "[??]"
        else:
            if c.status == "OK":
                status_disp = theme.format_success("[OK]")
            elif c.status == "WARN":
                status_disp = theme.format_warning("[WARN]")
            elif c.status == "FAIL":
                status_disp = theme.format_error("[FAIL]")
                any_fail = True
            else:
                status_disp = theme.format_muted("[??]")

        table.add_row(status_disp, escape(c.name), escape(c.message), escape(c.fix))

    console.print(theme.create_panel(table, title=f"Project Health: {escape(root.name)}"))
    
    if any_fail:
        return CommandResult.fail("One or more project doctor checks failed.")
    return CommandResult.success()


def handle_project(context: Any, args: list[str]) -> CommandResult:
    """Unified handler for 'project' command and subcommands."""
    console = context.console
    theme = context.theme

    if not args:
        console.print(theme.format_primary("Usage:", bold=True) + " project [info|tree|doctor|env] [options]")
        console.print("Subcommands:")
        console.print("  project info                 Display summary of detected project stack")
        console.print("  project tree [path] [--depth N] [--all]  Show hierarchy capped at depth")
        console.print("  project doctor               Check project configuration and dependencies")
        console.print("  project env                  Inspect Python virtualenv and activation")
        return CommandResult.success()

    subcmd = args[0].lower()
    sub_args = args[1:]

    # Locate project root starting from context.current_dir (never os.getcwd())
    root = find_project_root(context.current_dir)
    if not root:
        err = "No project detected here"
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail(
            err,
            hint="Navigate to a project directory with 'cd' or create one with 'create-project'.",
        )

    if subcmd == "info":
        return handle_project_info(context, root)
    elif subcmd == "tree":
        return handle_project_tree(context, root, sub_args)
    elif subcmd == "env":
        return handle_project_env(context, root)
    elif subcmd == "doctor":
        return handle_project_doctor(context, root)
    else:
        err = f"Unknown project subcommand '{args[0]}'."
        console.print(f"{theme.format_error('Error:')} {escape(err)}")
        return CommandResult.fail(
            err,
            hint="Valid subcommands: project info, project tree, project doctor, project env.",
        )


def register_project_aware_commands(registry: CommandRegistry) -> None:
    """Register 'project' command in the CommandRegistry."""
    registry.register(
        CommandInfo(
            name="project",
            description="Inspect project stack, tree hierarchy, environment, and doctor health",
            handler=handle_project,
            usage="project [info|tree|doctor|env] [options]",
            category="Projects",
            arg_rules=ArgumentRules(min_args=0, max_args=None),
        )
    )
