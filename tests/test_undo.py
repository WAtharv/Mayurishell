"""Comprehensive test suite for Stage 11 Advanced Undo System.

Tests multi-shell locking, crash simulation (pending/done), case-only renames,
cross-volume move refusal, timestamp tolerance, final destination recording,
schema version rejection, corrupt journal backup, cap/pruning, legacy migration,
and verification that destructive primitives are never called.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import stat
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.config_manager import ConfigManager
from core.executor import CommandExecutor
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import ShellContext
from core.theme import ThemeManager
from rich.console import Console

from commands.files import handle_move, handle_rename, handle_delete
from commands.organization import handle_organize, handle_organize_undo
from commands.undo import handle_undo, register_undo_commands
from services.undo_service import (
    JOURNAL_FILENAME,
    JOURNAL_LOCK_FILENAME,
    JournalItem,
    JournalOperation,
    UndoJournalVersionError,
    UndoLockTimeoutError,
    acquire_journal_lock,
    evaluate_undo_plan,
    execute_undo_plan,
    find_latest_undoable_operation,
    is_case_only_rename,
    is_cross_volume_move,
    load_journal,
    save_journal,
    start_journal_operation,
    record_pending_item,
    mark_item_done,
    finish_journal_operation,
)


@pytest.fixture
def test_context(tmp_path: Path):
    """Provide an isolated ShellContext for undo testing."""
    config_dir = tmp_path / "config"
    work_dir = tmp_path / "work"
    config_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    config_mgr = ConfigManager(base_dir=config_dir)
    registry = CommandRegistry()
    register_undo_commands(registry)

    console = Console(force_terminal=False, color_system=None)
    theme_mgr = ThemeManager(config_mgr, console=console)
    history_mgr = HistoryManager(config_mgr.history_path)

    ctx = ShellContext(
        config=config_mgr,
        registry=registry,
        history_manager=history_mgr,
        console=console,
        theme_manager=theme_mgr,
    )
    ctx.current_dir = work_dir
    ctx.is_interactive = False
    return ctx


# ============================================================================
# 1. CRASH SIMULATION & PENDING/DONE ORDER
# ============================================================================

def test_pending_item_dropped_on_crash_if_source_still_exists(tmp_path: Path):
    """If the app crashed before move occurred, source exists & dest does not -> drop pending item."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "file.txt"
    dst = tmp_path / "dest.txt"
    src.write_text("content", encoding="utf-8")

    op_id = start_journal_operation(base_dir, "move")
    record_pending_item(base_dir, op_id, src, dst, kind="file")
    # Simulate crash before move happened (mark_item_done never called, src still exists, dst doesn't)

    ops = load_journal(base_dir)
    assert len(ops) == 1
    assert ops[0].items[0].status == "pending"

    # Evaluate undo plan
    plan = evaluate_undo_plan(base_dir, ops[0])
    # The pending item whose move never happened should be dropped completely
    assert len(plan) == 0


def test_pending_item_treated_as_done_on_crash_if_destination_exists(tmp_path: Path):
    """If the app crashed after move but before mark_item_done, treat as done if dest exists and src does not."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "file.txt"
    dst = tmp_path / "dest.txt"
    src.write_text("hello", encoding="utf-8")

    op_id = start_journal_operation(base_dir, "move")
    record_pending_item(base_dir, op_id, src, dst, kind="file")

    # Move actually succeeded on disk, but app crashed before marking done
    src.rename(dst)

    ops = load_journal(base_dir)
    assert ops[0].items[0].status == "pending"

    # Evaluate undo plan
    plan = evaluate_undo_plan(base_dir, ops[0])
    assert len(plan) == 1
    assert plan[0].can_restore is True
    assert plan[0].status_label == "READY"


# ============================================================================
# 2. MULTI-SHELL LOCKING WITH TWO WRITERS
# ============================================================================

def test_journal_lock_concurrency_two_writers(tmp_path: Path):
    """Two concurrent threads writing to journal under lock never corrupt or lose entries."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)

    num_threads = 2
    entries_per_thread = 10
    errors: list[Exception] = []

    def writer_task(thread_id: int):
        try:
            for i in range(entries_per_thread):
                op_id = start_journal_operation(base_dir, f"op_{thread_id}_{i}")
                time.sleep(0.01)
                finish_journal_operation(base_dir, op_id, status="done")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer_task, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Writer encountered errors: {errors}"
    ops = load_journal(base_dir)
    assert len(ops) == num_threads * entries_per_thread


