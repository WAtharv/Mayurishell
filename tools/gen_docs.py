"""Documentation generator for MayuriShell commands catalog.

Inspects the live CommandRegistry and produces docs/commands.md so command
documentation never falls out of sync with registered commands.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys
import tempfile

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from core.version import VERSION
from main import register_all_commands


COMMAND_EXAMPLES: dict[str, list[str]] = {
    "help": ["help", "help organize", "help cd"],
    "version": ["version"],
    "clear": ["clear"],
    "exit": ["exit"],
    "history": ["history", "history clear"],
    "diagnostics": ["diagnostics", "diagnostics --export"],
    "pwd": ["pwd"],
    "ls": ["ls", "ls -a", "ls -l", "ls projects", "ls -a -l downloads"],
    "cd": ["cd projects", "cd ..", "cd ~", "cd downloads"],
    "open": ["open report.pdf", 'open "my notes.txt"'],
    "mkdir": ["mkdir new_folder", 'mkdir "my project"'],
    "touch": ["touch notes.txt", "touch newfile.py"],
    "copy": ["copy file.txt backup.txt", "copy notes.txt projects\\"],
    "move": ["move draft.txt archive\\", "move test.txt ..\\"],
    "rename": ["rename old.txt new.txt", 'rename "draft v1.txt" "draft v2.txt"'],
    "delete": ["delete old_file.txt", "delete -r temp_directory"],
    "find": ["find report.pdf", "find *.py", 'find "machine learning"'],
    "desktop": ["desktop"],
    "downloads": ["downloads"],
    "documents": ["documents"],
    "projects": ["projects"],
    "home": ["home"],
    "sysinfo": ["sysinfo"],
    "cpu": ["cpu"],
    "memory": ["memory"],
    "disk": ["disk"],
    "uptime": ["uptime"],
    "processes": ["processes", "processes --sort mem", "processes --limit 15"],
    "process": ["process find python", "process inspect 1234", "process kill 5678"],
    "theme": ["theme", "theme kawaii", "theme catppuccin", "theme tokyo-night", "theme preview"],
    "mascot": ["mascot", "mascot bunny", "mascot fox", "mascot shiba"],
    "fetch": ["fetch"],
    "pet": ["pet"],
    "alias": ["alias", "alias gs 'git status'", "alias c clear"],
    "unalias": ["unalias gs", "unalias c"],
    "aliases": ["aliases"],
    "config": ["config", "config show", "config get username", "config set prompt_symbol $", "config reset", "config path", "config backup", "config restore"],
    "add-website": ["add-website docs https://docs.python.org", "add-website yt https://youtube.com/results?search_query={query}"],
    "remove-website": ["remove-website docs"],
    "websites": ["websites"],
    "add-folder": ["add-folder notes ~/Notes", "add-folder work 'D:\\Work'"],
    "remove-folder": ["remove-folder notes"],
    "folders": ["folders"],
    "add-app": ["add-app vlc 'C:\\Program Files\\VideoLAN\\VLC\\vlc.exe'"],
    "remove-app": ["remove-app vlc"],
    "apps": ["apps"],
    "organize": ["organize downloads", "organize downloads --dry-run", "organize downloads --include-other", "organize undo"],
    "create-project": ["create-project my-app", "create-project ml-pipeline --template ml", "create-project api-server --template fastapi", "create-project --list-templates"],
    "workflow": ["workflow list", "workflow run dev", "workflow show web", "workflow add study 'notion, spotify'", "workflow remove study"],
}


def generate_commands_markdown() -> str:
    """Generate Markdown documentation for all registered commands."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_mgr = ConfigManager(base_dir=Path(temp_dir))
        registry = CommandRegistry()
        register_all_commands(registry, config_mgr)

        all_cmds = registry.list_commands()

    # Group commands by category
    categories: dict[str, list] = defaultdict(list)
    for cmd in all_cmds:
        cat = cmd.category or "General"
        categories[cat].append(cmd)

    lines: list[str] = [
        f"# MayuriShell Command Catalog (v{VERSION})",
        "",
        "This document lists every command available in MayuriShell. It is automatically generated from the internal command registry metadata.",
        "",
        "## Table of Contents",
        "",
    ]

    for cat in sorted(categories.keys()):
        slug = cat.lower().replace(" ", "-").replace("&", "").replace("/", "")
        lines.append(f"- [{cat}](#{slug})")

    lines.append("")
    lines.append("---")
    lines.append("")

    for cat in sorted(categories.keys()):
        slug = cat.lower().replace(" ", "-").replace("&", "").replace("/", "")
        lines.append(f"## {cat}")
        lines.append("")

        for cmd in sorted(categories[cat], key=lambda c: c.name):
            lines.append(f"### `{cmd.name}`")
            lines.append("")
            lines.append(f"**Description:** {cmd.description}")
            lines.append("")
            lines.append(f"**Usage:** `{cmd.usage}`")
            lines.append("")

            # Arguments info
            rules = cmd.arg_rules
            min_a = rules.min_args
            max_a = "Unlimited" if rules.max_args is None else str(rules.max_args)
            lines.append(f"**Arguments:** Minimum: `{min_a}`, Maximum: `{max_a}`")
            lines.append("")

            # Examples
            examples = COMMAND_EXAMPLES.get(cmd.name, [cmd.name])
            lines.append("**Examples:**")
            lines.append("```text")
            for ex in examples:
                lines.append(f"mayuri@pc > {ex}")
            lines.append("```")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Generate docs/commands.md in the project directory."""
    project_root = Path(__file__).resolve().parent.parent
    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_file = docs_dir / "commands.md"

    content = generate_commands_markdown()
    out_file.write_text(content, encoding="utf-8")
    print(f"Successfully generated {out_file} with live registry metadata.")


if __name__ == "__main__":
    main()
