"""Alias manager for MayuriShell."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.exceptions import AliasConflictError, AliasLoopError
from core.logging_config import get_logger
from core.parser import parse_command_line

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.registry import CommandRegistry

logger = get_logger()

VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")


def is_valid_name(name: str) -> bool:
    """Return True if name consists only of letters, numbers, and hyphens."""
    return bool(VALID_NAME_PATTERN.fullmatch(name.strip()))


class AliasManager:
    """Manages alias resolution, persistence, conflict checks, and loop detection."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager

    def get_all(self) -> dict[str, str]:
        """Return all defined aliases."""
        return self.config_manager.get_aliases()

    def get(self, name: str) -> str | None:
        """Get the target command for an alias."""
        return self.get_all().get(name.strip().lower())

    def validate_name(self, name: str, registry: CommandRegistry | None = None) -> None:
        """Validate alias name against naming rules and command collisions."""
        norm_name = name.strip().lower()
        if not norm_name:
            raise ValueError("Alias name cannot be empty.")

        if not is_valid_name(norm_name):
            raise ValueError(f"Invalid alias name '{name}'. Names may only contain letters, numbers, and hyphens.")

        # Check collision with registered commands
        if registry and registry.has_command(norm_name):
            cmd = registry.get(norm_name)
            if cmd and cmd.category != "Aliases":
                raise AliasConflictError(f"Cannot alias '{name}': conflicts with registered command ({cmd.category}).")

    def would_cause_loop(self, name: str, target: str) -> list[str] | None:
        """Check if adding alias name -> target would create a circular loop.
        
        Returns the cycle chain if a loop is detected, or None if safe.
        """
        temp_aliases = dict(self.get_all())
        temp_aliases[name.lower()] = target

        curr = name.lower()
        visited: list[str] = [curr]
        seen = {curr}

        for _ in range(30):
            target_str = temp_aliases.get(curr)
            if not target_str:
                return None

            parsed = parse_command_line(target_str)
            if not parsed:
                return None

            next_cmd = parsed.name.lower()
            if next_cmd in seen:
                return visited + [next_cmd]

            if next_cmd in temp_aliases:
                visited.append(next_cmd)
                seen.add(next_cmd)
                curr = next_cmd
            else:
                return None

        return visited + ["..."]

    def add_alias(self, name: str, target: str, registry: CommandRegistry | None = None) -> None:
        """Add or update an alias with validation and loop detection."""
        norm_name = name.strip().lower()
        target_str = target.strip()
        if not target_str:
            raise ValueError("Alias target cannot be empty.")

        self.validate_name(norm_name, registry=registry)

        loop_path = self.would_cause_loop(norm_name, target_str)
        if loop_path:
            chain_str = " -> ".join(loop_path)
            raise AliasLoopError(f"Alias loop detected: {chain_str}")

        self.config_manager.set_shortcut("aliases", norm_name, target_str)
        logger.info("Alias registered: '%s' -> '%s'", norm_name, target_str)

    def remove_alias(self, name: str) -> bool:
        """Remove an alias by name."""
        norm_name = name.strip().lower()
        removed = self.config_manager.remove_shortcut("aliases", norm_name)
        if removed:
            logger.info("Alias removed: '%s'", norm_name)
        return removed

    def resolve(self, name: str, args: list[str]) -> tuple[str, list[str]]:
        """Recursively resolve an alias to its target command and arguments.
        
        Raises:
            AliasLoopError: If an alias cycle is detected.
        """
        aliases = self.get_all()
        curr_name = name.strip().lower()
        curr_args = list(args)

        visited: list[str] = [curr_name]
        seen = {curr_name}

        while curr_name in aliases:
            target_str = aliases[curr_name]
            parsed = parse_command_line(target_str)
            if not parsed:
                break

            # Target command and any arguments defined in the alias
            curr_name = parsed.name.lower()
            curr_args = parsed.args + curr_args

            if curr_name in seen:
                chain = " -> ".join(visited + [curr_name])
                raise AliasLoopError(f"Alias loop detected: {chain}")

            if curr_name in aliases:
                visited.append(curr_name)
                seen.add(curr_name)

        return curr_name, curr_args
