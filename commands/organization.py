"""File organization and undo management for MayuriShell."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import time
from typing import Any

from rich.markup import escape
from rich.table import Table

from commands.files import confirm_prompt
from core.executor import CommandResult
from core.logging_config import get_logger
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.file_service import EXECUTABLE_EXTENSIONS, format_bytes
from services.undo_service import (
    finish_journal_operation,
    find_latest_undoable_operation,
    mark_item_done,
    record_pending_item,
    start_journal_operation,
)

logger = get_logger()


UNFINISHED_DOWNLOAD_EXTS = {".crdownload", ".part", ".tmp", ".download"}
MAX_PLAN_DISPLAY_ROWS = 50
MAX_UNDO_RUNS = 5


def get_undo_log_path(context: Any) -> Path:
    """Return path to organize_undo.json in appdata directory."""
    return context.config.base_dir / "organize_undo.json"


def load_undo_log(context: Any) -> list[dict[str, Any]]:
    """Load existing undo log runs."""
    path = get_undo_log_path(context)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "runs" in data and isinstance(data["runs"], list):
                return data["runs"]
            if isinstance(data, list):
                return data
    except Exception as exc:
        logger.warning("Failed to read organize undo log at %s: %s", path, exc)
    return []


def save_undo_log(context: Any, runs: list[dict[str, Any]]) -> None:
    """Safely persist undo log keeping at most MAX_UNDO_RUNS."""
    path = get_undo_log_path(context)
    trimmed_runs = runs[-MAX_UNDO_RUNS:]
    data = {"runs": trimmed_runs}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write directly and flush to ensure immediate persistence
        temp_path = path.parent / f"{path.name}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(path)
    except Exception as exc:
        logger.error("Failed to save organize undo log at %s: %s", path, exc)


def is_protected_organize_folder(target: Path, context: Any) -> tuple[bool, str]:
    """Check if target folder is protected against automatic organization."""
    try:
        res = target.resolve()
    except Exception:
        res = target

    # 1. Drive roots (e.g. C:\ or D:\)
    if res.parent == res or str(res) == res.anchor:
        return True, "Cannot organize drive root."

    # 2. User home folder itself
    home = Path.home().resolve()
    if res == home:
        return True, "Cannot organize user home folder itself."

    # 3. Windows directory
    windir = Path(os.getenv("WINDIR", "C:\\Windows")).resolve()
    if res == windir or res == windir / "System32":
        return True, "Cannot organize Windows system directory."

    # 4. Program Files
    prog_files = Path(os.getenv("ProgramFiles", "C:\\Program Files")).resolve()
    if res == prog_files:
        return True, "Cannot organize Program Files directory."
    prog_x86 = Path(os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")).resolve()
    if res == prog_x86:
        return True, "Cannot organize Program Files directory."

    # 5. Project/Install root
    from core.paths import get_app_root, is_frozen
    project_root = get_app_root().resolve()
    if res == project_root or project_root.is_relative_to(res):
        folder_desc = "install folder" if is_frozen() else "project folder"
        return True, f"Cannot organize the MayuriShell {folder_desc} or its parents."

    # 6. AppData configuration directory
    appdata_dir = context.config.base_dir.resolve()
    if res == appdata_dir or appdata_dir.is_relative_to(res):
        return True, "Cannot organize the MayuriShell AppData/configuration directory."

    return False, ""


def match_category(
    filename: str,
    categories: dict[str, list[str]],
    include_other: bool = False,
) -> str | None:
    """Determine the category for a file based on compound and single extensions."""
    fn_lower = filename.lower()

    # Check known compound extensions first (e.g. .tar.gz, .tar.bz2, .tar.xz)
    compound_exts = [".tar.gz", ".tar.bz2", ".tar.xz"]
    for c_ext in compound_exts:
        if fn_lower.endswith(c_ext):
            for cat_name, ext_list in categories.items():
                if any(e.lower() == c_ext for e in ext_list):
                    return cat_name
            # Fallback for compound archives
            return "Archives"

    # Check single extension
    ext = Path(filename).suffix.lower()
    if ext:
        for cat_name, ext_list in categories.items():
            if any(e.lower() == ext for e in ext_list):
                return cat_name

    # If unknown extension or no extension
    if include_other:
        return "Other"

    # Default: leave in place
    return None


def get_collision_free_path(dest_dir: Path, orig_filename: str, claimed: set[Path]) -> Path:
    """Generate a unique destination filename that does not exist and has not been claimed yet."""
    target = dest_dir / orig_filename
    if not target.exists() and target not in claimed:
        return target

    p = Path(orig_filename)
    stem = p.stem
    # If compound extension, adjust stem and suffix
    lower_name = orig_filename.lower()
    suffix = p.suffix
    for c_ext in [".tar.gz", ".tar.bz2", ".tar.xz"]:
        if lower_name.endswith(c_ext):
            stem = orig_filename[:-len(c_ext)]
            suffix = c_ext
            break

    counter = 1
    while True:
        candidate = dest_dir / f"{stem} ({counter}){suffix}"
        if not candidate.exists() and candidate not in claimed:
            return candidate
        counter += 1


def is_eligible_top_level_file(entry: Path, now: float) -> bool:
    """Check if top-level entry is eligible for organization."""
    try:
        # 1. Must be a top-level file (never a directory)
        if not entry.is_file() or entry.is_dir():
            return False

        # 2. Ignore shortcuts (.lnk)
        if entry.suffix.lower() == ".lnk":
            return False

        # 3. Ignore unfinished downloads
        if entry.suffix.lower() in UNFINISHED_DOWNLOAD_EXTS:
            return False

        # 4. Ignore dotfiles and system files
        name_lower = entry.name.lower()
        if entry.name.startswith(".") or name_lower in ("desktop.ini", "thumbs.db"):
            return False

        # Check Windows hidden / system attributes
        st = entry.stat()
        if hasattr(st, "st_file_attributes"):
            attrs = st.st_file_attributes
            if (attrs & stat.FILE_ATTRIBUTE_HIDDEN) or (attrs & stat.FILE_ATTRIBUTE_SYSTEM):
                return False

        # 5. Ignore files modified in the last 2 minutes (120 seconds)
        if now - st.st_mtime < 120.0:
            return False

        return True
    except (OSError, PermissionError):
        return False


def handle_organize(context: Any, args: list[str]) -> CommandResult:
    """Analyze and organize directory files by category."""
    console = context.console
    theme = context.theme

    if not args:
        console.print(
            f"{theme.format_warning('Usage:')} "
            f"{theme.format_primary('organize <folder or shortcut> [--dry-run] [--include-other]', bold=True)} "
            f"or {theme.format_primary('organize undo', bold=True)}"
        )
        return CommandResult.fail("Missing arguments")

    # Subcommand: organize undo
    if args[0].lower() == "undo":
        return handle_organize_undo(context, args[1:])

    # Parse flags and target
    dry_run = False
    include_other = False
    raw_target: str | None = None

    for arg in args:
        clean_arg = arg.strip()
        if clean_arg.lower() in ("--dry-run", "-n"):
            dry_run = True
        elif clean_arg.lower() in ("--include-other", "-o"):
            include_other = True
        elif not clean_arg.startswith("-") and raw_target is None:
            raw_target = clean_arg

    if not raw_target:
        console.print(f"{theme.format_error('Error:')} Missing folder or shortcut to organize.")
        return CommandResult.fail("Missing folder or shortcut to organize")

    # Resolve folder
    target_dir, note = context.resolve_path(raw_target)
    if not target_dir.exists():
        console.print(f"{theme.format_error('Directory not found:')} '{escape(str(target_dir))}'")
        return CommandResult.fail("Directory not found")

    if not target_dir.is_dir():
        console.print(f"{theme.format_error('Target is not a directory:')} '{escape(str(target_dir))}'")
        return CommandResult.fail("Target is not a directory")

    # Check protected folders
    is_prot, prot_reason = is_protected_organize_folder(target_dir, context)
    if is_prot:
        console.print(f"{theme.format_error('Refusing to organize protected folder:')} {escape(prot_reason)}")
        return CommandResult.fail("Protected folder")

    if note:
        console.print(theme.format_muted(f"({note})"))

    categories = context.config.get_organize_categories()
    now = time.time()

    # Collect eligible top-level files
    try:
        all_entries = list(target_dir.iterdir())
    except PermissionError as exc:
        console.print(f"{theme.format_error('Permission denied accessing directory:')} {escape(str(exc))}")
        return CommandResult.fail("Permission denied")

    eligible_files: list[Path] = []
    for entry in all_entries:
        if is_eligible_top_level_file(entry, now):
            eligible_files.append(entry)

    # Sort files by name
    eligible_files.sort(key=lambda p: p.name.lower())

    # Build plan
    plan_rows: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    claimed_destinations: set[Path] = set()

    for file_path in eligible_files:
        cat = match_category(file_path.name, categories, include_other=include_other)
        if not cat:
            # Stays in place
            continue

        dest_dir = target_dir / cat
        final_dest = get_collision_free_path(dest_dir, file_path.name, claimed_destinations)
        claimed_destinations.add(final_dest)

        try:
            file_size = file_path.stat().st_size
        except OSError:
            file_size = 0

        plan_rows.append({
            "src": file_path,
            "filename": file_path.name,
            "category": cat,
            "dest": final_dest,
            "rel_dest": f"{cat}/{final_dest.name}",
            "size": file_size,
        })
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if not plan_rows:
        console.print(
            theme.format_muted(
                f"No eligible files to organize in '{target_dir.name}'. "
                "(Subfolders, hidden files, recent files < 2m, and unknown extensions were skipped.)"
            )
        )
        return CommandResult.success()

    # Display Plan Table
    table = theme.create_table(
        title=f"Organize Plan for: {escape(target_dir.name)} ({len(plan_rows)} files)",
    )
    table.add_column("File", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Category", style=theme.success_style)
    table.add_column("Destination", style=theme.warning_style)
    table.add_column("Size", style=theme.muted_style, justify="right")

    displayed_rows = plan_rows[:MAX_PLAN_DISPLAY_ROWS]
    for row in displayed_rows:
        table.add_row(
            escape(row["filename"]),
            escape(row["category"]),
            escape(row["rel_dest"]),
            format_bytes(row["size"]),
        )

    console.print(table)

    if len(plan_rows) > MAX_PLAN_DISPLAY_ROWS:
        remaining = len(plan_rows) - MAX_PLAN_DISPLAY_ROWS
        console.print(
            theme.format_muted(f"... and {remaining} more files (see category summary below).")
        )

    # Category Summary
    summary_parts = [
        f"{theme.format_primary(cat, bold=True)}: {count}"
        for cat, count in sorted(category_counts.items())
    ]
    console.print(
        f"{theme.format_accent('Summary:', bold=True)} {', '.join(summary_parts)} "
        f"({theme.format_success(f'Total: {len(plan_rows)} files', bold=True)})\n"
    )

    if dry_run:
        console.print(
            theme.format_warning("[Dry Run] No files were moved. Run without --dry-run to apply.")
        )
        return CommandResult.success()

    # Ask for confirmation (default No)
    confirmed = confirm_prompt(
        console,
        f"Organize {len(plan_rows)} files into categorized folders?",
        default_yes=False,
        theme=theme,
    )
    if not confirmed:
        console.print(theme.format_muted("Organization cancelled by user."))
        return CommandResult.cancel()

    # Execute Moves
    base_dir = context.config.base_dir
    op_id = start_journal_operation(base_dir, "organize")
    created_category_folders: set[Path] = set()

    existing_runs = load_undo_log(context)
    current_run: dict[str, Any] = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_dir": str(target_dir),
        "moves": [],
    }
    existing_runs.append(current_run)

    moved_count = 0
    failed_moves: list[tuple[str, str]] = []
    interrupted = False

    try:
        for item in plan_rows:
            src: Path = item["src"]
            dst: Path = item["dest"]

            if not src.exists():
                failed_moves.append((src.name, "Source file no longer exists"))
                continue

            try:
                # Capture stat before moving
                st = src.stat()
                file_size = st.st_size
                file_mtime = st.st_mtime

                # Track created category folder
                if not dst.parent.exists():
                    created_category_folders.add(dst.parent)

                # Record pending item BEFORE move
                record_pending_item(base_dir, op_id, src, dst, kind="file")

                # Create category folder only when needed
                dst.parent.mkdir(parents=True, exist_ok=True)

                # Move file
                shutil.move(str(src), str(dst))

                # Mark item done in journal
                mark_item_done(base_dir, op_id, dst)

                # Append move record and immediately flush to disk (legacy log)
                current_run["moves"].append({
                    "original": str(src),
                    "current": str(dst),
                    "size": file_size,
                    "mtime": file_mtime,
                })
                save_undo_log(context, existing_runs)
                moved_count += 1

            except (PermissionError, OSError) as exc:
                logger.warning("Failed to move '%s' to '%s': %s", src, dst, exc)
                failed_moves.append((src.name, f"Locked or inaccessible ({exc})"))

    except KeyboardInterrupt:
        interrupted = True
        logger.info("Organize operation interrupted by user")

    # Finalize journal operation
    final_op_status = "partial" if (interrupted and moved_count > 0) else ("done" if moved_count > 0 else "failed")
    finish_journal_operation(
        base_dir,
        op_id,
        status=final_op_status,
        created_folders=list(created_category_folders),
    )


    # Final reporting
    if interrupted:
        console.print(
            f"\n{theme.format_warning('Organization interrupted by user.')} "
            f"Successfully moved {moved_count} of {len(plan_rows)} files."
        )
        console.print(
            f"You can reverse these moves at any time with: "
            f"{theme.format_primary('organize undo', bold=True)}"
        )
        return CommandResult.cancel()

    if moved_count > 0:
        console.print(
            f"{theme.format_success('Successfully organized')} "
            f"{theme.format_primary(str(moved_count), bold=True)} files into {escape(target_dir.name)}."
        )
        console.print(
            f"{theme.format_muted('Tip: You can reverse this run with ')}"
            f"{theme.format_primary('organize undo', bold=True)}{theme.format_muted('.')}"
        )

    if failed_moves:
        console.print(
            f"\n{theme.format_warning('Skipped / Failed files:', bold=True)}"
        )
        for fn, reason in failed_moves:
            console.print(f"  • {theme.format_primary(escape(fn))}: {escape(reason)}")

    return CommandResult.success()


def handle_organize_undo(context: Any, args: list[str]) -> CommandResult:
    """Reverse the most recent organize run safely."""
    console = context.console
    theme = context.theme
    base_dir = context.config.base_dir

    latest_op = find_latest_undoable_operation(base_dir, op_type="organize")
    if latest_op:
        from commands.undo import _preview_and_execute_undo
        return _preview_and_execute_undo(context, latest_op, confirm_func=confirm_prompt)

    runs = load_undo_log(context)
    if not runs:
        console.print(theme.format_muted("No previous organize run found to undo."))
        return CommandResult.success()


    # Find the latest run with moves
    target_run_idx = -1
    for idx in range(len(runs) - 1, -1, -1):
        if runs[idx].get("moves"):
            target_run_idx = idx
            break

    if target_run_idx == -1:
        console.print(theme.format_muted("No previous organize moves found to undo."))
        return CommandResult.success()

    latest_run = runs[target_run_idx]
    moves: list[dict[str, Any]] = latest_run.get("moves", [])
    if not moves:
        console.print(theme.format_muted("No file moves to undo in the last run."))
        return CommandResult.success()

    console.print(
        f"{theme.format_primary('Last organize run:', bold=True)} "
        f"{escape(latest_run.get('timestamp', 'Unknown time'))} "
        f"in {escape(latest_run.get('target_dir', ''))} ({len(moves)} files moved)"
    )

    # Show preview table of undo
    table = theme.create_table(title="Moves to Reverse")
    table.add_column("Current Location", style=theme.warning_style)
    table.add_column("Original Location", style=theme.success_style)
    table.add_column("Status", style=theme.bold_text_style)

    preview_rows = moves[:MAX_PLAN_DISPLAY_ROWS]
    for m in preview_rows:
        curr_p = Path(m["current"])
        orig_p = Path(m["original"])

        status = theme.format_success("Ready")
        if not curr_p.exists():
            status = theme.format_error("Missing")
        elif orig_p.exists():
            status = theme.format_error("Conflict (target exists)")

        table.add_row(escape(curr_p.name), escape(orig_p.name), status)

    console.print(table)
    if len(moves) > MAX_PLAN_DISPLAY_ROWS:
        console.print(theme.format_muted(f"... and {len(moves) - MAX_PLAN_DISPLAY_ROWS} more files."))

    confirmed = confirm_prompt(
        console,
        f"Reverse this organize run (restore {len(moves)} files)?",
        default_yes=False,
        theme=theme,
    )
    if not confirmed:
        console.print(theme.format_muted("Undo cancelled by user."))
        return CommandResult.cancel()

    restored_count = 0
    skipped_items: list[tuple[str, str]] = []
    interrupted = False
    cleaned_dirs: set[Path] = set()

    # Process moves in reverse order
    remaining_moves = list(moves)
    try:
        while remaining_moves:
            item = remaining_moves.pop()
            curr_p = Path(item["current"])
            orig_p = Path(item["original"])
            orig_size = item.get("size")
            orig_mtime = item.get("mtime")

            # 1. Target check: if original destination exists, refuse to overwrite
            if orig_p.exists():
                skipped_items.append((curr_p.name, "Original destination already exists (refusing to overwrite)"))
                continue

            # 2. Source check: if file no longer exists at current location
            if not curr_p.exists():
                skipped_items.append((curr_p.name, "File no longer exists at destination"))
                continue

            # 3. Size and mtime check: verify file has not been modified
            try:
                cur_st = curr_p.stat()
                if orig_size is not None and cur_st.st_size != orig_size:
                    skipped_items.append((curr_p.name, "File size was modified since organize run"))
                    continue
                if orig_mtime is not None and abs(cur_st.st_mtime - orig_mtime) > 1.0:
                    skipped_items.append((curr_p.name, "File was modified since organize run"))
                    continue
            except OSError as exc:
                skipped_items.append((curr_p.name, f"Failed to verify file state: {exc}"))
                continue

            # 4. Move file back to original location
            try:
                parent_cat_dir = curr_p.parent
                shutil.move(str(curr_p), str(orig_p))
                restored_count += 1
                cleaned_dirs.add(parent_cat_dir)

                # Immediately update undo log
                latest_run["moves"] = remaining_moves
                save_undo_log(context, runs)

            except (PermissionError, OSError) as exc:
                skipped_items.append((curr_p.name, f"Failed to move file back: {exc}"))

    except KeyboardInterrupt:
        interrupted = True
        logger.info("Organize undo interrupted by user")

    # Clean up empty category directories created by organize
    for c_dir in cleaned_dirs:
        try:
            if c_dir.exists() and c_dir.is_dir() and not list(c_dir.iterdir()):
                c_dir.rmdir()
        except OSError:
            pass

    # If run completely processed, remove it from log
    if not latest_run["moves"]:
        runs.pop(target_run_idx)
        save_undo_log(context, runs)

    if interrupted:
        console.print(
            f"\n{theme.format_warning('Undo operation interrupted by user.')} "
            f"Restored {restored_count} files."
        )
        return CommandResult.cancel()

    console.print(
        f"{theme.format_success('Undo complete:')} Restored "
        f"{theme.format_primary(str(restored_count), bold=True)} files to original locations."
    )

    if skipped_items:
        console.print(f"\n{theme.format_warning('Skipped items during undo:', bold=True)}")
        for fn, reason in skipped_items:
            console.print(f"  • {theme.format_primary(escape(fn))}: {escape(reason)}")

    return CommandResult.success()


def register_organization_commands(registry: CommandRegistry, config: Any) -> None:
    """Register organize and organize undo commands."""
    registry.register(
        CommandInfo(
            name="organize",
            description="Analyze directory and organize files into categorized folders",
            handler=handle_organize,
            usage="organize <folder or shortcut> [--dry-run] [--include-other] | organize undo",
            category="Organization",
            arg_rules=ArgumentRules(min_args=1, max_args=3),
        )
    )
