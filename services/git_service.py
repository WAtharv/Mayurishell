"""Read-only Git assistant service for MayuriShell.

Provides hardened, read-only inspection of Git repositories. Never runs any
modifying Git commands or shell pipelines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import html
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Sequence

from core.logging_config import get_logger

logger = get_logger()

MAX_GIT_OUTPUT_BYTES = 1024 * 1024  # 1 MB read cap
GIT_TIMEOUT_SECONDS = 10.0
MAX_STATUS_FILES = 50
MAX_DIFF_LINES = 200
MAX_PROMPT_HEAD_BYTES = 256
MAX_PROMPT_BRANCH_LEN = 30
MAX_WALK_LEVELS = 8

# Subcommands strictly allowed by the read-only assistant
ALLOWED_GIT_SUBCOMMANDS = {
    "status",
    "log",
    "diff",
    "branches",
    "summary",
}

# Standard Git installation paths on Windows
STANDARD_WINDOWS_GIT_PATHS = [
    Path(r"C:\Program Files\Git\cmd\git.exe"),
    Path(r"C:\Program Files\Git\bin\git.exe"),
    Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "Git" / "cmd" / "git.exe",
]


@dataclass
class GitRunResult:
    """Result of running a low-level git command."""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    git_missing: bool = False


# Cache for cheap prompt branch reads:
# directory_path -> (head_file_path, cached_mtime, cached_branch_name)
_PROMPT_GIT_CACHE: dict[Path, tuple[Path, float, str | None]] = {}


def strip_ansi_and_control(text: str) -> str:
    """Strip ANSI escape sequences and non-printable control characters."""
    # Remove ANSI escape sequences
    no_ansi = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    # Strip control characters (keep tab and newline)
    clean_chars = [
        c for c in no_ansi
        if c in ("\t", "\n", "\r") or (ord(c) >= 32 and ord(c) != 127)
    ]
    return "".join(clean_chars)


def redact_credentials(text: str) -> str:
    """Redact username/password credentials in URLs (e.g. user:pass@ -> ***@)."""
    # https://user:pass@github.com -> https://***@github.com
    pattern = r"(https?://)([^:@\s/]+):([^@\s/]+)@"
    redacted = re.sub(pattern, r"\1***@", text)
    # Fallback user:pass@ pattern
    pattern2 = r"([^:@\s/]+):([^@\s/]+)@"
    return re.sub(pattern2, r"***@", redacted)


def sanitize_git_output(text: str) -> str:
    """Combined output sanitization: strip escapes, strip control chars, redact credentials."""
    return redact_credentials(strip_ansi_and_control(text))


def find_git_executable() -> str | None:
    """Locate git.exe on PATH or standard installation locations."""
    which_git = shutil.which("git")
    if which_git:
        return which_git

    for std_path in STANDARD_WINDOWS_GIT_PATHS:
        try:
            if std_path.is_file():
                return str(std_path)
        except (OSError, PermissionError):
            continue

    return None


def run_hardened_git(
    subcommand_args: list[str],
    cwd: Path,
    timeout: float = GIT_TIMEOUT_SECONDS,
) -> GitRunResult:
    """Execute Git using a hardened argument list and isolated environment.
    
    Hardening:
    - shell=False
    - stdin closed (DEVNULL)
    - output capped at 1 MB
    - UTF-8 with errors='replace'
    - always prepends: --no-pager, -c core.quotepath=false, -c core.fsmonitor=false,
      -c core.pager=cat, --no-optional-locks
    - env: GIT_TERMINAL_PROMPT=0, GIT_OPTIONAL_LOCKS=0, LC_ALL=C
    - strips all inherited GIT_* override variables
    """
    git_bin = find_git_executable()
    if not git_bin:
        return GitRunResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr="Git executable not found on PATH or standard install paths.",
            git_missing=True,
        )

    # Base top-level hardening arguments
    base_args = [
        git_bin,
        "--no-pager",
        "-c", "core.quotepath=false",
        "-c", "core.fsmonitor=false",
        "-c", "core.pager=cat",
        "--no-optional-locks",
    ]

    # Additional hardening flags for diff and log (must follow subcommand)
    first_sub = subcommand_args[0] if subcommand_args else ""
    sub_rest = subcommand_args[1:] if len(subcommand_args) > 1 else []
    sub_flags: list[str] = []
    if first_sub in ("diff", "log"):
        sub_flags.extend(["--no-ext-diff", "--no-textconv", "--no-color"])

    if first_sub:
        full_cmd = base_args + [first_sub] + sub_flags + sub_rest
    else:
        full_cmd = base_args + subcommand_args

    # Clean isolated environment
    clean_env = os.environ.copy()
    # Remove all inherited GIT_* override variables first
    for k in list(clean_env.keys()):
        if k.upper().startswith("GIT_"):
            del clean_env[k]

    # Set required isolated runtime env vars
    clean_env["GIT_TERMINAL_PROMPT"] = "0"
    clean_env["GIT_OPTIONAL_LOCKS"] = "0"
    clean_env["LC_ALL"] = "C"

    try:
        proc = subprocess.Popen(
            full_cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=clean_env,
        )

        try:
            raw_out, raw_err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=2.0)
            except Exception:
                pass
            return GitRunResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr="Git command timed out after 10 seconds.",
                timed_out=True,
            )

        # Cap output reads at 1 MB
        capped_out = raw_out[:MAX_GIT_OUTPUT_BYTES]
        capped_err = raw_err[:MAX_GIT_OUTPUT_BYTES]

        out_str = sanitize_git_output(capped_out.decode("utf-8", errors="replace"))
        err_str = sanitize_git_output(capped_err.decode("utf-8", errors="replace"))

        return GitRunResult(
            success=(proc.returncode == 0),
            returncode=proc.returncode,
            stdout=out_str,
            stderr=err_str,
        )

    except Exception as exc:
        logger.warning("Failed to invoke git process: %s", exc)
        return GitRunResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=sanitize_git_output(str(exc)),
        )


def classify_git_error(res: GitRunResult) -> tuple[str, str]:
    """Classify common Git error messages and provide helpful, safe fix instructions."""
    if res.git_missing:
        return (
            "Git is not installed or not found on system PATH.",
            "Install Git for Windows from https://git-scm.com/download/win and restart your shell.",
        )
    if res.timed_out:
        return (
            "Git command timed out after 10 seconds.",
            "The repository may be very large or waiting on background operations.",
        )

    err = res.stderr.lower()
    out = res.stdout.lower()
    combined = f"{err}\n{out}"

    if "not a git repository" in combined:
        return (
            "Not a git repository (or any of the parent directories).",
            "To initialize Git tracking in this folder, run 'git init' in your terminal.",
        )
    if "detected dubious ownership in repository" in combined or "safe.directory" in combined:
        return (
            "Git refused operation due to dubious directory ownership.",
            "To mark this folder safe in Git, run 'git config --global --add safe.directory <path>' in your terminal.",
        )
    if "does not have any commits yet" in combined or "your current branch" in combined and "does not have any commits" in combined:
        return (
            "No commits yet on this branch.",
            "Make your first commit in your normal terminal with 'git add .' and 'git commit -m \"initial commit\"'.",
        )
    if "index.lock" in combined:
        return (
            "Another git process may be running, or a crashed process left '.git/index.lock'.",
            "Check running processes. If no git process is active, delete '.git/index.lock' manually in your terminal.",
        )
    if "unmerged paths" in combined or "conflict" in combined:
        return (
            "Merge conflicts detected in this repository.",
            "Resolve conflicted files in your editor, then complete the merge in your normal terminal.",
        )
    if "pathspec" in combined and "did not match any" in combined:
        return (
            "The specified path does not match any tracked or existing files in this repository.",
            "Verify the file path relative to the current directory.",
        )

    clean_err = res.stderr.strip() or f"Git exited with status {res.returncode}"
    return (clean_err, "Run the command in your normal terminal for detailed output.")


# ============================================================================
# HIGH-LEVEL SUBCOMMAND PARSERS & RUNNERS
# ============================================================================

@dataclass
class GitStatusSummary:
    branch: str
    ahead: int = 0
    behind: int = 0
    staged: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    conflicted: list[str] = field(default_factory=list)
    total_files: int = 0


def get_git_status(cwd: Path) -> tuple[bool, GitStatusSummary | None, str, str]:
    """Parse git status --porcelain=v2 --branch --ignore-submodules=all.
    
    Returns (success, summary_or_None, error_msg, fix_hint).
    """
    res = run_hardened_git(["status", "--porcelain=v2", "--branch", "--ignore-submodules=all"], cwd)
    if not res.success:
        err_msg, fix_hint = classify_git_error(res)
        return False, None, err_msg, fix_hint

    summary = GitStatusSummary(branch="HEAD")
    file_count = 0

    for line in res.stdout.splitlines():
        if line.startswith("# branch.head "):
            summary.branch = line[len("# branch.head "):].strip()
        elif line.startswith("# branch.ab "):
            parts = line[len("# branch.ab "):].split()
            for p in parts:
                if p.startswith("+"):
                    try:
                        summary.ahead = int(p[1:])
                    except ValueError:
                        pass
                elif p.startswith("-"):
                    try:
                        summary.behind = int(p[1:])
                    except ValueError:
                        pass
        elif line.startswith("1 ") or line.startswith("2 "):
            # 1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>
            # 2 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <X><score> <path><sep><origPath>
            parts = line.split()
            if len(parts) >= 9:
                xy = parts[1]
                path_str = parts[-1]
                file_count += 1
                if xy[0] != ".":
                    summary.staged.append(path_str)
                if xy[1] != ".":
                    summary.modified.append(path_str)
        elif line.startswith("u "):
            # Unmerged conflict
            parts = line.split()
            if len(parts) >= 11:
                summary.conflicted.append(parts[-1])
                file_count += 1
        elif line.startswith("? "):
            # Untracked file
            path_str = line[2:].strip()
            summary.untracked.append(path_str)
            file_count += 1

    summary.total_files = file_count
    return True, summary, "", ""


def get_git_log(cwd: Path, count: int = 10) -> tuple[bool, list[dict[str, str]], str, str]:
    """Fetch recent git log entries with fixed format (hash, date, author name, subject)."""
    valid_count = max(1, min(count, 50))
    args = [
        "log",
        f"-n{valid_count}",
        "--format=%h%x09%ad%x09%an%x09%s",
        "--date=short",
    ]
    res = run_hardened_git(args, cwd)
    if not res.success:
        err_msg, fix_hint = classify_git_error(res)
        return False, [], err_msg, fix_hint

    entries: list[dict[str, str]] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            entries.append({
                "hash": parts[0].strip(),
                "date": parts[1].strip(),
                "author": parts[2].strip(),
                "subject": parts[3].strip(),
            })

    return True, entries, "", ""


def get_git_diff(
    cwd: Path,
    file_path: str | None = None,
    staged: bool = False,
) -> tuple[bool, str, bool, str, str]:
    """Execute git diff (capped at 200 lines).
    
    Returns (success, diff_text, was_truncated, error_msg, fix_hint).
    """
    args = ["diff", "--ignore-submodules=all"]
    if staged:
        args.append("--staged")

    if not file_path:
        # Default with no path shows stat summary
        args.append("--stat")
    else:
        # User specified a file path
        # Validate that path does not start with dash
        if file_path.startswith("-"):
            return False, "", False, "Invalid path: file paths must not start with '-'", "Specify a valid path."
        # Resolve path inside repository
        target_file = (cwd / file_path).resolve()
        repo_root = find_git_repo_root(cwd)
        if repo_root:
            try:
                target_file.relative_to(repo_root)
            except ValueError:
                return False, "", False, "Path must reside inside the repository.", "Specify a path within the repo."
        args.extend(["--", file_path])

    res = run_hardened_git(args, cwd)
    if not res.success:
        err_msg, fix_hint = classify_git_error(res)
        return False, "", False, err_msg, fix_hint

    lines = res.stdout.splitlines()
    truncated = False
    if len(lines) > MAX_DIFF_LINES:
        truncated = True
        lines = lines[:MAX_DIFF_LINES]

    return True, "\n".join(lines), truncated, "", ""


def get_git_branches(cwd: Path) -> tuple[bool, list[dict[str, Any]], str, str]:
    """List local branches with active branch marked and short upstream info."""
    res = run_hardened_git(["branch", "-vv", "--no-color"], cwd)
    if not res.success:
        err_msg, fix_hint = classify_git_error(res)
        return False, [], err_msg, fix_hint

    branches: list[dict[str, Any]] = []
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        is_current = line.startswith("*")
        content = line[2:].strip()
        # Parse name and upstream e.g. "main  1a2b3c4 [origin/main] commit subject"
        parts = content.split()
        if not parts:
            continue
        branch_name = parts[0]
        upstream_info = ""
        m = re.search(r"\[([^\]]+)\]", content)
        if m:
            upstream_info = m.group(1)

        branches.append({
            "name": branch_name,
            "current": is_current,
            "upstream": upstream_info,
        })

    return True, branches, "", ""


def get_git_summary(cwd: Path) -> tuple[bool, dict[str, Any] | None, str, str]:
    """Collect repository overview: branch, status counts, last commit, and safe next suggestions."""
    ok_status, status, err, hint = get_git_status(cwd)
    if not ok_status or status is None:
        return False, None, err, hint

    # Get last commit
    res_last = run_hardened_git(["log", "-1", "--format=%h%x09%cr%x09%s"], cwd)
    last_commit: dict[str, str] | None = None
    if res_last.success and res_last.stdout.strip():
        parts = res_last.stdout.strip().split("\t")
        if len(parts) >= 3:
            last_commit = {
                "hash": parts[0],
                "relative_date": parts[1],
                "subject": parts[2],
            }

    # Safe next suggestions (read-only only, never write commands)
    suggestions: list[str] = []
    if status.conflicted:
        suggestions.append("Inspect conflicts in your editor")
    if status.modified:
        suggestions.append("git diff")
    if status.staged:
        suggestions.append("git diff --staged")
    if status.untracked:
        suggestions.append("git status")
    if not suggestions:
        suggestions.append("git log")
        suggestions.append("ls")

    summary_data = {
        "branch": status.branch,
        "ahead": status.ahead,
        "behind": status.behind,
        "modified_count": len(status.modified),
        "staged_count": len(status.staged),
        "untracked_count": len(status.untracked),
        "conflict_count": len(status.conflicted),
        "last_commit": last_commit,
        "suggestions": suggestions,
    }

    return True, summary_data, "", ""


# ============================================================================
# PROMPT BRANCH (NO SUBPROCESS)
# ============================================================================

def find_git_repo_root(start_dir: Path) -> Path | None:
    """Find .git directory or worktree file walking up at most 8 levels."""
    try:
        curr = start_dir.resolve()
    except Exception:
        curr = start_dir

    for _ in range(MAX_WALK_LEVELS + 1):
        try:
            git_entry = curr / ".git"
            if git_entry.exists():
                return curr
        except (OSError, PermissionError):
            pass

        if len(curr.parts) <= 1 or curr.parent == curr:
            break
        curr = curr.parent

    return None


def get_prompt_git_branch(current_dir: Path) -> str | None:
    """Cheap, non-blocking read of .git/HEAD with NO subprocess.
    
    Supports:
    - Standard .git/HEAD directory
    - Worktree/submodule .git file containing "gitdir: <path>"
    - Detached HEAD (extracts 7-character commit hash)
    - Caches per directory, invalidating when the HEAD file's mtime changes
    - HTML-escapes branch name for prompt_toolkit (html.escape)
    - Strips control characters and caps at 30 characters
    - Reads at most 256 bytes of HEAD file
    """
    repo_root = find_git_repo_root(current_dir)
    if not repo_root:
        return None

    git_target = repo_root / ".git"
    head_file: Path | None = None

    try:
        if git_target.is_dir():
            head_file = git_target / "HEAD"
        elif git_target.is_file():
            # Worktree or submodule: read gitdir: <path>
            try:
                with open(git_target, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(MAX_PROMPT_HEAD_BYTES).strip()
                if content.startswith("gitdir:"):
                    raw_gitdir = content[len("gitdir:"):].strip()
                    resolved_gitdir = (repo_root / raw_gitdir).resolve()
                    if resolved_gitdir.is_dir():
                        head_file = resolved_gitdir / "HEAD"
            except Exception:
                return None
    except Exception:
        return None

    if not head_file or not head_file.is_file():
        return None

    # Check cache and mtime invalidation
    try:
        curr_mtime = head_file.stat().st_mtime
    except Exception:
        return None

    cached = _PROMPT_GIT_CACHE.get(current_dir)
    if cached is not None:
        c_head, c_mtime, c_branch = cached
        if c_head == head_file and c_mtime == curr_mtime:
            return c_branch

    # Read at most 256 bytes of HEAD
    branch_name: str | None = None
    try:
        with open(head_file, "r", encoding="utf-8", errors="replace") as f:
            raw_head = f.read(MAX_PROMPT_HEAD_BYTES).strip()

        if raw_head.startswith("ref: refs/heads/"):
            raw_branch = raw_head[len("ref: refs/heads/"):].strip()
            branch_name = raw_branch
        elif re.match(r"^[0-9a-fA-F]{40}$", raw_head):
            # Detached HEAD
            branch_name = raw_head[:7]
        elif raw_head:
            # Fallback for short commit hash or symbolic ref
            branch_name = raw_head.splitlines()[0][:7]
    except Exception:
        branch_name = None

    # Process and sanitize branch name if found
    if branch_name:
        # Strip control characters
        clean_name = strip_ansi_and_control(branch_name).strip()
        # Cap at 30 characters
        if len(clean_name) > MAX_PROMPT_BRANCH_LEN:
            clean_name = clean_name[:MAX_PROMPT_BRANCH_LEN - 3] + "..."
        # HTML-escape for prompt_toolkit
        branch_name = html.escape(clean_name)

    # Update cache
    _PROMPT_GIT_CACHE[current_dir] = (head_file, curr_mtime, branch_name)
    return branch_name
