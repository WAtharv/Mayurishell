"""Workflow profiles command for MayuriShell.

Provides a user-friendly profile management interface for launch configurations,
workspace setup, and multi-step tasks backed by config["workflows"].
"""
from __future__ import annotations

import re
import sys
from typing import Any

from rich.markup import escape
from rich.table import Table

from commands.files import confirm_prompt
from core.executor import CommandResult
from core.logging_config import get_logger
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.workflow_service import (
    MAX_WORKFLOW_STEPS,
    WorkflowStep,
    execute_workflow_step,
    parse_raw_step,
    resolve_step,
)

logger = get_logger()

PROFILE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9\-]{1,30}$")
RESERVED_NAMES = {
    "list",
    "show",
    "new",
    "edit",
    "remove",
    "undo",
    "last",
    "all",
    "help",
    "workflow",
    "workflows",
}
MAX_DESC_LENGTH = 80


def handle_profile(context: Any, args: list[str]) -> CommandResult:
    """Handle workflow profile commands.

    Usage:
      profile                   - Show profiles overview and help
      profile list              - List all profiles
      profile show <name>       - View profile steps and resolution details
      profile <name> [--dry-run]- Run a profile (or preview with --dry-run)
      profile new <name>        - Interactively create a new profile
      profile edit <name>       - Interactively edit an existing profile
      profile remove <name>     - Remove a profile
    """
    console = context.console
    theme = context.theme

    if not args:
        return _handle_profile_list(context)

    sub = args[0].strip()

    if sub == "list":
        return _handle_profile_list(context)

    if sub == "show":
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} profile show <name>")
            return CommandResult.fail("Missing profile name")
        return _handle_profile_show(context, args[1].strip())

    if sub == "new":
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} profile new <name>")
            return CommandResult.fail("Missing profile name")
        return _handle_profile_new(context, args[1].strip())

    if sub == "edit":
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} profile edit <name>")
            return CommandResult.fail("Missing profile name")
        return _handle_profile_edit(context, args[1].strip())

    if sub == "remove":
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} profile remove <name>")
            return CommandResult.fail("Missing profile name")
        return _handle_profile_remove(context, args[1].strip())

    if sub.startswith("-"):
        console.print(f"{theme.format_error('Unknown option:')} '{escape(sub)}'")
        return CommandResult.fail(f"Unknown option '{sub}'")

    # Otherwise: profile <name> [--dry-run]
    dry_run = "--dry-run" in args or "-n" in args
    return _handle_profile_run(context, sub, dry_run=dry_run)


