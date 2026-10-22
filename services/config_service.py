"""Configuration export, import, backup, and restore service for MayuriShell."""
from __future__ import annotations

import datetime
import getpass
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
from typing import Any, Sequence

from core.aliases import is_valid_name
from core.config_manager import ConfigManager, safe_atomic_write
from core.history import contains_secret
from core.logging_config import get_logger
from core.version import VERSION
from services.application_discovery import is_startfile_target, is_uri
from services.file_service import format_bytes
from services.launcher_service import validate_web_url
from services.workflow_service import FORBIDDEN_COMMANDS, parse_raw_step, resolve_step

logger = get_logger()

SCHEMA_VERSION = 1
KIND = "mayurishell-config"
MAX_IMPORT_FILE_SIZE = 1024 * 1024  # 1 MB

KNOWN_THEMES = {"kawaii", "catppuccin", "tokyo-night", "rose-pine", "gruvbox", "plain"}
KNOWN_MASCOTS = {"cat", "bunny", "bear", "fox", "penguin", "shiba"}

WHITELIST_KEYS = {
    "theme",
    "mascot",
    "preferences",
    "aliases",
    "folder_shortcuts",
    "applications",
    "websites",
    "workflows",
    "organize_categories",
    "search_directories",
    "excluded_directories",
}

SAFE_PREFERENCES_KEYS = {
    "prompt_symbol",
    "prompt_host",
    "suggestions",
    "reactive_mascot",
    "force_plain",
    "max_suggestions",
}


def get_real_desktop_path() -> Path:
    """Resolve the true Windows Desktop directory, checking OneDrive and Registry locations."""
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            val, _ = winreg.QueryValueEx(key, "Desktop")
            winreg.CloseKey(key)
            expanded = os.path.expandvars(str(val))
            p = Path(expanded).resolve()
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass

        one_drive = os.getenv("OneDrive")
        if one_drive:
            od_desktop = Path(one_drive) / "Desktop"
            if od_desktop.exists() and od_desktop.is_dir():
                return od_desktop

    std_desktop = Path.home() / "Desktop"
    if std_desktop.exists() and std_desktop.is_dir():
        return std_desktop
    return Path.home()


def sanitize_path_for_export(path_str: str) -> str:
    """Normalize paths under the home folder to ~/ and standardize separators."""
    try:
        home_str = str(Path.home())
        home_res = str(Path.home().resolve())
        p_str = str(path_str)
        if p_str.startswith(home_res):
            return "~/" + p_str[len(home_res):].lstrip("\\/").replace("\\", "/")
        if p_str.startswith(home_str):
            return "~/" + p_str[len(home_str):].lstrip("\\/").replace("\\", "/")
    except Exception:
        pass
    return path_str


def is_safe_regular_file(path: Path) -> tuple[bool, str]:
    """Verify that a path is a regular file and NOT a symlink or junction."""
    try:
        if path.is_symlink() or os.path.islink(str(path)):
            return False, f"Path '{path}' is a symbolic link or junction. Symlinks are not permitted for security."
        if not path.exists():
            return False, f"File '{path}' does not exist."
        if not path.is_file():
            return False, f"Path '{path}' is a directory or special device, not a regular file."
        try:
            resolved = path.resolve()
            if resolved.is_symlink() or os.path.islink(str(resolved)):
                return False, f"Path '{path}' resolves to a symbolic link or junction."
        except Exception:
            pass
        return True, ""
    except Exception as exc:
        return False, f"Cannot access path '{path}': {exc}"


# ============================================================================
# EXPORT
# ============================================================================

