"""Read-only Git assistant command for MayuriShell.

Provides read-only status, log, diff, branches, and summary.
Rejects all write, commit, staging, network, and modification subcommands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.git_service import (
    ALLOWED_GIT_SUBCOMMANDS,
    MAX_STATUS_FILES,
    get_git_branches,
    get_git_diff,
    get_git_log,
    get_git_status,
    get_git_summary,
)


def handle_git_status(context: Any, sub_args: list[str]) -> CommandResult:
    """Display git status with porcelain v2 grouping and file caps."""
    console = context.console
    theme = context.theme

    ok, summary, err_msg, fix_hint = get_git_status(context.current_dir)
    if not ok or summary is None:
        console.print(f"{theme.format_error('Git Status Error:')} {escape(err_msg)}")
        return CommandResult.fail(err_msg, hint=fix_hint)

    # Header info
    header = f"On branch {summary.branch}"
    if summary.ahead > 0 or summary.behind > 0:
        ab_parts = []
        if summary.ahead > 0:
            ab_parts.append(f"ahead {summary.ahead}")
        if summary.behind > 0:
            ab_parts.append(f"behind {summary.behind}")
        header += f" [{', '.join(ab_parts)}]"

    console.print(theme.format_primary(escape(header), bold=True))

    displayed_count = 0

    # 1. Conflicted files
    if summary.conflicted:
        console.print(f"\n{theme.format_error('Unmerged paths (conflicts):', bold=True)}")
        for f in summary.conflicted:
            if displayed_count >= MAX_STATUS_FILES:
                break
            console.print(f"  {theme.format_error('both modified:')}   {escape(f)}")
            displayed_count += 1

    # 2. Changes to be committed (staged)
    if summary.staged:
        console.print(f"\n{theme.format_success('Changes to be committed (staged):', bold=True)}")
        for f in summary.staged:
            if displayed_count >= MAX_STATUS_FILES:
                break
            console.print(f"  {theme.format_success('staged:')}          {escape(f)}")
            displayed_count += 1

    # 3. Changes not staged for commit
    if summary.modified:
        console.print(f"\n{theme.format_warning('Changes not staged for commit:', bold=True)}")
        for f in summary.modified:
            if displayed_count >= MAX_STATUS_FILES:
                break
            console.print(f"  {theme.format_warning('modified:')}        {escape(f)}")
            displayed_count += 1

    # 4. Untracked files
    if summary.untracked:
        console.print(f"\n{theme.format_accent('Untracked files:', bold=True)}")
        for f in summary.untracked:
            if displayed_count >= MAX_STATUS_FILES:
                break
            console.print(f"  {theme.format_muted('untracked:')}       {escape(f)}")
            displayed_count += 1

    if displayed_count >= MAX_STATUS_FILES and summary.total_files > MAX_STATUS_FILES:
        remaining = summary.total_files - MAX_STATUS_FILES
        console.print(f"\n{theme.format_muted(f'... and {remaining} more files (capped at {MAX_STATUS_FILES})')}")

    if summary.total_files == 0:
        console.print(theme.format_success("Nothing to commit, working tree clean"))

    return CommandResult.success()


def handle_git_log(context: Any, sub_args: list[str]) -> CommandResult:
    """Display git log with fixed formatting and validated count (-n 1..50)."""
    console = context.console
    theme = context.theme

    count = 10
    idx = 0
    while idx < len(sub_args):
        arg = sub_args[idx]
        if arg == "-n":
            if idx + 1 < len(sub_args):
                try:
                    count = int(sub_args[idx + 1])
                    idx += 2
                except ValueError:
                    return CommandResult.fail("Invalid count for -n", hint="Specify a number between 1 and 50.")
            else:
                return CommandResult.fail("Missing count argument for -n", hint="Usage: git log [-n N]")
        elif arg.startswith("-n"):
            try:
                count = int(arg[2:])
                idx += 1
            except ValueError:
                return CommandResult.fail("Invalid count for -n", hint="Specify a number between 1 and 50.")
        else:
            return CommandResult.fail(
                f"Unsupported argument '{arg}' for git log.",
                hint="Usage: git log [-n N] (allowed count: 1 to 50)",
            )

    if not (1 <= count <= 50):
        return CommandResult.fail(
            f"Invalid count {count}. Allowed range is 1 to 50.",
            hint="Specify a count between 1 and 50.",
        )

    ok, entries, err_msg, fix_hint = get_git_log(context.current_dir, count=count)
    if not ok:
        console.print(f"{theme.format_error('Git Log Error:')} {escape(err_msg)}")
        return CommandResult.fail(err_msg, hint=fix_hint)

    if not entries:
        console.print(theme.format_muted("No commits found."))
        return CommandResult.success()

    table = Table(box=None, padding=(0, 1), show_header=True)
    table.add_column("Commit", style=theme.bold_primary_style, width=9)
    table.add_column("Date", style=theme.muted_style, width=12)
    table.add_column("Author", style=theme.accent_style, width=16)
    table.add_column("Subject", overflow="fold")

    for e in entries:
        table.add_row(
            escape(e["hash"]),
            escape(e["date"]),
            escape(e["author"]),
            escape(e["subject"]),
        )

    console.print(theme.create_panel(table, title=f"Recent Commits (last {len(entries)})"))
    return CommandResult.success()


def handle_git_diff(context: Any, sub_args: list[str]) -> CommandResult:
    """Display git diff or stat summary with capped output."""
    console = context.console
    theme = context.theme

    staged = False
    path_arg: str | None = None

    idx = 0
    while idx < len(sub_args):
        arg = sub_args[idx]
        if arg in ("--staged", "--cached"):
            staged = True
            idx += 1
        elif not arg.startswith("-"):
            if path_arg is None:
                path_arg = arg
                idx += 1
            else:
                return CommandResult.fail(
                    "Only one file path may be specified for git diff.",
                    hint="Usage: git diff [path] [--staged]",
                )
        else:
            return CommandResult.fail(
                f"Unsupported diff option '{arg}'.",
                hint="Usage: git diff [path] [--staged]",
            )

    ok, diff_text, was_truncated, err_msg, fix_hint = get_git_diff(
        context.current_dir,
        file_path=path_arg,
        staged=staged,
    )

    if not ok:
        console.print(f"{theme.format_error('Git Diff Error:')} {escape(err_msg)}")
        return CommandResult.fail(err_msg, hint=fix_hint)

    if not diff_text.strip():
        scope = "staged" if staged else "working directory"
        console.print(theme.format_muted(f"No changes detected in {scope}."))
        return CommandResult.success()

    # Format diff output lines safely
    diff_lines = diff_text.splitlines()
    for dl in diff_lines:
        if dl.startswith("+") and not dl.startswith("+++"):
            console.print(theme.format_success(escape(dl)))
        elif dl.startswith("-") and not dl.startswith("---"):
            console.print(theme.format_error(escape(dl)))
        elif dl.startswith("@@"):
            console.print(theme.format_accent(escape(dl)))
        else:
            console.print(escape(dl))

    if was_truncated:
        console.print(
            f"\n{theme.format_warning('Note:')} Diff truncated to 200 lines. Run 'git diff' in your terminal for full diff."
        )

    return CommandResult.success()


def handle_git_branches(context: Any, sub_args: list[str]) -> CommandResult:
    """Display local branches with active branch marked and upstream tracking."""
    console = context.console
    theme = context.theme

    ok, branches, err_msg, fix_hint = get_git_branches(context.current_dir)
    if not ok:
        console.print(f"{theme.format_error('Git Branches Error:')} {escape(err_msg)}")
        return CommandResult.fail(err_msg, hint=fix_hint)

    if not branches:
        console.print(theme.format_muted("No local branches found."))
        return CommandResult.success()

    grid = Table.grid(padding=(0, 2))
    grid.add_column(width=2, justify="center")
    grid.add_column(style=theme.bold_accent_style)
    grid.add_column(style=theme.muted_style, overflow="fold")

    for b in branches:
        marker = "*" if b["current"] else " "
        name_str = theme.format_success(b["name"], bold=True) if b["current"] else escape(b["name"])
        upstream_str = f"[{b['upstream']}]" if b["upstream"] else ""
        grid.add_row(marker, name_str, escape(upstream_str))

    console.print(theme.create_panel(grid, title="Local Git Branches"))
    return CommandResult.success()


def handle_git_summary(context: Any, sub_args: list[str]) -> CommandResult:
    """Display high-level repository summary with branch, counts, and safe next suggestions."""
    console = context.console
    theme = context.theme

    ok, summary, err_msg, fix_hint = get_git_summary(context.current_dir)
    if not ok or summary is None:
        console.print(f"{theme.format_error('Git Summary Error:')} {escape(err_msg)}")
        return CommandResult.fail(err_msg, hint=fix_hint)

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=theme.bold_accent_style, justify="right")
    grid.add_column(overflow="fold")

    grid.add_row("Current Branch:", theme.format_primary(escape(summary["branch"]), bold=True))

    ab_str = f"+{summary['ahead']} / -{summary['behind']}" if (summary["ahead"] or summary["behind"]) else "Up to date"
    grid.add_row("Upstream Sync:", theme.format_muted(ab_str))

    status_counts = (
        f"{summary['staged_count']} staged, "
        f"{summary['modified_count']} modified, "
        f"{summary['untracked_count']} untracked, "
        f"{summary['conflict_count']} conflicts"
    )
    grid.add_row("Working Tree:", status_counts)

    last = summary.get("last_commit")
    if last:
        last_str = f"{last['hash']} - {last['subject']} ({last['relative_date']})"
        grid.add_row("Last Commit:", theme.format_muted(escape(last_str)))
    else:
        grid.add_row("Last Commit:", theme.format_muted("No commits yet"))

    # Harmless next suggestions
    suggs = summary.get("suggestions", [])
    if suggs:
        sugg_text = ", ".join(theme.format_accent(s) for s in suggs)
        grid.add_row("What next:", sugg_text)

    console.print(theme.create_panel(grid, title=f"Git Overview: {escape(summary['branch'])}"))
    return CommandResult.success()


def handle_git(context: Any, args: list[str]) -> CommandResult:
    """Unified handler for git command, strictly enforcing read-only allowlist."""
    console = context.console
    theme = context.theme

    if not args:
        console.print(theme.format_primary("Usage:", bold=True) + " git [status|log|diff|branches|summary] [options]")
        console.print("Allowed read-only subcommands:")
        console.print("  git status               Show branch and file change summary")
        console.print("  git log [-n N]           Show recent commits (1 to 50 entries)")
        console.print("  git diff [path] [--staged] Show changes or file diff (capped)")
        console.print("  git branches             List local branches")
        console.print("  git summary              Repository overview and safe next suggestions")
        return CommandResult.success()

    subcmd = args[0].lower()
    sub_args = args[1:]

    # Enforce strict read-only allowlist
    if subcmd not in ALLOWED_GIT_SUBCOMMANDS:
        err = "MayuriShell's Git assistant is read-only. Run this in your normal terminal."
        console.print(f"{theme.format_warning('Read-Only:')} {err}")
        return CommandResult.fail(err, hint="Only status, log, diff, branches, and summary are supported.")

    if subcmd == "status":
        return handle_git_status(context, sub_args)
    elif subcmd == "log":
        return handle_git_log(context, sub_args)
    elif subcmd == "diff":
        return handle_git_diff(context, sub_args)
    elif subcmd == "branches":
        return handle_git_branches(context, sub_args)
    elif subcmd == "summary":
        return handle_git_summary(context, sub_args)

    return CommandResult.fail("Unknown git command")


def register_git_commands(registry: CommandRegistry) -> None:
    """Register 'git' command in the CommandRegistry."""
    registry.register(
        CommandInfo(
            name="git",
            description="Read-only Git assistant (status, log, diff, branches, summary)",
            handler=handle_git,
            usage="git [status|log|diff|branches|summary] [options]",
            category="Git",
            arg_rules=ArgumentRules(min_args=0, max_args=None),
        )
    )
