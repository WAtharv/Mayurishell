# MayuriShell 

**Your PC. Your Commands.**  
*A customizable command environment and personal productivity tool for Windows with a cozy, kawaii aesthetic.*

---

## What is MayuriShell?

MayuriShell is a keyboard-driven command shell for Windows written in Python. It replaces tedious desktop navigation and complex commands with short, memorable shortcuts (`spotify`, `code projects`, `organize downloads`, `find report.pdf`).

It pairs practical daily desktop utilities with an expressive Linux-"rice" aesthetic: soothing pastel color palettes, original animal companions (cat, bunny, bear, fox, penguin, shiba), and a dynamic mascot that reacts to your commands in real time.

---

## Features at a Glance

- **Fast Application & Website Launching:** Open installed apps and websites with single words. Pass arguments safely (e.g. `code .`, `code projects\my-app`) or search websites directly (`youtube lo-fi hip hop`, `github python`).
- **File Management & Navigation:** Built-in commands (`pwd`, `ls`, `cd`, `open`, `mkdir`, `touch`, `copy`, `move`, `rename`, `delete`) and folder bookmarks (`desktop`, `downloads`, `documents`, `projects`, `home`).
- **Safe Desktop Organization:** Automatically sort cluttered folders like `Downloads` into organized categories (`Images`, `Documents`, `Code`, etc.) with interactive preview plans, dry runs (`organize downloads --dry-run`), and reliable multi-step undo (`organize undo`).
- **Project Scaffolding:** Scaffold production-ready starter projects with one command (`create-project my-app --template fastapi`). Built-in templates for Python, Machine Learning, Data Science, Flask, and FastAPI, plus user-defined custom templates.
- **Workflow Automation:** Combine multiple registered commands into reusable routines (`workflow run dev`).
- **Hardware Telemetry & Process Management:** Inspect real-time system stats (`sysinfo`, `cpu`, `memory`, `disk`, `uptime`) and manage running processes with protected safeguards (`processes`, `process find chrome`, `process kill 1234`).
- **Aesthetic Customization:** 6 switchable themes (`kawaii`, `catppuccin`, `tokyo-night`, `rose-pine`, `gruvbox`, `plain`) and 6 adorable animal mascots whose expressions reflect command execution outcomes.
- **Zero-Crash Architecture:** Non-destructive safeguards, atomic configuration saves, and automatic recovery if settings are ever corrupted.

---

## Quick Start

```text
mayuri@pc > spotify                  # Launch Spotify
mayuri@pc > code projects\my-app     # Open a project folder in VS Code
mayuri@pc > youtube anime lofi       # Search YouTube in default browser
mayuri@pc > organize downloads       # Preview and sort downloaded files
mayuri@pc > find *.pdf               # Recursively search configured folders
mayuri@pc > sysinfo                  # Display system telemetry
mayuri@pc > theme catppuccin         # Switch color theme
mayuri@pc > mascot bunny             # Change your companion mascot
mayuri@pc > fetch                    # Show the companion fetch screen
```

Type `help` at any time to browse all available commands.

---

## Installation & Setup

### Option 1: Install via Windows Installer (Recommended)
1. Download `MayuriShell-<version>-setup.exe` from the latest release.
2. Run the setup wizard. It installs into `%LOCALAPPDATA%\Programs\MayuriShell` without requiring administrator privileges.
3. Launch **MayuriShell** from your Start menu or Desktop shortcut.

### Option 2: Portable Zip
1. Download `MayuriShell-<version>-win64.zip`.
2. Extract the folder anywhere on your computer (e.g. `C:\Tools\MayuriShell` or on a USB drive).
3. Double-click `MayuriShell.exe` to start immediately. No installation required.

### Option 3: Run from Source
Requires **Python 3.11+**:
```cmd
git clone https://github.com/WAtharv/Mayurishell.git
cd MayuriShell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

---

## Recommended Terminal Environment

For the best visual experience, run MayuriShell inside **Windows Terminal**:
- Windows Terminal supports 24-bit TrueColor and UTF-8 Unicode characters required for MayuriShell's pastel boxes and companion ascii-art.
- **Set as default on Windows 11:** Open **Windows Terminal Settings** -> **Startup** -> set **Default terminal application** to **Windows Terminal**.
- On older consoles (`cmd.exe`), MayuriShell automatically detects terminal limitations and falls back to a clean plain-text ASCII theme.

---

## Safety & Security Principles

MayuriShell is built to safely interact with your PC:
- **No Unsafe Execution:** Never uses `shell=True` with user input. Does not run arbitrary Python `eval` or execute arbitrary script files.
- **Guarded Destructive Operations:** File deletion (`delete`) and process termination (`process kill`) require explicit confirmation (`y/N`).
- **Protected Locations:** Protects Windows system directories, Program Files, drive roots, user home folders, and MayuriShell installation directories against accidental deletion or bulk moves.
- **Critical Process Safeguards:** System-critical processes (`System`, `csrss.exe`, `lsass.exe`, `explorer.exe`, etc.) are protected against termination.
- **Isolated User Data:** All configuration and history reside in `%APPDATA%\MayuriShell\`, never next to the executable.

---

## Documentation

- **[Command Catalog](docs/commands.md):** Complete listing of every registered command with descriptions, argument requirements, and examples.
- **[Configuration Guide](docs/configuration.md):** Complete schema documentation for `config.json`, file paths, and backup mechanisms.
- **[Packaging Guide](docs/packaging.md):** Instructions on compiling standalone Windows binaries with PyInstaller and Inno Setup, SmartScreen verification, and troubleshooting.
- **[Changelog](CHANGELOG.md):** Version history and feature release notes.

### Regenerating Command Documentation
Command documentation is generated directly from the live command registry metadata:
```cmd
python tools/gen_docs.py
```

---

## Command Line Options

MayuriShell supports standard non-interactive command-line switches:

```text
MayuriShell.exe --version          # Print MayuriShell version and exit
MayuriShell.exe --selftest         # Run non-interactive environment diagnostic tests
MayuriShell.exe --config-dir <dir> # Override configuration directory path
```

---

## License

MayuriShell is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Atharv Patil.

You are free to use, copy, modify, merge, publish, distribute, sublicense, and sell
copies of MayuriShell, subject to the conditions of the MIT License.

See the [LICENSE](LICENSE) file for the complete license terms.
