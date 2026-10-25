"""Workflow engine and validation service for MayuriShell."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
from typing import Any, Sequence

from core.logging_config import get_logger
from services.application_discovery import launch_detached
from services.file_service import EXECUTABLE_EXTENSIONS
from services.launcher_service import launch_folder, launch_website

logger = get_logger()

# Safe commands permitted in workflows
ALLOWLISTED_BUILTIN_COMMANDS = {
    "cd",
    "ls",
    "pwd",
    "open",
    "fetch",
    "theme",
    "mascot",
    "sysinfo",
}

# Commands explicitly forbidden in workflows
FORBIDDEN_COMMANDS = {
    "delete",
    "kill",
    "process",
    "move",
    "rename",
    "copy",
    "alias",
    "unalias",
    "config",
    "workflow",
    "workflows",
    "add-website",
    "add-folder",
    "add-app",
    "remove-shortcut",
    "create-project",
    "templates",
    "diagnostics",
    "git",
    "project",
    "undo",
    "profile",
    "profiles",
}


MAX_WORKFLOW_STEPS = 20


@dataclass
class WorkflowStep:
    """Represents a single parsed and resolved workflow step."""
    raw: str
    command: str
    args: list[str]
    optional: bool = False
    resolved_target: str = ""
    step_type: str = "command"  # "app", "website", "folder", "builtin"


@dataclass
class WorkflowDefinition:
    """Represents a validated multi-step workflow."""
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)


def parse_raw_step(raw_step: Any) -> tuple[str, bool]:
    """Extract command string and optional flag from raw step config or CLI input."""
    if isinstance(raw_step, dict):
        cmd_str = str(raw_step.get("command", "")).strip()
        opt = bool(raw_step.get("optional", False))
        return cmd_str, opt

    text = str(raw_step).strip()
    if text.startswith("?"):
        # Strip leading ? and optional whitespace
        return text[1:].strip(), True
    return text, False


def resolve_step(
    raw_step: Any,
    context: Any,
) -> tuple[WorkflowStep | None, str | None]:
    """Parse, resolve aliases, and validate a single workflow step against security allowlists.
    
    Returns:
        (WorkflowStep, None) on success, or (None, error_message) on failure.
    """
    cmd_text, is_optional = parse_raw_step(raw_step)
    if not cmd_text:
        return None, "Empty workflow step."

    canonical_raw = f"? {cmd_text}" if is_optional else cmd_text

    try:
        tokens = shlex.split(cmd_text, posix=False)
    except Exception as exc:
        return None, f"Failed to parse step '{cmd_text}': {exc}"

    if not tokens:
        return None, "Empty workflow step."

    cmd_name = tokens[0].strip()
    args = tokens[1:]

    # Strip Windows quotes from tokens if needed
    clean_args: list[str] = []
    for a in args:
        cleaned = a.strip()
        if len(cleaned) >= 2 and (
            (cleaned.startswith('"') and cleaned.endswith('"'))
            or (cleaned.startswith("'") and cleaned.endswith("'"))
        ):
            cleaned = cleaned[1:-1]
        clean_args.append(cleaned)

    # 1. Pre-resolve alias BEFORE allowlist check
    alias_mgr = getattr(context, "alias_manager", None)
    if alias_mgr:
        try:
            res_name, res_args = alias_mgr.resolve(cmd_name, clean_args)
            cmd_name = res_name
            clean_args = res_args
        except Exception as exc:
            return None, f"Alias loop or resolution error in step '{cmd_text}': {exc}"

    norm_name = cmd_name.lower()

    # 2. Check forbidden commands
    if norm_name in FORBIDDEN_COMMANDS:
        return None, f"Command '{cmd_name}' is forbidden inside workflows."

    config = context.config
    apps = config.get_applications() if hasattr(config, "get_applications") else {}
    websites = config.get_websites() if hasattr(config, "get_websites") else {}
    folders = config.get_folder_shortcuts() if hasattr(config, "get_folder_shortcuts") else {}

    # 3. Check organize: ONLY allowed if --dry-run is present
    if norm_name == "organize":
        has_dry_run = any(arg.lower() in ("--dry-run", "-n") for arg in clean_args)
        if not has_dry_run:
            return None, "Only 'organize --dry-run' is allowed in workflows (never a real organize)."
        target_folder = clean_args[0] if clean_args and not clean_args[0].startswith("-") else "."
        res_path, _ = context.resolve_path(target_folder)
        return (
            WorkflowStep(
                raw=canonical_raw,
                command=norm_name,
                args=clean_args,
                optional=is_optional,
                resolved_target=f"organize {res_path} --dry-run",
                step_type="builtin",
            ),
            None,
        )

    # 4. Check special open restriction: refuse executables/scripts
    if norm_name == "open":
        if not clean_args:
            return None, "'open' requires a target file argument."
        target_path, _ = context.resolve_path(clean_args[0])
        ext = target_path.suffix.lower()
        if ext in EXECUTABLE_EXTENSIONS:
            return None, f"'open' inside workflows refuses executable/script types ({ext}): '{target_path.name}'"
        return (
            WorkflowStep(
                raw=canonical_raw,
                command=norm_name,
                args=clean_args,
                optional=is_optional,
                resolved_target=f"File: {target_path}",
                step_type="builtin",
            ),
            None,
        )

    # 5. Check other allowlisted built-in commands
    if norm_name in ALLOWLISTED_BUILTIN_COMMANDS:
        resolved_info = norm_name
        if norm_name == "cd":
            target_dir = clean_args[0] if clean_args else "~"
            res_p, _ = context.resolve_path(target_dir)
            resolved_info = f"Change directory -> {res_p}"
        elif norm_name == "ls":
            target_dir = clean_args[0] if clean_args else "."
            res_p, _ = context.resolve_path(target_dir)
            resolved_info = f"List directory -> {res_p}"
        elif norm_name == "pwd":
            resolved_info = f"Print working directory ({context.current_dir})"
        elif norm_name == "sysinfo":
            resolved_info = "Display system metrics"
        elif norm_name in ("theme", "mascot", "fetch"):
            resolved_info = f"{norm_name} {' '.join(clean_args)}".strip()

        return (
            WorkflowStep(
                raw=canonical_raw,
                command=norm_name,
                args=clean_args,
                optional=is_optional,
                resolved_target=resolved_info,
                step_type="builtin",
            ),
            None,
        )

    # 6. Check websites
    if norm_name in websites:
        raw_url = websites[norm_name]
        from services.launcher_service import format_website_url, get_plain_homepage_url
        if clean_args:
            valid, formatted_or_err = format_website_url(raw_url, clean_args, site_name=norm_name)
            if not valid:
                return None, f"Website step '{cmd_text}': {formatted_or_err}"
            target_desc = f"Website: {norm_name} -> {formatted_or_err}"
        else:
            if "{query}" in raw_url:
                plain = get_plain_homepage_url(raw_url)
                target_desc = f"Website: {norm_name} ({plain})"
            else:
                target_desc = f"Website: {norm_name} ({raw_url})"

        return (
            WorkflowStep(
                raw=canonical_raw,
                command=norm_name,
                args=clean_args,
                optional=is_optional,
                resolved_target=target_desc,
                step_type="website",
            ),
            None,
        )

    # 7. Check folder shortcuts
    if norm_name in folders:
        raw_folder = folders[norm_name]
        exp_folder, _ = context.resolve_path(raw_folder)
        return (
            WorkflowStep(
                raw=canonical_raw,
                command=norm_name,
                args=clean_args,
                optional=is_optional,
                resolved_target=f"Folder: {exp_folder}",
                step_type="folder",
            ),
            None,
        )

    # 8. Check applications
    if norm_name in apps:
        app_target = apps[norm_name]
        from services.application_discovery import is_startfile_target, is_uri
        if clean_args:
            if is_uri(app_target) or is_startfile_target(app_target):
                return None, f"Application '{cmd_name}' does not accept arguments (protocol/store application)."

            from services.file_service import validate_app_path_argument
            resolved_args_desc: list[str] = []
            for a in clean_args:
                valid, resolved_p, err = validate_app_path_argument(a, context)
                if not valid:
                    # Reject CLI flags immediately
                    if a.startswith(("-", "/")):
                        return None, f"Flags like '{a}' are not permitted in workflow steps: {err}"
                    if a.lower() == "projects":
                        resolved_args_desc.append("(Folder 'projects' not found. Run: add-folder projects <path>)")
                    else:
                        resolved_args_desc.append(f"(Path not found: {a})")
                else:
                    resolved_args_desc.append(str(resolved_p))
            desc = f"App: {cmd_name} ({app_target}) -> {' '.join(resolved_args_desc)}"
        else:
            desc = f"App: {cmd_name} ({app_target})"
        return (
            WorkflowStep(
                raw=canonical_raw,
                command=norm_name,
                args=clean_args,
                optional=is_optional,
                resolved_target=desc,
                step_type="app",
            ),
            None,
        )

    # Unknown or non-allowlisted command
    return None, f"Command '{cmd_name}' is not in the workflow allowlist."


def validate_workflow(
    name: str,
    raw_data: Any,
    context: Any,
) -> tuple[WorkflowDefinition | None, list[str]]:
    """Validate a complete workflow definition.
    
    Returns:
        (WorkflowDefinition, []) if valid, or (None, [error_messages]) if invalid.
    """
    errors: list[str] = []
    if not isinstance(raw_data, dict):
        return None, [f"Workflow '{name}' definition must be a JSON object."]

    desc = str(raw_data.get("description", f"Workflow {name}")).strip()
    raw_steps = raw_data.get("steps")
    if not isinstance(raw_steps, list):
        return None, [f"Workflow '{name}' missing 'steps' list."]

    if len(raw_steps) == 0:
        return None, [f"Workflow '{name}' has no steps."]

    if len(raw_steps) > MAX_WORKFLOW_STEPS:
        return None, [
            f"Workflow '{name}' has {len(raw_steps)} steps, exceeding maximum allowed ({MAX_WORKFLOW_STEPS})."
        ]

    resolved_steps: list[WorkflowStep] = []
    for idx, raw_st in enumerate(raw_steps, start=1):
        step_obj, err = resolve_step(raw_st, context)
        if err:
            errors.append(f"Step {idx}: {err}")
        elif step_obj:
            resolved_steps.append(step_obj)

    if errors:
        return None, errors

    return (
        WorkflowDefinition(
            name=name.lower(),
            description=desc,
            steps=resolved_steps,
        ),
        [],
    )


def execute_workflow_step(step: WorkflowStep, context: Any) -> tuple[bool, str]:
    """Execute a single workflow step. Arguments are passed as lists (never through a shell).
    
    Returns:
        (success, message)
    """
    config = context.config

    try:
        if step.step_type == "website":
            websites = config.get_websites()
            raw_url = websites.get(step.command)
            if not raw_url:
                return False, f"Website shortcut '{step.command}' no longer exists in config."
            from services.launcher_service import format_website_url
            valid, target_url_or_err = format_website_url(raw_url, step.args, site_name=step.command)
            if not valid:
                return False, target_url_or_err
            ok, msg = launch_website(target_url_or_err, site_name=step.command)
            return ok, msg

        elif step.step_type == "folder":
            folders = config.get_folder_shortcuts()
            raw_folder = folders.get(step.command)
            if not raw_folder:
                return False, f"Folder shortcut '{step.command}' no longer exists in config."
            ok, msg, _ = launch_folder(raw_folder, shortcut_name=step.command)
            return ok, msg

        elif step.step_type == "app":
            apps = config.get_applications()
            target = apps.get(step.command)
            if not target:
                return False, f"Application shortcut '{step.command}' no longer exists in config."

            from services.application_discovery import is_startfile_target, is_uri
            if is_uri(target) or is_startfile_target(target):
                if step.args:
                    return False, f"Application '{step.command}' does not accept arguments (protocol/store application)."
                ok = launch_detached(target, [], app_name=step.command)
                return ok, f"Launched {step.command}" if ok else f"Failed to launch application '{step.command}'"

            # Validate each path argument
            exec_args: list[str] = []
            from services.file_service import validate_app_path_argument
            for a in step.args:
                valid, resolved_p, err = validate_app_path_argument(a, context)
                if not valid:
                    return False, err
                exec_args.append(str(resolved_p))

            ok = launch_detached(target, exec_args, app_name=step.command)
            if ok:
                return True, f"Launched {step.command}"
            return False, f"Failed to launch application '{step.command}'"

        elif step.step_type == "builtin":
            if step.command == "open":
                if not step.args:
                    return False, "'open' requires a target file."
                target, _ = context.resolve_path(step.args[0])
                if not target.exists():
                    return False, f"File not found: '{target}'"
            elif step.command == "cd":
                target_raw = step.args[0] if step.args else "~"
                target, _ = context.resolve_path(target_raw)
                if not target.exists() or not target.is_dir():
                    return False, f"Directory not found: '{target}'"

            cmd_info = context.registry.get(step.command)
            if not cmd_info:
                return False, f"Command '{step.command}' not found in registry."
            cmd_info.arg_rules.validate(step.args)
            res = cmd_info.handler(context, step.args)
            if res is not None:
                from core.executor import CommandResult
                if isinstance(res, CommandResult) and not res.ok:
                    return False, res.message or f"Command '{step.command}' failed or refused."
            return True, f"Executed '{step.command}'"

        else:
            return False, f"Unknown step type '{step.step_type}'"

    except Exception as exc:
        logger.error("Error executing step '%s': %s", step.raw, exc)
        return False, str(exc)
