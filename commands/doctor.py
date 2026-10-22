"""System health inspection command: doctor."""
from __future__ import annotations

from typing import Any

from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.doctor_service import run_doctor


def handle_doctor(context: Any, args: list[str]) -> CommandResult:
    """Inspect shell health, shortcuts, Python runtime, and configuration."""
    console = context.console
    theme = context.theme

    category = "all"
    if args:
        sub = args[0].strip().lower()
        if sub in ("apps", "python", "config", "all"):
            category = sub
        else:
            err = f"Unknown doctor category '{escape(args[0])}'."
            console.print(f"{theme.format_error('Error:')} {err}")
            console.print("Valid categories: apps, python, config, all.")
            return CommandResult.fail(err, hint="Usage: doctor [apps|python|config|all]")

    console.print(theme.format_muted(f"Running MayuriShell Doctor checks ({category})...\n"))
    findings, counts = run_doctor(category=category, context=context)

    # Format findings in a clean Rich table
    table = theme.create_table(title=f"MayuriShell Doctor - Health Report ({category.upper()})")
    table.add_column("Status", justify="center", style=theme.bold_text_style, no_wrap=True)
    table.add_column("Component", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Details & Actionable Fix", style=theme.text_style, overflow="fold")

    for f in findings:
        # Status badge
        if theme.is_plain:
            if f.status == "OK":
                status_badge = "[OK]"
            elif f.status == "WARN":
                status_badge = "[WARN]"
            elif f.status == "FAIL":
                status_badge = "[FAIL]"
            else:
                status_badge = "[??]"
        else:
            if f.status == "OK":
                status_badge = theme.format_success("[OK]", bold=True)
            elif f.status == "WARN":
                status_badge = theme.format_warning("[WARN]", bold=True)
            elif f.status == "FAIL":
                status_badge = theme.format_error("[FAIL]", bold=True)
            else:
                status_badge = theme.format_muted("[??]")

        details = escape(f.message)
        if f.fix:
            if theme.is_plain:
                details += f"\n  Fix: {f.fix}"
            else:
                details += f"\n  {theme.format_accent('Fix:', bold=True)} {theme.format_primary(escape(f.fix))}"

        table.add_row(status_badge, escape(f.name), details)

    console.print(table)

    # Summary line
    if theme.is_plain:
        summary_text = f"Doctor Summary: {counts['OK']} OK, {counts['WARN']} WARN, {counts['FAIL']} FAIL, {counts['UNKNOWN']} UNKNOWN"
    else:
        summary_text = (
            f"Doctor Summary: "
            f"{theme.format_success(str(counts['OK']) + ' OK', bold=True)}, "
            f"{theme.format_warning(str(counts['WARN']) + ' WARN', bold=True)}, "
            f"{theme.format_error(str(counts['FAIL']) + ' FAIL', bold=True)}, "
            f"{theme.format_muted(str(counts['UNKNOWN']) + ' UNKNOWN')}"
        )
    console.print(f"\n{summary_text}\n")
    return CommandResult.success()


def register_doctor_commands(registry: CommandRegistry) -> None:
    """Register doctor command with the CommandRegistry."""
    registry.register(
        CommandInfo(
            name="doctor",
            description="Run system health checks and troubleshooting diagnostics",
            handler=handle_doctor,
            usage="doctor [apps|python|config|all]",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )
