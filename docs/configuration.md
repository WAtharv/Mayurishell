# MayuriShell Configuration Guide

This guide documents MayuriShell's configuration structure, default settings, storage locations, backup mechanics, and customization options.

---

## 1. File Locations

All personal user configuration, command history, execution logs, and backups live strictly inside your Windows user profile:

```text
%APPDATA%\MayuriShell\
├── config.json          # Main configuration file
├── history.json         # Persisted command history
├── organize_undo.json   # Undo journals for 'organize' commands
├── logs/                # Rotating runtime logs
│   ├── mayurishell.log
│   ├── mayurishell.log.1
│   └── mayurishell.log.2
├── backups/             # Automatic and manual config backups
│   └── config_backup_YYYYMMDD_HHMMSS.json
└── templates/           # User-defined project scaffolding templates
```

> **Safety Notice:** MayuriShell never writes configuration, history, or logs inside its installation folder or the application directory. When upgrading or reinstalling, your settings and history are fully preserved.

---

## 2. Configuration Schema & Default Settings

`config.json` is written in standard UTF-8 JSON. When MayuriShell launches for the first time, it automatically generates a default `config.json` if one does not exist.

### Default Configuration (`config.json`)

```json
{
  "version": "0.1.0",
  "username": "Mayuri",
  "prompt_theme": "default",
  "prompt_template": "{username}@{hostname} > ",
  "display": {
    "theme": "kawaii",
    "mascot": "cat",
    "force_plain": false
  },
  "applications": {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "code": "code",
    "spotify": "spotify:",
    "discord": "discord:",
    "whatsapp": "whatsapp:"
  },
  "websites": {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
    "chatgpt": "https://chatgpt.com"
  },
  "folder_shortcuts": {
    "desktop": "~/Desktop",
    "downloads": "~/Downloads",
    "documents": "~/Documents",
    "projects": "~/Projects",
    "home": "~"
  },
  "aliases": {
    "yt": "youtube",
    "gh": "github",
    "dl": "downloads"
  },
  "search_directories": [
    "~/Desktop",
    "~/Documents",
    "~/Downloads"
  ],
  "excluded_directories": [
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "AppData"
  ],
  "organize_categories": {
    "Images": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff"],
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".md"],
    "Spreadsheets": [".xlsx", ".xls", ".csv", ".ods"],
    "Presentations": [".pptx", ".ppt", ".odp", ".key"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tar.gz", ".tar.bz2", ".tar.xz"],
    "Code": [".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".json", ".xml", ".yaml", ".yml", ".sql", ".sh", ".bat", ".ps1"],
    "Installers": [".exe", ".msi", ".iso", ".dmg", ".pkg"]
  },
  "workflows": {
    "web": {
      "description": "Open default web services",
      "steps": ["github", "youtube"]
    },
    "dev": {
      "description": "Open development tools and projects",
      "steps": ["code projects", "github"]
    }
  },
  "preferences": {
    "confirm_destructive": true,
    "show_welcome": true,
    "show_cwd_in_prompt": true,
    "reactive_mascot": "all",
    "prompt_symbol": ">",
    "prompt_host": "pc"
  }
}
```

---

## 3. Configuration Keys Reference

| Key | Type | Description |
|---|---|---|
| `version` | string | Internal configuration schema version (managed by MayuriShell). |
| `username` | string | Display name used in greeting messages and the prompt. |
| `prompt_theme` | string | Prompt styling preset (`default`, etc.). |
| `prompt_template` | string | Format string for the command line prompt. Supports `{username}` and `{hostname}`. |
| `display.theme` | string | Active color theme: `kawaii`, `catppuccin`, `tokyo-night`, `rose-pine`, `gruvbox`, or `plain`. |
| `display.mascot` | string | Active companion mascot: `cat`, `bunny`, `bear`, `fox`, `penguin`, or `shiba`. |
| `display.force_plain` | boolean | Set to `true` to force plain ASCII output without Unicode characters or colors. |
| `applications` | object | Mapping of shortcut names to executable paths, command names, or URI schemes. |
| `websites` | object | Mapping of shortcut names to URLs or search templates containing `{query}`. |
| `folder_shortcuts` | object | Named shortcuts for directories. Supports `~` (home) and `%ENVVARS%`. |
| `aliases` | object | Command aliases (e.g. `yt` -> `youtube`). |
| `search_directories` | array | List of base folders searched recursively by `find`. |
| `excluded_directories` | array | Directory names skipped during recursive searches (e.g. `.git`, `node_modules`). |
| `organize_categories` | object | Mapping of category folder names to file extension lists for `organize`. |
| `workflows` | object | Reusable workflows containing a `description` and a list of registered command `steps`. |
| `preferences.confirm_destructive` | boolean | Whether to require confirmation before file deletion, process killing, etc. |
| `preferences.show_welcome` | boolean | Whether to show the fetch-style startup screen on shell launch. |
| `preferences.show_cwd_in_prompt` | boolean | Whether to display the current working directory above the command line. |
| `preferences.reactive_mascot` | string | Mascot reaction policy: `"all"` (reactions after every command), `"errors"` (only on failure), or `"none"`. |
| `preferences.prompt_symbol` | string | Terminal prompt symbol (defaults to `>`). |
| `preferences.prompt_host` | string | Hostname displayed in prompt and fetch screen (defaults to `pc`). |

---

## 4. Backups and Recovery Mechanics

### Atomic Configuration Writes
MayuriShell protects against corruption during sudden power losses or interruptions by using atomic file writes:
1. Configuration is serialized and written to a temporary file in `%APPDATA%\MayuriShell\`.
2. The file is flushed to disk via `os.fsync()`.
3. The temporary file is atomically replaced over `config.json`.

### Automatic Backup Rotation
Before any destructive change or modification to configuration (such as adding/removing shortcuts, changing themes, or performing schema upgrades), MayuriShell automatically archives the existing `config.json` into `%APPDATA%\MayuriShell\backups\config_backup_<timestamp>.json`. The 5 most recent backups are retained automatically.

### Graceful Crash Recovery
If `config.json` becomes malformed or invalid (e.g. manual JSON syntax error edited in an external text editor):
1. MayuriShell backs up the damaged file as `config_corrupted_<timestamp>.json` so no data is lost.
2. It logs a warning explaining the exact parsing failure.
3. It falls back safely to default settings so the shell starts immediately without crashing.

### Manual Backup Commands
You can also inspect, create, and restore backups directly from within MayuriShell:
```text
mayuri@pc > config backup
mayuri@pc > config restore
mayuri@pc > config path
mayuri@pc > config reset
```
