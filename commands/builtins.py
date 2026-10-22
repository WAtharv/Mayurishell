import datetime
import getpass
import os
from pathlib import Path
import platform
import sys
from typing import TYPE_CHECKING, Any

from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.file_service import format_bytes

if TYPE_CHECKING:
    from core.shell import ShellContext

from core.version import VERSION


def get_real_desktop_path() -> Path:
    """Resolve the true Windows Desktop directory, checking OneDrive and Registry locations."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            val, _ = winreg.QueryValueEx(key, "Desktop")
            winreg.CloseKey(key)
            expanded = os.path.expandvars(str(val))
            p = Path(expanded).resolve()
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass

        one_drive = os.getenv("OneDrive")
        if one_drive:
            od_desktop = Path(one_drive) / "Desktop"
            if od_desktop.exists() and od_desktop.is_dir():
                return od_desktop

    std_desktop = Path.home() / "Desktop"
    if std_desktop.exists() and std_desktop.is_dir():
        return std_desktop
    return Path.home()


def handle_help(context: Any, args: list[str]) -> CommandResult:
    """Show available commands or detailed info for a specific command."""
    registry: CommandRegistry = context.registry
    console = context.console
    theme = context.theme

    if args:
        target = args[0].lower()
        cmd = registry.get(target)
        if not cmd:
            suggestions = registry.suggest(target)
            console.print(f"{theme.format_error('Command not found:')} '{escape(target)}'")
            if suggestions:
                sugg_str = ", ".join(theme.format_primary(s, bold=True) for s in suggestions)
                console.print(f"  Did you mean: {sugg_str}?")
            return CommandResult.fail("Command not found")

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=theme.bold_accent_style, justify="right")
        grid.add_column(overflow="fold")
        grid.add_row("Command:", theme.format_primary(cmd.name, bold=True))
        grid.add_row("Category:", theme.format_success(cmd.category))
        grid.add_row("Usage:", theme.format_warning(cmd.usage))
        grid.add_row("Description:", escape(cmd.description))

        console.print(
            theme.create_panel(
                grid,
                title=f"MayuriShell - Command Info: {escape(cmd.name)}",
            )
        )
        return CommandResult.success()

    # List all commands grouped by category
    table = theme.create_table(
        title="Available Commands",
        show_lines=False,
    )
    table.add_column("Category", style=theme.success_style, no_wrap=True)
    table.add_column("Command", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Usage", style=theme.warning_style, overflow="fold")
    table.add_column("Description", style=theme.text_style, overflow="fold")

    for cat in registry.get_categories():
        for cmd in registry.list_commands(category=cat):
            table.add_row(cat, cmd.name, cmd.usage, cmd.description)

    console.print(table)
    console.print(
        f"{theme.format_muted('Type ')}{theme.format_primary('help <command>', bold=True)}{theme.format_muted(' for details on a specific command.')}\n"
    )
    return CommandResult.success()


def handle_clear(context: Any, args: list[str]) -> CommandResult:
    """Clear terminal screen."""
    context.console.clear()
    return CommandResult.success()


def handle_exit(context: Any, args: list[str]) -> CommandResult:
    """Exit MayuriShell gracefully."""
    theme = context.theme
    username = escape(context.config.get("username", "Mayuri"))
    if theme.is_plain:
        context.console.print(f"\nGoodbye, {username}! (^_^)/ See you next time!")
    else:
        context.console.print(f"\n{theme.format_primary(f'Goodbye, {username}! (,,•́ω•̀,,)ﾉ See you next time!', bold=True)}")
    context.running = False
    return CommandResult.success()


def handle_history(context: Any, args: list[str]) -> CommandResult:
    """Show command history or clear history."""
    console = context.console
    theme = context.theme
    history_mgr = context.history_manager

    if args:
        subcmd = args[0].lower()
        if subcmd == "clear":
            history_mgr.clear()
            console.print(theme.format_success("Command history cleared successfully."))
            return CommandResult.success()
        else:
            console.print(
                f"{theme.format_error('Unknown history subcommand:')} '{escape(subcmd)}'. "
                f"Usage: {theme.format_warning('history [clear]')}"
            )
            return CommandResult.fail("Unknown history subcommand")

    entries = history_mgr.get_all()
    if not entries:
        console.print(theme.format_muted("No command history recorded yet."))
        return CommandResult.success()

    # Display last 50 entries
    display_entries = entries[-50:]
    table = theme.create_table(
        title="Command History (Recent)",
    )
    table.add_column("#", style=theme.muted_style, justify="right", no_wrap=True)
    table.add_column("Timestamp", style=theme.muted_style, no_wrap=True)
    table.add_column("Command", style=theme.bold_text_style)

    start_idx = len(entries) - len(display_entries) + 1
    for i, entry in enumerate(display_entries, start=start_idx):
        table.add_row(str(i), escape(entry.get("timestamp", "-")), escape(entry.get("command", "")))

    console.print(table)
    console.print(
        f"{theme.format_muted('Tip: Use ')}{theme.format_primary('history clear', bold=True)}{theme.format_muted(' to wipe history.')}\n"
    )
    return CommandResult.success()


def handle_version(context: Any, args: list[str]) -> CommandResult:
    """Display MayuriShell version and environment details."""
    console = context.console
    theme = context.theme
    content = (
        f"{theme.format_primary('MayuriShell', bold=True)} version {theme.format_primary(VERSION, bold=True)}\n"
        f"Python: {theme.format_warning(sys.version.split()[0])}\n"
        f"Platform: {theme.format_success(f'{platform.system()} {platform.release()} ({platform.machine()})')}\n"
        f"Architecture: {theme.format_muted(platform.architecture()[0])}"
    )
    console.print(theme.create_panel(content, title="Version Info"))
    return CommandResult.success()


def handle_diagnostics(context: Any, args: list[str]) -> None:
    """Display system diagnostics or export a sanitized diagnostic report."""
    console = context.console
    theme = context.theme

    export_mode = any(arg.lower() in ("--export", "-e") for arg in args)

    # 1. Versions & OS
    py_ver = sys.version.split()[0]
    py_arch = platform.architecture()[0]
    os_name = platform.system()
    os_rel = platform.release()
    os_ver = platform.version()
    machine = platform.machine()
    hostname = platform.node()
    username = getpass.getuser()

    # 2. Terminal capabilities
    color_sys = str(console.color_system) if console.color_system else "None"
    stdout_enc = sys.stdout.encoding or "ascii"
    unicode_support = "Yes" if "utf" in stdout_enc.lower() or "65001" in stdout_enc.lower() else "Limited"
    term_width = console.size.width
    term_height = console.size.height

    # 3. Config & History
    cfg_path = context.config.config_path
    cfg_valid = "Valid"
    try:
        if not cfg_path.exists():
            cfg_valid = "Missing (using defaults)"
        else:
            with open(cfg_path, "r", encoding="utf-8") as f:
                import json
                json.load(f)
    except Exception as exc:
        cfg_valid = f"Corrupted ({exc})"

    history_path = context.config.history_path
    history_entries = len(context.history_manager.get_all()) if hasattr(context, "history_manager") else 0

    # 4. Commands & shortcuts
    cmd_count = len(context.registry.list_commands()) if hasattr(context, "registry") else 0
    apps_count = len(context.config.get_applications()) if hasattr(context.config, "get_applications") else 0
    web_count = len(context.config.get_websites()) if hasattr(context.config, "get_websites") else 0
    folder_count = len(context.config.get_folder_shortcuts()) if hasattr(context.config, "get_folder_shortcuts") else 0
    alias_count = len(context.config.get_aliases()) if hasattr(context.config, "get_aliases") else 0
    wf_count = len(context.config.get_workflows()) if hasattr(context.config, "get_workflows") else 0

    # 5. Logs & Error counts
    log_file = context.config.logs_dir / "mayurishell.log"
    log_size_str = "None"
    log_lines = 0
    log_errors = 0
    log_warnings = 0

    if log_file.exists():
        try:
            log_size_str = format_bytes(log_file.stat().st_size)
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    log_lines += 1
                    if " - ERROR - " in line or " - CRITICAL - " in line or line.startswith("ERROR") or line.startswith("CRITICAL"):
                        log_errors += 1
                    elif " - WARNING - " in line or line.startswith("WARNING"):
                        log_warnings += 1
        except Exception as exc:
            log_size_str = f"Error reading log: {exc}"

    # 6. Dependency imports
    dep_statuses: dict[str, str] = {}
    for mod_name in ["psutil", "rich", "prompt_toolkit", "send2trash"]:
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", "Installed")
            dep_statuses[mod_name] = f"Available ({ver})"
        except ImportError:
            dep_statuses[mod_name] = "Not installed"

    if export_mode:
        # Generate sanitized text report
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop_dir = get_real_desktop_path()

        # Collision-free filename
        base_name = f"mayurishell_diagnostics_{timestamp_str}"
        report_file = desktop_dir / f"{base_name}.txt"
        counter = 1
        while report_file.exists():
            report_file = desktop_dir / f"{base_name}_{counter}.txt"
            counter += 1

        home_str = str(Path.home())
        home_res = str(Path.home().resolve())

        def sanitize(text: str) -> str:
            res = text.replace(home_res, "~").replace(home_str, "~")
            if username:
                res = res.replace(username, "<user>")
            if hostname:
                res = res.replace(hostname, "<host>")
            return res

        sanitized_cfg = sanitize(str(cfg_path))
        sanitized_hist = sanitize(str(history_path))
        sanitized_log = sanitize(str(log_file))

        report_lines = [
            "=" * 60,
            "MAYURISHELL DIAGNOSTICS REPORT (SANITIZED)",
            "=" * 60,
            f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "[System Information]",
            f"  MayuriShell Version: {VERSION}",
            f"  Python Version:      {py_ver} ({py_arch})",
            f"  Operating System:    {os_name} {os_rel} (Build: {os_ver})",
            f"  Architecture:        {machine}",
            f"  Username:            <user>",
            f"  Hostname:            <host>",
            "",
            "[Terminal Capabilities]",
            f"  Color System:        {color_sys}",
            f"  Unicode Encoding:    {stdout_enc} (Supported: {unicode_support})",
            f"  Dimensions:          {term_width} x {term_height}",
            "",
            "[Configuration & State]",
            f"  Config File:         {sanitized_cfg}",
            f"  Config Status:       {cfg_valid}",
            f"  History File:        {sanitized_hist}",
            f"  History Entries:     {history_entries}",
            f"  Registered Commands: {cmd_count}",
            f"  App Shortcuts:       {apps_count}",
            f"  Website Shortcuts:   {web_count}",
            f"  Folder Shortcuts:    {folder_count}",
            f"  Aliases:             {alias_count}",
            f"  Workflows:           {wf_count}",
            "",
            "[Logging Metrics]",
            f"  Log File:            {sanitized_log}",
            f"  Log Size:            {log_size_str}",
            f"  Total Log Lines:     {log_lines}",
            f"  Error Count:         {log_errors}",
            f"  Warning Count:       {log_warnings}",
            "",
            "[Dependencies]",
        ]
        for dep, st in sorted(dep_statuses.items()):
            report_lines.append(f"  {dep:16}: {st}")

        report_lines.append("")
        report_lines.append("Note: Command lines, history entries, and log messages are omitted for privacy.")
        report_lines.append("=" * 60)

        report_content = "\n".join(report_lines) + "\n"
        try:
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(report_content, encoding="utf-8")
            console.print(
                f"{theme.format_success('Diagnostics report exported to:')} "
                f"{theme.format_primary(escape(str(report_file)), bold=True)}"
            )
            return CommandResult.success()
        except OSError as exc:
            console.print(f"{theme.format_error('Failed to export diagnostics report:')} {escape(str(exc))}")
            return CommandResult.fail("Failed to export diagnostics report")

    # Display interactive diagnostics
    table = theme.create_table(title="MayuriShell Diagnostics")
    table.add_column("Component", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Details", style=theme.text_style, overflow="fold")

    table.add_row("Shell Version", theme.format_accent(VERSION, bold=True))
    table.add_row("Python", f"{escape(py_ver)} ({escape(py_arch)})")
    table.add_row("OS Platform", f"{escape(os_name)} {escape(os_rel)} ({escape(machine)})")
    table.add_row("Terminal", f"Color: {escape(color_sys)} | Unicode: {escape(unicode_support)} ({escape(stdout_enc)}) | Size: {term_width}x{term_height}")
    table.add_row("Config File", f"{escape(str(cfg_path))} [{theme.format_success(cfg_valid) if cfg_valid == 'Valid' else theme.format_error(cfg_valid)}]")
    table.add_row("Command History", f"{history_entries} entries stored ({escape(str(history_path))})")
    table.add_row("Commands & Shortcuts", f"{cmd_count} registered commands ({apps_count} apps, {web_count} sites, {folder_count} folders, {alias_count} aliases, {wf_count} workflows)")
    table.add_row("Log File", f"{escape(str(log_file))} ({escape(log_size_str)})")
    table.add_row("Log Error Count", f"{theme.format_error(str(log_errors))} errors, {theme.format_warning(str(log_warnings))} warnings ({log_lines} total lines)")

    dep_summary = ", ".join(
        f"{d}: {theme.format_success('OK') if 'Available' in s else theme.format_error('Missing')}"
        for d, s in sorted(dep_statuses.items())
    )
    table.add_row("Dependencies", dep_summary)

    console.print(table)
    console.print(
        f"{theme.format_muted('Export a sanitized text report to Desktop with: ')}"
        f"{theme.format_primary('diagnostics --export', bold=True)}"
    )
    console.print(
        f"{theme.format_muted('Inspect shell health and troubleshooting fixes with: ')}"
        f"{theme.format_primary('doctor', bold=True)}\n"
    )
    return CommandResult.success()


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register all core built-in and shell management commands."""
    registry.register(
        CommandInfo(
            name="help",
            description="Display command list or details for a specific command",
            handler=handle_help,
            usage="help [command]",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="clear",
            description="Clear the terminal screen",
            handler=handle_clear,
            usage="clear",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="exit",
            description="Exit MayuriShell gracefully",
            handler=handle_exit,
            usage="exit",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="history",
            description="Display command history or clear stored history",
            handler=handle_history,
            usage="history [clear]",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )

    registry.register(
        CommandInfo(
            name="version",
            description="Display MayuriShell and runtime version information",
            handler=handle_version,
            usage="version",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )

    registry.register(
        CommandInfo(
            name="diagnostics",
            description="Display environment diagnostics or export a sanitized report",
            handler=handle_diagnostics,
            usage="diagnostics [--export]",
            category="Builtins",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )

