"""Launch services for websites and file explorer folder shortcuts."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import urllib.parse
import webbrowser

from core.logging_config import get_logger

logger = get_logger()


def validate_web_url(url: str) -> tuple[bool, str]:
    """Validate and normalize a web URL.
    
    Only http and https URLs are permitted.
    Returns:
        (is_valid, normalized_url_or_error_message)
    """
    stripped = url.strip()
    if not stripped:
        return False, "URL cannot be empty."

    try:
        parsed = urllib.parse.urlsplit(stripped)
        if parsed.scheme:
            if parsed.scheme.lower() not in ("http", "https"):
                return False, f"Invalid scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed."
        else:
            # Default to https:// if no scheme was specified
            stripped = f"https://{stripped}"
            parsed = urllib.parse.urlsplit(stripped)

        if not parsed.netloc:
            return False, "Invalid URL: missing domain/hostname."

        return True, stripped
    except Exception as exc:
        return False, f"Malformed URL: {exc}"


def launch_website(url: str) -> tuple[bool, str]:
    """Validate and open a website in the default browser.
    
    Returns:
        (success, message)
    """
    valid, norm_url_or_err = validate_web_url(url)
    if not valid:
        return False, norm_url_or_err

    try:
        logger.info("Opening website: %s", norm_url_or_err)
        opened = webbrowser.open(norm_url_or_err)
        if opened:
            return True, f"Opened {norm_url_or_err}"
        return True, f"Requested browser to open {norm_url_or_err}"
    except Exception as exc:
        logger.error("Failed to open URL '%s': %s", norm_url_or_err, exc)
        return False, f"Failed to open browser: {exc}"


def launch_folder(raw_path: str | Path) -> tuple[bool, str, Path]:
    """Expand, verify, and open a directory in File Explorer.
    
    Returns:
        (success, message, expanded_path)
    """
    expanded_str = os.path.expandvars(str(raw_path))
    target_path = Path(os.path.expanduser(expanded_str)).resolve()

    if not target_path.exists():
        return False, f"Folder does not exist: '{target_path}'", target_path

    if not target_path.is_dir():
        return False, f"Path is a file, not a directory: '{target_path}'", target_path

    try:
        logger.info("Opening folder in File Explorer: %s", target_path)
        if hasattr(os, "startfile"):
            os.startfile(str(target_path))
        else:
            subprocess.Popen(["explorer.exe", str(target_path)], shell=False)
        return True, f"Opened {target_path}", target_path
    except Exception as exc:
        logger.error("Failed to open folder '%s': %s", target_path, exc)
        return False, f"Failed to open File Explorer: {exc}", target_path
