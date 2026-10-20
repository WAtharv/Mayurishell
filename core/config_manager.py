"""Configuration manager for MayuriShell."""
from __future__ import annotations

import copy
import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from core.exceptions import ConfigError
from core.logging_config import get_logger

logger = get_logger()

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "0.1.0",
    "username": "Mayuri",
    "prompt_theme": "default",
    "prompt_template": "{username}@{hostname} > ",
    "applications": {},
    "websites": {},
    "folder_shortcuts": {},
    "aliases": {},
    "search_directories": [],
    "excluded_directories": [".git", "node_modules", ".venv", "__pycache__"],
    "preferences": {
        "confirm_destructive": True,
        "show_welcome": True,
    },
}


def get_default_appdata_dir() -> Path:
    """Return default application data directory (%APPDATA%\\MayuriShell)."""
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "MayuriShell"
    return Path.home() / "AppData" / "Roaming" / "MayuriShell"


def safe_atomic_write(target_path: Path, data_str: str) -> None:
    """Write string data safely using a temporary file followed by atomic replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = target_path.parent
    
    # Create temp file in same directory to ensure atomic replace across file systems
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
        temp_file_path = Path(tf.name)
        tf.write(data_str)
        tf.flush()
        os.fsync(tf.fileno())

    temp_file_path.replace(target_path)


class ConfigManager:
    """Manages loading, validating, and persisting MayuriShell configuration."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir if base_dir is not None else get_default_appdata_dir()
        self.config_path = self.base_dir / "config.json"
        self.logs_dir = self.base_dir / "logs"
        self.backups_dir = self.base_dir / "backups"
        self.history_path = self.base_dir / "history.json"
        
        self.data: dict[str, Any] = {}
        self._ensure_directories()
        self.load()

    def _ensure_directories(self) -> None:
        """Create standard application data directories."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        """Load configuration from disk. Recovers with defaults if missing or corrupted."""
        if not self.config_path.exists():
            logger.info("Config file not found. Creating default configuration at %s", self.config_path)
            self.data = copy.deepcopy(DEFAULT_CONFIG)
            self.save()
            return self.data

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            
            if not isinstance(loaded, dict):
                raise ConfigError("Configuration root must be a JSON object.")
            
            # Merge with default keys to ensure new config keys exist
            merged = copy.deepcopy(DEFAULT_CONFIG)
            merged.update(loaded)
            self.data = merged
            logger.info("Successfully loaded configuration from %s", self.config_path)
            return self.data

        except Exception as exc:
            logger.warning("Failed to load configuration from %s: %s. Backing up and restoring defaults.", self.config_path, exc)
            self.backup_corrupt_config()
            self.data = copy.deepcopy(DEFAULT_CONFIG)
            self.save()
            return self.data

    def backup_corrupt_config(self) -> Path | None:
        """Create a backup of corrupted config file."""
        if not self.config_path.exists():
            return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backups_dir / f"config_corrupt_{timestamp}.json"
        try:
            with open(self.config_path, "rb") as src, open(backup_file, "wb") as dst:
                dst.write(src.read())
            logger.info("Corrupted configuration backed up to %s", backup_file)
            return backup_file
        except OSError as e:
            logger.error("Failed to backup corrupted config: %s", e)
            return None

    def backup(self, tag: str = "manual") -> Path:
        """Create a timestamped backup of the current configuration."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backups_dir / f"config_{tag}_{timestamp}.json"
        safe_atomic_write(backup_file, json.dumps(self.data, indent=2, ensure_ascii=False))
        logger.info("Config backed up to %s", backup_file)
        return backup_file

    def save(self) -> None:
        """Safely save current configuration to config.json using atomic file replacement."""
        serialized = json.dumps(self.data, indent=2, ensure_ascii=False)
        safe_atomic_write(self.config_path, serialized)
        logger.debug("Configuration saved to %s", self.config_path)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by top-level key."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Set a configuration value and optionally persist immediately."""
        self.data[key] = value
        if auto_save:
            self.save()

    @staticmethod
    def expand_path(raw_path: str | Path) -> Path:
        """Expand ~ and Windows environment variables in paths."""
        expanded = os.path.expandvars(str(raw_path))
        return Path(os.path.expanduser(expanded)).resolve()