def _handle_profile_list(context: Any) -> CommandResult:
    """List all configured profiles with status validation."""
    console = context.console
    theme = context.theme
    workflows = context.config.get_workflows()

    if not workflows:
        console.print(theme.format_muted("No profiles configured."))
        console.print(
            f"Create one with: {theme.format_primary('profile new <name>', bold=True)}"
        )
        return CommandResult.success()

    table = theme.create_table(title=f"Workflow Profiles ({len(workflows)} configured)")
    table.add_column("Profile", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Description", style=theme.text_style)
    table.add_column("Steps", justify="right")
    table.add_column("Status")

    for name, data in sorted(workflows.items()):
        desc = data.get("description", "-") if isinstance(data, dict) else "-"
        steps = data.get("steps", []) if isinstance(data, dict) else []

        # Validate steps for shortcut or syntax issues
        unresolved_count = 0
        for s in steps:
            step_obj, err = resolve_step(s, context)
            if err or not step_obj:
                unresolved_count += 1

        if unresolved_count == 0:
            status_text = theme.format_success("READY")
        else:
            status_text = theme.format_warning(f"{unresolved_count} unresolvable")

        table.add_row(
            escape(name),
            escape(desc),
            str(len(steps)),
            status_text,
        )

    console.print(table)
    console.print(
        f"{theme.format_muted('Run a profile with: ')}"
        f"{theme.format_primary('profile <name>', bold=True)}"
        f"{theme.format_muted('  |  Edit: ')}"
        f"{theme.format_primary('profile edit <name>', bold=True)}"
    )
    return CommandResult.success()


def _handle_profile_show(context: Any, name: str) -> CommandResult:
    """Display detailed steps and target resolution for a profile."""
    console = context.console
    theme = context.theme

    data = context.config.get_workflow(name)
    if not data:
        console.print(f"{theme.format_error('Profile not found:')} '{escape(name)}'")
        return CommandResult.fail("Profile not found")

    desc = data.get("description", "-")
    steps = data.get("steps", [])

    console.print(f"{theme.format_primary(f'Profile: {name}', bold=True)}")
    console.print(f"{theme.format_muted('Description:')} {escape(desc)}")
    console.print(f"{theme.format_muted('Total Steps:')} {len(steps)}\n")

    if not steps:
        console.print(theme.format_muted("This profile has no steps."))
        return CommandResult.success()

    table = theme.create_table(title=f"Steps for '{escape(name)}'")
    table.add_column("#", justify="right", style=theme.muted_style)
    table.add_column("Step", style=theme.bold_primary_style)
    table.add_column("Action / Target", style=theme.accent_style)
    table.add_column("Optional")

    for idx, raw_step in enumerate(steps, 1):
        step_obj, err = resolve_step(raw_step, context)
        if step_obj:
            action_desc = step_obj.resolved_target or step_obj.step_type
            opt_desc = theme.format_warning("Yes (?)") if step_obj.optional else "No"
            table.add_row(str(idx), escape(step_obj.raw), escape(action_desc), opt_desc)
        else:
            opt_desc = theme.format_warning("Yes (?)") if str(raw_step).strip().startswith("?") else "No"
            table.add_row(
                str(idx),
                escape(str(raw_step)),
                theme.format_error(f"Error: {err}"),
                opt_desc,
            )

    console.print(table)
    return CommandResult.success()


def _handle_profile_run(context: Any, name: str, dry_run: bool = False) -> CommandResult:
    """Preview plan, confirm, and execute profile steps."""
    console = context.console
    theme = context.theme

    data = context.config.get_workflow(name)
    if not data:
        console.print(f"{theme.format_error('Profile not found:')} '{escape(name)}'")
        console.print(f"Type {theme.format_primary('profile list', bold=True)} to view available profiles.")
        return CommandResult.fail("Profile not found")

    steps = data.get("steps", [])
    if not steps:
        console.print(theme.format_muted(f"Profile '{escape(name)}' has no steps to run."))
        return CommandResult.success()

    # Build plan
    resolved_plan: list[tuple[int, Any, WorkflowStep | None, str | None]] = []
    for idx, raw_step in enumerate(steps, 1):
        step_obj, err = resolve_step(raw_step, context)
        resolved_plan.append((idx, raw_step, step_obj, err))

    # Show execution plan table
    table = theme.create_table(title=f"Profile Plan: {escape(name)} ({len(steps)} steps)")
    table.add_column("#", justify="right", style=theme.muted_style)
    table.add_column("Step", style=theme.bold_primary_style)
    table.add_column("Target / Resolution", style=theme.accent_style)
    table.add_column("Optional")

    for idx, raw_s, step_obj, err in resolved_plan:
        if step_obj:
            opt_str = theme.format_warning("Yes (?)") if step_obj.optional else "No"
            table.add_row(str(idx), escape(step_obj.raw), escape(step_obj.resolved_target), opt_str)
        else:
            opt_str = theme.format_warning("Yes (?)") if str(raw_s).strip().startswith("?") else "No"
            table.add_row(str(idx), escape(str(raw_s)), theme.format_error(f"Unresolvable: {err}"), opt_str)

    console.print(table)

    if dry_run:
        console.print(theme.format_warning("[Dry Run] No steps executed. Run without --dry-run to apply."))
        return CommandResult.success()

    # Prompt confirmation
    confirmed = confirm_prompt(
        console,
        f"Run profile '{name}' ({len(steps)} steps)?",
        default_yes=False,
        theme=theme,
    )
    if not confirmed:
        console.print(theme.format_muted("Profile execution cancelled."))
        return CommandResult.cancel()

    # Execute steps sequentially
    console.print(f"\n{theme.format_primary(f'Executing profile: {name}', bold=True)}")
    succeeded_count = 0
    skipped_optional_count = 0

    for idx, raw_s, step_obj, err in resolved_plan:
        if not step_obj or err:
            _, is_opt = parse_raw_step(raw_s)
            if is_opt:
                console.print(f"  {theme.format_warning('⚠')} Step #{idx} {escape(str(raw_s))} (optional, unresolvable): {escape(str(err))}")
                skipped_optional_count += 1
                continue
            else:
                console.print(f"  {theme.format_error('✗')} Step #{idx} {escape(str(raw_s))} failed: {escape(str(err))}")
                console.print(f"{theme.format_error('Profile aborted:')} Step failed and was not optional.")
                return CommandResult.fail(f"Step #{idx} failed")

        ok, msg = execute_workflow_step(step_obj, context)
        if ok:
            console.print(f"  {theme.format_success('✓')} {escape(step_obj.raw)}: {escape(msg)}")
            succeeded_count += 1
        else:
            if step_obj.optional:
                console.print(f"  {theme.format_warning('⚠')} {escape(step_obj.raw)} (optional, ignored): {escape(msg)}")
                skipped_optional_count += 1
            else:
                console.print(f"  {theme.format_error('✗')} {escape(step_obj.raw)}: {escape(msg)}")
                console.print(f"{theme.format_error('Profile aborted:')} Step failed and was not optional.")
                return CommandResult.fail(f"Step '{step_obj.raw}' failed")

    console.print(
        f"\n{theme.format_success('Profile finished:')} "
        f"{succeeded_count} step(s) succeeded"
        f"{f', {skipped_optional_count} optional skipped' if skipped_optional_count else ''}."
    )
    return CommandResult.success()


def _handle_profile_remove(context: Any, name: str) -> CommandResult:
    """Prompt confirmation, back up config, and remove profile."""
    console = context.console
    theme = context.theme

    clean_name = name.lower()
    if not context.config.get_workflow(clean_name):
        console.print(f"{theme.format_error('Profile not found:')} '{escape(name)}'")
        return CommandResult.fail("Profile not found")

    confirmed = confirm_prompt(
        console,
        f"Are you sure you want to remove profile '{clean_name}'?",
        default_yes=False,
        theme=theme,
    )
    if not confirmed:
        console.print(theme.format_muted("Profile removal cancelled."))
        return CommandResult.cancel()

    context.config.backup("profile_remove")
    context.config.remove_workflow(clean_name)
    console.print(f"{theme.format_success('Removed profile:')} {theme.format_primary(clean_name, bold=True)}")
    return CommandResult.success()


def _validate_profile_name(name: str) -> tuple[bool, str]:
    """Validate profile name against syntax and collision rules."""
    clean = name.strip().lower()
    if not clean:
        return False, "Profile name cannot be empty."
    if not PROFILE_NAME_REGEX.match(clean):
        return False, "Profile name must be 1-30 alphanumeric characters or hyphens (a-z, 0-9, -)."
    if clean in RESERVED_NAMES:
        return False, f"Name '{clean}' is a reserved command and cannot be used as a profile name."
    return True, ""


def _handle_profile_new(context: Any, name: str) -> CommandResult:
    """Start interactive creation of a new profile."""
    console = context.console
    theme = context.theme

    if not sys.stdin.isatty():
        console.print(f"{theme.format_error('Interactive profile creation requires a terminal.')}")
        return CommandResult.fail("Non-interactive mode")

    valid, err = _validate_profile_name(name)
    if not valid:
        console.print(f"{theme.format_error('Invalid profile name:')} {err}")
        return CommandResult.fail(err)

    clean_name = name.strip().lower()
    if context.config.get_workflow(clean_name):
        console.print(f"{theme.format_error('Profile already exists:')} '{escape(clean_name)}'")
        return CommandResult.fail("Profile already exists")

    console.print(f"{theme.format_primary(f'Creating new profile: {clean_name}', bold=True)}")
    console.print(theme.format_muted("Type 'help' for editor commands or 'cancel' to exit.\n"))

    return _run_profile_editor(context, clean_name, initial_desc="", initial_steps=[])


def _handle_profile_edit(context: Any, name: str) -> CommandResult:
    """Start interactive editing of an existing profile."""
    console = context.console
    theme = context.theme

    if not sys.stdin.isatty():
        console.print(f"{theme.format_error('Interactive profile editing requires a terminal.')}")
        return CommandResult.fail("Non-interactive mode")

    clean_name = name.strip().lower()
    data = context.config.get_workflow(clean_name)
    if not data:
        console.print(f"{theme.format_error('Profile not found:')} '{escape(clean_name)}'")
        return CommandResult.fail("Profile not found")

    initial_desc = str(data.get("description", ""))
    initial_steps = list(data.get("steps", []))

    console.print(f"{theme.format_primary(f'Editing profile: {clean_name}', bold=True)}")
    console.print(theme.format_muted("Type 'help' for editor commands or 'cancel' to exit.\n"))

    return _run_profile_editor(context, clean_name, initial_desc=initial_desc, initial_steps=initial_steps)


def _run_profile_editor(
    context: Any,
    name: str,
    initial_desc: str,
    initial_steps: list[str],
) -> CommandResult:
    """Run the interactive profile editor loop.

    Never logs editor commands or writes them to command history.
    Refuses inputs with control characters or newlines.
    """
    console = context.console
    theme = context.theme

    working_desc = initial_desc
    working_steps = list(initial_steps)
    dirty = False

    while True:
        try:
            prompt_str = f"[profile:{name}] > "
            console.print(theme.format_accent(prompt_str, bold=True), end="")
            line = input()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n{theme.format_muted('Editor cancelled.')}")
            return CommandResult.cancel()

        # Reject control characters or newlines
        if any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in line) or "\n" in line or "\r" in line:
            console.print(f"{theme.format_error('Error:')} Control characters and newlines are not permitted.")
            continue

        raw = line.strip()
        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        action = parts[0].lower()
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        if action == "help":
            _print_editor_help(context)

        elif action == "show":
            _display_editor_state(context, name, working_desc, working_steps)

        elif action == "desc":
            if not sub_arg:
                console.print(f"{theme.format_error('Usage:')} desc <description text>")
                continue
            if len(sub_arg) > MAX_DESC_LENGTH:
                console.print(f"{theme.format_error('Error:')} Description cannot exceed {MAX_DESC_LENGTH} characters.")
                continue
            working_desc = sub_arg
            dirty = True
            console.print(f"{theme.format_success('Description updated:')} {escape(working_desc)}")

        elif action == "add":
            if not sub_arg:
                console.print(f"{theme.format_error('Usage:')} add <step>")
                continue
            if len(working_steps) >= MAX_WORKFLOW_STEPS:
                console.print(f"{theme.format_error('Error:')} Profile has reached maximum of {MAX_WORKFLOW_STEPS} steps.")
                continue

            # Validate step immediately against security allowlists
            step_obj, err = resolve_step(sub_arg, context)
            if err or not step_obj:
                console.print(f"{theme.format_error('Invalid step:')} {err}")
                continue

            working_steps.append(step_obj.raw)
            dirty = True
            console.print(
                f"{theme.format_success('Added step')} #{len(working_steps)}: "
                f"{theme.format_primary(escape(step_obj.raw), bold=True)} "
                f"({escape(step_obj.resolved_target)})"
            )

        elif action == "remove":
            if not sub_arg or not sub_arg.isdigit():
                console.print(f"{theme.format_error('Usage:')} remove <step_number>")
                continue
            idx = int(sub_arg)
            if idx < 1 or idx > len(working_steps):
                console.print(f"{theme.format_error('Error:')} Step number {idx} is out of range (1..{len(working_steps)}).")
                continue
            removed = working_steps.pop(idx - 1)
            dirty = True
            console.print(f"{theme.format_success('Removed step')} #{idx}: {escape(removed)}")

        elif action == "move":
            tokens = sub_arg.split()
            if len(tokens) != 2 or not tokens[0].isdigit() or not tokens[1].isdigit():
                console.print(f"{theme.format_error('Usage:')} move <from_step> <to_step>")
                continue
            from_idx = int(tokens[0])
            to_idx = int(tokens[1])
            if from_idx < 1 or from_idx > len(working_steps) or to_idx < 1 or to_idx > len(working_steps):
                console.print(f"{theme.format_error('Error:')} Step index out of range (1..{len(working_steps)}).")
                continue
            item = working_steps.pop(from_idx - 1)
            working_steps.insert(to_idx - 1, item)
            dirty = True
            console.print(f"{theme.format_success('Moved step')} #{from_idx} to #{to_idx}")

        elif action == "optional":
            if not sub_arg or not sub_arg.isdigit():
                console.print(f"{theme.format_error('Usage:')} optional <step_number>")
                continue
            idx = int(sub_arg)
            if idx < 1 or idx > len(working_steps):
                console.print(f"{theme.format_error('Error:')} Step number {idx} is out of range (1..{len(working_steps)}).")
                continue
            curr_step = working_steps[idx - 1].strip()
            if curr_step.startswith("?"):
                # Make non-optional
                new_step = curr_step[1:].strip()
            else:
                # Make optional
                new_step = f"? {curr_step}"
            working_steps[idx - 1] = new_step
            dirty = True
            console.print(f"{theme.format_success('Updated step')} #{idx}: {escape(new_step)}")

        elif action == "save":
            if not working_steps:
                confirmed = confirm_prompt(
                    console,
                    f"Profile '{name}' has 0 steps. Save empty profile anyway?",
                    default_yes=False,
                    theme=theme,
                )
                if not confirmed:
                    continue
            else:
                confirmed = confirm_prompt(
                    console,
                    f"Save changes to profile '{name}' ({len(working_steps)} step(s))?",
                    default_yes=False,
                    theme=theme,
                )
                if not confirmed:
                    continue

            context.config.backup("profile_edit")
            context.config.set_workflow(
                name,
                {
                    "description": working_desc,
                    "steps": working_steps,
                },
            )
            console.print(f"{theme.format_success('Profile saved:')} {theme.format_primary(name, bold=True)}")
            return CommandResult.success()

        elif action == "cancel":
            if dirty:
                confirmed = confirm_prompt(
                    console,
                    "Discard unsaved profile changes?",
                    default_yes=False,
                    theme=theme,
                )
                if not confirmed:
                    continue
            console.print(theme.format_muted("Editor cancelled. No changes were saved."))
            return CommandResult.cancel()

        else:
            console.print(
                f"{theme.format_error('Unknown action:')} '{escape(action)}'. "
                f"Type 'help' for available actions."
            )


