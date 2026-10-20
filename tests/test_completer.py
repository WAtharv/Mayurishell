"""Unit and integration tests for context-aware auto-completion."""
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from commands.builtins import register_builtin_commands
from commands.files import register_file_commands
from commands.navigation import register_navigation_commands
from core.aliases import AliasManager
from core.completer import MayuriCompleter
from core.config_manager import ConfigManager
from core.history import HistoryManager
from core.registry import CommandRegistry
from core.shell import ShellContext


def create_completer_context(tmp_path: Path) -> tuple[ShellContext, MayuriCompleter]:
    """Helper to initialize ShellContext and MayuriCompleter for testing."""
    config = ConfigManager(base_dir=tmp_path / "appdata")
    history = HistoryManager(tmp_path / "appdata" / "history.json")
    alias_mgr = AliasManager(config)
    registry = CommandRegistry()

    register_builtin_commands(registry)
    register_navigation_commands(registry, config)
    register_file_commands(registry)

    work_dir = tmp_path / "workspace"
    work_dir.mkdir(parents=True, exist_ok=True)

    context = ShellContext(
        config=config,
        registry=registry,
        history_manager=history,
        alias_manager=alias_mgr,
        current_dir=work_dir,
    )
    completer = MayuriCompleter(context)
    return context, completer


def test_first_word_completion(tmp_path: Path) -> None:
    """First word completes commands, apps, websites, folders, and aliases."""
    context, completer = create_completer_context(tmp_path)
    context.alias_manager.add_alias("myalias", "ls -a")

    doc = Document("my", 2)
    completions = list(completer.get_completions(doc, CompleteEvent()))
    names = [c.text for c in completions]
    assert "myalias" in names


def test_cd_shows_only_dirs(tmp_path: Path) -> None:
    """cd command completion must show only directories, not files."""
    context, completer = create_completer_context(tmp_path)
    cur = context.current_dir
    (cur / "folder_alpha").mkdir()
    (cur / "file_beta.txt").write_text("hello")

    doc = Document("cd f", 4)
    completions = list(completer.get_completions(doc, CompleteEvent()))
    names = [c.display_text for c in completions]

    assert "folder_alpha\\" in names
    assert "file_beta.txt" not in names


def test_quoting_names_with_spaces(tmp_path: Path) -> None:
    """Names with spaces must be wrapped in double quotes automatically."""
    context, completer = create_completer_context(tmp_path)
    cur = context.current_dir
    (cur / "my cool folder").mkdir()
    (cur / "my document.txt").write_text("data")

    # In cd: folder with space
    doc_cd = Document("cd my", 5)
    completions_cd = list(completer.get_completions(doc_cd, CompleteEvent()))
    texts_cd = [c.text for c in completions_cd]
    assert '"my cool folder\\"' in texts_cd

    # In open: file with space
    doc_open = Document("open my", 7)
    completions_open = list(completer.get_completions(doc_open, CompleteEvent()))
    texts_open = [c.text for c in completions_open]
    assert '"my document.txt"' in texts_open


def test_case_insensitivity(tmp_path: Path) -> None:
    """Completions match case-insensitively on Windows."""
    context, completer = create_completer_context(tmp_path)
    cur = context.current_dir
    (cur / "ProjectOmega").mkdir()

    doc = Document("cd proj", 7)
    completions = list(completer.get_completions(doc, CompleteEvent()))
    texts = [c.text for c in completions]
    assert "ProjectOmega\\" in texts


def test_completion_uses_live_current_dir(tmp_path: Path) -> None:
    """Completer reads context.current_dir live at completion time, not os.getcwd()."""
    context, completer = create_completer_context(tmp_path)
    sub = context.current_dir / "test-area"
    sub.mkdir()
    (sub / "nested_target.txt").write_text("deep")

    # Before moving current_dir
    doc1 = Document("ls nested", 9)
    completions1 = list(completer.get_completions(doc1, CompleteEvent()))
    assert len(completions1) == 0

    # Switch shell's current_dir (simulating cd test-area)
    context.current_dir = sub
    doc2 = Document("ls nested", 9)
    completions2 = list(completer.get_completions(doc2, CompleteEvent()))
    texts2 = [c.text for c in completions2]
    assert "nested_target.txt" in texts2


def test_hidden_files_suppression(tmp_path: Path) -> None:
    """Hidden files are hidden by default and shown only when prefix starts with '.'."""
    context, completer = create_completer_context(tmp_path)
    cur = context.current_dir
    (cur / ".secret_config").write_text("key")
    (cur / "visible_file.txt").write_text("visible")

    # Without dot prefix
    doc_no_dot = Document("open ", 5)
    completions_no_dot = list(completer.get_completions(doc_no_dot, CompleteEvent()))
    texts_no_dot = [c.text for c in completions_no_dot]
    assert "visible_file.txt" in texts_no_dot
    assert ".secret_config" not in texts_no_dot

    # With dot prefix
    doc_dot = Document("open .", 6)
    completions_dot = list(completer.get_completions(doc_dot, CompleteEvent()))
    texts_dot = [c.text for c in completions_dot]
    assert ".secret_config" in texts_dot


def test_folder_shortcuts_in_cd(tmp_path: Path) -> None:
    """cd suggests folder shortcuts at top-level."""
    context, completer = create_completer_context(tmp_path)
    context.config.set_shortcut("folder_shortcuts", "workspace-box", str(tmp_path / "box"))

    doc = Document("cd work", 7)
    completions = list(completer.get_completions(doc, CompleteEvent()))
    names = [c.display_text for c in completions]
    assert "workspace-box" in names


def test_permission_error_safety(tmp_path: Path) -> None:
    """Permission errors during directory scans are handled silently without crashing."""
    context, completer = create_completer_context(tmp_path)

    with patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")):
        doc = Document("ls ", 3)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        # Must return empty generator without raising error
        assert completions == []


def test_context_specific_subcommands(tmp_path: Path) -> None:
    """Test help, command-info, alias, and history completions."""
    context, completer = create_completer_context(tmp_path)
    context.alias_manager.add_alias("sample-alias", "pwd")

    # help command names
    doc_help = Document("help pw", 7)
    comp_help = [c.text for c in completer.get_completions(doc_help, CompleteEvent())]
    assert "pwd" in comp_help

    # unalias alias names
    doc_unalias = Document("unalias samp", 12)
    comp_unalias = [c.text for c in completer.get_completions(doc_unalias, CompleteEvent())]
    assert "sample-alias" in comp_unalias

    # history clear subcommand
    doc_hist = Document("history cl", 10)
    comp_hist = [c.text for c in completer.get_completions(doc_hist, CompleteEvent())]
    assert "clear" in comp_hist


def test_process_and_processes_completions(tmp_path: Path) -> None:
    """Test process subcommands and processes --sort options completion."""
    context, completer = create_completer_context(tmp_path)

    # process subcommands: find, info, kill, list
    doc_proc = Document("process ", 8)
    subcmds = [c.text for c in completer.get_completions(doc_proc, CompleteEvent())]
    assert "find" in subcmds
    assert "info" in subcmds
    assert "kill" in subcmds
    assert "list" in subcmds

    # process kill --force flag
    doc_kill = Document("process kill 1234 --f", 21)
    kill_flags = [c.text for c in completer.get_completions(doc_kill, CompleteEvent())]
    assert "--force" in kill_flags

    # processes --sort options
    doc_sort = Document("processes --sort ", 17)
    sort_opts = [c.text for c in completer.get_completions(doc_sort, CompleteEvent())]
    assert "cpu" in sort_opts
    assert "memory" in sort_opts
    assert "name" in sort_opts
