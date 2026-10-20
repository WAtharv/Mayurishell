"""Main entry point for MayuriShell."""
from __future__ import annotations

import sys

from commands.applications import register_application_commands
from commands.builtins import register_builtin_commands
from commands.customization import register_customization_commands
from commands.files import register_file_commands
from commands.navigation import register_navigation_commands
from commands.processes import register_process_commands
from commands.search import register_search_commands
from commands.system import register_system_commands
from commands.websites import register_website_commands
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.logging_config import setup_logging
from core.registry import CommandRegistry
from core.shell import MayuriShell


def main() -> int:
    """Initialize and run MayuriShell."""
    try:
        # Initialize configuration manager
        config_mgr = ConfigManager()

        # Setup rotating file logging in %APPDATA%\MayuriShell\logs
        setup_logging(config_mgr.logs_dir)

        # Initialize history and alias managers
        history_mgr = HistoryManager(config_mgr.history_path)
        alias_mgr = AliasManager(config_mgr)

        # Initialize command registry and register commands
        registry = CommandRegistry()
        register_builtin_commands(registry)
        register_application_commands(registry, config_mgr)
        register_website_commands(registry, config_mgr)
        register_navigation_commands(registry, config_mgr)
        register_customization_commands(registry, config_mgr)
        register_file_commands(registry)
        register_search_commands(registry)
        register_system_commands(registry)
        register_process_commands(registry)

        # Start shell
        shell = MayuriShell(
            config=config_mgr,
            registry=registry,
            history_manager=history_mgr,
            alias_manager=alias_mgr,
        )
        shell.run()
        return 0
    except Exception as exc:
        print(f"Fatal error starting MayuriShell: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
