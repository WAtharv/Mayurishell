"""Workflow command implementation: list, show, run, add, remove, validate."""
from __future__ import annotations

import re
from typing import Any

from rich.markup import escape
from rich.table import Table

from commands.files import confirm_prompt
from core.executor import CommandResult
from core.logging_config import get_logger
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.workflow_service import (
    MAX_WORKFLOW_STEPS,
    WorkflowDefinition,
    WorkflowStep,
    execute_workflow_step,
    parse_raw_step,
    resolve_step,
    validate_workflow,
)

logger = get_logger()


def handle_workflow_list(context: Any) -> CommandResult:
    """List all configured workflows."""
    console = context.console
    theme = context.theme
    workflows = context.config.get_workflows()

    if not workflows:
        console.print(theme.format_muted("No workflows configured."))
        return CommandResult.success()

    table = theme.create_table(title="Configured Workflows")
    table.add_column("Workflow", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Steps", style=theme.muted_style, justify="right")
    table.add_column("Description", style=theme.text_style)

    for name, data in sorted(workflows.items()):
        steps = data.get("steps", []) if isinstance(data, dict) else []
        desc = data.get("description", "-") if isinstance(data, dict) else "-"
        table.add_row(escape(name), str(len(steps)), escape(desc))

    console.print(table)
    console.print(
        f"{theme.format_muted('Run a workflow with ')}"
        f"{theme.format_primary('workflow run <name>', bold=True)}"
        f"{theme.format_muted(' or inspect steps with ')}"
        f"{theme.format_primary('workflow show <name>', bold=True)}"
        f"{theme.format_muted('.')}\n"
    )
    return CommandResult.success()


def handle_workflow_show(context: Any, name: str) -> CommandResult:
    """Display workflow details and step sequence."""
    console = context.console
    theme = context.theme
    raw_data = context.config.get_workflow(name)

    if not raw_data:
        console.print(f"{theme.format_error('Workflow not found:')} '{escape(name)}'")
        return CommandResult.fail("Workflow not found")

    wf_def, errors = validate_workflow(name, raw_data, context)

    table = theme.create_table(title=f"Workflow: {escape(name)}")
    table.add_column("Step", style=theme.muted_style, justify="right", no_wrap=True)
    table.add_column("Command", style=theme.bold_primary_style)
    table.add_column("Target / Action", style=theme.warning_style, overflow="fold")
    table.add_column("Optional", style=theme.accent_style)

    desc = raw_data.get("description", "") if isinstance(raw_data, dict) else ""
    console.print(f"{theme.format_accent('Description:', bold=True)} {escape(desc)}")

    if wf_def:
        for idx, step in enumerate(wf_def.steps, start=1):
            opt_label = "Yes (?)" if step.optional else "No"
            table.add_row(str(idx), escape(step.command), escape(step.resolved_target), opt_label)
        console.print(table)
        return CommandResult.success()
    else:
        console.print(f"{theme.format_error('Workflow contains invalid steps:')}")
        for err in errors:
            console.print(f"  • {escape(err)}")
        return CommandResult.fail("Invalid workflow")


def handle_workflow_run(context: Any, name: str, dry_run: bool = False) -> CommandResult:
    """Execute a workflow after displaying plan and confirmation."""
    console = context.console
    theme = context.theme
    raw_data = context.config.get_workflow(name)

    if not raw_data:
        console.print(f"{theme.format_error('Workflow not found:')} '{escape(name)}'")
        return CommandResult.fail("Workflow not found")

    # Re-validate workflow right before running
    wf_def, errors = validate_workflow(name, raw_data, context)
    if not wf_def:
        console.print(f"{theme.format_error('Cannot run invalid workflow:')} '{escape(name)}'")
        for err in errors:
            console.print(f"  • {escape(err)}")
        return CommandResult.fail("Cannot run invalid workflow")

    # Display plan table with resolved targets
    table = theme.create_table(
        title=f"Workflow Plan: {escape(name)} ({len(wf_def.steps)} steps)"
    )
    table.add_column("Step", style=theme.muted_style, justify="right")
    table.add_column("Command", style=theme.bold_primary_style)
    table.add_column("Resolved Target", style=theme.warning_style, overflow="fold")
    table.add_column("Optional", style=theme.accent_style)

    for idx, step in enumerate(wf_def.steps, start=1):
        opt_text = "Yes" if step.optional else "No"
        table.add_row(str(idx), escape(step.command), escape(step.resolved_target), opt_text)

    console.print(table)

    if dry_run:
        console.print(
            theme.format_warning(
                f"[Dry Run] Displayed plan for '{escape(name)}'. Run without --dry-run to execute."
            )
        )
        return CommandResult.success()

    # Confirmation (default No)
    confirmed = confirm_prompt(
        console,
        f"Run workflow '{name}' ({len(wf_def.steps)} steps)?",
        default_yes=False,
        theme=theme,
    )
    if not confirmed:
        console.print(theme.format_muted("Workflow execution cancelled."))
        return CommandResult.cancel()

    console.print(f"\n{theme.format_accent('Starting workflow:', bold=True)} {escape(name)}")
    success_count = 0

    for idx, step in enumerate(wf_def.steps, start=1):
        # Re-validate single step right before running
        fresh_step, val_err = resolve_step(step.raw, context)
        if fresh_step:
            fresh_step.optional = fresh_step.optional or step.optional
        if val_err or not fresh_step:
            err_msg = val_err or "Step validation failed"
            if step.optional:
                console.print(
                    f"  [{idx}/{len(wf_def.steps)}] {theme.format_warning(f'Optional step {idx} validation warning:')} {escape(err_msg)}"
                )
                continue
            else:
                console.print(
                    f"  [{idx}/{len(wf_def.steps)}] {theme.format_error(f'Step {idx} validation error:')} {escape(err_msg)}"
                )
                console.print(theme.format_error(f"Workflow '{escape(name)}' halted due to step failure."))
                return CommandResult.fail("Step validation error")

        console.print(
            f"  [{idx}/{len(wf_def.steps)}] Running {theme.format_primary(escape(fresh_step.command), bold=True)} "
            f"({theme.format_muted(escape(fresh_step.resolved_target))})..."
        )

        ok, msg = execute_workflow_step(fresh_step, context)
        if ok:
            success_count += 1
        else:
            if fresh_step.optional:
                console.print(
                    f"    {theme.format_warning('Warning (optional step skipped):')} {escape(msg)}"
                )
            else:
                console.print(f"    {theme.format_error('Error:')} {escape(msg)}")
                console.print(theme.format_error(f"Workflow '{escape(name)}' halted on step {idx}."))
                return CommandResult.fail("Step execution error")

    console.print(
        f"\n{theme.format_success('Workflow completed successfully:')} "
        f"{theme.format_primary(escape(name), bold=True)} ({success_count} steps executed).\n"
    )
    return CommandResult.success()


def handle_workflow_add(context: Any, name: str, step_args: list[str]) -> CommandResult:
    """Add a new workflow with validation."""
    console = context.console
    theme = context.theme

    clean_name = name.strip().lower()
    if not re.match(r"^[a-zA-Z0-9_-]+$", clean_name):
        console.print(
            f"{theme.format_error('Invalid workflow name:')} "
            "Names may only contain letters, numbers, hyphens, and underscores."
        )
        return CommandResult.fail("Invalid workflow name")

    if not step_args:
        console.print(f"{theme.format_error('Error:')} Missing steps for workflow '{escape(clean_name)}'.")
        return CommandResult.fail("Missing steps")

    # Split steps: supports quoted steps or semicolon separated
    parsed_steps: list[str] = []
    for arg in step_args:
        # Check semicolons inside argument
        if ";" in arg:
            sub = [s.strip() for s in arg.split(";") if s.strip()]
            parsed_steps.extend(sub)
        else:
            cleaned = arg.strip()
            if cleaned:
                parsed_steps.append(cleaned)

    if not parsed_steps:
        console.print(f"{theme.format_error('Error:')} No steps provided.")
        return CommandResult.fail("No steps provided")

    if len(parsed_steps) > MAX_WORKFLOW_STEPS:
        console.print(
            f"{theme.format_error('Error:')} Workflow has {len(parsed_steps)} steps, "
            f"exceeding maximum allowed ({MAX_WORKFLOW_STEPS})."
        )
        return CommandResult.fail("Exceeded maximum steps")

    # Validate each step before saving
    errors: list[str] = []
    for idx, st in enumerate(parsed_steps, start=1):
        step_obj, err = resolve_step(st, context)
        if err:
            errors.append(f"Step {idx} ('{st}'): {err}")

    if errors:
        console.print(f"{theme.format_error('Cannot add workflow: validation errors found:')}")
        for e in errors:
            console.print(f"  • {escape(e)}")
        return CommandResult.fail("Validation errors found")

    desc = f"Custom workflow {clean_name}"
    context.config.set_workflow(clean_name, {
        "description": desc,
        "steps": parsed_steps,
    })

    console.print(
        f"{theme.format_success('Workflow added successfully:')} "
        f"{theme.format_primary(escape(clean_name), bold=True)} ({len(parsed_steps)} steps)."
    )
    return CommandResult.success()


def handle_workflow_remove(context: Any, name: str) -> CommandResult:
    """Remove a configured workflow."""
    console = context.console
    theme = context.theme

    clean_name = name.strip().lower()
    removed = context.config.remove_workflow(clean_name)
    if removed:
        console.print(
            f"{theme.format_success('Workflow removed:')} {theme.format_primary(escape(clean_name), bold=True)}"
        )
        return CommandResult.success()
    else:
        console.print(f"{theme.format_error('Workflow not found:')} '{escape(clean_name)}'")
        return CommandResult.fail("Workflow not found")


def handle_workflow_validate(context: Any) -> CommandResult:
    """Validate all configured workflows and report results."""
    console = context.console
    theme = context.theme
    workflows = context.config.get_workflows()

    if not workflows:
        console.print(theme.format_muted("No workflows configured to validate."))
        return CommandResult.success()

    table = theme.create_table(title="Workflow Validation Report")
    table.add_column("Workflow", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Status", style=theme.bold_text_style)
    table.add_column("Steps", style=theme.muted_style, justify="right")
    table.add_column("Issues", style=theme.warning_style)

    for name, data in sorted(workflows.items()):
        wf_def, errors = validate_workflow(name, data, context)
        if wf_def and not errors:
            status = theme.format_success("VALID")
            issues = "None"
            step_count = str(len(wf_def.steps))
        else:
            status = theme.format_error("INVALID")
            issues = "; ".join(errors) if errors else "Malformed definition"
            step_count = str(len(data.get("steps", []))) if isinstance(data, dict) else "0"

        table.add_row(escape(name), status, step_count, escape(issues))

    console.print(table)
    return CommandResult.success()


def handle_workflow(context: Any, args: list[str]) -> CommandResult:
    """Dispatcher for workflow commands."""
    console = context.console
    theme = context.theme

    if not args or args[0].lower() == "list":
        return handle_workflow_list(context)

    subcmd = args[0].lower()

    if subcmd == "show":
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} workflow show <name>")
            return CommandResult.fail("Missing workflow name")
        return handle_workflow_show(context, args[1])

    elif subcmd == "run":
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} workflow run <name> [--dry-run]")
            return CommandResult.fail("Missing workflow name")
        dry_run = any(a.lower() in ("--dry-run", "-n") for a in args[2:])
        return handle_workflow_run(context, args[1], dry_run=dry_run)

    elif subcmd == "add":
        if len(args) < 3:
            console.print(f"{theme.format_error('Usage:')} workflow add <name> <step 1> [step 2...]")
            return CommandResult.fail("Missing arguments")
        return handle_workflow_add(context, args[1], args[2:])

    elif subcmd in ("remove", "delete"):
        if len(args) < 2:
            console.print(f"{theme.format_error('Usage:')} workflow remove <name>")
            return CommandResult.fail("Missing workflow name")
        return handle_workflow_remove(context, args[1])

    elif subcmd == "validate":
        return handle_workflow_validate(context)

    else:
        # Check if the user typed 'workflow <name>' directly as a shortcut for run or show
        wfs = context.config.get_workflows()
        if subcmd in wfs:
            return handle_workflow_run(context, subcmd, dry_run=False)
        else:
            console.print(
                f"{theme.format_error('Unknown workflow subcommand:')} '{escape(subcmd)}'. "
                f"Valid subcommands: {theme.format_primary('list, show, run, add, remove, validate')}"
            )
            return CommandResult.fail("Unknown workflow subcommand")


def register_workflow_commands(registry: CommandRegistry, config: Any) -> None:
    """Register workflow command in command registry."""
    registry.register(
        CommandInfo(
            name="workflow",
            description="Manage and execute multi-step automation workflows",
            handler=handle_workflow,
            usage="workflow [list | show <name> | run <name> [--dry-run] | add <name> <steps...> | remove <name> | validate]",
            category="Workflows",
            arg_rules=ArgumentRules(min_args=0, max_args=None),
        )
    )
