"""Unit tests for AliasManager, loop detection, and conflict prevention."""
from pathlib import Path
import pytest

from core.aliases import AliasManager, is_valid_name
from core.config_manager import ConfigManager
from core.exceptions import AliasConflictError, AliasLoopError
from core.registry import CommandInfo, CommandRegistry


def test_is_valid_name() -> None:
    """Test validation of alias / shortcut names."""
    assert is_valid_name("yt") is True
    assert is_valid_name("git-status") is True
    assert is_valid_name("app123") is True
    assert is_valid_name("my-app-2") is True

    # Invalid names
    assert is_valid_name("my app") is False
    assert is_valid_name("yt!") is False
    assert is_valid_name("app/1") is False
    assert is_valid_name("") is False


def test_alias_creation_and_resolution(tmp_path: Path) -> None:
    """Test creating an alias and resolving it."""
    cfg = ConfigManager(base_dir=tmp_path)
    mgr = AliasManager(cfg)

    mgr.add_alias("g", "google")
    assert mgr.get("g") == "google"

    resolved_cmd, resolved_args = mgr.resolve("g", ["search", "query"])
    assert resolved_cmd == "google"
    assert resolved_args == ["search", "query"]


def test_chained_aliases(tmp_path: Path) -> None:
    """Test multi-hop alias resolution (a -> b -> c)."""
    cfg = ConfigManager(base_dir=tmp_path)
    mgr = AliasManager(cfg)

    mgr.add_alias("step1", "step2")
    mgr.add_alias("step2", "version")

    resolved_cmd, resolved_args = mgr.resolve("step1", [])
    assert resolved_cmd == "version"
    assert resolved_args == []


def test_alias_loop_prevention_on_add(tmp_path: Path) -> None:
    """Test that creating a circular alias is detected and rejected."""
    cfg = ConfigManager(base_dir=tmp_path)
    mgr = AliasManager(cfg)

    # a -> a
    with pytest.raises(AliasLoopError) as exc_info:
        mgr.add_alias("loop1", "loop1")
    assert "Alias loop detected" in str(exc_info.value)

    # a -> b, then b -> a
    mgr.add_alias("chain-a", "chain-b")
    with pytest.raises(AliasLoopError) as exc_info:
        mgr.add_alias("chain-b", "chain-a")
    assert "Alias loop detected" in str(exc_info.value)


def test_alias_loop_detection_during_resolve(tmp_path: Path) -> None:
    """Test that resolving a circular alias raises AliasLoopError."""
    cfg = ConfigManager(base_dir=tmp_path)
    # Manually inject loop into config
    cfg.data["aliases"]["loop-x"] = "loop-y"
    cfg.data["aliases"]["loop-y"] = "loop-x"

    mgr = AliasManager(cfg)
    with pytest.raises(AliasLoopError) as exc_info:
        mgr.resolve("loop-x", [])
    assert "Alias loop detected" in str(exc_info.value)


def test_alias_conflict_with_registered_command(tmp_path: Path) -> None:
    """Test that creating an alias matching a built-in command is rejected."""
    cfg = ConfigManager(base_dir=tmp_path)
    mgr = AliasManager(cfg)

    reg = CommandRegistry()
    dummy = lambda ctx, args: None
    reg.register(CommandInfo("help", "Help desc", dummy, "help", category="Builtins"))

    with pytest.raises(AliasConflictError) as exc_info:
        mgr.add_alias("help", "version", registry=reg)
    assert "conflicts with registered command" in str(exc_info.value)


def test_unalias(tmp_path: Path) -> None:
    """Test removing an alias."""
    cfg = ConfigManager(base_dir=tmp_path)
    mgr = AliasManager(cfg)

    mgr.add_alias("temp", "version")
    assert mgr.get("temp") == "version"

    removed = mgr.remove_alias("temp")
    assert removed is True
    assert mgr.get("temp") is None

    # Removing non-existent returns False
    assert mgr.remove_alias("temp") is False
