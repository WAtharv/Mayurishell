"""Unit tests for file_service."""
from pathlib import Path
from unittest.mock import patch
import pytest

from services.file_service import (
    copy_path,
    create_directory,
    create_file,
    format_bytes,
    get_path_info,
    is_network_or_removable,
    is_protected_path,
    list_directory,
    move_path,
    recycle_path,
    rename_path,
    resolve_path,
    search_files,
)


def test_format_bytes() -> None:
    """Test byte formatting into human-readable strings."""
    assert format_bytes(500) == "500 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1048576) == "1.0 MB"


def test_resolve_path_precedence(tmp_path: Path) -> None:
    """Test that local directory takes precedence over a shortcut of the same name."""
    shortcuts = {"projects": str(tmp_path / "global_projects")}
    
    # Create a local directory named 'projects' in current_dir
    local_proj = tmp_path / "projects"
    local_proj.mkdir()

    resolved, note = resolve_path("projects", current_dir=tmp_path, folder_shortcuts=shortcuts)
    assert resolved == local_proj.resolve()
    assert note is not None
    assert "precedence over shortcut" in note


def test_resolve_path_shortcut(tmp_path: Path) -> None:
    """Test resolving a folder shortcut when no local item matches."""
    global_target = tmp_path / "somewhere_else"
    global_target.mkdir()
    shortcuts = {"work": str(global_target)}

    resolved, note = resolve_path("work", current_dir=tmp_path, folder_shortcuts=shortcuts)
    assert resolved == global_target.resolve()
    assert note is not None
    assert "Resolved folder shortcut 'work'" in note


def test_resolve_path_relative_and_parent(tmp_path: Path) -> None:
    """Test relative path and .. resolution."""
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)

    resolved, _ = resolve_path("..", current_dir=sub)
    assert resolved == (tmp_path / "a").resolve()

    resolved, _ = resolve_path("sub_item", current_dir=tmp_path)
    assert resolved == (tmp_path / "sub_item").resolve()


def test_is_protected_path(tmp_path: Path) -> None:
    """Test rejection of protected paths."""
    appdata = tmp_path / "AppData" / "MayuriShell"
    project_root = tmp_path / "MayuriShell"
    current_dir = tmp_path / "work"
    sub_dir = current_dir / "nested"
    current_dir.mkdir(parents=True)
    sub_dir.mkdir(parents=True)

    shortcuts = {"desktop": str(tmp_path / "Desktop")}

    # Current directory and its parents are protected
    is_prot, reason = is_protected_path(current_dir, current_dir, appdata, project_root, shortcuts)
    assert is_prot is True
    assert "current working directory" in reason

    ancestor_dir = tmp_path / "other_work"
    deep_dir = ancestor_dir / "deep"
    deep_dir.mkdir(parents=True)
    is_prot, reason = is_protected_path(ancestor_dir, deep_dir, appdata, project_root, shortcuts)
    assert is_prot is True
    assert "ancestor of the current working directory" in reason

    # Project root is protected
    is_prot, reason = is_protected_path(project_root, current_dir, appdata, project_root, shortcuts)
    assert is_prot is True
    assert "project folder" in reason

    # Appdata is protected
    is_prot, reason = is_protected_path(appdata, current_dir, appdata, project_root, shortcuts)
    assert is_prot is True
    assert "appdata" in reason

    # Folder shortcut target is protected
    desktop = Path(shortcuts["desktop"])
    is_prot, reason = is_protected_path(desktop, current_dir, appdata, project_root, shortcuts)
    assert is_prot is True
    assert "folder shortcut 'desktop'" in reason

    # Normal nested folder in current_dir is NOT protected
    is_prot, _ = is_protected_path(sub_dir, current_dir, appdata, project_root, shortcuts)
    assert is_prot is False


