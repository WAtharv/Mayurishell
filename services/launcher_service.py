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
    """Validate and normalize a web URL or URL template with optional {query}.
    
    Only http and https URLs are permitted. The '{query}' placeholder is allowed
    at most once, and only in the path or query portion of the URL.
    Returns:
        (is_valid, normalized_url_or_error_message)
    """
    stripped = url.strip()
    if not stripped:
        return False, "URL cannot be empty."

    # Validate {query} placeholder position if present
    if "{query}" in stripped:
        if stripped.count("{query}") > 1:
            return False, "The '{query}' placeholder may appear at most once."
        # Verify {query} is not in the scheme or domain/netloc
        dummy_test = stripped.replace("{query}", "queryplaceholder")
        if not dummy_test.startswith(("http://", "https://")):
            dummy_test = f"https://{dummy_test}"
            stripped = f"https://{stripped}"
        try:
            parsed_dummy = urllib.parse.urlsplit(dummy_test)
            if "queryplaceholder" in (parsed_dummy.scheme or ""):
                return False, "The '{query}' placeholder is not allowed in the URL scheme."
            if "queryplaceholder" in (parsed_dummy.netloc or ""):
                return False, "The '{query}' placeholder is not allowed in the domain/hostname."
        except Exception as exc:
            return False, f"Malformed URL template: {exc}"

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


def clean_search_query(query: str) -> tuple[bool, str]:
    """Strip control characters and newlines from queries and validate length.
    
    Returns:
        (is_valid, cleaned_query_or_error_message)
    """
    cleaned = "".join(c for c in query if ord(c) >= 32 and ord(c) != 127).strip()
    if not cleaned:
        return False, "Search query cannot be empty."
    if len(cleaned) > 200:
        return False, "Search query exceeds maximum length of 200 characters."
    return True, cleaned


def get_plain_homepage_url(url: str) -> str:
    """Return the plain scheme + host URL for a URL or template."""
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme or "https"
        return f"{scheme}://{parsed.netloc}"
    except Exception:
        return url


def format_website_url(
    template_or_url: str,
    query_args: Sequence[str] | None = None,
    site_name: str = "",
) -> tuple[bool, str]:
    """Resolve a website URL template with optional query arguments.
    
    If query_args are supplied:
      - Validates that template_or_url contains '{query}'.
      - Strips control characters, ensures non-empty, length <= 200.
      - URL-encodes with quote_plus.
      - Verifies that final URL retains the exact scheme and host of the template.
    If no query_args are supplied:
      - Returns plain homepage URL (scheme + host only) if template contains '{query}'.
      - Returns raw URL otherwise.
    
    Returns:
        (success, url_or_error_message)
    """
    if query_args:
        if "{query}" not in template_or_url:
            name_prefix = f"{site_name} " if site_name else ""
            return (
                False,
                f"{name_prefix}search is not set up for this site, use add-website to add a {{query}} template",
            )

        raw_query = " ".join(query_args)
        valid, cleaned_or_err = clean_search_query(raw_query)
        if not valid:
            return False, cleaned_or_err

        encoded_query = urllib.parse.quote_plus(cleaned_or_err)
        final_url = template_or_url.replace("{query}", encoded_query)

        # Integrity check: Ensure final URL still has the same scheme and host
        try:
            parsed_tmpl = urllib.parse.urlsplit(template_or_url)
            parsed_final = urllib.parse.urlsplit(final_url)
            if (
                parsed_final.scheme.lower() != parsed_tmpl.scheme.lower()
                or parsed_final.netloc.lower() != parsed_tmpl.netloc.lower()
            ):
                return False, "Security error: resolved URL host or scheme does not match the template."
        except Exception as exc:
            return False, f"Failed to verify resolved URL: {exc}"

        return True, final_url

    # No query arguments: open plain homepage URL if template contains {query}
    if "{query}" in template_or_url:
        return True, get_plain_homepage_url(template_or_url)

    return True, template_or_url


def launch_website(url: str, site_name: str | None = None) -> tuple[bool, str]:
    """Validate and open a website in the default browser.
    
    Logs only the site/shortcut name or domain, never the search query.
    Returns:
        (success, message)
    """
    valid, norm_url_or_err = validate_web_url(url)
    if not valid:
        return False, norm_url_or_err

    # Log target without sensitive search query parameters
    try:
        parsed = urllib.parse.urlsplit(norm_url_or_err)
        log_name = site_name if site_name else f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        log_name = site_name or "website"

    try:
        logger.info("Opening website shortcut '%s'", log_name)
        opened = webbrowser.open(norm_url_or_err)
        logger.info("Website launch completed: '%s'", log_name)
        if opened:
            return True, f"Opened {log_name}"
        return True, f"Requested browser to open {log_name}"
    except Exception as exc:
        logger.error("Failed to open website '%s': %s", log_name, exc)
        return False, f"Failed to open browser: {exc}"


def launch_folder(raw_path: str | Path, shortcut_name: str | None = None) -> tuple[bool, str, Path]:
    """Expand, verify, and open a directory in File Explorer.
    
    Logs only shortcut name or generic action, not full argument path.
    Returns:
        (success, message, expanded_path)
    """
    expanded_str = os.path.expandvars(str(raw_path))
    target_path = Path(os.path.expanduser(expanded_str)).resolve()

    if not target_path.exists():
        return False, f"Folder does not exist: '{target_path}'", target_path

    if not target_path.is_dir():
        return False, f"Path is a file, not a directory: '{target_path}'", target_path

    log_desc = f"shortcut '{shortcut_name}'" if shortcut_name else "folder"
    try:
        logger.info("Opening %s in File Explorer", log_desc)
        if hasattr(os, "startfile"):
            os.startfile(str(target_path))
        else:
            subprocess.Popen(["explorer.exe", str(target_path)], shell=False)
        logger.info("Opened %s successfully", log_desc)
        return True, f"Opened {target_path}", target_path
    except Exception as exc:
        logger.error("Failed to open %s: %s", log_desc, exc)
        return False, f"Failed to open File Explorer: {exc}", target_path
