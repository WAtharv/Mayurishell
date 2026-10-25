"""Smart command and argument suggestion engine for MayuriShell.

Logic-only module (no printing). Handles candidate collection, difflib and prefix
ranking, argument typos, safe prefill evaluation, directory hints, and app detection.
"""
from __future__ import annotations

import difflib
import os
from pathlib import Path
import re
import shutil
from typing import Any, Sequence

from core.history import contains_secret

# Commands considered destructive that must never be prefilled, and whose
# suggestions must hide user arguments and show usage only.
DESTRUCTIVE_COMMANDS = {
    "delete",
    "move",
    "rename",
    "copy",
    "process",
    "organize",
    "workflow",
    "alias",
    "config",
    "undo",
}


# Commands on the harmless allowlist that are safe to prefill on single confident match
PREFILL_ALLOWLIST = {
    "apps",
    "websites",
    "pwd",
    "ls",
    "cd",
    "help",
    "theme",
    "mascot",
    "fetch",
}

# Known applications to check for PATH suggestions
KNOWN_EXTERNAL_APPS = ("python", "git", "node", "chrome")

# Session-level cache for shutil.which lookups
_WHICH_CACHE: dict[str, str | None] = {}

# Subcommand and option mappings shared with completer
COMMAND_ARGUMENTS: dict[str, dict[str, Any]] = {
    "process": {
        "subcommands": ["find", "info", "kill", "list"],
        "options": ["--force", "-f"],
    },
    "processes": {
        "options": ["--sort", "--limit", "-s", "-l", "-n"],
        "values": {
            "--sort": ["cpu", "memory", "name"],
            "-s": ["cpu", "memory", "name"],
        },
    },
    "theme": {
        "subcommands": [
            "preview",
            "kawaii",
            "catppuccin",
            "tokyo-night",
            "rose-pine",
            "gruvbox",
            "plain",
        ],
    },
    "mascot": {
        "subcommands": [
            "random",
            "cat",
            "bunny",
            "bear",
            "fox",
            "penguin",
            "shiba",
        ],
    },
    "organize": {
        "subcommands": ["undo"],
        "options": ["--dry-run", "--include-other"],
    },
    "workflow": {
        "subcommands": ["list", "show", "run", "add", "remove", "validate"],
        "options": ["--dry-run"],
    },
    "history": {
        "subcommands": ["clear"],
    },
    "diagnostics": {
        "options": ["--export"],
    },
    "suggestions": {
        "subcommands": ["on", "off"],
    },
    "config": {
        "subcommands": ["export", "import", "backup", "restore"],
        "options": ["--dry-run", "--overwrite"],
    },
    "doctor": {
        "subcommands": ["apps", "python", "config", "all"],
    },
    "create-project": {
        "options": ["--template", "--here", "-t"],
        "values": {
            "--template": [
                "python-basic",
                "python-package",
                "web-landing",
                "web-app",
                "markdown-docs",
                "empty",
            ],
            "-t": [
                "python-basic",
                "python-package",
                "web-landing",
                "web-app",
                "markdown-docs",
                "empty",
            ],
        },
    },
    "project": {
        "subcommands": ["info", "tree", "doctor", "env"],
        "options": ["--depth", "--all"],
    },
    "git": {
        "subcommands": ["status", "log", "diff", "branches", "summary"],
        "options": ["-n", "--staged"],
    },
    "prompt": {
        "subcommands": ["git"],
        "values": {
            "git": ["on", "off"],
        },
    },
    "undo": {
        "subcommands": ["list", "last"],
        "options": ["--all"],
    },
    "profile": {
        "subcommands": ["list", "show", "new", "edit", "remove"],
        "options": ["--dry-run", "-n"],
    },
}



def cached_which(cmd_name: str) -> str | None:
    """Return the resolved path for an executable on PATH, cached for the session."""
    key = cmd_name.strip().lower()
    if key in _WHICH_CACHE:
        return _WHICH_CACHE[key]
    resolved = shutil.which(key)
    _WHICH_CACHE[key] = resolved
    return resolved


def is_secret_like(text: str, candidates: Sequence[str] | None = None) -> bool:
    """Return True if text matches the secret filter or looks like a token with no match."""
    stripped = text.strip()
    if not stripped:
        return False
    if contains_secret(stripped):
        return True

    # Check for long token-like strings (e.g. >= 20 characters with no whitespace)
    # Tokens typically contain digits/hex/base64 or token prefixes (ghp_, sk-, eyJ, etc.)
    # Normal command names (even long ones with letters, hyphens, underscores) are not tokens.
    if len(stripped) >= 20 and not any(ch.isspace() for ch in stripped):
        token_prefixes = ("ghp_", "gho_", "github_pat_", "sk-", "sk_", "xox", "eyJh", "ya29.")
        has_token_prefix = any(stripped.startswith(p) for p in token_prefixes)
        has_digits_and_letters = any(ch.isdigit() for ch in stripped) and any(ch.isalpha() for ch in stripped)
        has_token_casing = (
            len(stripped) >= 24
            and any(ch.isupper() for ch in stripped)
            and any(ch.islower() for ch in stripped)
            and not any(ch in "_-" for ch in stripped)
        )
        if has_token_prefix or has_digits_and_letters or has_token_casing:
            if candidates:
                ratios = [
                    difflib.SequenceMatcher(None, stripped.lower(), c.lower()).ratio()
                    for c in candidates
                ]
                if max(ratios, default=0.0) < 0.45:
                    return True
            else:
                return True

    return False


SYNONYM_MAPPINGS: dict[str, list[str]] = {
    "search": ["find", "apps"],
    "directory": ["folders", "cd", "pwd"],
    "dir": ["ls"],
    "remove": ["delete", "unalias"],
    "launch": ["apps"],
    "run": ["apps", "workflow"],
}


class SuggestionEngine:
    """Calculates ranked suggestions for typos, arguments, and context."""

    def __init__(self) -> None:
        self._cached_candidates: list[str] = []
        self._last_version: int = -1

    def get_candidates(self, context: Any) -> list[str]:
        """Collect all registered commands, aliases, and shortcuts (cached)."""
        current_version = getattr(context.config, "shortcuts_version", 0)
        if self._last_version == current_version and self._cached_candidates:
            return list(self._cached_candidates)

        candidates: set[str] = set()

        # 1. Registered commands
        if hasattr(context, "registry") and context.registry:
            for cmd in context.registry.list_commands():
                candidates.add(cmd.name.lower())

        # 2. Config shortcuts
        if hasattr(context, "config") and context.config:
            for name in context.config.get_applications():
                candidates.add(name.lower())
            for name in context.config.get_websites():
                candidates.add(name.lower())
            for name in context.config.get_folder_shortcuts():
                candidates.add(name.lower())
            for name in context.config.get_aliases():
                candidates.add(name.lower())

        self._cached_candidates = sorted(candidates)
        self._last_version = current_version
        return list(self._cached_candidates)

    def rank_candidates(
        self,
        word: str,
        candidates: Sequence[str],
        cutoff: float = 0.55,
        max_results: int = 3,
    ) -> list[str]:
        """Rank candidates using exact prefix matches and difflib similarity."""
        clean = word.strip().lower()
        if len(clean) < 2:
            return []

        scored: list[tuple[float, int, str]] = []

        # Check synonyms (e.g. search -> find, dir -> ls)
        synonyms = SYNONYM_MAPPINGS.get(clean, [])
        for syn in synonyms:
            if syn in candidates:
                scored.append((0.92, len(syn), syn))

        for cand in candidates:
            cand_lower = cand.lower()
            if cand_lower == clean:
                scored.append((1.0, len(cand), cand))
                continue

            # Prefix match gives high boost
            if cand_lower.startswith(clean):
                score = 0.85 + (len(clean) / max(len(cand_lower), 1)) * 0.14
                scored.append((score, len(cand), cand))
                continue

            # Substring match
            if clean in cand_lower:
                score = 0.70 + (len(clean) / max(len(cand_lower), 1)) * 0.1
                scored.append((score, len(cand), cand))
                continue

            # Difflib similarity
            ratio = difflib.SequenceMatcher(None, clean, cand_lower).ratio()
            if ratio >= cutoff:
                scored.append((ratio, len(cand), cand))

        # Sort by score descending, then shorter length, then alphabetical
        scored.sort(key=lambda x: (-x[0], x[1], x[2]))

        results: list[str] = []
        for _, _, cand in scored:
            if cand not in results:
                results.append(cand)
            if len(results) >= max_results:
                break

        return results


# Module-level default engine instance
_ENGINE = SuggestionEngine()


