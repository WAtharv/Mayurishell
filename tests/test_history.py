"""Unit tests for HistoryManager and secret sanitization."""
import json
from pathlib import Path

from core.history import HistoryManager, PromptToolkitHistory, contains_secret


def test_history_persistence(tmp_path: Path) -> None:
    """Test adding commands and reading them back."""
    history_file = tmp_path / "history.json"
    mgr = HistoryManager(history_file)

    assert mgr.add("help") is True
    assert mgr.add("version") is True

    # Immediate consecutive duplicate is skipped
    assert mgr.add("version") is False

    assert mgr.get_commands() == ["help", "version"]

    # Reload from disk
    reloaded = HistoryManager(history_file)
    assert reloaded.get_commands() == ["help", "version"]


def test_secret_filtering(tmp_path: Path) -> None:
    """Test that commands containing secrets are never recorded."""
    history_file = tmp_path / "history.json"
    mgr = HistoryManager(history_file)

    # Various secret patterns
    assert contains_secret("connect --password MySecret123") is True
    assert contains_secret("curl -H 'Authorization: Bearer xyz123'") is True
    assert contains_secret("export API_KEY=abc-xyz") is True
    assert contains_secret("set TOKEN=secretval") is True

    # Regular commands
    assert contains_secret("spotify") is False
    assert contains_secret("organize downloads") is False

    # Storing secret in history manager should be rejected
    added = mgr.add("login --password supersecret")
    assert added is False
    assert len(mgr.get_commands()) == 0


def test_history_clear(tmp_path: Path) -> None:
    """Test clearing history."""
    history_file = tmp_path / "history.json"
    mgr = HistoryManager(history_file)

    mgr.add("ls")
    mgr.add("pwd")
    assert len(mgr.get_commands()) == 2

    mgr.clear()
    assert len(mgr.get_commands()) == 0

    # Ensure disk is cleared
    reloaded = HistoryManager(history_file)
    assert len(reloaded.get_commands()) == 0


def test_corrupted_history_recovery(tmp_path: Path) -> None:
    """Test safe recovery when history.json contains malformed JSON."""
    history_file = tmp_path / "history.json"
    history_file.write_text("corrupted content not json!", encoding="utf-8")

    mgr = HistoryManager(history_file)
    assert mgr.get_commands() == []
    # Should be able to add new commands without crashing
    mgr.add("help")
    assert mgr.get_commands() == ["help"]


def test_prompt_toolkit_history_bridge(tmp_path: Path) -> None:
    """Test that PromptToolkitHistory returns newest items first."""
    history_file = tmp_path / "history.json"
    mgr = HistoryManager(history_file)
    mgr.add("cmd1")
    mgr.add("cmd2")
    mgr.add("cmd3")

    pt_hist = PromptToolkitHistory(mgr)
    strings = list(pt_hist.load_history_strings())
    assert strings == ["cmd3", "cmd2", "cmd1"]
