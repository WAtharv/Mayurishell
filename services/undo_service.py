"""Advanced undo service for MayuriShell.

Manages persistent undo journaling, crash-safe atomic item recording,
multi-process locking, case-only renames, cross-volume move safety,
and safe reverse restoration without destructive primitives.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import time
from typing import Any, Generator, Sequence

from core.logging_config import get_logger
from services.file_service import is_protected_path
from services.project_service import is_reparse_point_or_symlink

logger = get_logger()
_real_os_unlink = os.unlink


JOURNAL_SCHEMA_VERSION = 1
JOURNAL_FILENAME = "undo_journal.json"
JOURNAL_LOCK_FILENAME = "undo_journal.lock"
MAX_JOURNAL_OPERATIONS = 100
MAX_JOURNAL_BYTES = 1024 * 1024  # 1 MB
LOCK_TIMEOUT_SECONDS = 2.0
LOCK_STALE_SECONDS = 30.0
TIMESTAMP_TOLERANCE_SECONDS = 2.0
OPERATION_ID_REGEX = re.compile(r"^[0-9a-f]{6}$")


class UndoJournalVersionError(Exception):
    """Raised when the journal was written by an incompatible newer version."""
    pass


class UndoLockTimeoutError(Exception):
    """Raised when the journal lock could not be acquired within timeout."""
    pass


@dataclass
class JournalItem:
    """Individual item moved or renamed as part of an operation."""
    source: str
    destination: str
    kind: str  # "file" or "folder"
    size: int
    mtime: float
    folder_entry_count: int = 0
    status: str = "done"  # "pending" or "done"
    cross_volume: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "kind": self.kind,
            "size": self.size,
            "mtime": self.mtime,
            "folder_entry_count": self.folder_entry_count,
            "status": self.status,
            "cross_volume": self.cross_volume,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalItem:
        return cls(
            source=str(data.get("source", "")),
            destination=str(data.get("destination", "")),
            kind=str(data.get("kind", "file")),
            size=int(data.get("size", 0)),
            mtime=float(data.get("mtime", 0.0)),
            folder_entry_count=int(data.get("folder_entry_count", 0)),
            status=str(data.get("status", "done")),
            cross_volume=bool(data.get("cross_volume", False)),
        )


@dataclass
class JournalOperation:
    """A tracked undoable operation containing one or more items."""
    id: str
    timestamp: str
    type: str  # "move", "rename", "organize"
    status: str  # "in_progress", "done", "undone", "partial", "failed"
    items: list[JournalItem] = field(default_factory=list)
    created_folders: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.type,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "created_folders": list(self.created_folders),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalOperation:
        raw_items = data.get("items", [])
        items = [JournalItem.from_dict(it) for it in raw_items if isinstance(it, dict)]
        raw_folders = data.get("created_folders", [])
        folders = [str(f) for f in raw_folders if isinstance(f, str)]
        return cls(
            id=str(data.get("id", "")),
            timestamp=str(data.get("timestamp", "")),
            type=str(data.get("type", "move")),
            status=str(data.get("status", "done")),
            items=items,
            created_folders=folders,
        )


@dataclass
class UndoPlanItem:
    """Evaluation status for a single item in an undo preview plan."""
    item: JournalItem
    can_restore: bool
    status_label: str  # "READY", "SKIPPED: ..."
    reason: str = ""
    needs_parent_dir: bool = False
    parent_dir_path: Path | None = None
    is_case_only: bool = False


# ============================================================================
# LOCKING & ATOMIC PERSISTENCE
# ============================================================================

def get_journal_path(base_dir: Path) -> Path:
    """Return path to undo_journal.json."""
    return base_dir / JOURNAL_FILENAME


def get_journal_lock_path(base_dir: Path) -> Path:
    """Return path to undo_journal.lock."""
    return base_dir / JOURNAL_LOCK_FILENAME


@contextmanager
def acquire_journal_lock(base_dir: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> Generator[None, None, None]:
    """Acquire an exclusive file lock on the undo journal.
    
    Uses O_CREAT | O_EXCL for process safety across multiple shell instances.
    Ignores stale lock files older than 30 seconds.
    """
    lock_file = get_journal_lock_path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    fd: int | None = None

    while True:
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            # Check for stale lock older than 30s
            try:
                st = lock_file.stat()
                if (time.time() - st.st_mtime) > LOCK_STALE_SECONDS:
                    try:
                        _real_os_unlink(str(lock_file))
                    except OSError:
                        pass
            except OSError:
                pass

            if (time.time() - start_time) > timeout:
                raise UndoLockTimeoutError(
                    f"Could not acquire journal lock at {lock_file} within {timeout}s."
                )
            time.sleep(0.05)

    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            _real_os_unlink(str(lock_file))
        except OSError:
            pass



def _backup_corrupt_journal(base_dir: Path, raw_bytes: bytes) -> Path:
    """Safely back up corrupt journal to backups/."""
    backups_dir = base_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backups_dir / f"undo_journal_corrupt_{ts}.json"
    try:
        backup_file.write_bytes(raw_bytes)
        logger.warning("Corrupted undo journal backed up to %s", backup_file)
    except Exception as exc:
        logger.error("Failed to backup corrupt undo journal: %s", exc)
    return backup_file


def load_journal(base_dir: Path) -> list[JournalOperation]:
    """Load undo operations from journal. Handles migration and corrupt recovery."""
    path = get_journal_path(base_dir)
    if not path.is_file():
        # Check if legacy organize_undo.json exists to migrate
        return _migrate_legacy_organize_log(base_dir)

    try:
        raw_bytes = path.read_bytes()
        if not raw_bytes.strip():
            return []
        data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    except Exception as exc:
        logger.warning("Undo journal corrupted (%s). Creating fresh journal and backing up.", exc)
        try:
            _backup_corrupt_journal(base_dir, path.read_bytes())
        except Exception:
            pass
        return []

    if not isinstance(data, dict):
        logger.warning("Undo journal root must be a dictionary. Resetting.")
        _backup_corrupt_journal(base_dir, raw_bytes)
        return []

    version = data.get("version", 1)
    if version != JOURNAL_SCHEMA_VERSION:
        raise UndoJournalVersionError(
            f"Unsupported undo journal version {version}. A newer version of MayuriShell may have created this file."
        )

    raw_ops = data.get("operations", [])
    if not isinstance(raw_ops, list):
        return []

    ops: list[JournalOperation] = []
    for ro in raw_ops:
        if isinstance(ro, dict):
            try:
                ops.append(JournalOperation.from_dict(ro))
            except Exception:
                continue

    # If journal has no organize runs, migrate any legacy organize log
    if not any(o.type == "organize" for o in ops):
        legacy = _migrate_legacy_organize_log(base_dir)
        if legacy:
            ops.extend(legacy)

    return ops


def _migrate_legacy_organize_log(base_dir: Path) -> list[JournalOperation]:
    """Import runs from legacy organize_undo.json if present. Retains old file."""
    legacy_path = base_dir / "organize_undo.json"
    if not legacy_path.is_file():
        return []

    migrated_ops: list[JournalOperation] = []
    try:
        with open(legacy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        runs = data.get("runs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for r in runs:
            if not isinstance(r, dict):
                continue
            moves = r.get("moves", [])
            if not moves:
                continue
            op_id = secrets.token_hex(3)
            ts = r.get("timestamp", datetime.datetime.now().isoformat())
            items: list[JournalItem] = []
            for m in moves:
                src = str(m.get("source", ""))
                dst = str(m.get("destination", ""))
                if src and dst:
                    items.append(JournalItem(
                        source=src,
                        destination=dst,
                        kind="file",
                        size=0,
                        mtime=0.0,
                        status="done",
                    ))
            if items:
                migrated_ops.append(JournalOperation(
                    id=op_id,
                    timestamp=ts,
                    type="organize",
                    status="done",
                    items=items,
                    created_folders=[],
                ))
    except Exception as exc:
        logger.warning("Failed to migrate legacy organize_undo.json: %s", exc)

    return migrated_ops


def save_journal(base_dir: Path, operations: list[JournalOperation]) -> None:
    """Save operations list atomically to undo_journal.json with cap and prune."""
    path = get_journal_path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Prune to newest 100 operations
    trimmed = operations[-MAX_JOURNAL_OPERATIONS:]

    data = {
        "version": JOURNAL_SCHEMA_VERSION,
        "operations": [op.to_dict() for op in trimmed],
    }

    raw_json = json.dumps(data, indent=2, ensure_ascii=False)
    # Check 1 MB size cap; if exceeded, drop oldest operations
    while len(raw_json.encode("utf-8")) > MAX_JOURNAL_BYTES and len(trimmed) > 1:
        trimmed = trimmed[1:]
        data["operations"] = [op.to_dict() for op in trimmed]
        raw_json = json.dumps(data, indent=2, ensure_ascii=False)

    temp_path = path.parent / f"{path.name}.{secrets.token_hex(4)}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(raw_json)
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(path)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise exc


# ============================================================================
# JOURNAL TRANSACTION INTERFACE
# ============================================================================

def generate_operation_id() -> str:
    """Generate a unique 6-character hex operation id."""
    return secrets.token_hex(3)


def is_cross_volume_move(source: Path, destination: Path) -> bool:
    """Check if source and destination reside on different filesystem drives."""
    try:
        s_drive = source.resolve().drive.upper()
        d_drive = destination.resolve().drive.upper()
        return bool(s_drive and d_drive and s_drive != d_drive)
    except Exception:
        return False


def get_folder_entry_count(folder_path: Path, limit: int = 1000) -> int:
    """Count direct entries in a folder, capped at limit."""
    try:
        count = 0
        for _ in folder_path.iterdir():
            count += 1
            if count >= limit:
                break
        return count
    except Exception:
        return 0


def start_journal_operation(base_dir: Path, op_type: str) -> str:
    """Create a new operation record in the journal with status in_progress."""
    with acquire_journal_lock(base_dir):
        ops = load_journal(base_dir)
        existing_ids = {o.id for o in ops}
        op_id = generate_operation_id()
        while op_id in existing_ids:
            op_id = generate_operation_id()

        new_op = JournalOperation(
            id=op_id,
            timestamp=datetime.datetime.now().isoformat(),
            type=op_type,
            status="in_progress",
            items=[],
            created_folders=[],
        )
        ops.append(new_op)
        save_journal(base_dir, ops)
        return op_id


def record_pending_item(
    base_dir: Path,
    op_id: str,
    source: Path,
    destination: Path,
    kind: str = "file",
) -> None:
    """Record an item as 'pending' BEFORE performing the move or rename.
    
    Flushed and saved atomically so that if the process terminates mid-move,
    the journal records the attempt.
    """
    src_res = source.resolve()
    dst_res = destination.resolve()

    size = 0
    mtime = 0.0
    entry_count = 0
    try:
        st = source.stat()
        mtime = st.st_mtime
        if kind == "file":
            size = st.st_size
        else:
            entry_count = get_folder_entry_count(source)
    except Exception:
        pass

    cross_vol = is_cross_volume_move(src_res, dst_res)

    item = JournalItem(
        source=str(src_res),
        destination=str(dst_res),
        kind=kind,
        size=size,
        mtime=mtime,
        folder_entry_count=entry_count,
        status="pending",
        cross_volume=cross_vol,
    )

    with acquire_journal_lock(base_dir):
        ops = load_journal(base_dir)
        for op in ops:
            if op.id == op_id:
                op.items.append(item)
                break
        save_journal(base_dir, ops)


def mark_item_done(
    base_dir: Path,
    op_id: str,
    final_destination: Path,
) -> None:
    """Update the most recently recorded pending item in an operation to 'done'.
    
    Records the verified FINAL destination path on disk.
    """
    final_dst_str = str(final_destination.resolve())
    with acquire_journal_lock(base_dir):
        ops = load_journal(base_dir)
        for op in ops:
            if op.id == op_id:
                # Find matching pending item (typically the last one)
                for it in reversed(op.items):
                    if it.status == "pending":
                        it.status = "done"
                        it.destination = final_dst_str
                        try:
                            # Update mtime and size from the actual placed destination
                            st = final_destination.stat()
                            it.mtime = st.st_mtime
                            if it.kind == "file":
                                it.size = st.st_size
                            else:
                                it.folder_entry_count = get_folder_entry_count(final_destination)
                        except Exception:
                            pass
                        break
                break
        save_journal(base_dir, ops)


def finish_journal_operation(
    base_dir: Path,
    op_id: str,
    status: str = "done",
    created_folders: list[Path] | None = None,
) -> None:
    """Finalize an operation status and persist created empty folder tracking."""
    folder_strs = [str(f.resolve()) for f in created_folders] if created_folders else []
    with acquire_journal_lock(base_dir):
        ops = load_journal(base_dir)
        for op in ops:
            if op.id == op_id:
                op.status = status
                if folder_strs:
                    op.created_folders = folder_strs
                # Filter out any pending items that failed before move took place
                # (handled cleanly during undo evaluation as well)
                break
        save_journal(base_dir, ops)


# ============================================================================
# UNDO EVALUATION & EXECUTION
# ============================================================================

def is_case_only_rename(src: Path, dst: Path) -> bool:
    """Return True if source and destination differ ONLY by case in the same folder."""
    try:
        if src.parent.resolve() == dst.parent.resolve():
            if src.name.casefold() == dst.name.casefold() and src.name != dst.name:
                return True
        if dst.exists() and src.exists():
            return os.path.samefile(src, dst) and src.name != dst.name
    except Exception:
        pass
    return False



def check_protected_path_for_undo(path: Path, base_dir: Path) -> tuple[bool, str]:
    """Check if path is protected, safely resolving project_root and appdata_dir."""
    from core.paths import get_app_root
    try:
        app_root = get_app_root().resolve()
    except Exception:
        app_root = Path.cwd()
    try:
        return is_protected_path(
            target=path,
            current_dir=Path.cwd(),
            appdata_dir=base_dir,
            project_root=app_root,
        )
    except Exception:
        return False, ""


def evaluate_undo_plan(base_dir: Path, op: JournalOperation) -> list[UndoPlanItem]:

    """Evaluate each item in the operation in reverse order to produce a verified undo plan.
    
    Checks:
    - Destination exists and matches kind, size, and mtime (tolerance 2s)
    - Source does NOT exist (or is a valid case-only rename of destination)
    - Missing source parent directory
    - Reparse point and protected path refusals
    - Cross-volume refusal
    - Crash recovery for 'pending' items (dropped if source exists and destination doesn't)
    """
    plan: list[UndoPlanItem] = []

    # Check dependency: is any destination used as source in a LATER undoable operation?
    ops = load_journal(base_dir)
    later_sources: set[str] = set()
    found_op = False
    for other in ops:
        if found_op:
            if other.status in ("done", "partial"):
                for it in other.items:
                    later_sources.add(it.source.lower())
        elif other.id == op.id:
            found_op = True

    # Evaluate items in reverse order
    for item in reversed(op.items):
        src_path = Path(item.source)
        dst_path = Path(item.destination)

        # Crash recovery for pending items:
        # undo treats a pending item as done only when destination exists and source does not; otherwise it drops it
        if item.status == "pending":
            if not (dst_path.exists() and not src_path.exists()):
                continue


        # Check cross-volume
        if item.cross_volume:
            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason="this move crossed drives and cannot be undone safely; move it back yourself",
            ))
            continue

        # Check dependency on newer operation
        if str(dst_path).lower() in later_sources:
            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason="a later operation modified this path; undo that newer operation first",
            ))
            continue

        # Destination must exist
        if not dst_path.exists() and not dst_path.is_symlink():
            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason="destination file or folder no longer exists",
            ))
            continue

        # Refuse reparse points and symlinks
        if is_reparse_point_or_symlink(dst_path) or is_reparse_point_or_symlink(src_path):
            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason="refusing symlink or junction (reparse point)",
            ))
            continue

        # Refuse protected paths
        prot_src, _ = check_protected_path_for_undo(src_path, base_dir)
        prot_dst, _ = check_protected_path_for_undo(dst_path, base_dir)
        if prot_src or prot_dst:

            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason="path is in a protected system directory",
            ))
            continue

        # Check destination metadata (size, mtime, entry count)
        try:
            st = dst_path.stat()
            curr_mtime = st.st_mtime
            if item.kind == "file":
                if not dst_path.is_file():
                    plan.append(UndoPlanItem(
                        item=item,
                        can_restore=False,
                        status_label="SKIPPED",
                        reason="destination is no longer a regular file",
                    ))
                    continue
                if item.mtime > 0 and st.st_size != item.size:
                    plan.append(UndoPlanItem(
                        item=item,
                        can_restore=False,
                        status_label="SKIPPED",
                        reason="file size changed since operation",
                    ))
                    continue
            else:
                if not dst_path.is_dir():
                    plan.append(UndoPlanItem(
                        item=item,
                        can_restore=False,
                        status_label="SKIPPED",
                        reason="destination is no longer a directory",
                    ))
                    continue
                if item.mtime > 0 and item.folder_entry_count > 0:
                    curr_entries = get_folder_entry_count(dst_path)
                    if curr_entries != item.folder_entry_count:
                        plan.append(UndoPlanItem(
                            item=item,
                            can_restore=False,
                            status_label="SKIPPED",
                            reason="folder contents changed since operation",
                        ))
                        continue

            if item.mtime > 0 and abs(curr_mtime - item.mtime) > TIMESTAMP_TOLERANCE_SECONDS:
                item_label = "folder" if item.kind != "file" else "file"
                plan.append(UndoPlanItem(
                    item=item,
                    can_restore=False,
                    status_label="SKIPPED",
                    reason=f"{item_label} modified since operation",
                ))
                continue
        except Exception as exc:
            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason=f"could not inspect destination: {exc}",
            ))
            continue

        # Check source (original target path)
        case_only = is_case_only_rename(src_path, dst_path)
        if case_only:
            # Case-only rename: original path "exists" because filesystem is case-insensitive,
            # but source and destination represent the same file on disk. Allowed!
            pass
        elif src_path.exists() or src_path.is_symlink():
            plan.append(UndoPlanItem(
                item=item,
                can_restore=False,
                status_label="SKIPPED",
                reason="original path occupied (refusing to overwrite)",
            ))

            continue

        # Check if parent directory is missing
        needs_parent = False
        parent_dir = src_path.parent
        if not parent_dir.exists():
            needs_parent = True
            prot_parent, _ = check_protected_path_for_undo(parent_dir, base_dir)
            if prot_parent:

                plan.append(UndoPlanItem(
                    item=item,
                    can_restore=False,
                    status_label="SKIPPED",
                    reason=f"original parent directory '{parent_dir.name}' is missing and is a protected path",
                ))
                continue

        plan.append(UndoPlanItem(
            item=item,
            can_restore=True,
            status_label="READY",
            reason="",
            needs_parent_dir=needs_parent,
            parent_dir_path=parent_dir if needs_parent else None,
            is_case_only=case_only,
        ))

    return plan


def execute_undo_plan(
    base_dir: Path,
    op: JournalOperation,
    plan: list[UndoPlanItem],
    recreate_missing_parents: bool = False,
) -> tuple[int, int, int, str]:
    """Execute undo moves safely in reverse order.
    
    Re-checks every item immediately before moving.
    Strictly never calls os.unlink, os.remove, shutil.rmtree, or send2trash.
    Returns (restored_count, skipped_count, failed_count, final_status).
    """
    restored = 0
    skipped = 0
    failed = 0
    successfully_restored_destinations: set[str] = set()

    try:
        for plan_item in plan:
            if not plan_item.can_restore:
                skipped += 1
                continue

            item = plan_item.item
            src = Path(item.source)
            dst = Path(item.destination)

            # Re-check immediately before moving (files can change while confirmation was waiting)
            if not dst.exists() and not dst.is_symlink():
                skipped += 1
                continue

            if is_reparse_point_or_symlink(dst) or is_reparse_point_or_symlink(src):
                skipped += 1
                continue

            prot_src, _ = check_protected_path_for_undo(src, base_dir)
            prot_dst, _ = check_protected_path_for_undo(dst, base_dir)
            if prot_src or prot_dst:
                skipped += 1
                continue

            try:
                st = dst.stat()
                if item.kind == "file":
                    if not dst.is_file():
                        skipped += 1
                        continue
                    if item.mtime > 0 and st.st_size != item.size:
                        skipped += 1
                        continue
                else:
                    if not dst.is_dir():
                        skipped += 1
                        continue
                    if item.mtime > 0 and item.folder_entry_count > 0:
                        curr_entries = get_folder_entry_count(dst)
                        if curr_entries != item.folder_entry_count:
                            skipped += 1
                            continue
                if item.mtime > 0 and abs(st.st_mtime - item.mtime) > TIMESTAMP_TOLERANCE_SECONDS:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue

            if plan_item.is_case_only:
                pass
            elif src.exists() or src.is_symlink():
                skipped += 1
                continue

            # Recreate parent directory if needed and authorized
            if plan_item.needs_parent_dir:
                if not recreate_missing_parents:
                    skipped += 1
                    continue
                try:
                    src.parent.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    logger.warning("Failed to recreate parent directory: %s", exc)
                    failed += 1
                    continue

            # Perform safe rename
            try:
                if plan_item.is_case_only:
                    # Windows NTFS supports direct rename for case changes in same directory
                    # Use temporary intermediate name in same directory without overwriting
                    temp_name = src.parent / f".tmp_case_{secrets.token_hex(4)}_{src.name}"
                    os.rename(str(dst), str(temp_name))
                    os.rename(str(temp_name), str(src))
                else:
                    # Same volume move with non-overwriting primitive
                    os.rename(str(dst), str(src))

                restored += 1
                successfully_restored_destinations.add(str(dst).lower())
            except (PermissionError, OSError) as exc:
                logger.warning("Failed to restore item in operation %s: %s", op.id, exc)
                failed += 1

    except KeyboardInterrupt:
        # User aborted during execution: update journal to partial and stop cleanly
        final_status = "partial" if restored > 0 else op.status
        _update_operation_after_undo(base_dir, op.id, final_status, successfully_restored_destinations)
        raise

    # Clean up created empty category folders from organize runs using os.rmdir ONLY
    if op.created_folders:
        for folder_str in op.created_folders:
            folder_p = Path(folder_str)
            try:
                if folder_p.is_dir() and not is_reparse_point_or_symlink(folder_p):
                    # os.rmdir succeeds ONLY if directory is completely empty
                    os.rmdir(str(folder_p))
            except OSError:
                pass  # Folder not empty or in use; leave untouched safely

    # Determine final operation status
    total_restoreable = sum(1 for p in plan if p.can_restore)
    if restored == total_restoreable and restored > 0 and skipped == 0 and failed == 0:
        final_status = "undone"
    elif restored > 0:
        final_status = "partial"
    else:
        final_status = op.status

    _update_operation_after_undo(base_dir, op.id, final_status, successfully_restored_destinations)
    return restored, skipped, failed, final_status


def _update_operation_after_undo(
    base_dir: Path,
    op_id: str,
    new_status: str,
    restored_destinations: set[str],
) -> None:
    """Update operation status in journal under lock."""
    with acquire_journal_lock(base_dir):
        ops = load_journal(base_dir)
        for op in ops:
            if op.id == op_id:
                op.status = new_status
                # Remove successfully restored items from operation so future partial retries
                # only process what remains
                if new_status == "undone":
                    op.items.clear()
                elif new_status == "partial" and restored_destinations:
                    op.items = [
                        it for it in op.items
                        if it.destination.lower() not in restored_destinations
                    ]
                break
        save_journal(base_dir, ops)


def find_latest_undoable_operation(base_dir: Path, op_type: str | None = None) -> JournalOperation | None:
    """Find newest operation with status 'done' or 'partial', optionally filtered by type."""
    ops = load_journal(base_dir)
    for op in reversed(ops):
        if op.status in ("done", "partial"):
            if op_type is None or op.type == op_type:
                return op
    return None