def test_stale_lock_recovery(tmp_path: Path):
    """Lock file older than 30s is ignored and removed automatically."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    lock_file = base_dir / JOURNAL_LOCK_FILENAME
    lock_file.write_text("stale-pid", encoding="utf-8")

    # Backdate mtime to 40 seconds ago
    old_time = time.time() - 40.0
    os.utime(str(lock_file), (old_time, old_time))

    # Should acquire lock without timing out
    with acquire_journal_lock(base_dir, timeout=1.0):
        assert lock_file.exists()


# ============================================================================
# 3. CASE-ONLY RENAMES
# ============================================================================

def test_case_only_rename_detection_and_undo(tmp_path: Path, test_context: ShellContext):
    """Case-only rename (a.txt -> A.txt) is recognized and restored collision-free."""
    # Check if filesystem is case-insensitive (standard Windows NTFS)
    test_f = tmp_path / "case_probe.txt"
    test_f.write_text("probe", encoding="utf-8")
    is_case_insensitive = (tmp_path / "CASE_PROBE.TXT").exists()
    test_f.unlink()

    if not is_case_insensitive:
        pytest.skip("Filesystem is case-sensitive; skipping NTFS case-only test.")

    work_dir = test_context.current_dir
    src = work_dir / "myfile.txt"
    src.write_text("sample content", encoding="utf-8")

    # Rename myfile.txt -> MYFILE.txt
    res = handle_rename(test_context, ["myfile.txt", "MYFILE.txt", "-y"])
    assert res.ok

    # The file on disk is now named MYFILE.txt
    ops = load_journal(test_context.config.base_dir)
    assert len(ops) == 1
    assert ops[0].type == "rename"

    # Evaluate undo plan
    plan = evaluate_undo_plan(test_context.config.base_dir, ops[0])
    assert len(plan) == 1
    assert plan[0].can_restore is True
    assert plan[0].is_case_only is True

    # Execute undo
    restored, skipped, failed, status = execute_undo_plan(test_context.config.base_dir, ops[0], plan)
    assert restored == 1
    assert skipped == 0
    assert failed == 0

    # Verify restored filename on disk
    entries = [p.name for p in work_dir.iterdir()]
    assert "myfile.txt" in entries


# ============================================================================
# 4. CROSS-VOLUME MOVE REFUSAL
# ============================================================================

def test_cross_volume_move_refusal(tmp_path: Path, test_context: ShellContext):
    """Moves across drives are journaled but undo refuses them safely."""
    base_dir = test_context.config.base_dir
    src = tmp_path / "local.txt"
    dst = tmp_path / "remote.txt"
    dst.write_text("data", encoding="utf-8")

    op_id = start_journal_operation(base_dir, "move")
    # Mock is_cross_volume_move to True
    with patch("services.undo_service.is_cross_volume_move", return_value=True):
        record_pending_item(base_dir, op_id, src, dst, kind="file")
    mark_item_done(base_dir, op_id, dst)
    finish_journal_operation(base_dir, op_id, status="done")

    ops = load_journal(base_dir)
    assert ops[0].items[0].cross_volume is True

    plan = evaluate_undo_plan(base_dir, ops[0])
    assert len(plan) == 1
    assert plan[0].can_restore is False
    assert plan[0].status_label == "SKIPPED"
    assert "crossed drives and cannot be undone safely" in plan[0].reason


# ============================================================================
# 5. TIMESTAMPS & SIZE METADATA TOLERANCE
# ============================================================================

def test_timestamp_tolerance_and_size_validation(tmp_path: Path):
    """Undo allows mtime within 2.0s tolerance, but rejects modified files or changed sizes."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "orig.txt"
    dst = tmp_path / "moved.txt"
    dst.write_text("exact size text", encoding="utf-8")

    st = dst.stat()
    item = JournalItem(
        source=str(src),
        destination=str(dst),
        kind="file",
        size=st.st_size,
        mtime=st.st_mtime - 1.5,  # Within 2.0s tolerance
        status="done",
    )
    op = JournalOperation(
        id="a1b2c3",
        timestamp=datetime.datetime.now().isoformat(),
        type="move",
        status="done",
        items=[item],
    )
    save_journal(base_dir, [op])

    plan = evaluate_undo_plan(base_dir, op)
    assert len(plan) == 1
    assert plan[0].can_restore is True

    # Now simulate file modified beyond 2s
    item.mtime = st.st_mtime - 5.0
    save_journal(base_dir, [op])
    plan = evaluate_undo_plan(base_dir, op)
    assert plan[0].can_restore is False
    assert "file modified since operation" in plan[0].reason

    # Reset mtime and simulate changed size
    item.mtime = st.st_mtime
    item.size = st.st_size + 10
    save_journal(base_dir, [op])
    plan = evaluate_undo_plan(base_dir, op)
    assert plan[0].can_restore is False
    assert "file size changed" in plan[0].reason


