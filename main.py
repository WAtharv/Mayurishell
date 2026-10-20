"""Main entry point for MayuriShell."""
from __future__ import annotations

import sys

from commands.builtins import register_builtin_commands
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

        # Initialize history manager
        history_mgr = HistoryManager(config_mgr.history_path)

        # Initialize command registry and register builtins
        registry = CommandRegistry()
        register_builtin_commands(registry)

        # Start shell
        shell = MayuriShell(
            config=config_mgr,
            registry=registry,
            history_manager=history_mgr,
        )
        shell.run()
        return 0
    except Exception as exc:
        print(f"Fatal error starting MayuriShell: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
