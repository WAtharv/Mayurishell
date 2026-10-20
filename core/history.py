"""History management for MayuriShell."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable

from prompt_toolkit.history import History as PtHistory

from core.config_manager import safe_atomic_write
from core.logging_config import get_logger

logger = get_logger()

SECRET_PATTERNS = [
    re.compile(r"password\b", re.IGNORECASE),
    re.compile(r"passwd\b", re.IGNORECASE),
    re.compile(r"token\b", re.IGNORECASE),
    re.compile(r"secret\b", re.IGNORECASE),
    re.compile(r"api[_-]?key\b", re.IGNORECASE),
    re.compile(r"bearer\b", re.IGNORECASE),
]


def contains_secret(text: str) -> bool:
    """Return True if text appears to contain sensitive tokens or secrets."""
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


class HistoryManager:
    """Manages shell command history persistence and secret sanitization."""

    def __init__(self, history_file: Path) -> None:
        self.history_file = history_file
        self.entries: list[dict[str, str]] = []
        self.load()

    def load(self) -> list[dict[str, str]]:
        """Load history entries from history.json safely."""
        if not self.history_file.exists():
            self.entries = []
            return self.entries

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                normalized: list[dict[str, str]] = []
                for item in data:
                    if isinstance(item, dict) and "command" in item:
                        normalized.append({
                            "timestamp": str(item.get("timestamp", "")),
                            "command": str(item["command"]),
                        })
                    elif isinstance(item, str):
                        normalized.append({
                            "timestamp": "",
                            "command": item,
                        })
                self.entries = normalized
            else:
                logger.warning("History file was not a list; resetting history.")
                self.entries = []
        except Exception as exc:
            logger.warning("Failed to load history from %s: %s; resetting.", self.history_file, exc)
            self.entries = []

        return self.entries

    def save(self) -> None:
        """Atomically persist history entries to history.json."""
        serialized = json.dumps(self.entries, indent=2, ensure_ascii=False)
        safe_atomic_write(self.history_file, serialized)

    def add(self, command: str) -> bool:
        """Add a command to history if it is non-empty and contains no secrets.
        
        Returns True if stored, False if skipped.
        """
        stripped = command.strip()
        if not stripped:
            return False

        if contains_secret(stripped):
            logger.info("Command skipped from history due to detected secret pattern.")
            return False

        # Avoid immediate duplicate consecutive commands
        if self.entries and self.entries[-1]["command"] == stripped:
            return False

        timestamp = datetime.datetime.now().isoformat(timespec="seconds")
        self.entries.append({"timestamp": timestamp, "command": stripped})
        
        # Keep reasonable max history in file (e.g. 5000 entries)
        if len(self.entries) > 5000:
            self.entries = self.entries[-5000:]

        try:
            self.save()
        except Exception as exc:
            logger.error("Failed to save history: %s", exc)

        return True

    def get_all(self) -> list[dict[str, str]]:
        """Return all history entries."""
        return list(self.entries)

    def get_commands(self) -> list[str]:
        """Return list of command strings."""
        return [entry["command"] for entry in self.entries]

    def clear(self) -> None:
        """Clear all stored history."""
        self.entries = []
        self.save()
        logger.info("Command history cleared.")


class PromptToolkitHistory(PtHistory):
    """Bridge HistoryManager with prompt_toolkit's History interface."""

    def __init__(self, history_manager: HistoryManager) -> None:
        super().__init__()
        self.manager = history_manager

    def load_history_strings(self) -> Iterable[str]:
        """Yield history strings in reverse order (newest first) for prompt_toolkit."""
        commands = self.manager.get_commands()
        return reversed(commands)

    def store_string(self, string: str) -> None:
        """Store string in history manager."""
        self.manager.add(string)