def suggest_command_corrections(
    typed_name: str,
    args: list[str],
    context: Any,
) -> list[str]:
    """Suggest top command line corrections for an unknown command name."""
    if not hasattr(context, "config"):
        return []

    # Check if suggestions are enabled
    if not context.config.get_suggestions_enabled():
        return []

    max_suggestions = context.config.get_max_suggestions()
    candidates = _ENGINE.get_candidates(context)

    # Secret check
    if is_secret_like(typed_name, candidates):
        return []

    ranked = _ENGINE.rank_candidates(
        typed_name,
        candidates,
        cutoff=0.55,
        max_results=max_suggestions,
    )

    if not ranked:
        return []

    # If the closest match is a destructive command, show only that command without arguments
    if ranked[0] in DESTRUCTIVE_COMMANDS:
        return [ranked[0]]

    results: list[str] = []
    args_str = " ".join(args).strip()

    # If first argument itself is a registered command/app (e.g. 'search notepad' -> 'notepad')
    if args and args[0].strip().lower() in candidates:
        app_target = args[0].strip().lower()
        if app_target not in DESTRUCTIVE_COMMANDS:
            remaining = " ".join(args[1:]).strip()
            direct_sugg = f"{app_target} {remaining}".strip()
            if direct_sugg not in results:
                results.append(direct_sugg)

    for cmd in ranked:
        # If the candidate is destructive, NEVER include arguments
        if cmd in DESTRUCTIVE_COMMANDS:
            if cmd not in results:
                results.append(cmd)
        else:
            formatted = f"{cmd} {args_str}".strip() if args_str else cmd
            if formatted not in results:
                results.append(formatted)

    return results[:max_suggestions]


def suggest_arguments(
    cmd_name: str,
    args: list[str],
    context: Any,
) -> tuple[list[str], str] | None:
    """Suggest closest valid subcommands or options when an argument error occurs.
    
    Returns (suggested_full_commands, usage_line) or None if no problem found.
    """
    if not args:
        return None

    cmd_lower = cmd_name.strip().lower()
    info = COMMAND_ARGUMENTS.get(cmd_lower)
    if not info:
        return None

    # Get command usage from registry
    usage = ""
    if hasattr(context, "registry") and context.registry:
        cmd_obj = context.registry.get(cmd_lower)
        if cmd_obj:
            usage = cmd_obj.usage

    subcommands = info.get("subcommands", [])
    options = info.get("options", [])
    values_map = info.get("values", {})

    first_arg = args[0]
    first_arg_lower = first_arg.lower()

    # Case 1: Flag option typos (e.g. organize --dryrun -> --dry-run)
    for i, a in enumerate(args):
        a_lower = a.lower()
        if a_lower.startswith("-"):
            # Check if this flag is valid
            valid_flags = list(options) + list(values_map.keys())
            if valid_flags and a_lower not in valid_flags:
                # Find closest match
                matches = difflib.get_close_matches(a_lower, valid_flags, n=1, cutoff=0.55)
                if matches:
                    new_args = list(args)
                    new_args[i] = matches[0]
                    return [f"{cmd_lower} {' '.join(new_args)}"], usage

    # Case 2: Option value typos (e.g. processes --sort cpuu -> cpu)
    for i, a in enumerate(args):
        a_lower = a.lower()
        if a_lower in values_map and i + 1 < len(args):
            val = args[i + 1].lower()
            allowed_vals = values_map[a_lower]
            if val not in allowed_vals:
                matches = difflib.get_close_matches(val, allowed_vals, n=1, cutoff=0.55)
                if matches:
                    new_args = list(args)
                    new_args[i + 1] = matches[0]
                    return [f"{cmd_lower} {' '.join(new_args)}"], usage
        elif any(a_lower.startswith(f"{opt}=") for opt in values_map):
            opt_key, val_part = a_lower.split("=", 1)
            allowed_vals = values_map.get(opt_key, [])
            if val_part not in allowed_vals:
                matches = difflib.get_close_matches(val_part, allowed_vals, n=1, cutoff=0.55)
                if matches:
                    new_args = list(args)
                    new_args[i] = f"{opt_key}={matches[0]}"
                    return [f"{cmd_lower} {' '.join(new_args)}"], usage

    # Case 3: Subcommand typos (e.g. process kil, theme kawai, mascot fx, workflow rn, history clr)
    if subcommands and first_arg_lower not in subcommands:
        matches = difflib.get_close_matches(first_arg_lower, subcommands, n=1, cutoff=0.45)
        if matches:
            new_args = list(args)
            new_args[0] = matches[0]
            return [f"{cmd_lower} {' '.join(new_args)}"], usage

    return None


