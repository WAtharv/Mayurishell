"""Context-aware auto-completion engine for MayuriShell."""
from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any, Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document


def split_completion_line(text: str) -> tuple[list[str], str, str | None, int]:
    """Parse text_before_cursor into:
    (previous_tokens, current_word, quote_char, current_word_start_offset)
    
    Handles unclosed single and double quotes.
    """
    tokens: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    start_pos = 0

    i = 0
    while i < len(text):
        ch = text[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
                current.append(ch)
            else:
                current.append(ch)
        else:
            if ch in ('"', "'"):
                in_quote = ch
                if not current:
                    start_pos = i
                current.append(ch)
            elif ch.isspace():
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                if not current:
                    start_pos = i
                current.append(ch)
        i += 1

    current_token = "".join(current)
    if not current:
        start_pos = len(text)

    return tokens, current_token, in_quote, start_pos


def is_hidden_entry(entry: Path) -> bool:
    """Check if a directory entry is hidden (dotfile or Windows hidden attribute)."""
    if entry.name.startswith(".") or entry.name.startswith("$"):
        return True
    try:
        attrs = entry.stat().st_file_attributes
        if attrs & stat.FILE_ATTRIBUTE_HIDDEN:
            return True
    except (AttributeError, OSError, PermissionError):
        pass
    return False


class MayuriCompleter(Completer):
    """Context-aware completion for commands, shortcuts, aliases, and file paths."""

    def __init__(self, context: Any) -> None:
        self.context = context

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Generate context-aware completions based on cursor position."""
        text = document.text_before_cursor
        tokens, current_token, in_quote, _ = split_completion_line(text)

        # 1. First word: commands, shortcuts, and aliases
        if len(tokens) == 0:
            yield from self._complete_first_word(current_token)
            return

        raw_cmd = tokens[0].lower()
        # Resolve aliases if the first token is an alias
        cmd = self._resolve_alias_command(raw_cmd)

        # Suppress completions after website shortcuts (free-form search queries)
        websites = self.context.config.get_websites() if hasattr(self.context, "config") else {}
        if cmd in websites:
            return

        # 2. Context-specific commands
        if cmd in ("help", "command-info"):
            yield from self._complete_command_names(current_token)
        elif cmd in ("alias", "unalias"):
            yield from self._complete_alias_names(current_token)
        elif cmd == "history":
            yield from self._complete_history_subcommands(current_token)
        elif cmd == "theme":
            yield from self._complete_theme_options(current_token)
        elif cmd == "mascot":
            yield from self._complete_mascot_options(current_token)
        elif cmd == "process":
            yield from self._complete_process_command(tokens, current_token)
        elif cmd == "processes":
            yield from self._complete_processes_command(tokens, current_token)
        elif cmd == "organize":
            yield from self._complete_organize(tokens, current_token)
        elif cmd == "create-project":
            yield from self._complete_create_project(tokens, current_token)
        elif cmd == "workflow":
            yield from self._complete_workflow(tokens, current_token)
        elif cmd == "diagnostics":
            yield from self._complete_diagnostics(tokens, current_token)
        elif cmd == "config":
            yield from self._complete_config(tokens, current_token)
        elif cmd == "doctor":
            yield from self._complete_doctor(tokens, current_token)
        elif cmd == "suggestions":
            for opt in ("on", "off"):
                if opt.startswith(current_token.lower()):
                    yield Completion(opt, start_position=-len(current_token), display=opt, display_meta=f"Turn suggestions {opt}")
        elif cmd in ("cd", "code"):
            yield from self._complete_paths(current_token, only_dirs=True, include_shortcuts=True)
        elif cmd in ("ls", "open", "info", "copy", "move", "rename", "delete", "touch", "add-folder"):
            yield from self._complete_paths(current_token, only_dirs=False, include_shortcuts=False)
        else:
            # Fallback path completion for other commands
            yield from self._complete_paths(current_token, only_dirs=False, include_shortcuts=False)

    def _resolve_alias_command(self, cmd_name: str) -> str:
        """Resolve alias name to its target base command if present."""
        try:
            if hasattr(self.context, "alias_manager"):
                expansion = self.context.alias_manager.get(cmd_name)
                if expansion:
                    parts = expansion.strip().split()
                    if parts:
                        return parts[0].lower()
        except Exception:
            pass
        return cmd_name

    def _complete_first_word(self, current_token: str) -> Iterable[Completion]:
        """Suggest registered commands, apps, websites, folders, and aliases."""
        prefix = current_token.lower()
        seen: set[str] = set()
        count = 0
        limit = 200

        # Command names from registry
        if hasattr(self.context, "registry"):
            for cmd in self.context.registry.list_commands():
                name = cmd.name
                if name.lower().startswith(prefix) and name.lower() not in seen:
                    seen.add(name.lower())
                    yield Completion(
                        name,
                        start_position=-len(current_token),
                        display=name,
                        display_meta=cmd.description[:40] if cmd.description else "Command",
                    )
                    count += 1
                    if count >= limit:
                        return

        # App shortcuts
        if hasattr(self.context, "config"):
            for name, target in self.context.config.get_applications().items():
                if name.lower().startswith(prefix) and name.lower() not in seen:
                    seen.add(name.lower())
                    yield Completion(
                        name,
                        start_position=-len(current_token),
                        display=name,
                        display_meta=f"App: {target}",
                    )
                    count += 1
                    if count >= limit:
                        return

            # Website shortcuts
            for name, url in self.context.config.get_websites().items():
                if name.lower().startswith(prefix) and name.lower() not in seen:
                    seen.add(name.lower())
                    yield Completion(
                        name,
                        start_position=-len(current_token),
                        display=name,
                        display_meta=f"Website: {url}",
                    )
                    count += 1
                    if count >= limit:
                        return

            # Folder shortcuts
            for name, folder in self.context.config.get_folder_shortcuts().items():
                if name.lower().startswith(prefix) and name.lower() not in seen:
                    seen.add(name.lower())
                    yield Completion(
                        name,
                        start_position=-len(current_token),
                        display=name,
                        display_meta=f"Folder: {folder}",
                    )
                    count += 1
                    if count >= limit:
                        return

        # Aliases
        if hasattr(self.context, "alias_manager"):
            for name, expansion in self.context.alias_manager.get_all().items():
                if name.lower().startswith(prefix) and name.lower() not in seen:
                    seen.add(name.lower())
                    yield Completion(
                        name,
                        start_position=-len(current_token),
                        display=name,
                        display_meta=f"Alias: {expansion}",
                    )
                    count += 1
                    if count >= limit:
                        return

    def _complete_command_names(self, current_token: str) -> Iterable[Completion]:
        """Suggest command names for help / command-info."""
        prefix = current_token.lower()
        if hasattr(self.context, "registry"):
            for cmd in self.context.registry.list_commands():
                if cmd.name.lower().startswith(prefix):
                    yield Completion(
                        cmd.name,
                        start_position=-len(current_token),
                        display=cmd.name,
                        display_meta=cmd.description[:40] if cmd.description else "Command",
                    )

    def _complete_alias_names(self, current_token: str) -> Iterable[Completion]:
        """Suggest alias names for alias / unalias."""
        prefix = current_token.lower()
        if hasattr(self.context, "alias_manager"):
            for name, target in self.context.alias_manager.get_all().items():
                if name.lower().startswith(prefix):
                    yield Completion(
                        name,
                        start_position=-len(current_token),
                        display=name,
                        display_meta=f"Alias -> {target}",
                    )

    def _complete_history_subcommands(self, current_token: str) -> Iterable[Completion]:
        """Suggest 'clear' for history command."""
        prefix = current_token.lower()
        if "clear".startswith(prefix):
            yield Completion(
                "clear",
                start_position=-len(current_token),
                display="clear",
                display_meta="Clear command history",
            )

    def _complete_theme_options(self, current_token: str) -> Iterable[Completion]:
        """Suggest theme names and 'preview' subcommand."""
        from core.theme import THEMES
        prefix = current_token.lower()
        options = [("preview", "Preview all visual palettes side-by-side")]
        for key, thm in THEMES.items():
            options.append((key, thm.display_name))
        for name, desc in options:
            if name.lower().startswith(prefix):
                yield Completion(
                    name,
                    start_position=-len(current_token),
                    display=name,
                    display_meta=desc,
                )

    def _complete_mascot_options(self, current_token: str) -> Iterable[Completion]:
        """Suggest mascot names and 'random'."""
        from core.mascots import VALID_MASCOTS
        prefix = current_token.lower()
        options = [("random", "Random companion each startup")]
        for m in sorted(VALID_MASCOTS):
            options.append((m, f"{m.capitalize()} companion"))
        for name, desc in options:
            if name.lower().startswith(prefix):
                yield Completion(
                    name,
                    start_position=-len(current_token),
                    display=name,
                    display_meta=desc,
                )

    def _complete_process_command(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest process subcommands: find, info, kill, list."""
        if len(tokens) == 1:
            subcmds = [
                ("find", "Search processes by name"),
                ("info", "Show process details by PID"),
                ("kill", "Terminate process by PID"),
                ("list", "List running processes"),
            ]
            prefix = current_token.lower()
            for sub, desc in subcmds:
                if sub.startswith(prefix):
                    yield Completion(sub, start_position=-len(current_token), display=sub, display_meta=desc)
        elif len(tokens) >= 2 and tokens[1].lower() == "kill":
            if "--force".startswith(current_token.lower()):
                yield Completion("--force", start_position=-len(current_token), display="--force", display_meta="Force kill process")

    def _complete_processes_command(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest options and values for processes command."""
        prev = tokens[-1].lower() if tokens else ""
        if prev in ("--sort", "-s"):
            for val in ("cpu", "memory", "name"):
                if val.startswith(current_token.lower()):
                    yield Completion(val, start_position=-len(current_token), display=val, display_meta=f"Sort by {val}")
            return

        if current_token.startswith("--sort="):
            val_part = current_token.split("=", 1)[1].lower()
            for val in ("cpu", "memory", "name"):
                if val.startswith(val_part):
                    full = f"--sort={val}"
                    yield Completion(full, start_position=-len(current_token), display=val, display_meta=f"Sort by {val}")
            return

        # Suggest flags
        flags = [
            ("--sort", "Sort processes (cpu, memory, name)"),
            ("--limit", "Maximum number of processes to show"),
        ]
        prefix = current_token.lower()
        for flag, desc in flags:
            if flag.startswith(prefix):
                yield Completion(flag, start_position=-len(current_token), display=flag, display_meta=desc)

    def _complete_organize(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest organize options, subcommands, and folder paths."""
        prefix = current_token.lower()
        # Suggest flags
        if prefix.startswith("-"):
            for flag, desc in [("--dry-run", "Preview proposed file moves"), ("--include-other", "Move uncategorized files to Other")]:
                if flag.startswith(prefix):
                    yield Completion(flag, start_position=-len(current_token), display=flag, display_meta=desc)
            return

        # Suggest undo subcommand
        if "undo".startswith(prefix):
            yield Completion("undo", start_position=-len(current_token), display="undo", display_meta="Reverse last organize run")

        # Suggest directory paths and folder shortcuts
        yield from self._complete_paths(current_token, only_dirs=True, include_shortcuts=True)

    def _complete_create_project(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest templates and options for create-project."""
        prefix = current_token.lower()
        prev = tokens[-1].lower() if tokens else ""

        if prev in ("--template", "-t"):
            from commands.project_scaffolding import BUILTIN_TEMPLATES, get_custom_templates_dir
            for t_name, t_desc in BUILTIN_TEMPLATES.items():
                if t_name.startswith(prefix):
                    yield Completion(t_name, start_position=-len(current_token), display=t_name, display_meta=t_desc[:30])
            custom_dir = get_custom_templates_dir(self.context)
            if custom_dir.exists() and custom_dir.is_dir():
                for item in custom_dir.iterdir():
                    if item.is_dir() and not item.is_symlink() and item.name.lower().startswith(prefix):
                        yield Completion(item.name.lower(), start_position=-len(current_token), display=item.name.lower(), display_meta="Custom template")
            return

        # Suggest flags
        for flag, desc in [("--template", "Specify starter template"), ("--here", "Scaffold inside current empty directory")]:
            if flag.startswith(prefix):
                yield Completion(flag, start_position=-len(current_token), display=flag, display_meta=desc)

    def _complete_workflow(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest workflow subcommands, names, and options."""
        prefix = current_token.lower()

        if len(tokens) == 1:
            subcmds = [
                ("list", "List configured workflows"),
                ("show", "Show steps for a workflow"),
                ("run", "Execute a workflow"),
                ("add", "Create a new workflow"),
                ("remove", "Delete a configured workflow"),
                ("validate", "Check workflows for errors"),
            ]
            for sub, desc in subcmds:
                if sub.startswith(prefix):
                    yield Completion(sub, start_position=-len(current_token), display=sub, display_meta=desc)
            return

        subcmd = tokens[1].lower()
        if subcmd in ("show", "run", "remove", "delete") and len(tokens) == 2:
            wfs = self.context.config.get_workflows()
            for wf_name in sorted(wfs.keys()):
                if wf_name.lower().startswith(prefix):
                    desc = wfs[wf_name].get("description", "Workflow") if isinstance(wfs[wf_name], dict) else "Workflow"
                    yield Completion(wf_name, start_position=-len(current_token), display=wf_name, display_meta=desc[:30])
            return

        if subcmd == "run" and len(tokens) >= 3:
            if "--dry-run".startswith(prefix):
                yield Completion("--dry-run", start_position=-len(current_token), display="--dry-run", display_meta="Preview workflow steps")

    def _complete_diagnostics(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest options for diagnostics."""
        prefix = current_token.lower()
        if "--export".startswith(prefix):
            yield Completion("--export", start_position=-len(current_token), display="--export", display_meta="Export sanitized report to Desktop")

    def _complete_config(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest subcommands, flags, backup names, and file paths for config."""
        prefix = current_token.lower()
        if len(tokens) == 1:
            subcmds = [
                ("export", "Export sanitized configuration JSON"),
                ("import", "Import and validate configuration file"),
                ("backup", "Create timestamped configuration snapshot"),
                ("restore", "Restore configuration from backups/"),
            ]
            for sub, desc in subcmds:
                if sub.startswith(prefix):
                    yield Completion(sub, start_position=-len(current_token), display=sub, display_meta=desc)
            return

        subcmd = tokens[1].lower()
        if subcmd == "export":
            yield from self._complete_paths(current_token, only_dirs=False, include_shortcuts=False)
        elif subcmd == "import":
            for flag, desc in [("--dry-run", "Preview import without applying"), ("--overwrite", "Replace conflicting settings")]:
                if flag.startswith(prefix):
                    yield Completion(flag, start_position=-len(current_token), display=flag, display_meta=desc)
            yield from self._complete_paths(current_token, only_dirs=False, include_shortcuts=False)
        elif subcmd == "restore":
            if hasattr(self.context, "config"):
                backups_dir = self.context.config.backups_dir
                if backups_dir.exists():
                    for p in sorted(backups_dir.glob("*.json"), reverse=True):
                        if p.name.lower().startswith(prefix):
                            yield Completion(
                                p.name,
                                start_position=-len(current_token),
                                display=p.name,
                                display_meta="Backup file",
                            )

    def _complete_doctor(self, tokens: list[str], current_token: str) -> Iterable[Completion]:
        """Suggest categories for doctor command."""
        prefix = current_token.lower()
        if len(tokens) == 1:
            cats = [
                ("apps", "Verify configured shortcuts, folders, websites, workflows"),
                ("python", "Inspect Python interpreters on PATH"),
                ("config", "Check configuration, history, and write permissions"),
                ("all", "Run comprehensive health check across all categories"),
            ]
            for cat, desc in cats:
                if cat.startswith(prefix):
                    yield Completion(cat, start_position=-len(current_token), display=cat, display_meta=desc)

    def _complete_paths(
        self, current_token: str, only_dirs: bool = False, include_shortcuts: bool = False
    ) -> Iterable[Completion]:
        """Suggest matching file and/or directory paths."""
        count = 0
        limit = 200

        # Extract raw prefix by stripping surrounding or leading quotes
        has_quote = current_token.startswith('"') or current_token.startswith("'")
        raw_prefix = current_token
        if has_quote:
            raw_prefix = current_token[1:]
            if raw_prefix.endswith('"') or raw_prefix.endswith("'"):
                raw_prefix = raw_prefix[:-1]

        # Split into dir part and child prefix
        last_sep = max(raw_prefix.rfind("\\"), raw_prefix.rfind("/"))
        if last_sep >= 0:
            dir_part = raw_prefix[: last_sep + 1]
            file_prefix = raw_prefix[last_sep + 1 :]
        else:
            dir_part = ""
            file_prefix = raw_prefix

        # If typing top-level and shortcuts allowed, offer folder shortcuts
        if include_shortcuts and dir_part == "" and hasattr(self.context, "config"):
            try:
                for name, target in self.context.config.get_folder_shortcuts().items():
                    if name.lower().startswith(file_prefix.lower()):
                        comp_text = f'"{name}"' if " " in name else name
                        yield Completion(
                            comp_text,
                            start_position=-len(current_token),
                            display=name,
                            display_meta=f"Shortcut -> {target}",
                        )
                        count += 1
                        if count >= limit:
                            return
            except Exception:
                pass

        # Resolve directory to scan live from self.context.current_dir
        cur_dir: Path = getattr(self.context, "current_dir", Path.cwd())
        base_dir = self._resolve_scan_dir(dir_part, cur_dir)
        if base_dir is None:
            return

        try:
            if not base_dir.is_dir():
                return
            entries = sorted(base_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return

        match_prefix = file_prefix.lower()
        allow_hidden = file_prefix.startswith(".")

        for entry in entries:
            try:
                # Filter hidden files unless prefix starts with "."
                if not allow_hidden and is_hidden_entry(entry):
                    continue

                is_dir = entry.is_dir()
                if only_dirs and not is_dir:
                    continue

                if not entry.name.lower().startswith(match_prefix):
                    continue

                # Build completion text
                full_path_str = dir_part + entry.name
                if is_dir:
                    full_path_str += "\\"
                    display_text = f"{entry.name}\\"
                    meta = "<DIR>"
                else:
                    display_text = entry.name
                    meta = "File"

                # Wrap in double quotes if there are spaces or user already typed an opening quote
                if " " in full_path_str or has_quote:
                    comp_text = f'"{full_path_str}"'
                else:
                    comp_text = full_path_str

                yield Completion(
                    comp_text,
                    start_position=-len(current_token),
                    display=display_text,
                    display_meta=meta,
                )
                count += 1
                if count >= limit:
                    return
            except Exception:
                continue

    def _resolve_scan_dir(self, dir_part: str, current_dir: Path) -> Path | None:
        """Resolve a directory prefix string to a Path object safely."""
        try:
            if not dir_part:
                return current_dir
            if dir_part.startswith("~"):
                sub = dir_part[1:].lstrip("\\/")
                home = Path.home()
                return (home / sub) if sub else home
            p = Path(dir_part)
            if p.is_absolute():
                return p
            return (current_dir / dir_part).resolve()
        except Exception:
            return None
