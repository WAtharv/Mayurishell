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

        # 2. Context-specific commands
        if cmd in ("help", "command-info"):
            yield from self._complete_command_names(current_token)
        elif cmd in ("alias", "unalias"):
            yield from self._complete_alias_names(current_token)
        elif cmd == "history":
            yield from self._complete_history_subcommands(current_token)
        elif cmd == "process":
            yield from self._complete_process_command(tokens, current_token)
        elif cmd == "processes":
            yield from self._complete_processes_command(tokens, current_token)
        elif cmd == "cd":
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