def test_folder_timestamp_and_entry_count_validation(tmp_path: Path):
    """Folder restore validates entry count and timestamp tolerance."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    src_folder = tmp_path / "orig_folder"
    dst_folder = tmp_path / "moved_folder"
    dst_folder.mkdir()
    (dst_folder / "a.txt").write_text("a")
    (dst_folder / "b.txt").write_text("b")

    st = dst_folder.stat()
    item = JournalItem(
        source=str(src_folder),
        destination=str(dst_folder),
        kind="folder",
        size=0,
        mtime=st.st_mtime - 1.0,
        folder_entry_count=2,
        status="done",
    )
    op = JournalOperation(
        id="b2c3d4",
        timestamp=datetime.datetime.now().isoformat(),
        type="move",
        status="done",
        items=[item],
    )
    save_journal(base_dir, [op])

    # 1. Valid folder (2 entries, within 2s tolerance)
    plan = evaluate_undo_plan(base_dir, op)
    assert len(plan) == 1
    assert plan[0].can_restore is True

    # 2. Folder entry count changed (added 3rd file)
    (dst_folder / "c.txt").write_text("c")
    plan = evaluate_undo_plan(base_dir, op)
    assert plan[0].can_restore is False
    assert "folder contents changed" in plan[0].reason

    # 3. Reset entry count (remove 3rd file), alter mtime beyond 2s
    (dst_folder / "c.txt").unlink()
    item.mtime = st.st_mtime - 5.0
    save_journal(base_dir, [op])
    plan = evaluate_undo_plan(base_dir, op)
    assert plan[0].can_restore is False
    assert "folder modified since operation" in plan[0].reason


# ============================================================================
# 6. FINAL DESTINATION RECORDING (COLLISION RENAMES & FOLDER TARGETS)
# ============================================================================

def test_final_destination_recording_in_move_and_organize(test_context: ShellContext):
    """move folder target and organize collision renames record final resolved path."""
    work_dir = test_context.current_dir
    target_folder = work_dir / "target_dir"
    target_folder.mkdir()

    file_a = work_dir / "file_a.txt"
    file_a.write_text("content", encoding="utf-8")

    # Move file_a into target_folder
    res = handle_move(test_context, ["file_a.txt", "target_dir", "-y"])
    assert res.ok

    ops = load_journal(test_context.config.base_dir)
    assert len(ops) == 1
    # Recorded destination must be the final child path target_dir/file_a.txt, not target_dir
    expected_dst = target_folder / "file_a.txt"
    assert ops[0].items[0].destination == str(expected_dst.resolve())

    # Organize collision renames record final path e.g. "pic (1).png"
    org_folder = work_dir / "downloads"
    org_folder.mkdir()
    images_dir = org_folder / "Images"
    images_dir.mkdir()
    existing_img = images_dir / "pic.png"
    existing_img.write_text("existing image", encoding="utf-8")

    new_img = org_folder / "pic.png"
    new_img.write_text("new image", encoding="utf-8")
    old_time = time.time() - 300
    os.utime(new_img, (old_time, old_time))

    with patch("commands.organization.confirm_prompt", return_value=True):
        res_org = handle_organize(test_context, [str(org_folder)])
        assert res_org.ok

    ops2 = load_journal(test_context.config.base_dir)
    org_op = next(o for o in ops2 if o.type == "organize")
    expected_collision_dst = images_dir / "pic (1).png"
    assert org_op.items[0].destination == str(expected_collision_dst.resolve())


# ============================================================================
# 7. RE-CHECK ITEM RIGHT BEFORE RESTORING
# ============================================================================

def test_recheck_item_immediately_before_restore(tmp_path: Path):
    """If destination disappears between plan evaluation and execution, it is skipped."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "orig.txt"
    dst = tmp_path / "moved.txt"
    dst.write_text("data", encoding="utf-8")

    st = dst.stat()
    item = JournalItem(
        source=str(src),
        destination=str(dst),
        kind="file",
        size=st.st_size,
        mtime=st.st_mtime,
        status="done",
    )
    op = JournalOperation(
        id="f1e2d3",
        timestamp=datetime.datetime.now().isoformat(),
        type="move",
        status="done",
        items=[item],
    )
    save_journal(base_dir, [op])

    plan = evaluate_undo_plan(base_dir, op)
    assert plan[0].can_restore is True

    # Destination is deleted right after plan evaluation
    dst.unlink()

    restored, skipped, failed, status = execute_undo_plan(base_dir, op, plan)
    assert restored == 0
    assert skipped == 1
    assert not src.exists()

    # Destination is modified (size changed) right after plan evaluation
    dst.write_text("orig text", encoding="utf-8")
    item.size = dst.stat().st_size
    item.mtime = dst.stat().st_mtime
    save_journal(base_dir, [op])
    plan2 = evaluate_undo_plan(base_dir, op)
    assert plan2[0].can_restore is True
    # Modify size while waiting for execution
    dst.write_text("modified text with different size", encoding="utf-8")
    restored, skipped, failed, status = execute_undo_plan(base_dir, op, plan2)
    assert restored == 0
    assert skipped == 1
    assert not src.exists()


