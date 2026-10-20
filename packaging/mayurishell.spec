# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for MayuriShell."""
from pathlib import Path
import sys

# Ensure repository root is in sys.path
spec_dir = Path(SPECPATH).resolve()
repo_root = spec_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from core.version import VERSION

version_info_path = spec_dir / "version_info.txt"

a = Analysis(
    [str(repo_root / "main.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "prompt_toolkit",
        "prompt_toolkit.formatted_text",
        "prompt_toolkit.key_binding",
        "prompt_toolkit.history",
        "prompt_toolkit.completion",
        "rich",
        "rich.console",
        "rich.table",
        "rich.panel",
        "rich.box",
        "rich.text",
        "rich.markup",
        "psutil",
        "send2trash",
        "send2trash.win",
        "send2trash.win.legacy",
        "send2trash.win.modern",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "test",
        "tests",
        "pydoc_data",
        "xmlrpc",
        "curses",
        "lib2to3",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MayuriShell",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(version_info_path) if version_info_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MayuriShell",
)
