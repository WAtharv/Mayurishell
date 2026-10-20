"""Integration tests for search commands: find."""
from pathlib import Path
from unittest.mock import patch
from rich.console import Console

from commands.search import register_search_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell


def create_search_test_shell(tmp_path: Path) -> tuple[MayuriShell, Console]:
    """Helper to initialize shell for search testing."""
    config = ConfigManager(base_dir=tmp_path / "appdata")
    history = HistoryManager(tmp_path / "appdata" / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_search_commands(registry)

    console = Console(record=True, color_system=None, width=140)
    work_dir = tmp_path / "search_workspace"
    work_dir.mkdir(parents=True)

    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        console=console,
        current_dir=work_dir,
    )
    return shell, console


def test_command_find_query_and_results(tmp_path: Path) -> None:
    """Test find discovers files in configured search_directories."""
    shell, console = create_search_test_shell(tmp_path)

    # Set search_directories to a custom tmp folder
    search_root = tmp_path / "my_docs"
    search_root.mkdir()
    (search_root / "report2026.pdf").write_text("dummy")
    (search_root / "notes.txt").write_text("notes")

    shell.context.config.set("search_directories", [str(search_root)])

    shell.run_command_line("find report*.pdf")
    output = console.export_text()
    assert "Search Results" in output
    assert "report2026.pdf" in output
    assert "notes.txt" not in output


def test_command_find_limit_and_skipped(tmp_path: Path) -> None:
    """Test find with limit capping and skipped folder feedback."""
    shell, console = create_search_test_shell(tmp_path)
    search_root = tmp_path / "files"
    search_root.mkdir()
    for i in range(5):
        (search_root / f"file_{i}.txt").write_text("content")

    shell.context.config.set("search_directories", [str(search_root)])

    # Search with limit 2
    shell.run_command_line("find file --limit 2")
    output = console.export_text()
    assert "Result limit reached" in output
    assert "capped at 2 items" in output


def test_command_find_no_results(tmp_path: Path) -> None:
    """Test find when no matching files exist."""
    shell, console = create_search_test_shell(tmp_path)
    search_root = tmp_path / "empty_dir"
    search_root.mkdir()
    shell.context.config.set("search_directories", [str(search_root)])

    shell.run_command_line("find nonexistent_pattern_123")
    output = console.export_text()
    assert "No matching files found" in output
