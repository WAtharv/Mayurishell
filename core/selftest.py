"""Self-test runner for MayuriShell.

Performs a comprehensive, non-interactive diagnostic check verifying that all
modules load, dependencies are present, the command registry initializes properly,
and safe non-destructive commands run cleanly under an isolated temporary environment.
"""
from __future__ import annotations

import importlib
import io
from pathlib import Path
import pkgutil
import sys
import tempfile
from typing import Any

from rich.console import Console

from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.executor import CommandExecutor
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.theme import ThemeManager


def run_selftest() -> int:
    """Run non-interactive self-test and return 0 on success, 1 on failure."""
    passed_all = True

    def report_check(name: str, success: bool, detail: str = "") -> None:
        nonlocal passed_all
        if success:
            extra = f" ({detail})" if detail else ""
            print(f"  [PASS] {name}{extra}")
        else:
            passed_all = False
            extra = f": {detail}" if detail else ""
            print(f"  [FAIL] {name}{extra}", file=sys.stderr)

    print("Running MayuriShell self-tests...")

    # 1. Check third-party dependencies
    deps = ["rich", "psutil", "prompt_toolkit", "send2trash"]
    for dep in deps:
        try:
            mod = importlib.import_module(dep)
            ver = getattr(mod, "__version__", "unknown")
            report_check(f"Dependency '{dep}'", True, f"version {ver}")
        except Exception as exc:
            report_check(f"Dependency '{dep}'", False, str(exc))

    # 2. Walk and import all modules under core, commands, and services
    packages = ["core", "commands", "services"]
    known_modules = [
        "core.aliases", "core.completer", "core.config_manager", "core.exceptions",
        "core.executor", "core.history", "core.logging_config", "core.mascots",
        "core.parser", "core.paths", "core.registry", "core.shell", "core.theme",
        "core.version",
        "commands.appearance", "commands.applications", "commands.builtins",
        "commands.customization", "commands.files", "commands.navigation",
        "commands.organization", "commands.processes", "commands.project_scaffolding",
        "commands.search", "commands.system", "commands.websites", "commands.workflows",
        "services.application_discovery", "services.file_service",
        "services.launcher_service", "services.system_service", "services.workflow_service",
    ]

    imported_count = 0
    import_errors: list[str] = []

    for pkg_name in packages:
        try:
            pkg = importlib.import_module(pkg_name)
            if hasattr(pkg, "__path__"):
                for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
                    try:
                        importlib.import_module(mod_name)
                        imported_count += 1
                    except Exception as err:
                        import_errors.append(f"{mod_name}: {err}")
        except Exception as err:
            import_errors.append(f"{pkg_name}: {err}")

    # Explicit fallback imports in case walk_packages is constrained in a frozen archive
    for mod_name in known_modules:
        try:
            importlib.import_module(mod_name)
        except Exception as err:
            if mod_name not in [e.split(":")[0] for e in import_errors]:
                import_errors.append(f"{mod_name}: {err}")

    if not import_errors:
        report_check("Module imports (core, commands, services)", True, f"{len(known_modules)} verified")
    else:
        report_check("Module imports", False, "; ".join(import_errors))

    # 3. Create isolated environment in temporary directory
    try:
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            config_mgr = ConfigManager(base_dir=temp_dir)
            report_check("Isolated configuration setup", True, f"in temp dir")

            # 4. Build command registry
            registry = CommandRegistry()
            from commands.appearance import register_appearance_commands
            from commands.applications import register_application_commands
            from commands.builtins import register_builtin_commands
            from commands.customization import register_customization_commands
            from commands.files import register_file_commands
            from commands.navigation import register_navigation_commands
            from commands.organization import register_organization_commands
            from commands.processes import register_process_commands
            from commands.project_scaffolding import register_project_commands
            from commands.search import register_search_commands
            from commands.system import register_system_commands
            from commands.websites import register_website_commands
            from commands.workflows import register_workflow_commands

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
            register_workflow_commands(registry, config_mgr)

            cmd_names = registry.list_commands()
            report_check("Command registry population", len(cmd_names) > 0, f"{len(cmd_names)} commands registered")

            # 5. Initialize Theme and ShellContext with captured console output
            capture_stream = io.StringIO()
            captured_console = Console(file=capture_stream, force_terminal=False, color_system=None)
            theme_mgr = ThemeManager(config_mgr, console=captured_console)
            report_check("Theme initialization", theme_mgr.current is not None, f"active: {theme_mgr.current.name}")

            history_mgr = HistoryManager(config_mgr.history_path)
            alias_mgr = AliasManager(config_mgr)

            from core.shell import ShellContext
            context = ShellContext(
                config=config_mgr,
                registry=registry,
                history_manager=history_mgr,
                alias_manager=alias_mgr,
                console=captured_console,
                theme_manager=theme_mgr,
            )
            executor = CommandExecutor(registry, console=captured_console)

            # 6. Execute required safe, non-interactive commands
            from core.parser import parse_command_line
            test_commands = [
                "help",
                "version",
                "sysinfo",
                "fetch",
                "theme preview",
                "apps",
                "websites",
                "aliases",
                "diagnostics",
            ]

            for cmd in test_commands:
                try:
                    parsed = parse_command_line(cmd)
                    assert parsed is not None
                    result = executor.execute(parsed, context)
                    report_check(f"Command execution: '{cmd}'", bool(result))
                except Exception as exc:
                    report_check(f"Command execution: '{cmd}'", False, str(exc))

    except Exception as exc:
        report_check("Isolated execution environment", False, str(exc))

    if passed_all:
        print("\nAll MayuriShell self-tests PASSED successfully.")
        return 0
    else:
        print("\nOne or more MayuriShell self-tests FAILED.", file=sys.stderr)
        return 1