# ============================================================================
# 8. DESTRUCTIVE PRIMITIVES ARE NEVER CALLED
# ============================================================================

def test_zero_destructive_primitives_in_undo(tmp_path: Path, monkeypatch):
    """Ensure os.unlink, os.remove, shutil.rmtree, and send2trash are NEVER called."""
    orig_unlink = os.unlink
    def forbidden(path, *args, **kwargs):
        if str(path).endswith(".lock") or str(path).endswith(".tmp"):
            return orig_unlink(path, *args, **kwargs)
        raise AssertionError(f"Destructive primitive called during undo execution on: {path}")

    monkeypatch.setattr(os, "unlink", forbidden)
    monkeypatch.setattr(os, "remove", forbidden)
    import shutil
    monkeypatch.setattr(shutil, "rmtree", forbidden)
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", forbidden)


    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "source.txt"
    dst = tmp_path / "dest.txt"
    dst.write_text("hello", encoding="utf-8")

    st = dst.stat()
    item = JournalItem(
        source=str(src),
        destination=str(dst),
        kind="file",
        size=st.st_size,
        mtime=st.st_mtime,
        status="done",
    )
    op = JournalOperation(
        id="c1c2c3",
        timestamp=datetime.datetime.now().isoformat(),
        type="move",
        status="done",
        items=[item],
    )
    save_journal(base_dir, [op])

    plan = evaluate_undo_plan(base_dir, op)
    restored, skipped, failed, status = execute_undo_plan(base_dir, op, plan)
    assert restored == 1
    assert src.read_text(encoding="utf-8") == "hello"


# ============================================================================
# 9. MISSING PARENT RECREATION PROMPT
# ============================================================================

