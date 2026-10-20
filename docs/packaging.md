# MayuriShell Packaging & Distribution Guide

This document explains how MayuriShell is packaged into a standalone Windows application, how to build releases, and how to resolve common distribution issues.

---

## 1. Overview

MayuriShell is distributed in two formats:
1. **Portable Zip (`MayuriShell-<version>-win64.zip`)**: A self-contained folder that can be unzipped anywhere and run without installation or administrator privileges.
2. **Windows Installer (`MayuriShell-<version>-setup.exe`)**: Built with Inno Setup 6, providing Start menu shortcuts, an optional desktop shortcut, and a clean Windows uninstaller.

Neither distribution requires Python to be installed on the destination computer.

---

## 2. Prerequisites for Building

To build MayuriShell binaries from source on Windows:
- **Windows 10 or 11 (64-bit)**
- **Python 3.11+**
- **pip** and **virtualenv**
- **Inno Setup 6** (optional; required only if generating the setup executable). Download from: [https://jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)

---

## 3. Repeatable Windows Build Process

The repository includes automated batch scripts that perform tests, compile the binaries, verify the build, and generate checksums.

### Step 1: Build the Portable Executable & Release Zip

Open PowerShell or Command Prompt in the repository root and run:

```cmd
packaging\build_windows.bat
```

The script performs the following actions automatically:
1. Checks for Python, pip, and a virtual environment.
2. Installs production dependencies (`requirements.txt`) and dev dependencies (`requirements-dev.txt`).
3. Runs the full test suite (`pytest`). **Build halts immediately if any test fails.**
4. Cleans previous compilation artifacts (`build/` and `dist/MayuriShell/`).
5. Invokes PyInstaller with `packaging/mayurishell.spec` to create `dist\MayuriShell\`.
6. Executes smoke tests directly against the compiled binary:
   - `dist\MayuriShell\MayuriShell.exe --version`
   - `dist\MayuriShell\MayuriShell.exe --selftest`
7. Creates a standalone archive: `dist\MayuriShell-<version>-win64.zip`.
8. Generates a SHA256 checksum file: `dist\MayuriShell-<version>-win64.zip.sha256`.

### Step 2: Build the Inno Setup Windows Installer

After completing Step 1, run:

```cmd
packaging\build_installer.bat
```

- If **Inno Setup 6** (`ISCC.exe`) is detected on your system, it compiles `packaging\installer.iss` into `dist\MayuriShell-<version>-setup.exe`.
- If Inno Setup is not installed, the script prints an informative message with the download link and exits cleanly without failing the zip build.

---

## 4. PyInstaller Specification Details (`packaging/mayurishell.spec`)

- **Format:** One-folder application (`console=True`). One-folder builds launch significantly faster than one-file packages because they do not decompress the entire Python environment into `%TEMP%` on every startup.
- **UPX Compression:** Disabled (`upx=False`) to minimize antivirus false-positive triggers and maximize launch performance.
- **Hidden Imports:** Explicitly bundles prompt_toolkit formatting, Rich console/table renderers, psutil, and Send2Trash Windows platform hooks.
- **Exclusions:** Omits heavy, unneeded standard library modules (`tkinter`, `unittest`, `test`, `pydoc_data`) to keep the distribution size compact.
- **Version Resource:** Embedded Windows Version Info (Product Name: MayuriShell, File Version from `core/version.py`).

---

## 5. Inno Setup Configuration (`packaging/installer.iss`)

- **Privileges:** `PrivilegesRequired=lowest` (installs cleanly into `{localappdata}\Programs\MayuriShell` without requiring administrator elevation).
- **Shortcuts:** Adds a Start Menu shortcut (`MayuriShell.lnk`). Also adds an optional desktop shortcut (unchecked by default).
- **Windows Terminal Integration:** If Windows Terminal (`wt.exe`) is detected on the user's system during installation, an extra Start Menu shortcut is added to launch MayuriShell directly inside Windows Terminal.
- **Uninstallation Safety:** The uninstaller explicitly preserves user settings in `%APPDATA%\MayuriShell` by default. It prompts the user whether they wish to delete their settings with the default button set to **No**. On silent uninstallation, settings are always preserved.

---

## 6. Antivirus & Windows SmartScreen False Positives

### Understanding False Positives
Because MayuriShell is packaged using PyInstaller and does not have an expensive Microsoft Authenticode EV code-signing certificate ($400+/year), Windows SmartScreen and some heuristic antivirus engines may flag the new binary as "unrecognized" or "suspicious".

This is an industry-wide occurrence with unsigned open-source Python executables:
- The PyInstaller bootloader stub is commonly targeted by broad heuristic rules.
- Newly compiled files have zero reputation history in Microsoft's telemetry database.

### How Users Can Verify and Run Safely
1. **Verify Integrity:** Compare the SHA256 hash of your downloaded zip file against the published `.sha256` checksum:
   ```powershell
   Get-FileHash -Algorithm SHA256 MayuriShell-0.1.0-win64.zip
   ```
2. **SmartScreen Prompt:** When Windows SmartScreen displays "Windows protected your PC", click **More info** -> **Run anyway**.
3. **Alternative:** Users who prefer not to run pre-compiled binaries can always run MayuriShell directly from Python source:
   ```cmd
   git clone https://github.com/WAtharv/Mayurishell.git
   cd MayuriShell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python main.py
   ```

---

## 7. Recommended Terminal Environment

For the best experience, run MayuriShell in **Windows Terminal**:
- Modern Windows Terminal supports full 24-bit TrueColor and UTF-8 Unicode characters needed for MayuriShell's pastel themes and cute animal mascots.
- In Windows 11, set Windows Terminal as your default terminal:
  1. Open **Settings** -> **System** -> **For developers** (or Windows Terminal Settings).
  2. Set **Default terminal application** to **Windows Terminal**.
- If running under legacy `cmd.exe` without UTF-8 support, MayuriShell automatically detects console limitations and degrades gracefully into a plain-text ASCII fallback mode without crashing.
