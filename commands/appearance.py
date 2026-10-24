"""Visual appearance commands: theme, mascot, fetch, pet."""
from __future__ import annotations

import random
from typing import Any

from rich.cells import cell_len
from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.mascots import VALID_MASCOTS, get_mascot, resolve_mascot_name
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from core.theme import THEMES, ThemeManager
from core.version import VERSION
from services.system_service import (
    format_bytes_gb,
    format_bytes_mb_or_gb,
    get_disk_info,
    get_memory_info,
    get_os_info,
    get_uptime,
)

TIPS = [
    "Type 'theme preview' to view all visual palettes side-by-side.",
    "Type 'mascot <name>' to switch your animal companion.",
    "You can organize files safely with 'organize downloads' (supports dry run).",
    "Press Tab to autocomplete commands, shortcuts, directories, and options.",
    "Type 'process find <name>' to quickly locate running tasks by name.",
    "Type 'pet' to interact with your mascot anytime!",
]


def render_banner(context: Any) -> None:
    """Render the top welcoming banner."""
    console = context.console
    theme_mgr: ThemeManager = context.theme_manager
    theme = theme_mgr.current
    username = escape(context.config.get("username", "Mayuri"))

    if theme.is_plain:
        banner = (
            "+----------------------------------------------+\n"
            "|                 MAYURISHELL                  |\n"
            "|          YOUR PC. YOUR COMMANDS.             |\n"
            "+----------------------------------------------+\n\n"
            f"Welcome back, {username}!\n"
            "Type 'help' to explore your commands.\n"
        )
    else:
        top_border = theme.format_primary("╔══════════════════════════════════════════════╗", bold=True)
        bot_border = theme.format_primary("╚══════════════════════════════════════════════╝", bold=True)
        pipe = theme.format_primary("║", bold=True)
        title_text = theme.format_text("MAYURISHELL", bold=True)
        sub_text = theme.format_muted("YOUR PC. YOUR COMMANDS.")
        welcome = f"{theme.format_accent('Welcome back, ')}{theme.format_primary(username, bold=True)}{theme.format_accent('!')}"
        help_quote = theme.format_warning("'help'", bold=True)
        help_hint = f"{theme.format_text('Type ')}{help_quote}{theme.format_text(' to explore your commands.')}"

        banner = (
            f"{top_border}\n"
            f"{pipe}                 {title_text}                  {pipe}\n"
            f"{pipe}          {sub_text}             {pipe}\n"
            f"{bot_border}\n\n"
            f"{welcome}\n"
            f"{help_hint}\n"
        )
    console.print(banner)