def _print_editor_help(context: Any) -> None:
    """Print available interactive profile editor actions."""
    console = context.console
    theme = context.theme

    console.print(f"\n{theme.format_accent('Profile Editor Actions:', bold=True)}")
    console.print(f"  {theme.format_primary('add <step>')}        - Add a workflow step (e.g. 'code projects', '? discord')")
    console.print(f"  {theme.format_primary('remove <n>')}        - Remove step at 1-based index n")
    console.print(f"  {theme.format_primary('move <n> <m>')}      - Move step from index n to m")
    console.print(f"  {theme.format_primary('optional <n>')}      - Toggle optional '?' prefix for step n")
    console.print(f"  {theme.format_primary('desc <text>')}       - Set description (max 80 chars)")
    console.print(f"  {theme.format_primary('show')}              - Display current steps and description")
    console.print(f"  {theme.format_primary('save')}              - Save profile changes to config")
    console.print(f"  {theme.format_primary('cancel')}            - Exit without saving\n")


def _display_editor_state(
    context: Any,
    name: str,
    description: str,
    steps: list[str],
) -> None:
    """Display current draft state inside the profile editor."""
    console = context.console
    theme = context.theme

    console.print(f"\n{theme.format_primary(f'Profile Draft: {name}', bold=True)}")
    console.print(f"{theme.format_muted('Description:')} {escape(description or '(none)')}")
    console.print(f"{theme.format_muted('Steps:')} {len(steps)} / {MAX_WORKFLOW_STEPS}")

    if not steps:
        console.print(theme.format_muted("(no steps added yet)\n"))
        return

    table = theme.create_table(title="Current Steps")
    table.add_column("#", justify="right", style=theme.muted_style)
    table.add_column("Step", style=theme.bold_primary_style)
    table.add_column("Target / Action", style=theme.accent_style)
    table.add_column("Optional")

    for idx, raw_step in enumerate(steps, 1):
        step_obj, err = resolve_step(raw_step, context)
        if step_obj:
            opt_desc = theme.format_warning("Yes (?)") if step_obj.optional else "No"
            table.add_row(str(idx), escape(step_obj.raw), escape(step_obj.resolved_target), opt_desc)
        else:
            opt_desc = theme.format_warning("Yes (?)") if str(raw_step).strip().startswith("?") else "No"
            table.add_row(str(idx), escape(str(raw_step)), theme.format_error(f"Error: {err}"), opt_desc)

    console.print(table)
    console.print()


def register_profile_commands(registry: CommandRegistry) -> None:
    """Register profile command in the registry."""
    registry.register(
        CommandInfo(
            name="profile",
            description="Manage and run multi-step workflow profiles.",
            category="Workflows",
            usage="profile [<name> [--dry-run] | list | show <name> | new <name> | edit <name> | remove <name>]",
            handler=handle_profile,
            arg_rules=ArgumentRules(
                min_args=0,
                max_args=None,
            ),
        )
    )
    registry.register(
        CommandInfo(
            name="profiles",
            description="List all configured workflow profiles.",
            category="Workflows",
            usage="profiles",
            handler=lambda ctx, args: handle_profile(ctx, ["list"] + args),
            arg_rules=ArgumentRules(
                min_args=0,
                max_args=None,
            ),
        )
    )

