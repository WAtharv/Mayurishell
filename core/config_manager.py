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
from core.version import VERSION

logger = get_logger()

DEFAULT_CONFIG: dict[str, Any] = {
    "version": VERSION,
    "username": "Mayuri",
    "prompt_theme": "default",
    "prompt_template": "{username}@{hostname} > ",
    "display": {
        "theme": "kawaii",
        "mascot": "cat",
        "force_plain": False,
    },
    "applications": {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "code": "code",
        "spotify": "spotify:",
        "discord": "discord:",
        "whatsapp": "whatsapp:",
    },
    "websites": {
        "youtube": "https://www.youtube.com/results?search_query={query}",
        "github": "https://github.com/search?q={query}",
        "google": "https://www.google.com/search?q={query}",
        "chatgpt": "https://chatgpt.com",
    },
    "folder_shortcuts": {
        "desktop": "~/Desktop",
        "downloads": "~/Downloads",
        "documents": "~/Documents",
        "projects": "~/Projects",
        "home": "~",
    },
    "aliases": {
        "yt": "youtube",
        "gh": "github",
        "dl": "downloads",
    },
    "search_directories": ["~/Desktop", "~/Documents", "~/Downloads"],
    "excluded_directories": [".git", "node_modules", ".venv", "__pycache__", "AppData"],
    "organize_categories": {
        "Images": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff"],
        "Documents": [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".md"],
        "Spreadsheets": [".xlsx", ".xls", ".csv", ".ods"],
        "Presentations": [".pptx", ".ppt", ".odp", ".key"],
        "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tar.gz", ".tar.bz2", ".tar.xz"],
        "Code": [".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".json", ".xml", ".yaml", ".yml", ".sql", ".sh", ".bat", ".ps1"],
        "Installers": [".exe", ".msi", ".iso", ".dmg", ".pkg"],
    },
    "workflows": {
        "web": {
            "description": "Open default web services",
            "steps": ["github", "youtube"],
        },
        "dev": {
            "description": "Open development tools and projects",
            "steps": ["code projects", "github"],
        },
    },
    "preferences": {
        "confirm_destructive": True,
        "show_welcome": True,
        "show_cwd_in_prompt": True,
        "reactive_mascot": "all",
        "prompt_symbol": ">",
        "prompt_host": "pc",
    },
}


OLD_DEFAULT_WEBSITES: dict[str, set[str]] = {
    "youtube": {"https://www.youtube.com", "https://youtube.com"},
    "google": {"https://www.google.com", "https://google.com"},
    "github": {"https://github.com", "https://www.github.com"},
}

NEW_WEBSITE_TEMPLATES: dict[str, str] = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "google": "https://www.google.com/search?q={query}",
    "github": "https://github.com/search?q={query}",
}