def render_fetch(context: Any) -> None:
    """Render fetch dashboard with mascot on the left and system statistics on the right."""
    console = context.console
    theme_mgr: ThemeManager = context.theme_manager
    theme = theme_mgr.current

    # Collect stats safely (non-blocking CPU)
    import psutil
    try:
        cpu_pct = psutil.cpu_percent(interval=None)
    except Exception:
        cpu_pct = 0.0

    os_info = get_os_info()
    mem_info = get_memory_info()
    vmem = mem_info.get("virtual", {})
    disks = get_disk_info()
    main_disk = disks[0] if disks else None
    uptime = get_uptime()

    configured_mascot = context.config.get_mascot_name()
    resolved_mascot = resolve_mascot_name(configured_mascot)
    mascot_data = get_mascot(resolved_mascot, mood="happy", is_plain=theme.is_plain)
    art_lines = mascot_data.art_lines

    username = context.config.get("username", "Mayuri")
    host = context.config.get_prompt_host()
    ver = context.config.get("version", VERSION)
    num_cmds = len(context.registry.list_commands())
    num_aliases = len(context.alias_manager.get_all()) if hasattr(context, "alias_manager") else 0

    # Format info rows
    info_rows: list[tuple[str, str]] = [
        (f"{username}@{host}", ""),
        ("-----------------", ""),
        ("OS:", str(os_info.get("windows_version", "Windows"))),
        ("Uptime:", str(uptime.get("formatted_uptime", "Unavailable"))),
        ("Shell:", f"MayuriShell v{ver}"),
        ("CPU:", f"{cpu_pct:.1f}% ({psutil.cpu_count(logical=True) or 1} threads)"),
        ("RAM:", f"{vmem.get('used_formatted', '0 GB')} / {vmem.get('total_formatted', '0 GB')} ({vmem.get('percent', 0.0):.1f}%)"),
    ]
    if main_disk:
        info_rows.append(("Disk:", f"{main_disk.get('mountpoint', 'C:')} {main_disk.get('used_formatted', '0 GB')} / {main_disk.get('total_formatted', '0 GB')} ({main_disk.get('percent', 0.0):.1f}%)"))
    info_rows.append(("Theme / Mascot:", f"{theme.name} / {resolved_mascot}"))
    info_rows.append(("Commands:", f"{num_cmds} cmds, {num_aliases} aliases"))

    # Width check for narrow layout (< 80 columns)
    terminal_width = console.width or 80

    if terminal_width < 80:
        # Narrow layout: stack info below the mascot
        for line in art_lines:
            console.print(theme.format_primary(line) if not theme.is_plain else line)
        console.print()
        for label, val in info_rows:
            if not val:
                console.print(theme.format_accent(label) if not theme.is_plain else label)
            else:
                lbl_str = theme.format_accent(label) if not theme.is_plain else label
                console.print(f"{lbl_str} {escape(val)}")
    else:
        # Side-by-side layout using cell_len alignment
        max_art_width = max((cell_len(l) for l in art_lines), default=12)
        total_rows = max(len(art_lines), len(info_rows))

        lines_output = []
        for i in range(total_rows):
            # Left side
            if i < len(art_lines):
                art_raw = art_lines[i]
                pad = " " * max(0, max_art_width - cell_len(art_raw))
                left = (theme.format_primary(art_raw) if not theme.is_plain else art_raw) + pad
            else:
                left = " " * max_art_width

            # Right side
            if i < len(info_rows):
                lbl, val = info_rows[i]
                if not val:
                    right = theme.format_accent(lbl) if not theme.is_plain else lbl
                else:
                    lbl_str = theme.format_accent(f"{lbl:<16}") if not theme.is_plain else f"{lbl:<16}"
                    right = f"{lbl_str} {escape(val)}"
            else:
                right = ""

            lines_output.append(f"{left}   {right}".rstrip())

        console.print("\n".join(lines_output))

    # Add random tip
    tip = random.choice(TIPS)
    console.print()
    if theme.is_plain:
        console.print(f"Tip: {tip}\n")
    else:
        console.print(f"{theme.format_muted(f'Tip: {tip}')}\n")


def handle_fetch(context: Any, args: list[str]) -> CommandResult:
    """Display the system fetch dashboard with mascot art."""
    render_fetch(context)
    return CommandResult.success()


def handle_theme(context: Any, args: list[str]) -> CommandResult:
    """List available themes or switch to a theme by name."""
    console = context.console
    theme_mgr: ThemeManager = context.theme_manager
    theme = theme_mgr.current

    if not args:
        # List themes
        table = theme.create_table(title="Available Visual Themes")
        table.add_column("Theme", style=theme.bold_text_style, no_wrap=True)
        table.add_column("Display Name", style=theme.bold_primary_style, no_wrap=True)
        table.add_column("Description", style=theme.text_style)
        table.add_column("Status", justify="center", style=theme.warning_style, no_wrap=True)

        for name, d_name, desc, is_active in theme_mgr.list_themes():
            status = "* (Active)" if is_active else ""
            table.add_row(escape(name), escape(d_name), escape(desc), status)

        console.print(table)
        console.print(theme.format_muted("Use 'theme <name>' to apply a theme, or 'theme preview' to inspect palettes."))
        return CommandResult.success()

    sub = args[0].lower()
    if sub == "preview":
        return handle_theme_preview(context)

    # Set theme
    success, msg = theme_mgr.set_theme(sub)
    if success:
        console.print(theme_mgr.current.format_success(f"Success: {msg}"))
        # Show mini palette preview of the selected theme
        preview_table = theme_mgr.current.create_table(title=f"Preview: {theme_mgr.current.display_name}")
        preview_table.add_column("Token", style=theme_mgr.current.bold_text_style)
        preview_table.add_column("Sample Text", style=theme_mgr.current.text_style)
        for token in ("primary", "accent", "success", "warning", "error", "muted", "border"):
            val = theme_mgr.current.colors.get(token, "")
            sample = theme_mgr.current.format(token, f"Sample {token.capitalize()}")
            preview_table.add_row(token, f"{sample} ({val})")
        console.print(preview_table)
        return CommandResult.success()
    else:
        console.print(theme.format_error(f"Error: {msg}"))
        return CommandResult.fail(msg)


