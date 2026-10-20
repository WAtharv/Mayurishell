"""Command registry and command metadata for MayuriShell."""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
from typing import Any, Callable

from core.exceptions import ArgumentError


@dataclass(frozen=True)
class ArgumentRules:
    """Rules and constraints for command arguments."""
    min_args: int = 0
    max_args: int | None = None
    custom_validator: Callable[[list[str]], str | None] | None = None

    def validate(self, args: list[str]) -> None:
        """Validate an argument list against the constraints.
        
        Raises:
            ArgumentError: If validation fails.
        """
        if len(args) < self.min_args:
            raise ArgumentError(f"Expected at least {self.min_args} arguments, but got {len(args)}.")
        if self.max_args is not None and len(args) > self.max_args:
            raise ArgumentError(f"Expected at most {self.max_args} arguments, but got {len(args)}.")
        if self.custom_validator is not None:
            err = self.custom_validator(args)
            if err:
                raise ArgumentError(err)


@dataclass
class CommandInfo:
    """Metadata describing a registered command."""
    name: str
    description: str
    handler: Callable[..., Any]
    usage: str
    category: str = "General"
    arg_rules: ArgumentRules = field(default_factory=ArgumentRules)


class CommandRegistry:
    """Central registry of executable commands in MayuriShell."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandInfo] = {}

    def register(self, command: CommandInfo) -> None:
        """Register a new command.
        
        Names are normalized to lower-case.
        """
        key = command.name.strip().lower()
        if not key:
            raise ValueError("Command name cannot be empty.")
        self._commands[key] = command

    def unregister(self, name: str) -> bool:
        """Unregister a command by name."""
        key = name.strip().lower()
        if key in self._commands:
            del self._commands[key]
            return True
        return False

    def get(self, name: str) -> CommandInfo | None:
        """Retrieve command metadata by name."""
        return self._commands.get(name.strip().lower())

    def has_command(self, name: str) -> bool:
        """Check if a command name is registered."""
        return name.strip().lower() in self._commands

    def list_commands(self, category: str | None = None) -> list[CommandInfo]:
        """Return all registered commands, optionally filtered by category, sorted by name."""
        cmds = list(self._commands.values())
        if category:
            cmds = [c for c in cmds if c.category.lower() == category.lower()]
        return sorted(cmds, key=lambda c: c.name)

    def get_categories(self) -> list[str]:
        """Return a sorted list of unique category names."""
        return sorted({c.category for c in self._commands.values()})

    def suggest(self, name: str, cutoff: float = 0.6) -> list[str]:
        """Suggest close matches for an unknown command name."""
        all_names = list(self._commands.keys())
        return difflib.get_close_matches(name.strip().lower(), all_names, n=3, cutoff=cutoff)
