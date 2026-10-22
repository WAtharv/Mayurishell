"""Unit and integration tests for config export, import, backup, and restore."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.executor import CommandExecutor, CommandResult
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell, ShellContext
from core.theme import ThemeManager
from services.config_service import (
    KIND,
    MAX_IMPORT_FILE_SIZE,
    SCHEMA_VERSION,
    apply_imported_config,
    backup_config,
    build_import_preview,
    export_config,
    list_backups,
    load_and_validate_import_file,
    restore_config,
)


def create_isolated_shell(tmp_path: Path):
    """Create an isolated test shell strictly inside tmp_path."""
    cfg_dir = tmp_path / "cfg"
    cfg = ConfigManager(base_dir=cfg_dir)
    reg = CommandRegistry()
    register_builtin_commands(reg)
    register_customization_commands(reg, cfg)

    hist = HistoryManager(cfg.history_path)
    aliases = AliasManager(cfg)
    console = Console(record=True, force_terminal=False, color_system=None)
    theme_mgr = ThemeManager(cfg, console=console)

    shell = MayuriShell(
        config=cfg,
        registry=reg,
        history_manager=hist,
        alias_manager=aliases,
        console=console,
        theme_manager=theme_mgr,
    )
    shell.context.is_interactive = False
    return shell, console


# ============================================================================
# 1. EXPORT TESTS
# ============================================================================

def test_export_whitelist_and_exclusions(tmp_path: Path) -> None:
    """Verify export only includes whitelisted keys and excludes secrets, history, and user info."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    # Add custom settings and shortcuts
    cfg.set_shortcut("aliases", "v", "version")
    cfg.set_shortcut("folder_shortcuts", "mybox", str(tmp_path / "box"))
    cfg.set_shortcut("applications", "customcalc", "calc.exe")
    cfg.set_shortcut("websites", "mysite", "https://example.com/search?q={query}")

    export_file = tmp_path / "exported_config.json"
    ok, msg, dest, summary = export_config(cfg, target_path=export_file)

    assert ok is True
    assert dest == export_file
    assert export_file.is_file()

    with open(export_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Check header
    assert payload["kind"] == KIND
    assert payload["schema_version"] == SCHEMA_VERSION
    assert "app_version" in payload
    assert "exported_at" in payload

    # Whitelisted sections
    assert "aliases" in payload
    assert payload["aliases"]["v"] == "version"
    assert "folder_shortcuts" in payload
    assert "applications" in payload
    assert "websites" in payload
    assert "theme" in payload
    assert "mascot" in payload
    assert "preferences" in payload

    # Excluded sections must NOT be in payload
    assert "history" not in payload
    assert "logs" not in payload
    assert "undo_journal" not in payload
    assert "backups" not in payload

    # Raw user info must not be top-level keys
    assert "username" not in payload
    assert "hostname" not in payload


def test_export_no_overwrite(tmp_path: Path) -> None:
    """Export refuses to overwrite an existing file."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    dest = tmp_path / "existing.json"
    dest.write_text("{}", encoding="utf-8")

    ok, msg, out_p, _ = export_config(cfg, target_path=dest)
    assert ok is False
    assert "already exists" in msg
    assert out_p is None


def test_export_path_normalization(tmp_path: Path) -> None:
    """Paths located under the home folder are normalized to ~/."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    home_p = Path.home() / "Documents" / "MyProject"
    cfg.set_shortcut("folder_shortcuts", "myproj", str(home_p))

    export_file = tmp_path / "norm_test.json"
    ok, _, _, _ = export_config(cfg, target_path=export_file)
    assert ok is True

    with open(export_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    stored_path = payload["folder_shortcuts"]["myproj"]
    assert stored_path.startswith("~/") or stored_path.startswith("~\\")


def test_export_desktop_fallback_to_home(tmp_path: Path) -> None:
    """When desktop path is unwritable, export safely falls back to home directory."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    fake_desktop = tmp_path / "unwritable_desktop"
    # Desktop does not exist and cannot be accessed
    with patch("services.config_service.get_real_desktop_path", return_value=fake_desktop):
        with patch("os.access", return_value=False):
            ok, msg, dest, summary = export_config(cfg, target_path=None)
            assert ok is True
            assert summary["fallback_used"] is True
            assert "home directory" in msg
            assert dest.parent == Path.home()
            if dest.exists():
                dest.unlink()


# ============================================================================
# 2. IMPORT VALIDATION TESTS
# ============================================================================

def test_import_refuses_symlink_or_junction(tmp_path: Path) -> None:
    """Import refuses symlinks and junctions for security."""
    real_file = tmp_path / "real.json"
    real_file.write_text(json.dumps({"kind": KIND, "schema_version": 1}), encoding="utf-8")

    symlink_file = tmp_path / "symlink.json"
    try:
        symlink_file.symlink_to(real_file)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment")

    ok, err, _, _ = load_and_validate_import_file(symlink_file)
    assert ok is False
    assert "symbolic link" in err.lower() or "junction" in err.lower()


def test_import_file_size_limit(tmp_path: Path) -> None:
    """Import strictly rejects files exceeding 1 MB."""
    large_file = tmp_path / "oversized.json"
    large_file.write_bytes(b"x" * (MAX_IMPORT_FILE_SIZE + 10))

    ok, err, _, _ = load_and_validate_import_file(large_file)
    assert ok is False
    assert "exceeds maximum allowed import limit" in err


def test_import_schema_version_check(tmp_path: Path) -> None:
    """Import refuses files with a newer schema version than supported."""
    future_file = tmp_path / "future_schema.json"
    future_file.write_text(
        json.dumps({"kind": KIND, "schema_version": SCHEMA_VERSION + 1}),
        encoding="utf-8",
    )

    ok, err, _, _ = load_and_validate_import_file(future_file)
    assert ok is False
    assert "newer than supported version" in err


def test_import_unknown_top_level_keys_warning(tmp_path: Path) -> None:
    """Unknown top-level keys produce warnings but allow valid items to parse."""
    file_with_extras = tmp_path / "extras.json"
    file_with_extras.write_text(
        json.dumps({
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "alien_key": 12345,
            "theme": "plain",
        }),
        encoding="utf-8",
    )

    ok, err, data, warnings = load_and_validate_import_file(file_with_extras)
    assert ok is True
    assert any("alien_key" in w for w in warnings)
    assert data["theme"] == "plain"


def test_import_validation_refuses_invalid_urls_and_forbidden_workflows(tmp_path: Path) -> None:
    """Import validates website URLs (only http/https with <=1 {query}) and workflow allowlists."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    import_data = {
        "websites": {
            "badsite1": "ftp://files.example.com",
            "badsite2": "https://example.com/{query}/extra/{query}",
            "goodsite": "https://google.com/search?q={query}",
        },
        "workflows": {
            "badwf": {
                "steps": ["delete notes.txt"],
            },
            "goodwf": {
                "steps": ["sysinfo", "fetch"],
            },
        },
    }

    preview = build_import_preview(cfg, import_data, shell.context)

    # Websites: bad sites must be in skipped
    skipped_names = [item[1] for item in preview["skipped"]]
    assert "badsite1" in skipped_names
    assert "badsite2" in skipped_names
    assert "goodsite" not in skipped_names

    # Workflows: badwf with forbidden 'delete' must be skipped
    assert "badwf" in skipped_names
    assert "goodwf" not in skipped_names


def test_import_builtin_command_collision_refused(tmp_path: Path) -> None:
    """Import refuses shortcut names that collide with registered built-in commands."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    import_data = {
        "folder_shortcuts": {
            "help": str(tmp_path),  # Collides with built-in 'help'
            "validfolder": str(tmp_path),
        },
        "applications": {
            "version": "version.exe",  # Collides with built-in 'version'
        },
    }

    preview = build_import_preview(cfg, import_data, shell.context)
    skipped_names = [item[1] for item in preview["skipped"]]
    assert "help" in skipped_names
    assert "version" in skipped_names
    assert "validfolder" not in skipped_names


def test_import_missing_paths_on_this_pc_skipped(tmp_path: Path) -> None:
    """Missing folder paths and missing app targets are marked missing and skipped."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    missing_dir = tmp_path / "nonexistent_dir_123"
    missing_exe = tmp_path / "nonexistent_app_456.exe"

    import_data = {
        "folder_shortcuts": {
            "missingbox": str(missing_dir),
        },
        "applications": {
            "missingapp": str(missing_exe),
        },
    }

    preview = build_import_preview(cfg, import_data, shell.context)
    skipped_names = [item[1] for item in preview["skipped"]]
    assert "missingbox" in skipped_names
    assert "missingapp" in skipped_names
    assert any("missingbox" in p for p in preview["missing_paths"])


# ============================================================================
# 3. ATOMIC APPLY, DRY-RUN, AND PRE-IMPORT BACKUP
# ============================================================================

def test_import_dry_run_leaves_config_untouched(tmp_path: Path) -> None:
    """Dry run generates preview but applies zero changes."""
    shell, console = create_isolated_shell(tmp_path)
    import_file = tmp_path / "import_data.json"
    import_file.write_text(
        json.dumps({
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "theme": "gruvbox",
            "aliases": {"testalias": "version"},
        }),
        encoding="utf-8",
    )

    shell.run_command_line(f"config import {import_file} --dry-run")
    out = console.export_text()
    assert "[Dry Run]" in out
    assert shell.context.config.get("theme") != "gruvbox"
    assert "testalias" not in shell.context.config.get_aliases()


def test_import_creates_backup_and_applies_atomically(tmp_path: Path) -> None:
    """Applying an import automatically creates a backup and updates config atomically."""
    shell, console = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    import_file = tmp_path / "import_apply.json"
    import_file.write_text(
        json.dumps({
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "theme": "gruvbox",
            "aliases": {"newalias": "help"},
        }),
        encoding="utf-8",
    )

    # Run import with mock confirm returning True
    with patch("commands.customization.confirm_prompt", return_value=True):
        shell.run_command_line(f"config import {import_file} --overwrite")

    # Verify backup was created in backups/
    backups = list_backups(cfg)
    assert len(backups) >= 1

    # Verify new values were applied
    assert cfg.get("theme") == "gruvbox"
    assert cfg.get_aliases().get("newalias") == "help"


def test_import_atomic_failure_leaves_config_untouched(tmp_path: Path) -> None:
    """If os.replace fails during apply, the original config is untouched and backup exists."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config
    original_theme = cfg.get("theme")

    imported_data = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "theme": "gruvbox",
    }
    preview = build_import_preview(cfg, imported_data, shell.context)

    # Simulate OSError specifically during atomic replace of config.json (not during backup)
    real_replace = os.replace

    def fake_replace(src, dst):
        if str(dst).endswith("config.json"):
            raise OSError("Disk write fault during config replace")
        return real_replace(src, dst)

    with patch("os.replace", side_effect=fake_replace):
        success, msg = apply_imported_config(cfg, imported_data, preview, overwrite=True)
        assert success is False
        assert "Original config is untouched" in msg

    # Original config must remain intact
    cfg.load()
    assert cfg.get("theme") == original_theme

    # Pre-import backup must exist
    backups = list_backups(cfg)
    assert len(backups) >= 1


def test_import_separate_app_confirmation(tmp_path: Path) -> None:
    """User can approve general import but reject application shortcuts."""
    shell, console = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    import_file = tmp_path / "import_apps.json"
    import_file.write_text(
        json.dumps({
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "theme": "rose-pine",
            "applications": {"testcalc": "calc.exe"},
        }),
        encoding="utf-8",
    )

    # First confirm_prompt (general import) returns True; second (apps) returns False
    with patch("commands.customization.confirm_prompt", side_effect=[True, False]):
        shell.run_command_line(f"config import {import_file} --overwrite")

    assert cfg.get("theme") == "rose-pine"
    assert "testcalc" not in cfg.get_applications()


# ============================================================================
# 4. BACKUP & RESTORE TESTS
# ============================================================================

def test_backup_and_listing(tmp_path: Path) -> None:
    """config backup creates timestamped copy, and config restore lists it."""
    shell, console = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    shell.run_command_line("config backup")
    out = console.export_text()
    assert "Backup created successfully" in out

    console.clear()
    shell.run_command_line("config restore")
    out_list = console.export_text()
    assert "config-backup-" in out_list
    assert ".json" in out_list


def test_restore_plain_name_enforced(tmp_path: Path) -> None:
    """Restore strictly rejects names containing path separators or traversal."""
    shell, console = create_isolated_shell(tmp_path)
    shell.run_command_line("config restore ../evil.json")
    out = console.export_text()
    assert "plain file name inside backups/" in out

    console.clear()
    shell.run_command_line(r"config restore sub\backup.json")
    out = console.export_text()
    assert "plain file name inside backups/" in out


def test_restore_validates_backup_before_touching_config(tmp_path: Path) -> None:
    """Corrupted backup file is rejected without modifying current configuration."""
    shell, console = create_isolated_shell(tmp_path)
    cfg = shell.context.config
    original_mascot = cfg.get("mascot")

    corrupt_backup = cfg.backups_dir / "corrupt_backup.json"
    corrupt_backup.write_text("{ this is not valid json }", encoding="utf-8")

    shell.run_command_line(f"config restore {corrupt_backup.name}")
    out = console.export_text()
    assert "Restore Refused:" in out

    cfg.load()
    assert cfg.get("mascot") == original_mascot


def test_restore_success_flow(tmp_path: Path) -> None:
    """Valid restore backs up current configuration first and applies backup cleanly."""
    shell, console = create_isolated_shell(tmp_path)
    cfg = shell.context.config

    cfg.set("theme", "tokyo-night")
    shell.run_command_line("config backup")
    backups = list_backups(cfg)
    target_backup_name = backups[0]["name"]

    # Change current theme
    cfg.set("theme", "plain")
    assert cfg.get("theme") == "plain"

    # Restore the backup with confirm returning True
    with patch("commands.customization.confirm_prompt", return_value=True):
        shell.run_command_line(f"config restore {target_backup_name}")

    cfg.load()
    assert cfg.get("theme") == "tokyo-night"


def test_restore_corrupt_structure_rejected(tmp_path: Path) -> None:
    """Backup with invalid structure (forbidden workflow step) is rejected without touching config."""
    shell, console = create_isolated_shell(tmp_path)
    cfg = shell.context.config
    cfg.set("mascot", "bunny")

    backups_before = len(list_backups(cfg))

    # Create backup with forbidden command in workflow
    bad_backup = cfg.backups_dir / "bad_structure.json"
    bad_backup.write_text(
        json.dumps({
            "workflows": {
                "evil": {"steps": ["delete confidential.txt"]},
            }
        }),
        encoding="utf-8",
    )

    shell.run_command_line(f"config restore {bad_backup.name}")
    out = console.export_text()
    assert "Restore Refused:" in out
    assert "forbidden command" in out

    # Config is untouched and NO pre-restore backup was created
    cfg.load()
    assert cfg.get("mascot") == "bunny"
    assert len(list_backups(cfg)) == backups_before + 1  # only bad_structure.json itself


def test_restore_atomic_failure_leaves_config_untouched(tmp_path: Path) -> None:
    """If os.replace fails during restore, the original config is untouched and backup still exists."""
    shell, _ = create_isolated_shell(tmp_path)
    cfg = shell.context.config
    cfg.set("theme", "kawaii")

    # Create a valid backup
    ok_b, _, b_file = backup_config(cfg)
    assert ok_b is True
    assert b_file is not None

    # Modify current config
    cfg.set("theme", "plain")

    # Simulate OSError specifically during atomic replace of config.json (not during pre-restore backup)
    real_replace = os.replace

    def fake_replace(src, dst):
        if str(dst).endswith("config.json"):
            raise OSError("Disk failure during config replace")
        return real_replace(src, dst)

    with patch("os.replace", side_effect=fake_replace):
        success, msg, _ = restore_config(cfg, b_file.name)
        assert success is False
        assert "Original config is untouched" in msg

    # Original config remains untouched
    cfg.load()
    assert cfg.get("theme") == "plain"

    # Pre-restore backup and original backup must still exist
    backups = list_backups(cfg)
    assert len(backups) >= 2


# ============================================================================
# 5. ROUND-TRIP TEST
# ============================================================================

def test_export_import_round_trip(tmp_path: Path) -> None:
    """Exporting from config A and importing into fresh config B restores identical shortcuts."""
    shell_a, _ = create_isolated_shell(tmp_path / "shell_a")
    cfg_a = shell_a.context.config

    cfg_a.set("theme", "catppuccin")
    cfg_a.set_shortcut("aliases", "cls-a", "clear")
    cfg_a.set_shortcut("websites", "github-a", "https://github.com/search?q={query}")

    export_path = tmp_path / "round_trip.json"
    ok, _, _, _ = export_config(cfg_a, target_path=export_path)
    assert ok is True

    # Fresh Shell B
    shell_b, _ = create_isolated_shell(tmp_path / "shell_b")
    cfg_b = shell_b.context.config

    with patch("commands.customization.confirm_prompt", return_value=True):
        shell_b.run_command_line(f"config import {export_path} --overwrite")

    assert cfg_b.get("theme") == "catppuccin"
    assert cfg_b.get_aliases().get("cls-a") == "clear"
    assert cfg_b.get_websites().get("github-a") == "https://github.com/search?q={query}"