def deep_merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Recursively add missing keys from defaults into target without overwriting existing values."""
    for key, def_val in defaults.items():
        if key not in target:
            target[key] = copy.deepcopy(def_val)
        elif key == "organize_categories":
            # Requirement 7: Keep user edits; do not re-add categories or extensions the user removed
            continue
        elif key == "workflows":
            # Keep user workflows; do not overwrite or force re-add
            continue
        elif isinstance(target[key], dict) and isinstance(def_val, dict):
            deep_merge_defaults(target[key], def_val)
        elif isinstance(target[key], list) and not target[key] and def_val:
            target[key] = copy.deepcopy(def_val)
    return target


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

    def _upgrade_config(self, loaded: dict[str, Any]) -> bool:
        """Upgrade old default website URLs and add missing default workflows.
        
        Never touches customized URLs or existing workflows.
        Returns True if changes were made.
        """
        upgraded = False
        websites = loaded.get("websites")
        if isinstance(websites, dict):
            for site_key, old_urls in OLD_DEFAULT_WEBSITES.items():
                if site_key in websites:
                    stored_url = websites[site_key]
                    if stored_url in old_urls:
                        websites[site_key] = NEW_WEBSITE_TEMPLATES[site_key]
                        upgraded = True
                        logger.info("Upgraded website shortcut '%s' to query template.", site_key)

        workflows = loaded.get("workflows")
        if not isinstance(workflows, dict):
            loaded["workflows"] = copy.deepcopy(DEFAULT_CONFIG["workflows"])
            upgraded = True
        else:
            if "dev" not in workflows:
                workflows["dev"] = copy.deepcopy(DEFAULT_CONFIG["workflows"]["dev"])
                upgraded = True
                logger.info("Added missing default workflow 'dev'.")

        return upgraded

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
            
            # Merge with default keys to ensure new config keys and shortcuts exist
            deep_merge_defaults(loaded, DEFAULT_CONFIG)
            upgraded = self._upgrade_config(loaded)
            self.data = loaded
            if upgraded:
                self.save()
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
        """Get a configuration value, supporting dotted keys e.g. 'display.theme'."""
        if "." in key:
            parts = key.split(".")
            curr = self.data
            for p in parts:
                if isinstance(curr, dict) and p in curr:
                    curr = curr[p]
                else:
                    return default
            return curr
        return self.data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Set a configuration value, supporting dotted keys e.g. 'display.force_plain'."""
        if "." in key:
            parts = key.split(".")
            curr = self.data
            for p in parts[:-1]:
                if p not in curr or not isinstance(curr[p], dict):
                    curr[p] = {}
                curr = curr[p]
            curr[parts[-1]] = value
        else:
            self.data[key] = value
        if auto_save:
            self.save()

    def get_applications(self) -> dict[str, str]:
        """Return dict of configured applications."""
        return dict(self.data.get("applications", {}))

    def get_websites(self) -> dict[str, str]:
        """Return dict of configured websites."""
        return dict(self.data.get("websites", {}))

    def get_folder_shortcuts(self) -> dict[str, str]:
        """Return dict of configured folder shortcuts."""
        return dict(self.data.get("folder_shortcuts", {}))

    def get_aliases(self) -> dict[str, str]:
        """Return dict of configured aliases."""
        return dict(self.data.get("aliases", {}))

    def set_shortcut(self, section: str, name: str, value: str) -> None:
        """Set a shortcut under specified section (applications, websites, folder_shortcuts, aliases)."""
        if section not in self.data or not isinstance(self.data[section], dict):
            self.data[section] = {}
        self.data[section][name.lower()] = value
        self.save()

    def remove_shortcut(self, section: str, name: str) -> bool:
        """Remove a shortcut under specified section."""
        if section in self.data and isinstance(self.data[section], dict):
            key = name.lower()
            if key in self.data[section]:
                del self.data[section][key]
                self.save()
                return True
        return False

    def get_organize_categories(self) -> dict[str, list[str]]:
        """Return dict of configured organize categories and their extension lists."""
        cats = self.data.get("organize_categories")
        if isinstance(cats, dict):
            return {
                str(k): [str(ext).lower() for ext in v]
                for k, v in cats.items()
                if isinstance(v, list)
            }
        return copy.deepcopy(DEFAULT_CONFIG["organize_categories"])

    def get_workflows(self) -> dict[str, Any]:
        """Return dict of configured workflows."""
        wfs = self.data.get("workflows")
        if isinstance(wfs, dict):
            return dict(wfs)
        return copy.deepcopy(DEFAULT_CONFIG["workflows"])

    def get_workflow(self, name: str) -> dict[str, Any] | None:
        """Return a specific workflow dict if configured."""
        wfs = self.get_workflows()
        return wfs.get(name.lower())

    def set_workflow(self, name: str, data: dict[str, Any]) -> None:
        """Add or update a workflow definition and persist config."""
        if "workflows" not in self.data or not isinstance(self.data["workflows"], dict):
            self.data["workflows"] = {}
        self.data["workflows"][name.lower()] = data
        self.save()

    def remove_workflow(self, name: str) -> bool:
        """Remove a workflow definition and persist config."""
        if "workflows" in self.data and isinstance(self.data["workflows"], dict):
            key = name.lower()
            if key in self.data["workflows"]:
                del self.data["workflows"][key]
                self.save()
                return True
        return False

    @staticmethod
    def expand_path(raw_path: str | Path) -> Path:
        """Expand ~ and Windows environment variables in paths."""
        expanded = os.path.expandvars(str(raw_path))
        return Path(os.path.expanduser(expanded)).resolve()

    def get_theme_name(self) -> str:
        """Get the configured theme name with validation and fallback."""
        val = self.data.get("display", {}).get("theme", "kawaii")
        if not isinstance(val, str):
            logger.warning("Invalid theme type in config: %s. Falling back to 'kawaii'.", type(val))
            return "kawaii"
        clean = val.strip().lower()
        valid = {"kawaii", "catppuccin", "tokyo-night", "rose-pine", "gruvbox", "plain"}
        if clean not in valid:
            logger.warning("Unknown theme '%s' in config. Falling back to 'kawaii'.", val)
            return "kawaii"
        return clean

    def set_theme_name(self, name: str) -> None:
        """Set and persist active theme name."""
        if "display" not in self.data or not isinstance(self.data["display"], dict):
            self.data["display"] = {}
        self.data["display"]["theme"] = name.strip().lower()
        self.save()

    def get_mascot_name(self) -> str:
        """Get the configured mascot name with validation and fallback."""
        val = self.data.get("display", {}).get("mascot", "cat")
        if not isinstance(val, str):
            logger.warning("Invalid mascot type in config: %s. Falling back to 'cat'.", type(val))
            return "cat"
        clean = val.strip().lower()
        valid = {"cat", "bunny", "bear", "fox", "penguin", "shiba", "random"}
        if clean not in valid:
            logger.warning("Unknown mascot '%s' in config. Falling back to 'cat'.", val)
            return "cat"
        return clean

    def set_mascot_name(self, name: str) -> None:
        """Set and persist active mascot name."""
        if "display" not in self.data or not isinstance(self.data["display"], dict):
            self.data["display"] = {}
        self.data["display"]["mascot"] = name.strip().lower()
        self.save()

    def is_force_plain(self) -> bool:
        """Return True if display.force_plain is enabled."""
        return bool(self.data.get("display", {}).get("force_plain", False))

    def get_reactive_mascot_mode(self) -> str:
        """Get reactive mascot setting: 'all', 'errors', or 'off'."""
        val = self.data.get("preferences", {}).get("reactive_mascot", "all")
        if isinstance(val, bool):
            return "all" if val else "off"
        if not isinstance(val, str):
            return "all"
        clean = val.strip().lower()
        if clean not in ("all", "errors", "off"):
            logger.warning("Invalid reactive_mascot mode '%s'. Falling back to 'all'.", val)
            return "all"
        return clean

    def get_prompt_symbol(self) -> str:
        """Get the prompt symbol string (default '>')."""
        val = self.data.get("preferences", {}).get("prompt_symbol", ">")
        return str(val) if val else ">"

    def get_prompt_host(self) -> str:
        """Get the prompt host name (default 'pc')."""
        val = self.data.get("preferences", {}).get("prompt_host", "pc")
        return str(val) if val else "pc"
