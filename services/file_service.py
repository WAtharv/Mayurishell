"""File, navigation, and search services for MayuriShell."""
from __future__ import annotations

from dataclasses import dataclass
import datetime
import fnmatch
import os
from pathlib import Path
import shutil
import sys
from typing import Sequence

import send2trash

from core.logging_config import get_logger

logger = get_logger()

EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".js", ".lnk"}


@dataclass
class FileInfo:
    """Represents file or directory metadata."""
    name: str
    path: Path
    is_dir: bool
    size: int
    mtime: float
    is_hidden: bool

    @property
    def formatted_size(self) -> str:
        if self.is_dir:
            return "<DIR>"
        return format_bytes(self.size)

    @property
    def formatted_mtime(self) -> str:
        dt = datetime.datetime.fromtimestamp(self.mtime)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_bytes(size: int) -> str:
    """Format byte size into human-readable representation."""
    if size < 1024:
        return f"{size} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def is_network_or_removable(path: Path) -> bool:
    """Check if path resides on a removable, network, or UNC drive."""
    resolved = path.resolve()
    path_str = str(resolved)
    if path_str.startswith(r"\\"):
        return True

    if sys.platform == "win32":
        try:
            import ctypes
            drive = os.path.splitdrive(path_str)[0]
            if drive:
                drive_root = drive + "\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_root)
                # DRIVE_REMOVABLE = 2, DRIVE_REMOTE = 4, DRIVE_CDROM = 5, DRIVE_RAMDISK = 6
                if drive_type in (2, 4, 5):
                    return True
        except Exception as exc:
            logger.debug("Drive type check failed for %s: %s", path_str, exc)
    return False