def export_config(
    config_mgr: ConfigManager,
    target_path: Path | str | None = None,
    cwd: Path | None = None,
) -> tuple[bool, str, Path | None, dict[str, Any]]:
    """Export configuration to a sanitized JSON file.
    
    Returns:
        (success, message, destination_file_path, export_summary_dict)
    """
    summary: dict[str, Any] = {
        "included": [],
        "excluded": [
            "history.json",
            "logs/",
            "undo journal",
            "backups/",
            "username / hostname",
            "secrets / credentials",
        ],
        "machine_specific_paths": [],
        "fallback_used": False,
    }

    # Determine destination path
    dest: Path
    fallback_used = False

    if target_path:
        raw_target = Path(target_path)
        if raw_target.is_absolute():
            dest = raw_target
        else:
            base_cwd = cwd or Path.cwd()
            dest = (base_cwd / raw_target).resolve()
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        desktop_dir = get_real_desktop_path()
        # Test if Desktop is writable
        desktop_writable = False
        try:
            if desktop_dir.exists() and os.access(str(desktop_dir), os.W_OK):
                desktop_writable = True
        except Exception:
            desktop_writable = False

        if desktop_writable:
            dest = desktop_dir / f"mayurishell-config-{timestamp}.json"
        else:
            fallback_used = True
            summary["fallback_used"] = True
            dest = Path.home() / f"mayurishell-config-{timestamp}.json"

    # Destination safety checks: never overwrite an existing file, no symlinks
    if dest.exists():
        return False, f"Export destination '{dest}' already exists. Overwrite is refused.", None, summary

    try:
        if dest.is_symlink() or os.path.islink(str(dest)):
            return False, f"Export destination '{dest}' is a symbolic link or junction.", None, summary
    except Exception:
        pass

    # Ensure parent directory exists and is writable
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return False, f"Failed to create directory for '{dest}': {exc}", None, summary

    # Build sanitized payload
    data = config_mgr.data
    payload: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "app_version": VERSION,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # Whitelisted sections
    theme_val = data.get("theme") or (data.get("display", {}).get("theme") if isinstance(data.get("display"), dict) else None) or (config_mgr.get_theme_name() if hasattr(config_mgr, "get_theme_name") else None)
    if theme_val and isinstance(theme_val, str):
        payload["theme"] = theme_val
        summary["included"].append("theme")

    mascot_val = data.get("mascot") or (data.get("display", {}).get("mascot") if isinstance(data.get("display"), dict) else None) or (config_mgr.get_mascot_name() if hasattr(config_mgr, "get_mascot_name") else None)
    if mascot_val and isinstance(mascot_val, str):
        payload["mascot"] = mascot_val
        summary["included"].append("mascot")

    # Safe preferences
    if "preferences" in data and isinstance(data["preferences"], dict):
        safe_prefs: dict[str, Any] = {}
        for k, v in data["preferences"].items():
            if k in SAFE_PREFERENCES_KEYS and not contains_secret(str(v)):
                safe_prefs[k] = v
        payload["preferences"] = safe_prefs
        summary["included"].append("preferences")

    # Aliases
    if "aliases" in data and isinstance(data["aliases"], dict):
        clean_aliases: dict[str, str] = {}
        for k, v in data["aliases"].items():
            if not contains_secret(k) and not contains_secret(str(v)):
                clean_aliases[k] = str(v)
        payload["aliases"] = clean_aliases
        summary["included"].append(f"aliases ({len(clean_aliases)} items)")

    # Folder shortcuts
    if "folder_shortcuts" in data and isinstance(data["folder_shortcuts"], dict):
        clean_folders: dict[str, str] = {}
        for k, v in data["folder_shortcuts"].items():
            if not contains_secret(k) and not contains_secret(str(v)):
                norm_p = sanitize_path_for_export(str(v))
                clean_folders[k] = norm_p
                if not norm_p.startswith("~/"):
                    summary["machine_specific_paths"].append(f"folder '{k}': {norm_p}")
        payload["folder_shortcuts"] = clean_folders
        summary["included"].append(f"folder_shortcuts ({len(clean_folders)} items)")

    # Applications
    if "applications" in data and isinstance(data["applications"], dict):
        clean_apps: dict[str, str] = {}
        for k, v in data["applications"].items():
            if not contains_secret(k) and not contains_secret(str(v)):
                norm_target = sanitize_path_for_export(str(v))
                clean_apps[k] = norm_target
                if not is_uri(norm_target) and not norm_target.startswith("~/"):
                    summary["machine_specific_paths"].append(f"app '{k}': {norm_target}")
        payload["applications"] = clean_apps
        summary["included"].append(f"applications ({len(clean_apps)} items)")

    # Websites
    if "websites" in data and isinstance(data["websites"], dict):
        clean_websites: dict[str, str] = {}
        for k, v in data["websites"].items():
            if not contains_secret(k) and not contains_secret(str(v)):
                clean_websites[k] = str(v)
        payload["websites"] = clean_websites
        summary["included"].append(f"websites ({len(clean_websites)} items)")

    # Workflows
    if "workflows" in data and isinstance(data["workflows"], dict):
        clean_wfs: dict[str, Any] = {}
        for k, v in data["workflows"].items():
            if not contains_secret(k):
                clean_wfs[k] = v
        payload["workflows"] = clean_wfs
        summary["included"].append(f"workflows ({len(clean_wfs)} items)")

    # Organize categories
    if "organize_categories" in data and isinstance(data["organize_categories"], dict):
        payload["organize_categories"] = data["organize_categories"]
        summary["included"].append("organize_categories")

    # Search & excluded directories
    if "search_directories" in data and isinstance(data["search_directories"], list):
        clean_search = [sanitize_path_for_export(str(d)) for d in data["search_directories"] if not contains_secret(str(d))]
        payload["search_directories"] = clean_search
        summary["included"].append(f"search_directories ({len(clean_search)} items)")

    if "excluded_directories" in data and isinstance(data["excluded_directories"], list):
        clean_excl = [str(d) for d in data["excluded_directories"] if not contains_secret(str(d))]
        payload["excluded_directories"] = clean_excl
        summary["included"].append(f"excluded_directories ({len(clean_excl)} items)")

    # Write out JSON atomically
    try:
        temp_fd, temp_path = tempfile.mkstemp(dir=str(dest.parent), prefix="export_", suffix=".tmp")
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, str(dest))
    except Exception as exc:
        if "temp_path" in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False, f"Failed to write export file: {exc}", None, summary

    msg = f"Configuration exported successfully to: {dest}"
    if fallback_used:
        msg += " (Desktop was unwritable; saved to home directory)."
    return True, msg, dest, summary


