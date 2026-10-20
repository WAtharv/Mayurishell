"""Tests verifying documentation integrity and command registry coverage."""
from __future__ import annotations

from pathlib import Path

from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from main import register_all_commands


def test_commands_doc_covers_all_registered_commands(tmp_path: Path):
    """Test that docs/commands.md covers every registered command with description and usage."""
    doc_path = Path(__file__).resolve().parent.parent / "docs" / "commands.md"
    assert doc_path.exists(), "docs/commands.md must exist."

    doc_text = doc_path.read_text(encoding="utf-8")

    # Build registry in isolated temp directory
    cfg = ConfigManager(base_dir=tmp_path / "cfg")
    registry = CommandRegistry()
    register_all_commands(registry, cfg)

    commands = registry.list_commands()
    assert len(commands) > 0

    missing_in_doc: list[str] = []
    missing_description: list[str] = []
    missing_usage: list[str] = []

    for cmd in commands:
        # Check description and usage metadata
        if not cmd.description or not cmd.description.strip():
            missing_description.append(cmd.name)
        if not cmd.usage or not cmd.usage.strip():
            missing_usage.append(cmd.name)

        # Check documentation heading
        heading = f"### `{cmd.name}`"
        if heading not in doc_text:
            missing_in_doc.append(cmd.name)

    assert not missing_description, f"Commands missing descriptions: {missing_description}"
    assert not missing_usage, f"Commands missing usage strings: {missing_usage}"
    assert not missing_in_doc, f"Commands missing from docs/commands.md: {missing_in_doc}"
