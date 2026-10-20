"""Application discovery and detached process launching for Windows."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

from core.logging_config import get_logger

logger = get_logger()

# Detached process flags for Windows to decouple child process lifecycle and prevent console output
DETACHED_FLAGS = (
    getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
)

# Known non-recursive candidate paths for standard Windows apps
KNOWN_APP_LOCATIONS: dict[str, list[str]] = {
    "code": [
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
        r"%PROGRAMFILES(X86)%\Microsoft VS Code\Code.exe",
    ],
    "spotify": [
        r"%APPDATA%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
    ],
    "discord": [
        r"%LOCALAPPDATA%\Discord\Update.exe",
        r"%LOCALAPPDATA%\Discord\app-1.0.9000\Discord.exe",
    ],
    "whatsapp": [
        r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe",
        r"%PROGRAMFILES%\WhatsApp\WhatsApp.exe",
    ],
    "notepad": [
        r"%WINDIR%\System32\notepad.exe",
        r"%WINDIR%\notepad.exe",
    ],
    "calculator": [
        r"%WINDIR%\System32\calc.exe",
    ],
    "calc": [
        r"%WINDIR%\System32\calc.exe",
    ],
}


def is_startfile_target(target: str) -> bool:
    """Return True if target should be launched directly via os.startfile.
    
    Includes protocol URIs (spotify:, discord:, whatsapp:), URL schemes,
    and Windows shell virtual paths (shell:AppsFolder\\...).
    """
    stripped = target.strip()
    if stripped.lower().startswith("shell:"):
        return True
    if stripped.endswith(":") and len(stripped) > 2 and "\\" not in stripped and "/" not in stripped:
        return True
    return bool("://" in stripped or stripped.lower().startswith(("spotify:", "discord:", "whatsapp:", "mailto:", "ms-")))


def is_uri(target: str) -> bool:
    """Return True if target is a protocol URI or startfile target."""
    return is_startfile_target(target)


def find_executable(target: str) -> str | None:
    """Find the full executable path for an application.
    
    Checks PATH first, then a short list of known static Windows paths.
    Does NOT scan recursively.
    """
    stripped = target.strip()

    # 1. Direct path check (with env variable expansion)
    expanded = os.path.expandvars(stripped)
    candidate_path = Path(os.path.expanduser(expanded))
    if candidate_path.is_file():
        return str(candidate_path)

    # 2. PATH-based discovery via shutil.which
    which_path = shutil.which(stripped)
    if which_path:
        return which_path

    # Try with .exe extension if not present
    if not stripped.lower().endswith(".exe"):
        which_exe = shutil.which(f"{stripped}.exe")
        if which_exe:
            return which_exe

    # 3. Known static locations for standard apps
    clean_key = Path(stripped).stem.lower()
    if clean_key in KNOWN_APP_LOCATIONS:
        for raw_loc in KNOWN_APP_LOCATIONS[clean_key]:
            expanded_loc = Path(os.path.expandvars(raw_loc))
            if expanded_loc.is_file():
                return str(expanded_loc)

    return None


def launch_detached(target: str, args: Sequence[str] | None = None) -> bool:
    """Launch an application detached from MayuriShell with all console output silenced.
    
    This is the SINGLE entry point for all application launches in MayuriShell.
    No other code may call Popen or os.startfile for apps directly.
    
    1. For URI (spotify:, discord:, whatsapp:) and shell:AppsFolder targets:
       Launches via subprocess.Popen(["explorer.exe", target]) with DEVNULL streams and shell=False,
       so the parent process is Explorer and cannot attach to MayuriShell's console.
    
    2. For executable paths:
       Uses subprocess.Popen with CREATE_NEW_CONSOLE, STARTUPINFO with SW_HIDE, DEVNULL for all
       three streams, close_fds=True, and shell=False. Falls back to explorer.exe if execution fails.
    
    Returns:
        True if application was successfully launched, False otherwise.
    """
    cmd_args = list(args) if args else []
    stripped = target.strip()

    # 1. Handle URI-based, protocol, and Microsoft Store app launching via explorer.exe
    if is_startfile_target(stripped):
        try:
            logger.info("Launching URI/Store target via explorer.exe: '%s'", stripped)
            subprocess.Popen(
                ["explorer.exe", stripped],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            return True
        except Exception as exc:
            logger.error("Failed to launch URI/Store target '%s' via explorer.exe: %s", stripped, exc)
            return False

    # 2. Handle executable launching
    exe_path = find_executable(stripped)
    if not exe_path:
        logger.warning("Application executable not found for: '%s'", stripped)
        return False

    cmd_list = [exe_path] + cmd_args
    try:
        logger.info("Launching executable with CREATE_NEW_CONSOLE: %s", cmd_list)
        startupinfo = None
        creationflags = 0

        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

        subprocess.Popen(
            cmd_list,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
            close_fds=True,
            shell=False,
        )
        return True
    except Exception as exc:
        logger.warning("Failed direct launch for '%s': %s. Falling back to explorer.exe.", exe_path, exc)
        try:
            subprocess.Popen(
                ["explorer.exe", exe_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            return True
        except Exception as fallback_exc:
            logger.error("Explorer fallback failed for '%s': %s", exe_path, fallback_exc)
            return False


# Primary alias to ensure single launch function requirement
launch_application = launch_detached