# ============================================================================
# IMPORT & PREVIEW
# ============================================================================

def load_and_validate_import_file(file_path: Path | str) -> tuple[bool, str, dict[str, Any] | None, list[str]]:
    """Load JSON import file, enforce <= 1 MB, kind, schema_version, and return warnings for unknown keys."""
    raw_p = Path(file_path)
    is_safe, err = is_safe_regular_file(raw_p)
    if not is_safe:
        return False, err, None, []
    p = raw_p.resolve()

    # Check size limit
    try:
        size = p.stat().st_size
        if size > MAX_IMPORT_FILE_SIZE:
            return False, f"File size ({format_bytes(size)}) exceeds maximum allowed import limit of 1 MB.", None, []
    except Exception as exc:
        return False, f"Cannot inspect file size: {exc}", None, []

    # Parse JSON
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as exc:
        return False, f"Failed to parse JSON configuration file: {exc}", None, []

    if not isinstance(raw_data, dict):
        return False, "Invalid format: Root JSON element must be an object.", None, []

    # Validate kind
    kind = raw_data.get("kind")
    if kind != KIND:
        return False, f"Invalid file kind '{kind}'. Expected '{KIND}'.", None, []

    # Validate schema version
    schema_v = raw_data.get("schema_version")
    if not isinstance(schema_v, int):
        return False, "Missing or invalid 'schema_version' in configuration file.", None, []

    if schema_v > SCHEMA_VERSION:
        return (
            False,
            f"Configuration file uses schema version {schema_v}, which is newer than supported version {SCHEMA_VERSION}. Please upgrade MayuriShell.",
            None,
            [],
        )

    # Unknown top-level keys
    known_keys = WHITELIST_KEYS | {"kind", "schema_version", "app_version", "exported_at"}
    warnings: list[str] = []
    for k in raw_data.keys():
        if k not in known_keys:
            warnings.append(f"Unknown top-level key '{k}' will be ignored.")

    return True, "", raw_data, warnings