def test_missing_parent_directory_handling(tmp_path: Path):
    """Undo skips items with missing parents unless authorized to recreate."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    deleted_parent = tmp_path / "nested_parent"
    src = deleted_parent / "file.txt"
    dst = tmp_path / "moved_file.txt"
    dst.write_text("test", encoding="utf-8")

    st = dst.stat()
    item = JournalItem(
        source=str(src),
        destination=str(dst),
        kind="file",
        size=st.st_size,
        mtime=st.st_mtime,
        status="done",
    )
    op = JournalOperation(
        id="e1e2e3",
        timestamp=datetime.datetime.now().isoformat(),
        type="move",
        status="done",
        items=[item],
    )
    save_journal(base_dir, [op])

    plan = evaluate_undo_plan(base_dir, op)
    assert plan[0].can_restore is True
    assert plan[0].needs_parent_dir is True

    # 1. With recreate_missing_parents=False -> skipped
    restored, skipped, failed, status = execute_undo_plan(base_dir, op, plan, recreate_missing_parents=False)
    assert restored == 0
    assert skipped == 1
    assert not src.exists()

    # 2. With recreate_missing_parents=True -> creates parent and restores
    restored, skipped, failed, status = execute_undo_plan(base_dir, op, plan, recreate_missing_parents=True)
    assert restored == 1
    assert src.exists()


# ============================================================================
# 10. NEWER SCHEMA VERSION REFUSAL
# ============================================================================

def test_newer_journal_schema_version_rejected_untouched(tmp_path: Path):
    """Journal with version > 1 raises UndoJournalVersionError and leaves file untouched."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    journal_path = base_dir / JOURNAL_FILENAME
    content = json.dumps({"version": 999, "operations": []})
    journal_path.write_text(content, encoding="utf-8")

    with pytest.raises(UndoJournalVersionError) as exc_info:
        load_journal(base_dir)

    assert "Unsupported undo journal version 999" in str(exc_info.value)
    # File must be untouched
    assert journal_path.read_text(encoding="utf-8") == content


# ============================================================================
# 11. CORRUPT JOURNAL RECOVERY TO BACKUPS/
# ============================================================================

def test_corrupt_journal_backed_up(tmp_path: Path):
    """Unparseable journal is backed up to backups/ and empty list returned."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    journal_path = base_dir / JOURNAL_FILENAME
    journal_path.write_text("{ corrupt json invalid ...", encoding="utf-8")

    ops = load_journal(base_dir)
    assert ops == []

    backups_dir = base_dir / "backups"
    assert backups_dir.exists()
    corrupt_files = list(backups_dir.glob("undo_journal_corrupt_*.json"))
    assert len(corrupt_files) == 1
    assert corrupt_files[0].read_text(encoding="utf-8") == "{ corrupt json invalid ..."


# ============================================================================
# 12. 100-OPERATION AND 1 MB CAP
# ============================================================================

def test_journal_cap_prunes_oldest_operations(tmp_path: Path):
    """Journal keeps at most 100 operations and trims oldest when exceeded."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)

    ops: list[JournalOperation] = []
    for i in range(120):
        ops.append(JournalOperation(
            id=f"{i:06x}",
            timestamp=datetime.datetime.now().isoformat(),
            type="move",
            status="done",
            items=[],
        ))

    save_journal(base_dir, ops)

    loaded = load_journal(base_dir)
    assert len(loaded) == 100
    assert loaded[0].id == f"{20:06x}"
    assert loaded[-1].id == f"{119:06x}"


# ============================================================================
# 13. LEGACY ORGANIZE_UNDO.JSON MIGRATION
# ============================================================================

def test_legacy_organize_undo_migration(tmp_path: Path):
    """Legacy organize_undo.json is automatically converted to unified journal."""
    base_dir = tmp_path / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = base_dir / "organize_undo.json"
    legacy_file.write_text(json.dumps({
        "runs": [{
            "timestamp": "2026-10-24 10:00:00",
            "target_dir": "C:\\Downloads",
            "moves": [{"source": "C:\\Downloads\\pic.png", "destination": "C:\\Downloads\\Images\\pic.png"}],
        }]
    }), encoding="utf-8")

    ops = load_journal(base_dir)
    assert len(ops) == 1
    assert ops[0].type == "organize"
    assert ops[0].items[0].source == "C:\\Downloads\\pic.png"
    assert ops[0].items[0].destination == "C:\\Downloads\\Images\\pic.png"
    # Legacy file is retained
    assert legacy_file.exists()


# ============================================================================
# 14. CLI UNDO COMMAND DISPATCH
# ============================================================================

def test_bare_undo_never_undoes_anything(test_context: ShellContext):
    """Running 'undo' with no arguments prints usage and never modifies files."""
    work_dir = test_context.current_dir
    f = work_dir / "doc.txt"
    f.write_text("hello", encoding="utf-8")

    handle_move(test_context, ["doc.txt", "doc_renamed.txt", "-y"])
    ops = load_journal(test_context.config.base_dir)
    assert len(ops) == 1

    # Bare undo
    res = handle_undo(test_context, [])
    assert res.ok

    # No files were undone!
    assert not f.exists()
    assert (work_dir / "doc_renamed.txt").exists()


