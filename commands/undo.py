"""Undo command for MayuriShell.

Provides multi-operation persistent undo for file move, rename, and organize operations.
Never undoes anything without an explicit target.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.markup import escape
from rich.table import Table

from commands.files import confirm_prompt
from core.executor import CommandResult
from core.logging_config import get_logger
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.undo_service import (
    OPERATION_ID_REGEX,
    UndoJournalVersionError,
    UndoLockTimeoutError,
    JournalOperation,
    evaluate_undo_plan,
    execute_undo_plan,
    find_latest_undoable_operation,
    load_journal,
)

logger = get_logger()

MAX_LIST_ROWS = 20
MAX_PLAN_ROWS = 50


def handle_undo(context: Any, args: list[str]) -> CommandResult:
    """Handle undo commands.

    Usage:
      undo                  - Show usage instructions and recent operations
      undo list [--all]     - List tracked operations (newest first)
      undo last             - Undo the most recent move, rename, or organize
      undo <operation-id>   - Undo a specific operation by 6-character hex ID
    """
    console = context.console
    theme = context.theme
    base_dir = context.config.base_dir

    try:
        ops = load_journal(base_dir)
    except UndoJournalVersionError as exc:
        console.print(f"{theme.format_error('Undo journal version error:')} {escape(str(exc))}")
        return CommandResult.fail(str(exc))
    except Exception as exc:
        logger.warning("Failed to load undo journal: %s", exc)
        ops = []

    # Case 1: bare 'undo' -> show usage and recent operations table. NEVER undoes anything.
    if not args:
        _display_undo_help(context, ops)
        return CommandResult.success()

    sub = args[0].strip()

    # Case 2: 'undo list [--all]'
    if sub == "list":
        show_all = "--all" in args
        _display_undo_list(context, ops, show_all=show_all)
        return CommandResult.success()

    # Case 3: 'undo last'
    if sub == "last":
        target_op = find_latest_undoable_operation(base_dir)
        if not target_op:
            console.print(theme.format_muted("No previous operations found to undo."))
            return CommandResult.success()
        return _preview_and_execute_undo(context, target_op)

    # Case 4: 'undo <operation-id>'
    if OPERATION_ID_REGEX.match(sub.lower()):
        target_id = sub.lower()
        target_op = next((o for o in ops if o.id.lower() == target_id), None)
        if not target_op:
            console.print(f"{theme.format_error('Operation not found:')} '{escape(sub)}'")
            return CommandResult.fail("Operation not found")

        if target_op.status == "undone" and not target_op.items:
            console.print(theme.format_muted(f"Operation '{target_op.id}' has already been completely undone."))
            return CommandResult.success()

        return _preview_and_execute_undo(context, target_op)

    # Case 5: unrecognized subcommand / invalid ID
    if sub.startswith("-"):
        console.print(f"{theme.format_error('Unknown option:')} '{escape(sub)}'")
        return CommandResult.fail(f"Unknown option '{sub}'")

    console.print(
        f"{theme.format_error('Invalid operation ID or subcommand:')} '{escape(sub)}'. "
        f"Operation IDs are 6 hexadecimal characters (e.g. 'a1b2c3'). "
        f"Type {theme.format_primary('undo list', bold=True)} to view operations."
    )
    return CommandResult.fail("Invalid undo target")


def _display_undo_help(context: Any, ops: list[JournalOperation]) -> None:
    """Display undo usage guide and a table of the most recent operations."""
    console = context.console
    theme = context.theme

    console.print(f"{theme.format_primary('MayuriShell Undo System', bold=True)}\n")
    console.print(f"{theme.format_accent('Usage:')}")
    console.print(f"  {theme.format_primary('undo')}                - Show this help guide and recent operations")
    console.print(f"  {theme.format_primary('undo list [--all]')}  - List tracked operations (max 20 unless --all)")
    console.print(f"  {theme.format_primary('undo last')}           - Undo the most recent move, rename, or organize")
    console.print(f"  {theme.format_primary('undo <id>')}           - Undo a specific operation by 6-char hex ID\n")

    if not ops:
        console.print(theme.format_muted("No operations recorded yet."))
        console.print(theme.format_muted("Note: File deletions cannot be undone here. Restore deleted files from the Recycle Bin."))
        return

    recent_ops = list(reversed(ops))[:5]
    table = theme.create_table(title="Recent Undoable Operations")
    table.add_column("ID", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Time", style=theme.muted_style)
    table.add_column("Type", style=theme.accent_style)
    table.add_column("Items", justify="right")
    table.add_column("Status")

    for op in recent_ops:
        status_styled = _format_op_status(theme, op.status)
        table.add_row(
            escape(op.id),
            escape(_format_timestamp(op.timestamp)),
            escape(op.type),
            str(len(op.items)),
            status_styled,
        )

    console.print(table)
    console.print(theme.format_muted("Note: File deletions cannot be undone here. Restore deleted files from the Recycle Bin."))


def _display_undo_list(context: Any, ops: list[JournalOperation], show_all: bool = False) -> None:
    """Display the list of recorded operations, newest first."""
    console = context.console
    theme = context.theme

    if not ops:
        console.print(theme.format_muted("No operations recorded yet."))
        console.print(theme.format_muted("Note: File deletions cannot be undone here. Restore deleted files from the Recycle Bin."))
        return

    reversed_ops = list(reversed(ops))
    display_ops = reversed_ops if show_all else reversed_ops[:MAX_LIST_ROWS]

    title = f"Tracked Operations ({len(ops)} total)" if not show_all and len(ops) > MAX_LIST_ROWS else "Tracked Operations"
    table = theme.create_table(title=title)
    table.add_column("ID", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Timestamp", style=theme.muted_style)
    table.add_column("Type", style=theme.accent_style)
    table.add_column("Items", justify="right")
    table.add_column("Status")

    for op in display_ops:
        status_styled = _format_op_status(theme, op.status)
        table.add_row(
            escape(op.id),
            escape(_format_timestamp(op.timestamp)),
            escape(op.type),
            str(len(op.items)),
            status_styled,
        )

    console.print(table)
    if not show_all and len(ops) > MAX_LIST_ROWS:
        remaining = len(ops) - MAX_LIST_ROWS
        console.print(theme.format_muted(f"... and {remaining} older operations. Use 'undo list --all' to see everything."))

    console.print(theme.format_muted("Note: File deletions cannot be undone here. Restore deleted files from the Recycle Bin."))


def _preview_and_execute_undo(
    context: Any,
    op: JournalOperation,
    confirm_func: Any = None,
) -> CommandResult:
    """Display preview plan for an operation, prompt for confirmation, and execute safely."""
    console = context.console
    theme = context.theme
    base_dir = context.config.base_dir
    prompt_fn = confirm_func if confirm_func is not None else confirm_prompt


    if not op.items:
        console.print(theme.format_muted(f"Operation '{op.id}' has no items recorded."))
        return CommandResult.success()

    try:
        plan = evaluate_undo_plan(base_dir, op)
    except UndoJournalVersionError as exc:
        console.print(f"{theme.format_error('Undo journal version error:')} {escape(str(exc))}")
        return CommandResult.fail(str(exc))
    except Exception as exc:
        console.print(f"{theme.format_error('Failed to evaluate undo plan:')} {escape(str(exc))}")
        return CommandResult.fail("Plan evaluation failed")

    if not plan:
        console.print(theme.format_muted(f"No active items to undo for operation '{op.id}'."))
        return CommandResult.success()

    # Display preview table
    table = theme.create_table(title=f"Undo Preview: Operation {escape(op.id)} ({escape(op.type)}, {len(plan)} items)")
    table.add_column("Item", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("From", style=theme.warning_style)
    table.add_column("To", style=theme.success_style)
    table.add_column("Status")

    display_items = plan[:MAX_PLAN_ROWS]
    for plan_item in display_items:
        it = plan_item.item
        src_path = Path(it.source)
        dst_path = Path(it.destination)
        item_name = dst_path.name or src_path.name

        # Fold directory paths for display privacy and clean presentation
        from_display = dst_path.parent.name or str(dst_path.parent)
        to_display = src_path.parent.name or str(src_path.parent)

        if plan_item.can_restore:
            status_text = theme.format_success("READY")
        else:
            status_text = theme.format_error(f"SKIPPED ({plan_item.reason})")

        table.add_row(
            escape(item_name),
            escape(from_display),
            escape(to_display),
            status_text,
        )

    console.print(table)
    if len(plan) > MAX_PLAN_ROWS:
        console.print(theme.format_muted(f"... and {len(plan) - MAX_PLAN_ROWS} more items."))

    ready_count = sum(1 for p in plan if p.can_restore)
    skipped_count = len(plan) - ready_count
    console.print(
        f"{theme.format_accent('Summary:', bold=True)} "
        f"{theme.format_success(f'{ready_count} ready')} / "
        f"{theme.format_warning(f'{skipped_count} skipped')} "
        f"({len(plan)} total)\n"
    )

    if ready_count == 0:
        console.print(theme.format_warning("None of the items in this operation can be safely restored."))
        return CommandResult.fail("No items can be restored")

    # Prompt once if any item's original parent folder is missing
    recreate_parents = False
    needs_parent_count = sum(1 for p in plan if p.can_restore and p.needs_parent_dir)
    if needs_parent_count > 0:
        recreate_parents = prompt_fn(
            console,
            f"{needs_parent_count} original parent folder(s) no longer exist. Recreate them?",
            default_yes=False,
            theme=theme,
        )

    # Prompt user for final confirmation
    confirmed = prompt_fn(
        console,
        f"Restore {ready_count} file(s) for operation {op.id}?",
        default_yes=False,
        theme=theme,
    )

    if not confirmed:
        console.print(theme.format_muted("Undo cancelled."))
        return CommandResult.cancel()

    # Execute moves safely in reverse order
    try:
        restored, skipped, failed, final_status = execute_undo_plan(
            base_dir,
            op,
            plan,
            recreate_missing_parents=recreate_parents,
        )
    except KeyboardInterrupt:
        console.print(f"\n{theme.format_warning('Undo interrupted by user.')}")
        return CommandResult.cancel()
    except UndoLockTimeoutError as exc:
        console.print(f"{theme.format_error('Undo lock error:')} {escape(str(exc))}")
        return CommandResult.fail("Undo lock timeout")

    # Report results
    console.print(
        f"{theme.format_success('Undo completed:')} "
        f"{theme.format_primary(str(restored), bold=True)} restored, "
        f"{skipped} skipped, "
        f"{failed} failed."
    )

    if restored > 0:
        return CommandResult.success()
    return CommandResult.fail("Undo failed to restore any items")


def _format_op_status(theme: Any, status: str) -> str:
    """Format an operation status label with theme colors."""
    if status == "done":
        return theme.format_success("done")
    if status == "undone":
        return theme.format_muted("undone")
    if status == "partial":
        return theme.format_warning("partial")
    if status == "failed":
        return theme.format_error("failed")
    if status == "in_progress":
        return theme.format_primary("in_progress")
    return status


def _format_timestamp(ts: str) -> str:
    """Format an ISO timestamp to a friendly short display."""
    try:
        # e.g. 2026-10-24T20:30:00.123456 -> 2026-10-24 20:30:00
        clean = ts.replace("T", " ")
        if "." in clean:
            clean = clean.split(".")[0]
        return clean
    except Exception:
        return ts


def register_undo_commands(registry: CommandRegistry) -> None:
    """Register the undo command in the command registry."""
    registry.register(
        CommandInfo(
            name="undo",
            description="Inspect and reverse file move, rename, or organize operations.",
            category="Files",
            usage="undo [list [--all] | last | <operation-id>]",
            handler=handle_undo,
            arg_rules=ArgumentRules(
                min_args=0,
                max_args=2,
            ),
        )
    )