def get_history_suggestions(
    corrected_cmd: str,
    context: Any,
    limit: int = 2,
) -> list[str]:
    """Retrieve successful, non-secret past commands starting with corrected_cmd."""
    if not hasattr(context, "history_manager") or not context.history_manager:
        return []

    base_cmd = corrected_cmd.split()[0].lower() if corrected_cmd else ""
    if not base_cmd or base_cmd in DESTRUCTIVE_COMMANDS:
        return []

    entries = context.history_manager.get_all()
    results: list[str] = []
    seen: set[str] = set()

    for item in reversed(entries):
        if not item.get("success", True):
            continue
        cmd_str = item.get("command", "").strip()
        if not cmd_str:
            continue
        if contains_secret(cmd_str):
            continue

        parts = cmd_str.split()
        if not parts:
            continue
        if parts[0].lower() == base_cmd and cmd_str != base_cmd:
            if cmd_str not in seen:
                seen.add(cmd_str)
                results.append(cmd_str)
                if len(results) >= limit:
                    break

    return results


def get_directory_hints(current_dir: Path | None) -> list[str]:
    """Inspect current directory non-recursively (max 200 items) for workflow hints.
    
    Never reads file contents. If .py files or pyproject.toml are present, suggests
    'code .' and 'ls *.py'.
    """
    if current_dir is None:
        return []

    try:
        p = Path(current_dir)
        if not p.exists() or not p.is_dir():
            return []

        has_py = False
        count = 0
        for entry in p.iterdir():
            count += 1
            name_lower = entry.name.lower()
            if name_lower.endswith(".py") or name_lower == "pyproject.toml":
                has_py = True
                break
            if count >= 200:
                break

        if has_py:
            return ["code .", "ls *.py"]
    except (OSError, PermissionError):
        pass

    return []


def get_available_app_hints(typed_name: str, context: Any) -> list[str]:
    """If typed_name matches an unregistered PATH program, suggest add-app."""
    clean = typed_name.strip().lower()
    if not clean or len(clean) < 2:
        return []

    # If it is already a registered shortcut or command, don't suggest add-app
    if hasattr(context, "registry") and context.registry.has_command(clean):
        return []
    if hasattr(context, "config") and context.config:
        if clean in context.config.get_applications():
            return []

    resolved_path = cached_which(clean)
    if not resolved_path:
        for app in KNOWN_EXTERNAL_APPS:
            if clean == app:
                resolved_path = cached_which(app)
                if resolved_path:
                    break

    if resolved_path:
        hints = [f"add-app {clean} {resolved_path}"]
        if clean == "python":
            hints.append("create-project python")
        return hints

    return []


def should_prefill(
    corrections: list[str],
    context: Any,
    is_interactive: bool,
) -> tuple[bool, str | None]:
    """Determine if a correction is safe to prefill on the next prompt line.
    
    Prefill only occurs if:
    - Input is interactive.
    - Exactly one correction was found.
    - The base command is in PREFILL_ALLOWLIST or is a shortcut.
    - Not in DESTRUCTIVE_COMMANDS.
    - Contains no destructive flags.
    """
    if not is_interactive:
        return False, None

    if len(corrections) != 1:
        return False, None

    candidate = corrections[0].strip()
    parts = candidate.split()
    if not parts:
        return False, None

    base_cmd = parts[0].lower()

    # Never prefill destructive commands
    if base_cmd in DESTRUCTIVE_COMMANDS:
        return False, None

    # Check for destructive flags
    destructive_flags = {"--force", "-f", "-r", "--recursive", "--yes", "-y"}
    if any(p.lower() in destructive_flags for p in parts[1:]):
        return False, None

    # Check allowlist
    if base_cmd in PREFILL_ALLOWLIST:
        return True, candidate

    # Check if base_cmd is a launcher shortcut (app, website, folder)
    if hasattr(context, "config") and context.config:
        if (
            base_cmd in context.config.get_applications()
            or base_cmd in context.config.get_websites()
            or base_cmd in context.config.get_folder_shortcuts()
        ):
            return True, candidate

    return False, None