def build_import_preview(
    config_mgr: ConfigManager,
    imported_data: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Inspect and categorize every item into ADDED, UNCHANGED, CONFLICTING, or SKIPPED."""
    current_data = config_mgr.data
    preview: dict[str, Any] = {
        "added": [],
        "unchanged": [],
        "conflicting": [],
        "skipped": [],
        "app_shortcuts": [],
        "workflow_steps_detail": [],
        "missing_paths": [],
    }

    reg = getattr(context, "registry", None)

    # 1. Theme
    if "theme" in imported_data:
        val = str(imported_data["theme"]).strip().lower()
        if val not in KNOWN_THEMES:
            preview["skipped"].append(("Theme", val, f"Invalid theme name '{val}'. Must be one of: {', '.join(sorted(KNOWN_THEMES))}"))
        else:
            curr_val = current_data.get("theme") or (current_data.get("display", {}).get("theme") if isinstance(current_data.get("display"), dict) else None)
            if curr_val == val:
                preview["unchanged"].append(("Theme", "theme", val))
            elif curr_val is None:
                preview["added"].append(("Theme", "theme", val))
            else:
                preview["conflicting"].append(("Theme", "theme", f"Current: {curr_val} -> Import: {val}"))

    # 2. Mascot
    if "mascot" in imported_data:
        val = str(imported_data["mascot"]).strip().lower()
        if val not in KNOWN_MASCOTS:
            preview["skipped"].append(("Mascot", val, f"Invalid mascot name '{val}'. Must be one of: {', '.join(sorted(KNOWN_MASCOTS))}"))
        else:
            curr_val = current_data.get("mascot") or (current_data.get("display", {}).get("mascot") if isinstance(current_data.get("display"), dict) else None)
            if curr_val == val:
                preview["unchanged"].append(("Mascot", "mascot", val))
            elif curr_val is None:
                preview["added"].append(("Mascot", "mascot", val))
            else:
                preview["conflicting"].append(("Mascot", "mascot", f"Current: {curr_val} -> Import: {val}"))

    # 3. Preferences
    if "preferences" in imported_data and isinstance(imported_data["preferences"], dict):
        curr_prefs = current_data.get("preferences", {})
        for pk, pv in imported_data["preferences"].items():
            if pk not in SAFE_PREFERENCES_KEYS:
                preview["skipped"].append(("Preference", pk, "Unknown or non-whitelisted preference key."))
                continue
            if contains_secret(str(pv)):
                preview["skipped"].append(("Preference", pk, "Contains secret-like content."))
                continue

            curr_v = curr_prefs.get(pk)
            if curr_v == pv:
                preview["unchanged"].append(("Preference", pk, str(pv)))
            elif curr_v is None:
                preview["added"].append(("Preference", pk, str(pv)))
            else:
                preview["conflicting"].append(("Preference", pk, f"Current: {curr_v} -> Import: {pv}"))

    # Helper for collision with built-in commands
    def check_builtin_collision(name: str) -> str | None:
        if reg and reg.has_command(name):
            cmd = reg.get(name)
            if cmd and cmd.category != "Aliases":
                return f"Cannot use '{name}': conflicts with built-in command '{cmd.name}'."
        return None

    # 4. Folder shortcuts
    if "folder_shortcuts" in imported_data and isinstance(imported_data["folder_shortcuts"], dict):
        curr_folders = current_data.get("folder_shortcuts", {})
        for name, raw_path in imported_data["folder_shortcuts"].items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                preview["skipped"].append(("Folder Shortcut", clean_name, "Invalid name (alphanumeric and hyphens only)."))
                continue
            coll = check_builtin_collision(clean_name)
            if coll:
                preview["skipped"].append(("Folder Shortcut", clean_name, coll))
                continue

            # Expand ~ and env vars
            expanded_path = os.path.expanduser(os.path.expandvars(str(raw_path)))
            resolved_p = Path(expanded_path).resolve()
            if not resolved_p.exists() or not resolved_p.is_dir():
                msg = f"Target directory '{expanded_path}' missing on this PC. Skipped (use 'add-folder {clean_name} <path>' to add later)."
                preview["skipped"].append(("Folder Shortcut", clean_name, msg))
                preview["missing_paths"].append(f"Folder shortcut '{clean_name}': {expanded_path}")
                continue

            curr_val = curr_folders.get(clean_name)
            if curr_val == str(raw_path):
                preview["unchanged"].append(("Folder Shortcut", clean_name, str(raw_path)))
            elif curr_val is None:
                preview["added"].append(("Folder Shortcut", clean_name, str(raw_path)))
            else:
                preview["conflicting"].append(("Folder Shortcut", clean_name, f"Current: {curr_val} -> Import: {raw_path}"))

    # 5. Application shortcuts
    if "applications" in imported_data and isinstance(imported_data["applications"], dict):
        curr_apps = current_data.get("applications", {})
        for name, raw_target in imported_data["applications"].items():
            clean_name = str(name).strip().lower()
            target_str = str(raw_target).strip()

            if not is_valid_name(clean_name):
                preview["skipped"].append(("Application", clean_name, "Invalid name (alphanumeric and hyphens only)."))
                continue
            coll = check_builtin_collision(clean_name)
            if coll:
                preview["skipped"].append(("Application", clean_name, coll))
                continue

            # Verify target exists or is URI
            if is_uri(target_str):
                target_valid = True
            else:
                expanded_target = os.path.expanduser(os.path.expandvars(target_str))
                target_path = Path(expanded_target)
                if target_path.is_file() or shutil.which(target_str) or shutil.which(f"{target_str}.exe"):
                    target_valid = True
                else:
                    target_valid = False

            if not target_valid:
                msg = f"Target '{target_str}' missing on this PC. Skipped (use 'add-app {clean_name} <path>' to add later)."
                preview["skipped"].append(("Application", clean_name, msg))
                preview["missing_paths"].append(f"App target '{clean_name}': {target_str}")
                continue

            preview["app_shortcuts"].append((clean_name, target_str))

            curr_val = curr_apps.get(clean_name)
            if curr_val == target_str:
                preview["unchanged"].append(("Application", clean_name, target_str))
            elif curr_val is None:
                preview["added"].append(("Application", clean_name, target_str))
            else:
                preview["conflicting"].append(("Application", clean_name, f"Current: {curr_val} -> Import: {target_str}"))

    # 6. Website shortcuts
    if "websites" in imported_data and isinstance(imported_data["websites"], dict):
        curr_web = current_data.get("websites", {})
        for name, raw_url in imported_data["websites"].items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                preview["skipped"].append(("Website", clean_name, "Invalid name (alphanumeric and hyphens only)."))
                continue
            coll = check_builtin_collision(clean_name)
            if coll:
                preview["skipped"].append(("Website", clean_name, coll))
                continue

            valid_url, norm_or_err = validate_web_url(str(raw_url))
            if not valid_url:
                preview["skipped"].append(("Website", clean_name, f"Invalid URL: {norm_or_err}"))
                continue

            curr_val = curr_web.get(clean_name)
            if curr_val == norm_or_err:
                preview["unchanged"].append(("Website", clean_name, norm_or_err))
            elif curr_val is None:
                preview["added"].append(("Website", clean_name, norm_or_err))
            else:
                preview["conflicting"].append(("Website", clean_name, f"Current: {curr_val} -> Import: {norm_or_err}"))

    # 7. Aliases
    if "aliases" in imported_data and isinstance(imported_data["aliases"], dict):
        curr_aliases = current_data.get("aliases", {})
        for name, target_cmd in imported_data["aliases"].items():
            clean_name = str(name).strip().lower()
            target_str = str(target_cmd).strip()

            if not is_valid_name(clean_name):
                preview["skipped"].append(("Alias", clean_name, "Invalid name (alphanumeric and hyphens only)."))
                continue
            coll = check_builtin_collision(clean_name)
            if coll:
                preview["skipped"].append(("Alias", clean_name, coll))
                continue

            curr_val = curr_aliases.get(clean_name)
            if curr_val == target_str:
                preview["unchanged"].append(("Alias", clean_name, target_str))
            elif curr_val is None:
                preview["added"].append(("Alias", clean_name, target_str))
            else:
                preview["conflicting"].append(("Alias", clean_name, f"Current: {curr_val} -> Import: {target_str}"))

    # 8. Workflows
    if "workflows" in imported_data and isinstance(imported_data["workflows"], dict):
        curr_wfs = current_data.get("workflows", {})
        for name, wf_obj in imported_data["workflows"].items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                preview["skipped"].append(("Workflow", clean_name, "Invalid workflow name."))
                continue
            coll = check_builtin_collision(clean_name)
            if coll:
                preview["skipped"].append(("Workflow", clean_name, coll))
                continue

            if not isinstance(wf_obj, dict):
                preview["skipped"].append(("Workflow", clean_name, "Workflow definition must be an object."))
                continue

            steps = wf_obj.get("steps", [])
            if not isinstance(steps, list) or not steps:
                preview["skipped"].append(("Workflow", clean_name, "Workflow has no steps."))
                continue

            # Validate workflow steps and resolve their targets
            steps_valid = True
            resolved_step_details: list[dict[str, Any]] = []

            from urllib.parse import quote_plus

            for raw_step in steps:
                step_text, is_opt = parse_raw_step(raw_step)
                parts = step_text.split()
                cmd_first = parts[0].lower() if parts else ""
                step_args = parts[1:] if len(parts) > 1 else []

                if cmd_first in FORBIDDEN_COMMANDS:
                    preview["skipped"].append(("Workflow", clean_name, f"Step '{step_text}' contains forbidden command '{cmd_first}'."))
                    steps_valid = False
                    break

                curr_folders = current_data.get("folder_shortcuts", {})
                curr_websites = current_data.get("websites", {})
                curr_apps = current_data.get("applications", {})

                imp_folders = imported_data.get("folder_shortcuts", {})
                imp_websites = imported_data.get("websites", {})
                imp_apps = imported_data.get("applications", {})

                target_desc = "builtin"
                exists_on_pc = True
                shortcut_on_pc = True

                # Check if shortcut exists on this PC (in current config)
                is_on_this_pc = (
                    cmd_first in curr_folders
                    or cmd_first in curr_websites
                    or cmd_first in curr_apps
                    or (reg and reg.has_command(cmd_first))
                )

                if not is_on_this_pc:
                    # Check if at least in imported shortcuts
                    is_in_imported = (
                        cmd_first in imp_folders
                        or cmd_first in imp_websites
                        or cmd_first in imp_apps
                    )
                    if not is_in_imported:
                        shortcut_on_pc = False
                        exists_on_pc = False
                        target_desc = f"Unrecognized shortcut or command '{cmd_first}'"

                if cmd_first in curr_folders or cmd_first in imp_folders:
                    f_target = curr_folders.get(cmd_first) or imp_folders.get(cmd_first)
                    exp = Path(os.path.expanduser(os.path.expandvars(str(f_target)))).resolve()
                    target_desc = f"Folder -> {exp}"
                    if not exp.exists():
                        exists_on_pc = False
                elif cmd_first in curr_websites or cmd_first in imp_websites:
                    w_target = str(curr_websites.get(cmd_first) or imp_websites.get(cmd_first))
                    if "{query}" in w_target and step_args:
                        final_url = w_target.replace("{query}", quote_plus(" ".join(step_args)))
                    elif "{query}" in w_target:
                        final_url = w_target.replace("{query}", "")
                    else:
                        final_url = w_target
                    target_desc = f"Website -> {final_url}"
                elif cmd_first in curr_apps or cmd_first in imp_apps:
                    a_target = str(curr_apps.get(cmd_first) or imp_apps.get(cmd_first))
                    target_desc = f"Application -> {a_target}"
                    if not is_uri(a_target):
                        exp = Path(os.path.expanduser(os.path.expandvars(a_target)))
                        if not exp.is_file() and not shutil.which(a_target):
                            exists_on_pc = False
                elif reg and reg.has_command(cmd_first):
                    target_desc = f"Built-in -> {cmd_first}"

                resolved_step_details.append({
                    "step": raw_step,
                    "target": target_desc,
                    "exists_on_pc": exists_on_pc,
                    "shortcut_on_pc": shortcut_on_pc,
                })

            if not steps_valid:
                continue

            preview["workflow_steps_detail"].append((clean_name, resolved_step_details))

            curr_val = curr_wfs.get(clean_name)
            if curr_val == wf_obj:
                preview["unchanged"].append(("Workflow", clean_name, f"{len(steps)} steps"))
            elif curr_val is None:
                preview["added"].append(("Workflow", clean_name, f"{len(steps)} steps"))
            else:
                preview["conflicting"].append(("Workflow", clean_name, f"Steps changed ({len(curr_val.get('steps', []))} -> {len(steps)})"))

    return preview


def apply_imported_config(
    config_mgr: ConfigManager,
    imported_data: dict[str, Any],
    preview: dict[str, Any],
    overwrite: bool = False,
    include_apps: bool = False,
    context: Any = None,
) -> tuple[bool, str]:
    """Atomically apply validated items to config.json with a pre-import backup."""
    # 1. Create automatic backup of current configuration
    success_bkp, msg_bkp, _ = backup_config(config_mgr)
    if not success_bkp:
        return False, f"Pre-import backup failed: {msg_bkp}. Aborting import for safety."

    # 2. Prepare new configuration dict by merging
    new_data = dict(config_mgr.data)

    # Theme & Mascot
    conflicting_keys = {item[1] for item in preview["conflicting"]}

    if "Theme" not in [item[0] for item in preview["skipped"]]:
        if "theme" in imported_data:
            if "theme" not in conflicting_keys or overwrite:
                new_data["theme"] = imported_data["theme"]
                if "display" in new_data and isinstance(new_data["display"], dict):
                    new_data["display"]["theme"] = imported_data["theme"]

    if "Mascot" not in [item[0] for item in preview["skipped"]]:
        if "mascot" in imported_data:
            if "mascot" not in conflicting_keys or overwrite:
                new_data["mascot"] = imported_data["mascot"]
                if "display" in new_data and isinstance(new_data["display"], dict):
                    new_data["display"]["mascot"] = imported_data["mascot"]

    # Preferences
    if "preferences" in imported_data and isinstance(imported_data["preferences"], dict):
        new_prefs = dict(new_data.get("preferences", {}))
        for pk, pv in imported_data["preferences"].items():
            if pk in SAFE_PREFERENCES_KEYS and (pk not in conflicting_keys or overwrite):
                new_prefs[pk] = pv
        new_data["preferences"] = new_prefs

    # Helper for merging sections
    def merge_section(section_name: str, items_dict: dict[str, Any]):
        curr = dict(new_data.get(section_name, {}))
        for name, val in items_dict.items():
            clean_name = name.strip().lower()
            # If skipped, ignore
            if any(item[0] == section_name.capitalize() and item[1] == clean_name for item in preview["skipped"]):
                continue
            is_conflicting = any(item[1] == clean_name for item in preview["conflicting"])
            if not is_conflicting or overwrite:
                curr[clean_name] = val
        new_data[section_name] = curr

    # Folder shortcuts
    if "folder_shortcuts" in imported_data and isinstance(imported_data["folder_shortcuts"], dict):
        merge_section("folder_shortcuts", imported_data["folder_shortcuts"])

    # Applications (only if separate app confirmation was approved)
    if include_apps and "applications" in imported_data and isinstance(imported_data["applications"], dict):
        merge_section("applications", imported_data["applications"])

    # Websites
    if "websites" in imported_data and isinstance(imported_data["websites"], dict):
        merge_section("websites", imported_data["websites"])

    # Aliases
    if "aliases" in imported_data and isinstance(imported_data["aliases"], dict):
        merge_section("aliases", imported_data["aliases"])

    # Workflows
    if "workflows" in imported_data and isinstance(imported_data["workflows"], dict):
        merge_section("workflows", imported_data["workflows"])

    # 3. Apply atomically to config.json (temp file in same folder, flush, replace)
    config_file = config_mgr.config_path
    temp_dir = config_file.parent
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path_str = tempfile.mkstemp(dir=str(temp_dir), prefix="cfg_import_", suffix=".tmp")
        temp_p = Path(temp_path_str)
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(str(temp_p), str(config_file))
    except Exception as exc:
        if "temp_p" in locals() and temp_p.exists():
            try:
                temp_p.unlink()
            except Exception:
                pass
        return False, f"Failed to apply configuration atomically: {exc}. Original config is untouched."

    # 4. Reload in-memory config
    config_mgr.load()
    if hasattr(config_mgr, "shortcuts_version"):
        config_mgr.shortcuts_version += 1

    return True, "Configuration successfully imported and updated."


# ============================================================================
# BACKUP & RESTORE
# ============================================================================

def backup_config(config_mgr: ConfigManager) -> tuple[bool, str, Path | None]:
    """Create a timestamped copy of config.json in backups/.
    
    Returns:
        (success, message_or_warning, backup_path)
    """
    if not config_mgr.config_path.exists():
        return False, "Configuration file does not exist to back up.", None

    backups_dir = config_mgr.backups_dir
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return False, f"Failed to create backups directory: {exc}", None

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    counter = 1
    target_name = f"config-backup-{timestamp}.json"
    backup_file = backups_dir / target_name
    while backup_file.exists():
        target_name = f"config-backup-{timestamp}_{counter}.json"
        backup_file = backups_dir / target_name
        counter += 1

    # Atomic copy via temp file
    try:
        temp_fd, temp_path_str = tempfile.mkstemp(dir=str(backups_dir), prefix="bkp_", suffix=".tmp")
        temp_p = Path(temp_path_str)
        with open(config_mgr.config_path, "r", encoding="utf-8") as src, os.fdopen(temp_fd, "w", encoding="utf-8") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())

        os.replace(str(temp_p), str(backup_file))
    except Exception as exc:
        if "temp_p" in locals() and temp_p.exists():
            try:
                temp_p.unlink()
            except Exception:
                pass
        return False, f"Failed to create backup: {exc}", None

    # Check count of existing backups
    warning = ""
    try:
        existing_backups = [p for p in backups_dir.glob("*.json") if p.is_file()]
        if len(existing_backups) > 50:
            warning = f" (Warning: {len(existing_backups)} backups exist in backups/. Consider removing older files.)"
    except Exception:
        pass

    return True, f"Backup created successfully: {backup_file.name}{warning}", backup_file


def list_backups(config_mgr: ConfigManager) -> list[dict[str, Any]]:
    """Return all valid backup files in backups/, newest first."""
    backups_dir = config_mgr.backups_dir
    if not backups_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    try:
        for p in backups_dir.glob("*.json"):
            if p.is_file() and not p.is_symlink() and not os.path.islink(str(p)):
                st = p.stat()
                results.append({
                    "name": p.name,
                    "path": p,
                    "size": st.st_size,
                    "size_str": format_bytes(st.st_size),
                    "mtime": st.st_mtime,
                    "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
    except Exception as exc:
        logger.warning("Failed to list backups: %s", exc)

    # Sort newest first
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def validate_backup_data(backup_data: Any) -> tuple[bool, str]:
    """Validate that backup configuration data has valid types and structures.
    
    Ensures backup is not corrupted and uses the same validators as import
    (valid shortcut names, valid URLs, forbidden workflow commands, etc.).
    """
    if not isinstance(backup_data, dict):
        return False, "Root JSON element must be an object."

    # Validate theme / mascot / display
    if "theme" in backup_data and not isinstance(backup_data["theme"], str):
        return False, "Invalid 'theme' property in backup (must be a string)."
    if "mascot" in backup_data and not isinstance(backup_data["mascot"], str):
        return False, "Invalid 'mascot' property in backup (must be a string)."
    if "display" in backup_data and not isinstance(backup_data["display"], dict):
        return False, "Invalid 'display' section in backup (must be an object)."

    # Validate preferences
    if "preferences" in backup_data and not isinstance(backup_data["preferences"], dict):
        return False, "Invalid 'preferences' section in backup (must be an object)."

    # Validate applications
    if "applications" in backup_data:
        apps = backup_data["applications"]
        if not isinstance(apps, dict):
            return False, "Invalid 'applications' section in backup (must be an object)."
        for name, target in apps.items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                return False, f"Invalid application name in backup: '{name}'"
            if not isinstance(target, str):
                return False, f"Invalid application target for '{name}' in backup (must be a string)."

    # Validate websites
    if "websites" in backup_data:
        websites = backup_data["websites"]
        if not isinstance(websites, dict):
            return False, "Invalid 'websites' section in backup (must be an object)."
        for name, url_template in websites.items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                return False, f"Invalid website name in backup: '{name}'"
            if not isinstance(url_template, str):
                return False, f"Invalid website URL for '{name}' in backup (must be a string)."
            valid_url, err = validate_web_url(str(url_template))
            if not valid_url:
                return False, f"Invalid website URL template for '{name}' in backup: {err}"

    # Validate folder_shortcuts
    if "folder_shortcuts" in backup_data:
        folders = backup_data["folder_shortcuts"]
        if not isinstance(folders, dict):
            return False, "Invalid 'folder_shortcuts' section in backup (must be an object)."
        for name, fpath in folders.items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                return False, f"Invalid folder shortcut name in backup: '{name}'"
            if not isinstance(fpath, str):
                return False, f"Invalid folder path for '{name}' in backup (must be a string)."

    # Validate aliases
    if "aliases" in backup_data:
        aliases = backup_data["aliases"]
        if not isinstance(aliases, dict):
            return False, "Invalid 'aliases' section in backup (must be an object)."
        for name, target in aliases.items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                return False, f"Invalid alias name in backup: '{name}'"
            if not isinstance(target, str):
                return False, f"Invalid alias target for '{name}' in backup (must be a string)."

    # Validate workflows
    if "workflows" in backup_data:
        workflows = backup_data["workflows"]
        if not isinstance(workflows, dict):
            return False, "Invalid 'workflows' section in backup (must be an object)."
        for name, wf in workflows.items():
            clean_name = str(name).strip().lower()
            if not is_valid_name(clean_name):
                return False, f"Invalid workflow name in backup: '{name}'"
            if not isinstance(wf, dict):
                return False, f"Invalid workflow definition for '{name}' (must be an object)."
            steps = wf.get("steps", [])
            if not isinstance(steps, list):
                return False, f"Invalid steps in workflow '{name}' (must be a list)."
            for s in steps:
                step_text, _ = parse_raw_step(s)
                parts = step_text.split()
                if parts and parts[0].lower() in FORBIDDEN_COMMANDS:
                    return False, f"Workflow '{name}' contains forbidden command '{parts[0]}'."

    return True, ""


def restore_config(
    config_mgr: ConfigManager,
    backup_name: str,
    context: Any = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Validate a backup file and restore it atomically after creating a pre-restore backup.
    
    The backup name must be a plain file name inside backups/.
    """
    clean_name = backup_name.strip()
    if not clean_name:
        return False, "Please specify a backup file name to restore.", None

    # Refuse path separators or traversal
    if "/" in clean_name or "\\" in clean_name or ".." in clean_name:
        return False, "Backup name must be a plain file name inside backups/ without directory separators.", None

    unresolved_target_file = config_mgr.backups_dir / clean_name
    is_safe, err = is_safe_regular_file(unresolved_target_file)
    if not is_safe:
        return False, f"Invalid backup file: {err}", None

    target_file = unresolved_target_file.resolve()
    if target_file.parent != config_mgr.backups_dir.resolve():
        return False, "Backup file must reside directly in backups/ directory.", None

    # Check size limit (<= 1MB)
    try:
        size = target_file.stat().st_size
        if size > MAX_IMPORT_FILE_SIZE:
            return False, f"Backup file size ({format_bytes(size)}) exceeds maximum allowed limit of 1 MB.", None
    except Exception as exc:
        return False, f"Cannot inspect backup file size: {exc}", None

    # Validate backup JSON structure BEFORE touching current config
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
    except Exception as exc:
        return False, f"Backup file is corrupted and cannot be parsed as JSON: {exc}. Restore refused.", None

    valid_structure, struct_err = validate_backup_data(backup_data)
    if not valid_structure:
        return False, f"Backup file is corrupt: {struct_err}. Restore refused.", None

    # Create pre-restore backup of the current configuration (strictly after validation succeeded)
    success_pre, msg_pre, _ = backup_config(config_mgr)
    if not success_pre:
        return False, f"Failed to back up current configuration prior to restore: {msg_pre}. Restore aborted.", None

    # Apply backup atomically
    config_file = config_mgr.config_path
    temp_dir = config_file.parent
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path_str = tempfile.mkstemp(dir=str(temp_dir), prefix="cfg_restore_", suffix=".tmp")
        temp_p = Path(temp_path_str)
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(str(temp_p), str(config_file))
    except Exception as exc:
        if "temp_p" in locals() and temp_p.exists():
            try:
                temp_p.unlink()
            except Exception:
                pass
        return False, f"Failed to restore configuration file: {exc}. Original config is untouched.", None

    # Reload in-memory config
    config_mgr.load()
    if hasattr(config_mgr, "shortcuts_version"):
        config_mgr.shortcuts_version += 1

    return True, f"Successfully restored configuration from backup '{clean_name}'.", backup_data
