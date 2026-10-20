"""Tests for runtime path helpers, frozen environment detection, and install-folder protections."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from commands.organization import is_protected_organize_folder
from core.paths import get_app_root, get_bundle_resource_dir, is_frozen, validate_config_dir
from services.file_service import is_protected_path


def test_is_frozen_detection():
    """Test is_frozen returns True when sys.frozen is set and False otherwise."""
    with patch.object(sys, "frozen", True, create=True):
        assert is_frozen() is True

    # When attribute does not exist
    if hasattr(sys, "frozen"):
        delattr(sys, "frozen")
    assert is_frozen() is False


def test_get_app_root_normal_and_frozen(tmp_path: Path):
    """Test get_app_root returns repo root normally and exe dir when frozen."""
    # 1. Normal (from source)
    repo_root = Path(__file__).resolve().parent.parent
    assert get_app_root() == repo_root

    # 2. Frozen
    fake_exe = tmp_path / "installed" / "MayuriShell.exe"
    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "executable", str(fake_exe)):
            assert get_app_root() == fake_exe.parent


def test_get_bundle_resource_dir(tmp_path: Path):
    """Test get_bundle_resource_dir resolves sys._MEIPASS when present."""
    fake_meipass = tmp_path / "_MEI123456"
    fake_meipass.mkdir()

    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "_MEIPASS", str(fake_meipass), create=True):
            assert get_bundle_resource_dir() == fake_meipass


def test_validate_config_dir_valid(tmp_path: Path):
    """Test that a clean custom directory is accepted."""
    custom_cfg = tmp_path / "my_custom_config"
    valid, reason = validate_config_dir(custom_cfg)
    assert valid is True
    assert reason == ""


def test_validate_config_dir_refusals(tmp_path: Path):
    """Test that dangerous paths are refused for config directory."""
    # 1. Drive root
    drive_root = Path("C:\\") if sys.platform == "win32" else Path("/")
    valid, reason = validate_config_dir(drive_root)
    assert valid is False
    assert "drive root" in reason.lower()

    # 2. Home folder
    valid, reason = validate_config_dir(Path.home())
    assert valid is False
    assert "home folder" in reason.lower()

    # 3. Windows folder
    windir = Path(os.getenv("WINDIR", "C:\\Windows"))
    valid, reason = validate_config_dir(windir)
    assert valid is False
    assert "windows" in reason.lower()

    # 4. Program Files
    prog_files = Path(os.getenv("ProgramFiles", "C:\\Program Files"))
    valid, reason = validate_config_dir(prog_files)
    assert valid is False
    assert "program files" in reason.lower()

    # 5. Inside project folder (running from source)
    inside_project = Path(__file__).resolve().parent.parent / "my_cfg"
    valid, reason = validate_config_dir(inside_project)
    assert valid is False
    assert "project folder" in reason.lower()

    # 6. Inside install folder (when frozen)
    fake_install = tmp_path / "InstalledPrograms" / "MayuriShell"
    fake_exe = fake_install / "MayuriShell.exe"
    inside_install = fake_install / "user_config"
    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "executable", str(fake_exe)):
            valid, reason = validate_config_dir(inside_install)
            assert valid is False
            assert "install folder" in reason.lower()


def test_protected_install_folder_in_delete(tmp_path: Path):
    """Test that is_protected_path protects the install directory when frozen."""
    fake_install = tmp_path / "InstalledApp"
    fake_install.mkdir()
    fake_exe = fake_install / "MayuriShell.exe"
    fake_exe.touch()

    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "executable", str(fake_exe)):
            app_root = get_app_root()
            is_prot, reason = is_protected_path(
                target=fake_install,
                current_dir=tmp_path,
                appdata_dir=tmp_path / "appdata",
                project_root=app_root,
            )
            assert is_prot is True
            assert "install folder" in reason.lower()


def test_protected_install_folder_in_organize(tmp_path: Path):
    """Test that validate_organize_target refuses the install folder when frozen."""
    fake_install = tmp_path / "InstalledApp"
    fake_install.mkdir()
    fake_exe = fake_install / "MayuriShell.exe"
    fake_exe.touch()

    class FakeConfig:
        base_dir = tmp_path / "appdata"

    class FakeContext:
        config = FakeConfig()

    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "executable", str(fake_exe)):
            refused, reason = is_protected_organize_folder(fake_install, FakeContext())
            assert refused is True
            assert "install folder" in reason.lower()