def handle_theme_preview(context: Any) -> CommandResult:
    """Preview all visual themes side-by-side or in structured comparison tables."""
    console = context.console
    theme_mgr: ThemeManager = context.theme_manager

    console.print(theme_mgr.current.format_accent("MayuriShell Theme Showcase\n", bold=True))

    for key, thm in THEMES.items():
        table = thm.create_table(title=f"Theme: {thm.display_name} ('{key}')")
        table.add_column("Sample Heading", style=thm.bold_primary_style)
        table.add_column("Accent", style=thm.bold_accent_style)
        table.add_column("Status", style=thm.success_style)
        table.add_column("Description", style=thm.muted_style)

        success_sample = thm.format_success("Online / Ready")
        accent_sample = thm.format_accent("Accent Item")
        heading_sample = thm.format_primary("Primary Value")
        table.add_row(heading_sample, accent_sample, success_sample, escape(thm.description))
        console.print(table)
        console.print()
    return CommandResult.success()


def handle_mascot(context: Any, args: list[str]) -> CommandResult:
    """List available mascot characters or set your active companion."""
    console = context.console
    theme_mgr: ThemeManager = context.theme_manager
    theme = theme_mgr.current

    if not args:
        current_mascot = context.config.get_mascot_name()
        table = theme.create_table(title="Mascot Companions")
        table.add_column("Mascot", style=theme.bold_text_style, no_wrap=True)
        table.add_column("Preview Face", style=theme.bold_primary_style, no_wrap=True)
        table.add_column("Status", justify="center", style=theme.warning_style, no_wrap=True)

        for name in list(VALID_MASCOTS) + ["random"]:
            if name == "random":
                face = "(Random per session)"
            else:
                m = get_mascot(name, mood="happy", is_plain=theme.is_plain)
                face = m.face
            status = "* (Active)" if name == current_mascot else ""
            table.add_row(escape(name), escape(face), status)

        console.print(table)
        console.print(theme.format_muted("Use 'mascot <name|random>' to select your mascot."))
        return CommandResult.success()

    choice = args[0].lower()
    valid_choices = list(VALID_MASCOTS) + ["random"]
    if choice not in valid_choices:
        valid_str = ", ".join(valid_choices)
        console.print(theme.format_error(f"Error: Unknown mascot '{escape(choice)}'. Available: {valid_str}"))
        return CommandResult.fail("Unknown mascot")

    context.config.set_mascot_name(choice)
    resolved = resolve_mascot_name(choice)
    m = get_mascot(resolved, mood="happy", is_plain=theme.is_plain)

    console.print(theme.format_success(f"Mascot set to '{escape(choice)}'!"))
    art_str = "\n".join(m.art_lines)
    console.print(theme.format_primary(art_str) if not theme.is_plain else art_str)
    console.print(f"{m.face} Welcome to the team!\n")
    return CommandResult.success()


def handle_pet(context: Any, args: list[str]) -> CommandResult:
    """Pet your animal mascot companion and watch them react!"""
    console = context.console
    theme_mgr: ThemeManager = context.theme_manager
    theme = theme_mgr.current

    configured = context.config.get_mascot_name()
    resolved = resolve_mascot_name(configured)
    m = get_mascot(resolved, mood="happy", is_plain=theme.is_plain)

    reactions = {
        "cat": "*purrrrrrs loudly and rubs against your hand*",
        "bunny": "*hops happily around you and munches a cookie*",
        "bear": "*gives you a big warm, gentle bear hug*",
        "fox": "*chirps playfully and curls its fluffy tail around you*",
        "penguin": "*waddles excitedly and flaps its flippers*",
        "shiba": "*wags tail vigorously and offers a friendly paw*",
    }
    reaction_text = reactions.get(resolved, "*happily leans into your hand*")

    console.print(theme.format_accent(f"You gently pet {resolved.capitalize()}..."))
    console.print(theme.format_primary(f"{m.face} {reaction_text}"))
    return CommandResult.success()


def handle_prompt(context: Any, args: list[str]) -> CommandResult:
    """Toggle or inspect shell prompt settings, including Git branch display."""
    console = context.console
    theme = context.theme
    config = context.config

    if not args:
        symbol = config.get_prompt_symbol()
        host = config.get_prompt_host()
        git_enabled = config.get_prompt_git_enabled()
        status_str = "on" if git_enabled else "off"

        console.print(theme.format_primary("Shell Prompt Settings:", bold=True))
        console.print(f"  Symbol: {theme.format_accent(escape(symbol))}")
        console.print(f"  Host:   {theme.format_accent(escape(host))}")
        console.print(f"  Git branch in prompt: {theme.format_success(status_str) if git_enabled else theme.format_warning(status_str)}")
        console.print(theme.format_muted("\nUsage: prompt git on|off"))
        return CommandResult.success()

    subcmd = args[0].lower()
    if subcmd == "git":
        if len(args) == 1:
            git_enabled = config.get_prompt_git_enabled()
            status_str = "on" if git_enabled else "off"
            console.print(f"Prompt git branch display: {status_str}")
            return CommandResult.success()

        val = args[1].lower()
        if val in ("on", "off"):
            try:
                config.set_prompt_git_enabled(val)
                msg = f"Prompt git branch display set to '{val}'."
                if theme.is_plain:
                    console.print(msg)
                else:
                    console.print(theme.format_success(msg, bold=True))
                return CommandResult.success()
            except ValueError as exc:
                return CommandResult.fail(str(exc))
        else:
            err = f"Invalid option '{args[1]}'. Use 'prompt git on' or 'prompt git off'."
            console.print(f"{theme.format_error('Error:')} {escape(err)}")
            return CommandResult.fail(err, hint="Usage: prompt git on|off")

    err = f"Unknown prompt subcommand '{args[0]}'."
    console.print(f"{theme.format_error('Error:')} {escape(err)}")
    return CommandResult.fail(err, hint="Usage: prompt [git on|off]")


def register_appearance_commands(registry: CommandRegistry) -> None:
    """Register all visual appearance commands in the CommandRegistry."""
    registry.register(
        CommandInfo(
            name="theme",
            description="Inspect, preview, and switch visual color themes",
            handler=handle_theme,
            usage="theme [name|preview]",
            category="Appearance",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )
    registry.register(
        CommandInfo(
            name="mascot",
            description="Inspect and select your original animal mascot companion",
            handler=handle_mascot,
            usage="mascot [name|random]",
            category="Appearance",
            arg_rules=ArgumentRules(min_args=0, max_args=1),
        )
    )
    registry.register(
        CommandInfo(
            name="fetch",
            description="Display system fetch dashboard with mascot art and hardware info",
            handler=handle_fetch,
            usage="fetch",
            category="Appearance",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
    registry.register(
        CommandInfo(
            name="pet",
            description="Pet your mascot companion and watch them react",
            handler=handle_pet,
            usage="pet",
            category="Appearance",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
    registry.register(
        CommandInfo(
            name="prompt",
            description="Configure prompt settings (e.g. prompt git on|off)",
            handler=handle_prompt,
            usage="prompt [git on|off]",
            category="Appearance",
            arg_rules=ArgumentRules(min_args=0, max_args=2),
        )
    )
