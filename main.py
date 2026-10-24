"""Main entry point for MayuriShell."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from commands.appearance import register_appearance_commands
from commands.applications import register_application_commands
from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from commands.files import register_file_commands
from commands.navigation import register_navigation_commands
from commands.organization import register_organization_commands
from commands.doctor import register_doctor_commands
from commands.processes import register_process_commands
from commands.project import register_project_aware_commands
from commands.project_scaffolding import register_project_commands
from commands.git import register_git_commands
from commands.search import register_search_commands
from commands.system import register_system_commands
from commands.websites import register_website_commands
from commands.workflows import register_workflow_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.logging_config import get_logger, setup_logging
from core.paths import validate_config_dir
from core.registry import CommandRegistry
from core.selftest import run_selftest
from core.shell import MayuriShell
from core.version import VERSION

logger = get_logger()


def setup_windows_console() -> None:
    """Configure stdout and stderr to UTF-8 on Windows where supported."""
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def register_all_commands(registry: CommandRegistry, config_mgr: ConfigManager) -> None:
    """Register all available commands with the registry."""
    register_builtin_commands(registry)
    register_appearance_commands(registry)
    register_application_commands(registry, config_mgr)
    register_website_commands(registry, config_mgr)
    register_navigation_commands(registry, config_mgr)
    register_customization_commands(registry, config_mgr)
    register_file_commands(registry)
    register_search_commands(registry)
    register_system_commands(registry)
    register_process_commands(registry)
    register_organization_commands(registry, config_mgr)
    register_project_commands(registry, config_mgr)
    register_project_aware_commands(registry)
    register_git_commands(registry)
    register_workflow_commands(registry, config_mgr)
    register_doctor_commands(registry)


def wait_for_enter_if_terminal() -> None:
    """Wait for user to press Enter if running in an interactive terminal window."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to exit...")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    """Initialize and run MayuriShell."""
    setup_windows_console()

    args_list = sys.argv[1:] if argv is None else argv

    # Parse optional --config-dir
    config_dir_override: Path | None = None
    if "--config-dir" in args_list:
        idx = args_list.index("--config-dir")
        if idx + 1 >= len(args_list):
            print("Error: --config-dir requires a directory path argument.", file=sys.stderr)
            return 1
        raw_path = args_list[idx + 1]
        valid, reason = validate_config_dir(raw_path)
        if not valid:
            print(f"Error: Invalid configuration directory: {reason}", file=sys.stderr)
            return 1
        config_dir_override = Path(raw_path).resolve()
        try:
            config_dir_override.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(f"Error: Failed to create configuration directory: {exc}", file=sys.stderr)
            return 1

    # Handle quick non-interactive CLI flags
    if "--version" in args_list:
        print(f"MayuriShell {VERSION}")
        return 0

    if "--selftest" in args_list:
        return run_selftest()

    log_file_hint = None
    try:
        # Initialize configuration manager
        config_mgr = ConfigManager(base_dir=config_dir_override)
        log_file_hint = config_mgr.logs_dir / "mayurishell.log"

        # Setup rotating file logging
        setup_logging(config_mgr.logs_dir)

        # Initialize history and alias managers
        history_mgr = HistoryManager(config_mgr.history_path)
        alias_mgr = AliasManager(config_mgr)

        # Initialize command registry and register commands
        registry = CommandRegistry()
        register_all_commands(registry, config_mgr)

        # Start shell
        shell = MayuriShell(
            config=config_mgr,
            registry=registry,
            history_manager=history_mgr,
            alias_manager=alias_mgr,
        )
        shell.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        try:
            logger.error("Fatal error during shell execution", exc_info=True)
        except Exception:
            pass
        print(f"\nFatal error encountered: {exc}", file=sys.stderr)
        if log_file_hint:
            print(f"A detailed error log has been written to: {log_file_hint}", file=sys.stderr)
        wait_for_enter_if_terminal()
        return 1


if __name__ == "__main__":
    sys.exit(main())
