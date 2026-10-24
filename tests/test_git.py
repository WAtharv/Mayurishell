"""Tests for read-only Git assistant service and commands."""
from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.appearance import register_appearance_commands
from commands.git import handle_git, register_git_commands
from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from core.shell import MayuriShell, ShellContext
from core.theme import ThemeManager
from services.git_service import (
    ALLOWED_GIT_SUBCOMMANDS,
    _PROMPT_GIT_CACHE,
    classify_git_error,
    find_git_executable,
    get_git_branches,
    get_git_diff,
    get_git_log,
    get_git_status,
    get_git_summary,
    get_prompt_git_branch,
    redact_credentials,
    run_hardened_git,
    strip_ansi_and_control,
)


@pytest.fixture
def isolated_context(tmp_path: Path):
    """Create an isolated ShellContext."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = ConfigManager(base_dir=config_dir)
    registry = CommandRegistry()
    register_git_commands(registry)
    register_appearance_commands(registry)

    capture = io.StringIO()
    console = Console(file=capture, force_terminal=False, color_system=None)
    theme_mgr = ThemeManager(config, console=console)

    context = ShellContext(
        config=config,
        registry=registry,
        history_manager=MagicMock(),
        alias_manager=MagicMock(),
        console=console,
        theme_manager=theme_mgr,
    )
    context.current_dir = tmp_path
    context.is_interactive = False
    return context, capture


def test_git_write_subcommands_are_refused(isolated_context):
    """All modifying git subcommands are rejected with read-only notice and fail result."""
    context, capture = isolated_context
    forbidden_subcommands = [
        "commit",
        "push",
        "pull",
        "add",
        "reset",
        "checkout",
        "switch",
        "restore",
        "clean",
        "stash",
        "rebase",
        "merge",
        "rm",
        "config",
        "remote",
        "tag",
        "cherry-pick",
        "fetch",
        "init",
        "clone",
    ]

    for subcmd in forbidden_subcommands:
        capture.truncate(0)
        capture.seek(0)
        res = handle_git(context, [subcmd])
        assert not res.ok, f"Expected {subcmd} to fail"
        assert res.message == "MayuriShell's Git assistant is read-only. Run this in your normal terminal."
        assert "read-only" in capture.getvalue().lower()


def test_exact_git_arguments_and_isolated_environment(tmp_path: Path):
    """Hardened runner sets shell=False, hardening flags, closed stdin, and stripped GIT_* env."""
    captured_args = None
    captured_env = None
    captured_stdin = None
    captured_shell = None

    class DummyProc:
        returncode = 0
        def communicate(self, timeout=None):
            return b"dummy stdout", b""

    def mock_popen(args, cwd=None, stdin=None, stdout=None, stderr=None, shell=None, env=None):
        nonlocal captured_args, captured_env, captured_stdin, captured_shell
        captured_args = args
        captured_env = env
        captured_stdin = stdin
        captured_shell = shell
        return DummyProc()

    # Set some GIT_* overrides in current environment to ensure they are stripped
    with patch.dict(os.environ, {"GIT_DIR": "bad_dir", "GIT_CONFIG_KEY": "val", "GIT_SSH_COMMAND": "ssh"}):
        with patch("services.git_service.find_git_executable", return_value="git.exe"):
            with patch("subprocess.Popen", side_effect=mock_popen):
                res = run_hardened_git(["status", "--porcelain=v2"], tmp_path)

    assert res.success
    assert captured_shell is False
    assert captured_stdin == subprocess.DEVNULL
    assert captured_args is not None
    # Hardening flags present
    assert "--no-pager" in captured_args
    assert "core.quotepath=false" in captured_args
    assert "core.fsmonitor=false" in captured_args
    assert "core.pager=cat" in captured_args
    assert "--no-optional-locks" in captured_args
    assert "status" in captured_args
    assert "--porcelain=v2" in captured_args

    # Environment isolation
    assert captured_env["GIT_TERMINAL_PROMPT"] == "0"
    assert captured_env["GIT_OPTIONAL_LOCKS"] == "0"
    assert captured_env["LC_ALL"] == "C"
    assert "GIT_DIR" not in captured_env
    assert "GIT_CONFIG_KEY" not in captured_env
    assert "GIT_SSH_COMMAND" not in captured_env


def test_diff_and_log_hardening_flags(tmp_path: Path):
    """diff and log receive --no-ext-diff, --no-textconv, --no-color."""
    captured_args = []

    class DummyProc:
        returncode = 0
        def communicate(self, timeout=None):
            return b"", b""

    def mock_popen(args, **kwargs):
        captured_args.append(args)
        return DummyProc()

    with patch("services.git_service.find_git_executable", return_value="git.exe"):
        with patch("subprocess.Popen", side_effect=mock_popen):
            run_hardened_git(["diff"], tmp_path)
            run_hardened_git(["log", "-n5"], tmp_path)

    for args in captured_args:
        assert "--no-ext-diff" in args
        assert "--no-textconv" in args
        assert "--no-color" in args


def test_git_diff_path_validation_and_dash_prevention(isolated_context, tmp_path: Path):
    """git diff rejects paths starting with dash and validates path inside repo."""
    context, capture = isolated_context
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    context.current_dir = repo_dir

    # Refuse flag starting with dash as path
    res = handle_git(context, ["diff", "-bad-flag"])
    assert not res.ok

    # Refuse path outside repo
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("hello", encoding="utf-8")
    res_outside = handle_git(context, ["diff", str(outside_file)])
    assert not res_outside.ok
    assert "Path must reside inside the repository" in capture.getvalue()


def test_git_log_count_limits(isolated_context):
    """git log validates -n count to range 1..50."""
    context, capture = isolated_context

    # Over 50
    res_high = handle_git(context, ["log", "-n", "100"])
    assert not res_high.ok
    assert "Allowed range is 1 to 50" in res_high.message

    # Zero or negative
    res_zero = handle_git(context, ["log", "-n", "0"])
    assert not res_zero.ok

    # Invalid string
    res_str = handle_git(context, ["log", "-n", "abc"])
    assert not res_str.ok


def test_sanitization_ansi_control_and_credentials():
    """Output sanitization strips ANSI colors, control characters, and redacts URL credentials."""
    raw_dirty = "\x1b[31;1mError\x1b[0m\x07: https://myuser:secret_token123@github.com/org/repo.git\x00"
    clean = strip_ansi_and_control(raw_dirty)
    assert "\x1b[31;1m" not in clean
    assert "\x07" not in clean
    assert "\x00" not in clean

    redacted = redact_credentials(clean)
    assert "secret_token123" not in redacted
    assert "https://***@github.com" in redacted


def test_status_and_diff_output_capping(isolated_context, tmp_path: Path):
    """git status caps at 50 files and git diff caps at 200 lines."""
    context, capture = isolated_context
    repo = tmp_path / "capped_repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    context.current_dir = repo

    # Mock git status with 60 files
    status_lines = ["# branch.head main"]
    for i in range(60):
        status_lines.append(f"? file_{i}.txt")
    mock_status_out = "\n".join(status_lines)

    with patch("services.git_service.run_hardened_git") as mock_run:
        mock_run.return_value = MagicMock(success=True, stdout=mock_status_out, stderr="")
        res = handle_git(context, ["status"])
        assert res.ok
        assert "... and 10 more files (capped at 50)" in capture.getvalue()

    capture.truncate(0)
    capture.seek(0)

    # Mock git diff with 250 lines
    diff_lines = [f"+ line {i}" for i in range(250)]
    mock_diff_out = "\n".join(diff_lines)

    with patch("services.git_service.run_hardened_git") as mock_run:
        mock_run.return_value = MagicMock(success=True, stdout=mock_diff_out, stderr="")
        res2 = handle_git(context, ["diff", "test.py"])
        assert res2.ok
        assert "Diff truncated to 200 lines" in capture.getvalue()


def test_classify_git_errors():
    """Classifies repository errors into clear, friendly guidance without running destructive actions."""
    from services.git_service import GitRunResult

    # Not a git repo
    res_not_repo = GitRunResult(success=False, returncode=128, stdout="", stderr="fatal: not a git repository (or any of the parent directories): .git")
    err, fix = classify_git_error(res_not_repo)
    assert "Not a git repository" in err
    assert "git init" in fix

    # Dubious ownership
    res_dubious = GitRunResult(success=False, returncode=128, stdout="", stderr="fatal: detected dubious ownership in repository at 'C:/repo'")
    err_dub, fix_dub = classify_git_error(res_dubious)
    assert "dubious directory ownership" in err_dub
    assert "safe.directory" in fix_dub

    # index.lock
    res_lock = GitRunResult(success=False, returncode=128, stdout="", stderr="fatal: Unable to create '.../.git/index.lock': File exists.")
    err_lock, fix_lock = classify_git_error(res_lock)
    assert "index.lock" in err_lock


def test_prompt_branch_no_subprocess_and_html_escaping(tmp_path: Path):
    """Prompt branch reader reads .git/HEAD cheaply with NO subprocess and HTML-escapes branch name."""
    repo = tmp_path / "prompt_repo"
    repo.mkdir()
    git_dir = repo / ".git"
    git_dir.mkdir()

    # Normal branch with special HTML characters: feat<1>&2
    (git_dir / "HEAD").write_text("ref: refs/heads/feat<1>&2\n", encoding="utf-8")

    # Invalidate cache for test directory
    _PROMPT_GIT_CACHE.clear()

    # Strictly assert that subprocess.Popen and subprocess.run are NOT called
    with patch("subprocess.Popen", side_effect=AssertionError("Subprocess called for prompt!")):
        with patch("subprocess.run", side_effect=AssertionError("Subprocess called for prompt!")):
            branch = get_prompt_git_branch(repo)

    assert branch == "feat&lt;1&gt;&amp;2"

    # Test detached HEAD (40-char SHA -> 7-char hash)
    (git_dir / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8")
    # Cache invalidation via mtime
    os.utime(str(git_dir / "HEAD"), (time_now := 2000000000, time_now))
    branch_detached = get_prompt_git_branch(repo)
    assert branch_detached == "0123456"

    # Test worktree gitdir file
    wt_repo = tmp_path / "worktree_dir"
    wt_repo.mkdir()
    actual_gitdir = tmp_path / "actual_gitdir"
    actual_gitdir.mkdir()
    (actual_gitdir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (wt_repo / ".git").write_text(f"gitdir: {actual_gitdir.as_posix()}\n", encoding="utf-8")

    branch_wt = get_prompt_git_branch(wt_repo)
    assert branch_wt == "main"


def test_prompt_branch_in_shell_prompt_and_toggle(isolated_context, tmp_path: Path):
    """Shell prompt displays (branch) and 'prompt git off' toggles it."""
    context, capture = isolated_context
    repo = tmp_path / "shell_repo"
    repo.mkdir()
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    context.current_dir = repo

    shell = MayuriShell(
        context.config,
        context.registry,
        context.history_manager,
        console=context.console,
        current_dir=context.current_dir,
    )
    prompt_html = shell.get_prompt_text()
    assert "(main)" in prompt_html.value

    # Turn off prompt git
    from commands.appearance import handle_prompt
    res_off = handle_prompt(context, ["git", "off"])
    assert res_off.ok
    assert context.config.get_prompt_git_enabled() is False

    # Check prompt again: branch should be gone
    prompt_html_off = shell.get_prompt_text()
    assert "(main)" not in prompt_html_off.value

    # Turn back on
    res_on = handle_prompt(context, ["git", "on"])
    assert res_on.ok
    assert context.config.get_prompt_git_enabled() is True
    prompt_html_on = shell.get_prompt_text()
    assert "(main)" in prompt_html_on.value


@pytest.mark.skipif(shutil.which("git") is None, reason="Git executable not available on PATH")
def test_real_git_integration_in_temp_repo(isolated_context, tmp_path: Path):
    """Live integration test against a temporary repository under tmp_path.
    
    Never touches any real user repositories.
    """
    context, capture = isolated_context
    temp_repo = tmp_path / "live_git_repo"
    temp_repo.mkdir()
    context.current_dir = temp_repo

    # Set up temp repo with safe dummy config for author only
    safe_env = os.environ.copy()
    safe_env["GIT_CONFIG_GLOBAL"] = ""
    safe_env["GIT_CONFIG_SYSTEM"] = ""

    # Initialize temp repo
    subprocess.run(["git", "init"], cwd=str(temp_repo), check=True, capture_output=True, env=safe_env)
    test_file = temp_repo / "test_file.txt"
    test_file.write_text("initial content\n", encoding="utf-8")
    subprocess.run(["git", "add", "test_file.txt"], cwd=str(temp_repo), check=True, capture_output=True, env=safe_env)
    subprocess.run(
        ["git", "-c", "user.name=MayuriTester", "-c", "user.email=tester@example.com", "commit", "-m", "first commit"],
        cwd=str(temp_repo),
        check=True,
        capture_output=True,
        env=safe_env,
    )

    # Test git status
    res_status = handle_git(context, ["status"])
    assert res_status.ok
    assert "Nothing to commit, working tree clean" in capture.getvalue()

    # Modify file and test git diff
    capture.truncate(0)
    capture.seek(0)
    test_file.write_text("modified content\n", encoding="utf-8")
    res_diff = handle_git(context, ["diff"])
    assert res_diff.ok

    # Test git log
    capture.truncate(0)
    capture.seek(0)
    res_log = handle_git(context, ["log", "-n", "5"])
    assert res_log.ok
    assert "first commit" in capture.getvalue()
    assert "tester@example.com" not in capture.getvalue()  # No emails printed

    # Test git summary
    capture.truncate(0)
    capture.seek(0)
    res_summary = handle_git(context, ["summary"])
    assert res_summary.ok
    assert "Working Tree:" in capture.getvalue()
    assert "What next:" in capture.getvalue()
