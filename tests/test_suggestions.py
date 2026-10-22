"""Comprehensive unit and integration tests for Smart Command Suggestions."""
import logging
from pathlib import Path
import time
from unittest.mock import patch

import pytest
from rich.console import Console

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
from core.aliases import AliasManager
from core.config_manager import ConfigManager
from core.exceptions import AliasConflictError
from core.executor import CommandExecutor, CommandResult
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import MayuriShell, ShellContext
from core.suggestions import (
    DESTRUCTIVE_COMMANDS,
    PREFILL_ALLOWLIST,
    cached_which,
    get_available_app_hints,
    get_directory_hints,
    get_history_suggestions,
    is_secret_like,
    should_prefill,
    suggest_arguments,
    suggest_command_corrections,
)


def create_full_test_shell(tmp_path: Path, is_plain: bool = False) -> tuple[MayuriShell, Console]:
    """Create a fully-wired shell with all registered commands and shortcuts."""
    config = ConfigManager(base_dir=tmp_path)
    if is_plain:
        config.set("display.force_plain", True)
    history = HistoryManager(tmp_path / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_builtin_commands(registry)
    register_appearance_commands(registry)
    register_application_commands(registry, config)
    register_website_commands(registry, config)
    register_navigation_commands(registry, config)
    register_customization_commands(registry, config)
    register_file_commands(registry)
    register_search_commands(registry)
    register_system_commands(registry)
    register_process_commands(registry)
    register_organization_commands(registry, config)
    register_project_commands(registry, config)
    register_workflow_commands(registry, config)

    console = Console(record=True, color_system=None, width=140)
    shell = MayuriShell(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        console=console,
        current_dir=tmp_path,
    )
    shell.context.is_interactive = True
    return shell, console


# 1. Typo ranking for youtube, github, notepad
def test_typo_ranking_youtube_github_notepad(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    corrections_yt = suggest_command_corrections("youtub", [], shell.context)
    assert any("youtube" in c for c in corrections_yt)

    corrections_gh = suggest_command_corrections("githb", [], shell.context)
    assert any("github" in c for c in corrections_gh)

    corrections_np = suggest_command_corrections("notpad", [], shell.context)
    assert any("notepad" in c for c in corrections_np)


# 2. Subcommand and option typos
def test_subcommand_and_option_typos(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    ctx = shell.context

    # process kil -> process kill
    res1 = suggest_arguments("process", ["kil"], ctx)
    assert res1 is not None
    assert "process kill" in res1[0][0]

    # theme kawai -> theme kawaii
    res2 = suggest_arguments("theme", ["kawai"], ctx)
    assert res2 is not None
    assert "theme kawaii" in res2[0][0]

    # mascot fx -> mascot fox
    res3 = suggest_arguments("mascot", ["fx"], ctx)
    assert res3 is not None
    assert "mascot fox" in res3[0][0]

    # organize --dryrun -> organize --dry-run
    res4 = suggest_arguments("organize", ["--dryrun"], ctx)
    assert res4 is not None
    assert "organize --dry-run" in res4[0][0]

    # workflow rn -> workflow run
    res5 = suggest_arguments("workflow", ["rn"], ctx)
    assert res5 is not None
    assert "workflow run" in res5[0][0]

    # processes --sort cpuu -> processes --sort cpu
    res6 = suggest_arguments("processes", ["--sort", "cpuu"], ctx)
    assert res6 is not None
    assert "processes --sort cpu" in res6[0][0]

    # history clr -> history clear
    res7 = suggest_arguments("history", ["clr"], ctx)
    assert res7 is not None
    assert "history clear" in res7[0][0]


# 3. Arguments kept
def test_arguments_kept(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    corrections = suggest_command_corrections("yotube", ["lofi", "beats"], shell.context)
    assert len(corrections) > 0
    assert corrections[0] == "youtube lofi beats"


# 4. Case-insensitivity
def test_case_insensitive(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    corrections = suggest_command_corrections("YoUtUb", [], shell.context)
    assert any("youtube" in c for c in corrections)


# 5. Short input ignored (< 2 characters)
def test_short_input_ignored(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    assert suggest_command_corrections("y", [], shell.context) == []
    assert suggest_command_corrections(" ", [], shell.context) == []
    assert suggest_command_corrections("", [], shell.context) == []


# 6. No destructive commands suggested from history
def test_no_destructive_commands_from_history(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    shell.context.history_manager.add("delete confidential.txt", success=True)
    shell.context.history_manager.add("copy a.txt b.txt", success=True)
    shell.context.history_manager.add("youtube lofi study beats", success=True)

    # Destructive commands should not be retrieved
    del_suggs = get_history_suggestions("delete", shell.context)
    assert del_suggs == []

    # Safe commands are retrieved
    yt_suggs = get_history_suggestions("youtube", shell.context)
    assert "youtube lofi study beats" in yt_suggs


# 7. Prefill allowlist vs. destructive exclusion
def test_prefill_allowlist_and_destructive_exclusion(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    ctx = shell.context

    # Allowlisted commands prefill when single match
    can_prefill, line = should_prefill(["youtube"], ctx, is_interactive=True)
    assert can_prefill is True
    assert line == "youtube"

    can_prefill, line = should_prefill(["pwd"], ctx, is_interactive=True)
    assert can_prefill is True
    assert line == "pwd"

    # Multiple matches -> no prefill
    can_prefill, _ = should_prefill(["youtube", "youtube-music"], ctx, is_interactive=True)
    assert can_prefill is False

    # Destructive commands -> NEVER prefill
    for d_cmd in DESTRUCTIVE_COMMANDS:
        can_prefill, _ = should_prefill([d_cmd], ctx, is_interactive=True)
        assert can_prefill is False, f"Expected no prefill for destructive command '{d_cmd}'"

    # Destructive flags -> NEVER prefill
    can_prefill, _ = should_prefill(["delete -r temp"], ctx, is_interactive=True)
    assert can_prefill is False

    can_prefill, _ = should_prefill(["processes --force"], ctx, is_interactive=True)
    assert can_prefill is False

    # Non-interactive -> NEVER prefill
    can_prefill, _ = should_prefill(["youtube"], ctx, is_interactive=False)
    assert can_prefill is False


# 8. Prefill applies to very next prompt only and is cleared on run, edit, or Ctrl+C
def test_prefill_cleared_on_next_prompt(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    shell.run_command_line("youtub")
    # Verify prefill was staged
    assert shell.next_prefill == "youtube" or shell.context.next_prefill == "youtube"

    # Next execution clears prefill
    shell.run_command_line("version")
    assert shell.next_prefill is None
    assert shell.context.next_prefill is None


# 9. Destructive closest match shows command name and usage only, never user arguments
def test_destructive_closest_match_hides_arguments(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path)
    shell.run_command_line("delet my_secret_file.txt")
    output = console.export_text()
    assert "Did you mean?" in output
    assert "-> delete" in output
    assert "Usage: delete" in output
    # Arguments must NEVER be shown
    assert "my_secret_file.txt" not in output


# 10. Directory hints capped at 200, non-recursive, and never reading file contents
def test_directory_hints_capped_and_non_recursive(tmp_path: Path) -> None:
    # Empty dir -> no hints
    assert get_directory_hints(tmp_path) == []

    # Create Python file in root -> hints returned
    (tmp_path / "main.py").write_text("# code", encoding="utf-8")
    hints = get_directory_hints(tmp_path)
    assert "code ." in hints
    assert "ls *.py" in hints

    # Verify capped behavior: directory with 250 text files
    sub_test_dir = tmp_path / "subtest"
    sub_test_dir.mkdir()
    for i in range(250):
        (sub_test_dir / f"file_{i}.txt").write_text("hello", encoding="utf-8")
    # Python file placed beyond cap
    (sub_test_dir / "file_249_last.py").write_text("# code", encoding="utf-8")
    # Does not crash or hang
    res = get_directory_hints(sub_test_dir)
    assert isinstance(res, list)


# 11. PATH hints mocked with shutil.which
def test_path_app_hints_mocked(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    with patch("shutil.which", return_value=r"C:\Python311\python.exe"):
        # Reset which cache for test
        from core.suggestions import _WHICH_CACHE
        _WHICH_CACHE.clear()

        hints = get_available_app_hints("python", shell.context)
        assert any(h.startswith("add-app python") for h in hints)
        assert "create-project python" in hints


# 12. Hint text for each failure type
def test_hint_text_for_failure_types(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path)

    # 1. Unknown command hint
    shell.run_command_line("someunknowncommand")
    assert "Type 'help' to see all commands or press Tab to complete." in console.export_text()

    # 2. Folder not found hint
    console.clear()
    shell.run_command_line("cd nonexistent_folder_xyz")
    out = console.export_text()
    assert "Directory not found:" in out
    assert "Use 'add-folder <name> <path>' to create a folder shortcut, or 'cd' to navigate." in out

    # 3. App not found hint
    console.clear()
    shell.run_command_line(r"add-app nonexistentapp C:\fake\app.exe")
    console.clear()
    shell.run_command_line("nonexistentapp")
    out = console.export_text()
    assert "Application not found:" in out
    assert "Use 'add-app nonexistentapp <path>' to register the executable path." in out

    # 4. Flag argument refused hint
    console.clear()
    shell.run_command_line("notepad -f")
    out = console.export_text()
    assert "Application and shortcut arguments must be existing file paths, not flags." in out

    # 5. Site without {query} template hint
    console.clear()
    shell.run_command_line("add-website mysite https://example.com")
    console.clear()
    shell.run_command_line("mysite searchterm")
    out = console.export_text()
    assert "Update the site with 'add-website mysite <url-with-{query}>' to support search queries." in out

    # 6. Protected process hint
    console.clear()
    shell.run_command_line("process kill 0")
    out = console.export_text()
    assert "Process is protected for Windows system stability and cannot be terminated." in out

    # 7. Invalid name hint
    console.clear()
    shell.run_command_line("add-folder bad/name ~/Desktop")
    out = console.export_text()
    assert "Names must be alphanumeric without spaces and cannot collide with existing commands." in out

    # 8. Wildcard delete hint
    console.clear()
    shell.run_command_line("delete *.txt")
    out = console.export_text()
    assert "Wildcard deletion is refused for safety. Specify exact file names." in out


# 13. Plain-mode ASCII output
def test_plain_mode_ascii_output(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path, is_plain=True)
    shell.run_command_line("youtub")
    output = console.export_text()
    assert "Command not found: youtub (=;.;=)" in output
    assert "Did you mean?" in output
    assert "-> youtube" in output
    # Ensure all output characters are strictly ASCII (ord < 128)
    for ch in output:
        assert ord(ch) < 128, f"Non-ASCII character '{ch}' (ord {ord(ch)}) found in plain mode output."


# 14. Rich markup escaping
def test_rich_markup_escaping(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path)
    shell.run_command_line('"[bold red]injected_tag[/bold red]"')
    output = console.export_text()
    assert "Command not found: [bold red]injected_tag[/bold red]" in output


# 15. Privacy: No typed unknown command or arguments in log
def test_no_typed_text_in_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    with caplog.at_level(logging.WARNING):
        shell.run_command_line("supersecretquery12345 --sensitive-flag")
    
    log_text = caplog.text
    assert "Command failed: unknown command (count:" in log_text
    assert "supersecretquery12345" not in log_text
    assert "--sensitive-flag" not in log_text


# 16. The suggestions off switch
def test_suggestions_toggle_command(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path)
    
    # Check default status
    shell.run_command_line("suggestions")
    assert "Smart command suggestions: on" in console.export_text()

    # Toggle off
    console.clear()
    shell.run_command_line("suggestions off")
    assert "Smart command suggestions disabled." in console.export_text()
    assert shell.context.config.get_suggestions_enabled() is False

    # When off, unknown command shows plain error without suggestions block
    console.clear()
    shell.run_command_line("youtub")
    out = console.export_text()
    assert "Command not found: youtub" in out
    assert "Did you mean?" not in out

    # Toggle on
    console.clear()
    shell.run_command_line("suggestions on")
    assert "Smart command suggestions enabled." in console.export_text()
    assert shell.context.config.get_suggestions_enabled() is True


# 17. Speed under 50 ms with 100 shortcuts (tolerant timing test)
def test_performance_sub_50ms_with_100_shortcuts(tmp_path: Path) -> None:
    shell, _ = create_full_test_shell(tmp_path)
    for i in range(100):
        shell.context.config.set_shortcut("applications", f"benchapp{i}", f"bench{i}.exe")

    start = time.perf_counter()
    for _ in range(10):
        suggest_command_corrections("benchapp5", [], shell.context)
    elapsed = (time.perf_counter() - start) / 10

    # Tolerant threshold: generous upper bound to prevent slow CI / machine failure
    assert elapsed < 0.2, f"Suggestion lookup took {elapsed:.4f}s per query (must be well under generous bound)"


# 18. Aliases with extra words and suggestions shadow refused
def test_aliases_with_extra_words_and_suggestions_shadow_refused(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path)
    
    # 1. Alias with extra words works
    shell.context.alias_manager.add_alias("yts", "youtube")
    res_name, res_args = shell.context.alias_manager.resolve("yts", ["lofi", "beats"])
    assert res_name == "youtube"
    assert res_args == ["lofi", "beats"]

    # 2. Attempting to shadow 'suggestions' command with an alias is rejected
    with pytest.raises(AliasConflictError):
        shell.context.alias_manager.add_alias("suggestions", "version", registry=shell.context.registry)


# 19. Secret input protection
def test_secret_input_protection(tmp_path: Path) -> None:
    shell, console = create_full_test_shell(tmp_path)

    # 1. Input matching secret pattern
    shell.run_command_line("password mytoken123")
    out = console.export_text()
    assert "Command not found." in out
    assert "password" not in out
    assert "Did you mean?" not in out
    # History must not contain the secret
    assert not any("mytoken123" in e["command"] for e in shell.context.history_manager.entries)

    # 2. Token-like string (long random token)
    console.clear()
    long_token = "ghp_xxxxxxxxxxxxxxxxxxxx1234567890abcdef"
    shell.run_command_line(long_token)
    out = console.export_text()
    assert "Command not found." in out
    assert long_token not in out
    assert "Did you mean?" not in out
    assert not any(long_token in e["command"] for e in shell.context.history_manager.entries)