def is_protected_path(
    target: Path,
    current_dir: Path,
    appdata_dir: Path,
    project_root: Path,
    folder_shortcuts: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Check if a path is protected against deletion.
    
    Refuses: drive roots, home folder, Windows directory, Program Files,
    the MayuriShell project folder, %APPDATA%\\MayuriShell, current directory
    or any parent directory, and configured folder shortcuts themselves.
    """
    try:
        res_target = target.resolve()
    except Exception:
        res_target = target

    # 1. Drive roots (e.g. C:\)
    if res_target.parent == res_target or str(res_target) == res_target.anchor:
        return True, "Cannot delete drive root."

    # 2. User home folder
    home = Path.home().resolve()
    if res_target == home:
        return True, "Cannot delete user home directory."

    # 3. Windows directory
    windir = Path(os.getenv("WINDIR", "C:\\Windows")).resolve()
    if res_target == windir or res_target == windir / "System32":
        return True, "Cannot delete Windows system directory."

    # 4. Program Files
    prog_files = Path(os.getenv("ProgramFiles", "C:\\Program Files")).resolve()
    if res_target == prog_files:
        return True, "Cannot delete Program Files directory."
    prog_x86 = Path(os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")).resolve()
    if res_target == prog_x86:
        return True, "Cannot delete Program Files directory."

    # 5. Project root and AppData directory
    if res_target == project_root.resolve() or project_root.resolve().is_relative_to(res_target):
        return True, "Cannot delete MayuriShell project folder or its parents."
    if res_target == appdata_dir.resolve() or appdata_dir.resolve().is_relative_to(res_target):
        return True, "Cannot delete MayuriShell configuration/appdata directory."

    # 6. Current directory or any parent of it
    res_current = current_dir.resolve()
    if res_target == res_current:
        return True, "Cannot delete the current working directory."
    try:
        if res_current.is_relative_to(res_target):
            return True, "Cannot delete an ancestor of the current working directory."
    except AttributeError:
        # Fallback for Python < 3.9 if ever needed
        if str(res_current).startswith(str(res_target)):
            return True, "Cannot delete an ancestor of the current working directory."

    # 7. Configured folder shortcuts themselves
    if folder_shortcuts:
        for s_name, raw_s_path in folder_shortcuts.items():
            try:
                exp_shortcut = Path(os.path.expanduser(os.path.expandvars(raw_s_path))).resolve()
                if res_target == exp_shortcut:
                    return True, f"Cannot delete configured folder shortcut '{s_name}' directly."
            except Exception:
                continue

    return False, ""


def resolve_path(
    raw: str,
    current_dir: Path,
    folder_shortcuts: dict[str, str] | None = None,
) -> tuple[Path, str | None]:
    """Resolve a raw path string relative to current directory or folder shortcuts.
    
    If the argument matches both a local directory and a folder shortcut, the
    local directory in current_dir takes precedence.
    
    Returns:
        (resolved_path, note_if_shortcut_or_local_resolution)
    """
    stripped = raw.strip()
    if not stripped:
        return current_dir, None

    # Strip surrounding quotes
    if len(stripped) >= 2 and (
        (stripped.startswith('"') and stripped.endswith('"'))
        or (stripped.startswith("'") and stripped.endswith("'"))
    ):
        stripped = stripped[1:-1].strip()

    # 1. Local resolution check: if exists directly in current_dir
    local_candidate = (current_dir / stripped).resolve()
    if (current_dir / stripped).exists():
        # Document preference: if it also happened to match a shortcut
        note = None
        if folder_shortcuts and stripped.lower() in folder_shortcuts:
            note = f"Resolved to local path '{local_candidate.name}' (precedence over shortcut '{stripped.lower()}')."
        return local_candidate, note

    # 2. Folder shortcut match (exact or prefix like projects\my-app)
    if folder_shortcuts:
        if stripped.lower() in folder_shortcuts:
            shortcut_raw = folder_shortcuts[stripped.lower()]
            expanded = Path(os.path.expanduser(os.path.expandvars(shortcut_raw))).resolve()
            return expanded, f"Resolved folder shortcut '{stripped.lower()}' -> {expanded}"

        # Prefix match: check first path component
        first_part, sep, rest = stripped.partition("\\")
        if not sep:
            first_part, sep, rest = stripped.partition("/")
        if sep and first_part.lower() in folder_shortcuts:
            shortcut_raw = folder_shortcuts[first_part.lower()]
            base_dir = Path(os.path.expanduser(os.path.expandvars(shortcut_raw))).resolve()
            expanded_sub = (base_dir / rest).resolve()
            return expanded_sub, f"Resolved folder shortcut prefix '{first_part.lower()}' -> {expanded_sub}"

    # 3. Standard path expansion (~, %ENVVARS%, relative to current_dir)
    expanded_str = os.path.expanduser(os.path.expandvars(stripped))
    candidate = Path(expanded_str)

    if candidate.is_absolute() or (len(expanded_str) > 1 and expanded_str[1] == ":"):
        return candidate.resolve(), None

    return (current_dir / candidate).resolve(), None


def validate_app_path_argument(
    raw_arg: str,
    context: Any,
) -> tuple[bool, Path | None, str]:
    """Validate an argument destined for an application launcher or workflow app step.
    
    Rules:
      - App arguments must be existing paths only.
      - Refuse any argument that starts with '-' or '/' unless it resolves to an existing path.
      - Resolves relative paths against context.current_dir, expands ~ and folder shortcuts.
      - Returns (is_valid, resolved_absolute_path_or_None, error_message_or_info)
    """
    stripped = raw_arg.strip()
    if not stripped:
        return False, None, "Path argument cannot be empty."

    resolved_path, _ = context.resolve_path(stripped)
    resolved_exists = resolved_path.exists()

    # Refuse options/flags starting with '-' or '/' unless resolving to an existing path
    if stripped.startswith(("-", "/")):
        if not resolved_exists:
            return False, None, f"Argument '{stripped}' starts with '-' or '/' and does not resolve to an existing path."

    if not resolved_exists:
        if stripped.lower() == "projects":
            return False, resolved_path, "Folder 'projects' not found. Run: add-folder projects <path>"
        return False, resolved_path, f"Path does not exist: '{resolved_path}'"

    return True, resolved_path.resolve(), ""


def list_directory(
    directory: Path,
    pattern: str | None = None,
    show_hidden: bool = False,
) -> list[FileInfo]:
    """List directory contents with metadata, sorting, and pattern matching."""
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: '{directory}'")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: '{directory}'")

    results: list[FileInfo] = []
    for entry in directory.iterdir():
        name = entry.name
        is_hidden = name.startswith(".")

        if not show_hidden and is_hidden:
            continue

        try:
            stat = entry.stat()
            is_dir = entry.is_dir()
            size = stat.st_size if not is_dir else 0
            mtime = stat.st_mtime
        except (PermissionError, OSError):
            is_dir = entry.is_dir() if hasattr(entry, "is_dir") else False
            size = 0
            mtime = 0.0

        # Pattern filtering (only filters files, directories always listed unless pattern specified)
        if pattern:
            if not fnmatch.fnmatch(name.lower(), pattern.lower()):
                continue

        results.append(
            FileInfo(
                name=name,
                path=entry,
                is_dir=is_dir,
                size=size,
                mtime=mtime,
                is_hidden=is_hidden,
            )
        )

    # Sort directories first, then alphabetical
    results.sort(key=lambda x: (not x.is_dir, x.name.lower()))
    return results


def get_path_info(path: Path) -> dict[str, str | int]:
    """Gather detailed metadata about a file or directory."""
    if not path.exists():
        raise FileNotFoundError(f"File or directory not found: '{path}'")

    stat = path.stat()
    is_dir = path.is_dir()
    
    item_count = 0
    if is_dir:
        try:
            item_count = sum(1 for _ in path.iterdir())
        except (PermissionError, OSError):
            item_count = -1

    created_dt = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
    modified_dt = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "name": path.name or str(path),
        "path": str(path.resolve()),
        "type": "Directory" if is_dir else "File",
        "size_bytes": stat.st_size if not is_dir else 0,
        "size_formatted": format_bytes(stat.st_size) if not is_dir else f"{item_count} items",
        "created": created_dt,
        "modified": modified_dt,
        "is_symlink": path.is_symlink(),
        "is_dir": is_dir,
        "item_count": item_count,
    }


def create_file(path: Path) -> None:
    """Create an empty file or update timestamp."""
    if path.is_dir():
        raise IsADirectoryError(f"Target '{path}' is an existing directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def create_directory(path: Path) -> None:
    """Create a directory, including parents if needed."""
    if path.is_file():
        raise FileExistsError(f"Path '{path}' already exists as a file.")
    path.mkdir(parents=True, exist_ok=True)


def copy_path(src: Path, dst: Path, overwrite: bool = False) -> Path:
    """Copy file or directory with nesting and overwrite guards."""
    if not src.exists():
        raise FileNotFoundError(f"Source not found: '{src}'")

    res_src = src.resolve()
    res_dst = dst.resolve()

    # Prevent copying a folder into itself or subfolder
    if res_src.is_dir():
        if res_dst == res_src or res_dst.is_relative_to(res_src):
            raise ValueError(f"Cannot copy folder '{src.name}' into itself or one of its own subfolders.")

    # Target path adjustment if dst is an existing directory
    final_dst = dst
    if dst.is_dir():
        final_dst = dst / src.name

    if final_dst.exists() and not overwrite:
        raise FileExistsError(f"Target already exists: '{final_dst}'")

    if src.is_dir():
        if final_dst.exists() and overwrite:
            shutil.rmtree(final_dst)
        shutil.copytree(src, final_dst)
    else:
        shutil.copy2(src, final_dst)

    return final_dst


def move_path(src: Path, dst: Path, overwrite: bool = False) -> Path:
    """Move file or directory with nesting and overwrite guards."""
    if not src.exists():
        raise FileNotFoundError(f"Source not found: '{src}'")

    res_src = src.resolve()
    res_dst = dst.resolve()

    # Prevent moving a folder into itself or subfolder
    if res_src.is_dir():
        if res_dst == res_src or res_dst.is_relative_to(res_src):
            raise ValueError(f"Cannot move folder '{src.name}' into itself or one of its own subfolders.")

    final_dst = dst
    if dst.is_dir():
        final_dst = dst / src.name

    if final_dst.exists() and not overwrite:
        raise FileExistsError(f"Target already exists: '{final_dst}'")

    if final_dst.exists() and overwrite:
        if final_dst.is_dir():
            shutil.rmtree(final_dst)
        else:
            final_dst.unlink()

    shutil.move(str(src), str(final_dst))
    return final_dst


def rename_path(src: Path, new_name: str, overwrite: bool = False) -> Path:
    """Rename a file or folder in place. Rejects path separators."""
    if "/" in new_name or "\\" in new_name:
        raise ValueError("New name must be a plain filename with no path separators. Use 'move' to relocate items.")

    if not src.exists():
        raise FileNotFoundError(f"Target not found: '{src}'")

    target = src.parent / new_name
    if target.exists() and not overwrite:
        raise FileExistsError(f"Target '{target}' already exists.")

    return src.rename(target)


def recycle_path(path: Path, recursive: bool = False) -> None:
    """Send file or folder to the Recycle Bin safely."""
    if not path.exists():
        raise FileNotFoundError(f"Target not found: '{path}'")

    if path.is_dir() and not recursive:
        raise IsADirectoryError(f"'{path.name}' is a directory. Use -r / --recursive to delete directories.")

    send2trash.send2trash(str(path))


def search_files(
    search_roots: Sequence[Path],
    query: str,
    extension: str | None = None,
    excluded_names: set[str] | None = None,
    limit: int = 100,
) -> tuple[list[Path], int, bool]:
    """Search for files in configured root directories.
    
    Supports wildcards (*.py), partial substring matches, quoted phrases,
    and extension filters. Handles permission errors without crashing.
    
    Returns:
        (matches, skipped_permission_count, hit_limit)
    """
    matches: list[Path] = []
    skipped_count = 0
    hit_limit = False

    excl = {name.lower() for name in (excluded_names or set())}
    clean_query = query.strip()
    is_wildcard = any(ch in clean_query for ch in ("*", "?", "["))
    norm_query = clean_query.lower()
    norm_ext = f".{extension.lstrip('.').lower()}" if extension else None

    for root in search_roots:
        if hit_limit:
            break
        if not root.exists() or not root.is_dir():
            continue

        try:
            # os.walk for controlled directory pruning
            for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
                # Prune excluded directories
                dirnames[:] = [d for d in dirnames if d.lower() not in excl]

                for fname in filenames:
                    # Extension filter check
                    if norm_ext and not fname.lower().endswith(norm_ext):
                        continue

                    matched = False
                    if is_wildcard:
                        matched = fnmatch.fnmatch(fname.lower(), norm_query)
                    else:
                        matched = norm_query in fname.lower()

                    if matched:
                        matches.append(Path(dirpath) / fname)
                        if len(matches) >= limit:
                            hit_limit = True
                            break

                if hit_limit:
                    break

        except PermissionError:
            skipped_count += 1
            continue
        except OSError:
            skipped_count += 1
            continue

    return matches, skipped_count, hit_limit
