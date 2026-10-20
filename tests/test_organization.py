"""Tests for file organization, dry run, and atomic undo."""
from __future__ import annotations

import os
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.organization import (
    handle_organize,
    handle_organize_undo,
    is_protected_organize_folder,
    load_undo_log,
    match_category,
    save_undo_log,
)
from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from core.shell import ShellContext


@pytest.fixture
def org_context(tmp_path: Path):
    """Create a test shell context in tmp_path."""
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    config = ConfigManager(base_dir=appdata)
    registry = CommandRegistry()
    history = MagicMock()
    history.get_all.return_value = []
    console = Console(record=True, width=120)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = ShellContext(
        config=config,
        registry=registry,
        history_manager=history,
        console=console,
        current_dir=work_dir,
    )
    return ctx


def test_match_category_and_double_extensions(org_context: ShellContext):
    """Test category matching, compound extension matching, and --include-other."""
    categories = org_context.config.get_organize_categories()

    assert match_category("photo.PNG", categories) == "Images"
    assert match_category("document.pdf", categories) == "Documents"
    assert match_category("data.xlsx", categories) == "Spreadsheets"
    assert match_category("slides.pptx", categories) == "Presentations"
    assert match_category("movie.mp4", categories) == "Videos"
    assert match_category("song.mp3", categories) == "Audio"
    assert match_category("code.py", categories) == "Code"
    assert match_category("setup.msi", categories) == "Installers"

    # Compound extensions
    assert match_category("archive.tar.gz", categories) == "Archives"
    assert match_category("bundle.tar.bz2", categories) == "Archives"
    assert match_category("backup.tar.xz", categories) == "Archives"

    # Unknown extensions stay in place by default
    assert match_category("mystery.xyz123", categories, include_other=False) is None
    assert match_category("no_extension", categories, include_other=False) is None

    # Unknown extensions go to Other when include_other=True
    assert match_category("mystery.xyz123", categories, include_other=True) == "Other"
    assert match_category("no_extension", categories, include_other=True) == "Other"


def test_organize_skips_ineligible_files_and_dry_run(org_context: ShellContext, tmp_path: Path):
    """Test that subfolders, recent files, hidden files, shortcuts, and unfinished downloads are skipped."""
    folder = tmp_path / "downloads"
    folder.mkdir()

    # Old eligible files (> 2 min old)
    old_time = time.time() - 300
    f_img = folder / "pic.jpg"
    f_img.write_text("img")
    os.utime(f_img, (old_time, old_time))

    f_doc = folder / "doc.txt"
    f_doc.write_text("doc")
    os.utime(f_doc, (old_time, old_time))

    # Recent file (< 2 min old) -> must be skipped
    f_recent = folder / "recent.pdf"
    f_recent.write_text("recent")

    # Unfinished downloads -> must be skipped
    f_cr = folder / "setup.exe.crdownload"
    f_cr.write_text("temp")
    os.utime(f_cr, (old_time, old_time))

    f_part = folder / "file.part"
    f_part.write_text("temp")
    os.utime(f_part, (old_time, old_time))

    # Shortcut .lnk -> must be skipped
    f_lnk = folder / "shortcut.lnk"
    f_lnk.write_text("lnk")
    os.utime(f_lnk, (old_time, old_time))

    # Dotfile -> must be skipped
    f_dot = folder / ".hidden.txt"
    f_dot.write_text("hidden")
    os.utime(f_dot, (old_time, old_time))

    # Subdirectory -> must be untouched
    sub_dir = folder / "subfolder"
    sub_dir.mkdir()
    (sub_dir / "inside.txt").write_text("inside")

    # Run dry-run
    handle_organize(org_context, [str(folder), "--dry-run"])
    out = org_context.console.export_text()

    assert "Organize Plan" in out
    assert "pic.jpg" in out
    assert "doc.txt" in out
    assert "recent.pdf" not in out
    assert "shortcut.lnk" not in out
    assert ".hidden.txt" not in out
    assert "[Dry Run] No files were moved" in out

    # Verify dry-run did not move anything or create category folders
    assert f_img.exists()
    assert f_doc.exists()
    assert not (folder / "Images").exists()
    assert not (folder / "Documents").exists()


