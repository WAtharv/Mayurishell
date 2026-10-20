"""Runtime path and environment helpers for MayuriShell."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def is_frozen() -> bool:
    """Return True if running as a bundled executable (e.g., PyInstaller)."""
    return getattr(sys, "frozen", False)


def get_app_root() -> Path:
    """Return the application installation or repository root directory.
    
    When running as a frozen executable, returns the directory containing the executable.
    When running from source, returns the repository root directory.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundle_resource_dir() -> Path:
    """Return directory containing bundled resources (sys._MEIPASS when frozen)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return get_app_root()


def validate_config_dir(target: Path | str) -> tuple[bool, str]:
    """Validate a requested custom configuration directory.
    
    Refuses drive roots, the user's home folder, Windows system directories,
    Program Files directories, and paths inside the MayuriShell install/project folder.
    """
    p = Path(target)
    try:
        res = p.resolve()
    except Exception as exc:
        return False, f"Invalid path '{target}': {exc}"

    # 1. Drive root
    if res.parent == res or str(res) == res.anchor:
        return False, "Config directory cannot be a drive root."

    # 2. User home folder
    home = Path.home().resolve()
    if res == home:
        return False, "Config directory cannot be the user home folder directly."

    # 3. Windows directory
    windir = Path(os.getenv("WINDIR", "C:\\Windows")).resolve()
    if res == windir or res == windir / "System32":
        return False, "Config directory cannot be a Windows system folder."

    # 4. Program Files
    prog_files = Path(os.getenv("ProgramFiles", "C:\\Program Files")).resolve()
    prog_x86 = Path(os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")).resolve()
    if res == prog_files or res == prog_x86:
        return False, "Config directory cannot be Program Files."

    # 5. Inside install folder or project folder
    app_root = get_app_root().resolve()
    is_inside_app = False
    try:
        is_inside_app = (res == app_root) or res.is_relative_to(app_root)
    except AttributeError:
        is_inside_app = (res == app_root) or str(res).startswith(str(app_root))

    if is_inside_app:
        folder_type = "install folder" if is_frozen() else "project folder"
        return False, f"Config directory cannot be inside the MayuriShell {folder_type}."

    return True, ""