def test_list_directory_and_pattern_filtering(tmp_path: Path) -> None:
    """Test directory listing, hidden file suppression, and glob matching."""
    (tmp_path / "script.py").write_text("print('hi')")
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / ".hidden").write_text("secret")
    (tmp_path / "subdir").mkdir()

    # Default listing (hides .hidden)
    items = list_directory(tmp_path, show_hidden=False)
    names = [i.name for i in items]
    assert "script.py" in names
    assert "notes.txt" in names
    assert "subdir" in names
    assert ".hidden" not in names

    # Show hidden
    items_all = list_directory(tmp_path, show_hidden=True)
    assert any(i.name == ".hidden" for i in items_all)

    # Filter with pattern
    items_py = list_directory(tmp_path, pattern="*.py")
    py_names = [i.name for i in items_py]
    assert py_names == ["script.py"]


def test_copy_and_move_nesting_prevention(tmp_path: Path) -> None:
    """Test that copying or moving a folder into itself or its subfolder is refused."""
    parent = tmp_path / "parent_folder"
    parent.mkdir()
    sub = parent / "sub"
    sub.mkdir()

    # Refuse copying folder into itself
    with pytest.raises(ValueError) as exc_info:
        copy_path(parent, parent)
    assert "itself or one of its own subfolders" in str(exc_info.value)

    # Refuse copying folder into subfolder
    with pytest.raises(ValueError) as exc_info:
        copy_path(parent, sub / "parent_folder")
    assert "itself or one of its own subfolders" in str(exc_info.value)

    # Refuse moving folder into subfolder
    with pytest.raises(ValueError) as exc_info:
        move_path(parent, sub / "parent_folder")
    assert "itself or one of its own subfolders" in str(exc_info.value)


def test_copy_and_move_overwrite_protection(tmp_path: Path) -> None:
    """Test overwrite protection for copy and move."""
    file1 = tmp_path / "f1.txt"
    file2 = tmp_path / "f2.txt"
    file1.write_text("content 1")
    file2.write_text("content 2")

    # Copy without overwrite should fail
    with pytest.raises(FileExistsError):
        copy_path(file1, file2, overwrite=False)

    # Copy with overwrite
    copy_path(file1, file2, overwrite=True)
    assert file2.read_text() == "content 1"

    # Move without overwrite should fail
    file3 = tmp_path / "f3.txt"
    file3.write_text("content 3")
    with pytest.raises(FileExistsError):
        move_path(file3, file2, overwrite=False)

    # Move with overwrite
    move_path(file3, file2, overwrite=True)
    assert file2.read_text() == "content 3"
    assert not file3.exists()


def test_rename_path_separators_rejected(tmp_path: Path) -> None:
    """Test rename rejects slashes and backslashes."""
    f = tmp_path / "doc.txt"
    f.write_text("text")

    with pytest.raises(ValueError) as exc:
        rename_path(f, "sub/doc.txt")
    assert "plain filename with no path separators" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        rename_path(f, "sub\\doc.txt")
    assert "plain filename with no path separators" in str(exc.value)

    # Valid rename
    renamed = rename_path(f, "doc_new.txt")
    assert renamed.name == "doc_new.txt"
    assert renamed.exists()


def test_recycle_path_directory_recursive_flag(tmp_path: Path) -> None:
    """Test delete requires recursive flag for directories and calls send2trash."""
    d = tmp_path / "my_dir"
    d.mkdir()

    # Directory without recursive flag fails
    with pytest.raises(IsADirectoryError) as exc:
        recycle_path(d, recursive=False)
    assert "Use -r / --recursive" in str(exc.value)

    # Directory with recursive flag calls send2trash
    with patch("services.file_service.send2trash.send2trash") as mock_trash:
        recycle_path(d, recursive=True)
        mock_trash.assert_called_once_with(str(d))


def test_search_files(tmp_path: Path) -> None:
    """Test search_files with wildcards, exclusions, and limit."""
    root1 = tmp_path / "root1"
    root1.mkdir()
    (root1 / "match1.py").write_text("code")
    (root1 / "other.txt").write_text("text")

    # Excluded folder
    node_modules = root1 / "node_modules"
    node_modules.mkdir()
    (node_modules / "match2.py").write_text("ignored")

    matches, skipped, hit_limit = search_files(
        search_roots=[root1],
        query="match*.py",
        excluded_names={"node_modules"},
        limit=10,
    )
    assert len(matches) == 1
    assert matches[0].name == "match1.py"
    assert skipped == 0
    assert hit_limit is False