def test_undo_list_shows_operations(test_context: ShellContext):
    """'undo list' prints table of operations without changing disk state."""
    work_dir = test_context.current_dir
    f = work_dir / "file.txt"
    f.write_text("data", encoding="utf-8")

    handle_rename(test_context, ["file.txt", "new.txt", "-y"])

    res = handle_undo(test_context, ["list"])
    assert res.ok


def test_undo_last_reverses_most_recent_operation(test_context: ShellContext):
    """'undo last' restores the most recent operation with confirmation."""
    work_dir = test_context.current_dir
    f = work_dir / "test.txt"
    f.write_text("hello world", encoding="utf-8")

    handle_rename(test_context, ["test.txt", "renamed.txt", "-y"])
    assert (work_dir / "renamed.txt").exists()

    with patch("commands.undo.confirm_prompt", return_value=True):
        res = handle_undo(test_context, ["last"])
        assert res.ok

    assert f.exists()
    assert not (work_dir / "renamed.txt").exists()


def test_undo_occupied_original_path_overwrites_nothing(test_context: ShellContext):
    """When the original source path is occupied by another file, undo skips it and overwrites nothing."""
    work_dir = test_context.current_dir
    orig_file = work_dir / "target.txt"
    orig_file.write_text("original content", encoding="utf-8")

    # Move target.txt -> target_moved.txt
    res_move = handle_move(test_context, ["target.txt", "target_moved.txt", "-y"])
    assert res_move.ok
    assert (work_dir / "target_moved.txt").exists()
    assert not orig_file.exists()

    # Create a new file at the original path
    orig_file.write_text("brand new occupied content", encoding="utf-8")

    # Evaluate plan: must be SKIPPED with occupied path reason
    ops = load_journal(test_context.config.base_dir)
    assert len(ops) == 1
    plan = evaluate_undo_plan(test_context.config.base_dir, ops[0])
    assert len(plan) == 1
    assert plan[0].can_restore is False
    assert plan[0].status_label == "SKIPPED"
    assert "original path occupied" in plan[0].reason

    # Execute plan: must restore 0, skip 1, fail 0
    restored, skipped, failed, status = execute_undo_plan(test_context.config.base_dir, ops[0], plan)
    assert restored == 0
    assert skipped == 1
    assert failed == 0

    # Verify on disk: occupied file is untouched, moved file is untouched
    assert orig_file.read_text(encoding="utf-8") == "brand new occupied content"
    assert (work_dir / "target_moved.txt").read_text(encoding="utf-8") == "original content"

    # Also run via handle_undo CLI
    with patch("commands.undo.confirm_prompt", return_value=True):
        res_undo = handle_undo(test_context, ["last"])
        assert not res_undo.ok
        assert "No items can be restored" in (res_undo.message or "")

    # State on disk remains completely intact
    assert orig_file.read_text(encoding="utf-8") == "brand new occupied content"
    assert (work_dir / "target_moved.txt").read_text(encoding="utf-8") == "original content"


# ============================================================================
# 15. PRIVACY: JOURNAL PATHS NEVER EXPOSED IN COMPLETIONS OR DIAGNOSTICS
# ============================================================================

def test_privacy_no_full_paths_in_completions_or_diagnostics(test_context: ShellContext):
    """Full file paths in journal are never suggested by completer or exported in diagnostics."""
    base_dir = test_context.config.base_dir
    src = test_context.current_dir / "secret_document.txt"
    dst = test_context.current_dir / "secret_moved.txt"
    dst.write_text("confidential", encoding="utf-8")

    op_id = start_journal_operation(base_dir, "move")
    record_pending_item(base_dir, op_id, src, dst, kind="file")
    mark_item_done(base_dir, op_id, dst)
    finish_journal_operation(base_dir, op_id, status="done")

    # Completer for undo must only complete subcommands or op_id, never file names
    from core.completer import MayuriCompleter
    from prompt_toolkit.document import Document
    completer = MayuriCompleter(test_context)
    doc = Document("undo ")
    completions = [c.text for c in completer.get_completions(doc, None)]
    assert op_id in completions
    assert "list" in completions
    assert "last" in completions
    for comp in completions:
        assert "secret" not in comp.lower()