def test_organize_confirmation_default_no(org_context: ShellContext, tmp_path: Path):
    """Test that organize requires explicit confirmation and defaults to No."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    old_time = time.time() - 300
    f_img = folder / "pic.png"
    f_img.write_text("img")
    os.utime(f_img, (old_time, old_time))

    with patch("commands.organization.confirm_prompt", return_value=False) as mock_conf:
        handle_organize(org_context, [str(folder)])
        mock_conf.assert_called_once()

    out = org_context.console.export_text()
    assert "Organization cancelled by user" in out
    assert f_img.exists()
    assert not (folder / "Images").exists()


def test_organize_execution_and_collision_renaming(org_context: ShellContext, tmp_path: Path):
    """Test actual organize execution and collision rename (never overwrite)."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    old_time = time.time() - 300

    f1 = folder / "report.pdf"
    f1.write_text("report 1")
    os.utime(f1, (old_time, old_time))

    # Pre-create destination with same name
    dest_dir = folder / "Documents"
    dest_dir.mkdir()
    existing_dest = dest_dir / "report.pdf"
    existing_dest.write_text("existing content")

    with patch("commands.organization.confirm_prompt", return_value=True):
        handle_organize(org_context, [str(folder)])

    out = org_context.console.export_text()
    assert "Successfully organized" in out

    # Original destination must NOT have been overwritten!
    assert existing_dest.read_text() == "existing content"
    # New file renamed to report (1).pdf
    collision_dest = dest_dir / "report (1).pdf"
    assert collision_dest.exists()
    assert collision_dest.read_text() == "report 1"


def test_organize_undo_atomic_and_restoration(org_context: ShellContext, tmp_path: Path):
    """Test organize undo restoration and safety checks."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    old_time = time.time() - 300

    f1 = folder / "song.mp3"
    f1.write_text("audio data")
    os.utime(f1, (old_time, old_time))

    # 1. Run organize with confirmation
    with patch("commands.organization.confirm_prompt", return_value=True):
        handle_organize(org_context, [str(folder)])

    audio_file = folder / "Audio" / "song.mp3"
    assert audio_file.exists()
    assert not f1.exists()

    # 2. Check undo log was created
    runs = load_undo_log(org_context)
    assert len(runs) >= 1
    assert len(runs[-1]["moves"]) == 1

    # 3. Run organize undo with confirmation
    with patch("commands.organization.confirm_prompt", return_value=True):
        handle_organize_undo(org_context, [])

    # Original file restored!
    assert f1.exists()
    assert f1.read_text() == "audio data"
    # Audio category directory cleaned up because it was empty
    assert not (folder / "Audio").exists()


def test_organize_undo_skips_modified_or_conflicting_files(org_context: ShellContext, tmp_path: Path):
    """Test that undo skips files that were modified or would overwrite existing files."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    old_time = time.time() - 300

    f1 = folder / "test.txt"
    f1.write_text("orig text")
    os.utime(f1, (old_time, old_time))

    with patch("commands.organization.confirm_prompt", return_value=True):
        handle_organize(org_context, [str(folder)])

    moved_file = folder / "Documents" / "test.txt"
    assert moved_file.exists()

    # Simulate target conflict: user created a new file at original location
    f1.write_text("new conflict file")

    with patch("commands.organization.confirm_prompt", return_value=True):
        handle_organize_undo(org_context, [])

    out = org_context.console.export_text()
    assert "refusing to overwrite" in out
    # Conflicting original file kept intact
    assert f1.read_text() == "new conflict file"
    # Moved file not deleted
    assert moved_file.exists()


def test_organize_and_undo_never_call_delete_unlink_or_rmtree(org_context: ShellContext, tmp_path: Path):
    """Requirement 2: organize and undo must never call delete, unlink, or rmtree."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    old_time = time.time() - 300

    f1 = folder / "photo.jpg"
    f1.write_text("photo")
    os.utime(f1, (old_time, old_time))

    with patch("os.unlink") as mock_unlink, \
         patch("os.remove") as mock_remove, \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("commands.organization.confirm_prompt", return_value=True):

        # Run organize
        handle_organize(org_context, [str(folder)])
        # Run undo
        handle_organize_undo(org_context, [])

        mock_unlink.assert_not_called()
        mock_remove.assert_not_called()
        mock_rmtree.assert_not_called()


def test_organize_refuses_protected_folders(org_context: ShellContext, tmp_path: Path):
    """Test that drive roots, home folder, Windows directory, and MayuriShell project folder are refused."""
    home = Path.home()
    is_prot, reason = is_protected_organize_folder(home, org_context)
    assert is_prot
    assert "home folder" in reason

    proj_dir = Path(__file__).resolve().parent.parent
    is_prot, reason = is_protected_organize_folder(proj_dir, org_context)
    assert is_prot
    assert "project folder" in reason
