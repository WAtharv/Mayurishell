"""Unit tests for configuration manager."""
from pathlib import Path
import json
import os

from core.config_manager import ConfigManager, safe_atomic_write


def test_default_config_creation(tmp_path: Path) -> None:
    """Test that default configuration is created if missing."""
    mgr = ConfigManager(base_dir=tmp_path)
    assert mgr.config_path.exists()
    assert mgr.get("username") == "Mayuri"
    assert mgr.get("version") == "0.1.0"
    assert isinstance(mgr.get("applications"), dict)


def test_config_get_and_set(tmp_path: Path) -> None:
    """Test setting and getting configuration values."""
    mgr = ConfigManager(base_dir=tmp_path)
    mgr.set("username", "Kurisu")
    assert mgr.get("username") == "Kurisu"

    # Reload from disk to verify persistence
    reloaded = ConfigManager(base_dir=tmp_path)
    assert reloaded.get("username") == "Kurisu"


def test_corrupted_config_recovery(tmp_path: Path) -> None:
    """Test recovery and backup when config.json has invalid JSON."""
    mgr = ConfigManager(base_dir=tmp_path)
    # Corrupt the config file intentionally
    with open(mgr.config_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json content ...")

    # Re-instantiate ConfigManager, should backup corrupted file and restore defaults
    recovered_mgr = ConfigManager(base_dir=tmp_path)
    assert recovered_mgr.get("username") == "Mayuri"
    
    # Check that backup file was created
    backups = list(recovered_mgr.backups_dir.glob("config_corrupt_*.json"))
    assert len(backups) == 1
    assert "{ invalid json" in backups[0].read_text(encoding="utf-8")


def test_safe_atomic_write(tmp_path: Path) -> None:
    """Test that safe_atomic_write writes file properly without leaving temp artifacts."""
    target = tmp_path / "test_file.json"
    data = json.dumps({"test": 123})
    safe_atomic_write(target, data)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"test": 123}
    # No temporary files should be left behind in directory
    assert list(tmp_path.iterdir()) == [target]


def test_manual_backup(tmp_path: Path) -> None:
    """Test manual backup creation."""
    mgr = ConfigManager(base_dir=tmp_path)
    backup_file = mgr.backup("test_backup")
    assert backup_file.exists()
    assert "test_backup" in backup_file.name


def test_expand_path(tmp_path: Path, monkeypatch) -> None:
    """Test environment variable and home directory expansion."""
    monkeypatch.setenv("TEST_MAYURI_VAR", "SampleFolder")
    expanded = ConfigManager.expand_path("%TEST_MAYURI_VAR%\\sub")
    assert "SampleFolder" in str(expanded)
