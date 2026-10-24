"""Tests for project-aware service and commands."""
from __future__ import annotations

import io
from pathlib import Path
import stat
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.project import handle_project, register_project_aware_commands
from core.config_manager import ConfigManager
from core.executor import CommandExecutor
from core.parser import parse_command_line
from core.registry import CommandRegistry
from core.shell import ShellContext
from core.theme import ThemeManager
from services.project_service import (
    FILE_ATTRIBUTE_REPARSE_POINT,
    build_project_tree,
    detect_project_kinds,
    find_project_root,
    get_project_info,
    is_reparse_point_or_symlink,
    parse_dependency_entries,
    render_tree_lines,
    run_project_doctor_checks,
)


@pytest.fixture
def isolated_context(tmp_path: Path):
    """Create an isolated ShellContext."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = ConfigManager(base_dir=config_dir)
    registry = CommandRegistry()
    register_project_aware_commands(registry)

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


def test_project_root_detection_and_8_level_limit(tmp_path: Path):
    """Project root detection walks up at most 8 levels and stops at drive root."""
    # Create project root at level 0
    project_root = tmp_path / "my_project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text('[project]\nname = "my-proj"\n', encoding="utf-8")

    # Create nested directories up to 7 levels (total 7 levels below root)
    curr = project_root
    for i in range(7):
        curr = curr / f"sub_{i}"
        curr.mkdir()

    # From 7 levels deep, root should be found
    detected = find_project_root(curr)
    assert detected == project_root.resolve()

    # Create 9 levels deep (exceeding 8 levels)
    curr9 = curr / "sub_7" / "sub_8"
    curr9.mkdir(parents=True)
    # Beyond 8 levels from root, find_project_root will stop before reaching root
    detected_9 = find_project_root(curr9)
    assert detected_9 is None


def test_project_root_detection_markers(tmp_path: Path):
    """Detection recognizes all supported project markers."""
    markers = [
        ".git",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "package.json",
        "Pipfile",
        "environment.yml",
        "Dockerfile",
        "manage.py",
    ]
    for m in markers:
        d = tmp_path / f"proj_{m.replace('.', '_')}"
        d.mkdir()
        target = d / m
        if m == ".git":
            target.mkdir()
        else:
            target.write_text("# marker\n", encoding="utf-8")
        assert find_project_root(d) == d.resolve()


def test_detect_project_kinds(tmp_path: Path):
    """Detects python, ml, flask, fastapi, node, docker without executing code."""
    proj = tmp_path / "multi_stack"
    proj.mkdir()
    (proj / "package.json").write_text('{"name": "test"}', encoding="utf-8")
    (proj / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
    (proj / "requirements.txt").write_text(
        "numpy==1.24.0\n"
        "pandas>=2.0.0\n"
        "torch\n"
        "flask>=3.0.0\n"
        "fastapi\n",
        encoding="utf-8",
    )

    kinds = detect_project_kinds(proj)
    assert "python" in kinds
    assert "ml" in kinds
    assert "flask" in kinds
    assert "fastapi" in kinds
    assert "node" in kinds
    assert "docker" in kinds


def test_parse_dependencies_credential_redaction(tmp_path: Path):
    """Requirements and pyproject entries with credentials or URLs are never returned."""
    proj = tmp_path / "cred_proj"
    proj.mkdir()
    (proj / "requirements.txt").write_text(
        "requests==2.31.0\n"
        "git+https://user:token123@github.com/org/repo.git\n"
        "secret-pkg @ https://apikey:secretpass@private.pypi.org/simple\n"
        "rich>=13.0.0\n",
        encoding="utf-8",
    )

    deps = parse_dependency_entries(proj)
    assert "requests" in deps
    assert "rich" in deps
    for d in deps:
        assert "token123" not in d
        assert "secretpass" not in d
        assert "://" not in d
        assert "@" not in d


def test_project_tree_caps_depth_and_skip(tmp_path: Path):
    """Tree respects depth limit, skips excluded dirs, and orders directories first."""
    proj = tmp_path / "tree_proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    (proj / "node_modules").mkdir()
    (proj / "a_file.txt").write_text("hello", encoding="utf-8")
    sub = proj / "src"
    sub.mkdir()
    (sub / "main.py").write_text("print('hi')", encoding="utf-8")
    sub2 = sub / "utils"
    sub2.mkdir()
    (sub2 / "helper.py").write_text("pass", encoding="utf-8")

    # Depth 1: should only see src/ and a_file.txt, .git and node_modules skipped
    root_node, entries, hit_limit = build_project_tree(proj, depth=1, show_all=False)
    lines = render_tree_lines(root_node, is_plain=True)
    joined = "\n".join(lines)

    assert "src/" in joined
    assert "a_file.txt" in joined
    assert ".git [skipped]" in joined
    assert "node_modules [skipped]" in joined
    assert "helper.py" not in joined  # beyond depth 1

    # With show_all=True
    root_node_all, _, _ = build_project_tree(proj, depth=1, show_all=True)
    lines_all = render_tree_lines(root_node_all, is_plain=True)
    joined_all = "\n".join(lines_all)
    assert ".git/" in joined_all
    assert "node_modules/" in joined_all


def test_reparse_point_and_junction_detection(tmp_path: Path):
    """is_reparse_point_or_symlink detects symlinks and FILE_ATTRIBUTE_REPARSE_POINT."""
    # Test standard directory
    regular_dir = tmp_path / "regular"
    regular_dir.mkdir()
    assert not is_reparse_point_or_symlink(regular_dir)

    # Test symlink if allowed by OS
    link_path = tmp_path / "test_link"
    try:
        link_path.symlink_to(regular_dir, target_is_directory=True)
        assert is_reparse_point_or_symlink(link_path)
    except (OSError, NotImplementedError):
        pass  # Non-elevated symlinks on some Windows configurations

    # Test mocked FILE_ATTRIBUTE_REPARSE_POINT
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IFDIR
    mock_stat.st_file_attributes = FILE_ATTRIBUTE_REPARSE_POINT
    with patch.object(Path, "lstat", return_value=mock_stat):
        assert is_reparse_point_or_symlink(regular_dir)


def test_project_tree_refuses_drive_root_and_home(isolated_context, tmp_path: Path):
    """Refuses drive root or home directory as project tree target."""
    context, capture = isolated_context
    proj = tmp_path / "proj_for_tree"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[project]\nname = "tree-proj"\n', encoding="utf-8")
    context.current_dir = proj

    drive_root = Path("C:\\") if Path("C:\\").exists() else Path("/")
    res = handle_project(context, ["tree", str(drive_root)])
    assert not res.ok
    assert "Refusing to render drive root" in capture.getvalue()

    capture.truncate(0)
    capture.seek(0)
    home_dir = Path.home()
    res2 = handle_project(context, ["tree", str(home_dir)])
    assert not res2.ok
    assert "Refusing to render user home directory" in capture.getvalue()


def test_env_file_is_never_opened(isolated_context, tmp_path: Path):
    """Ensure .env files are never opened or read when running project env or doctor."""
    context, capture = isolated_context
    proj = tmp_path / "env_proj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[project]\nname = "env-proj"\n', encoding="utf-8")
    (proj / ".gitignore").write_text(".env\n.venv\n", encoding="utf-8")
    env_file = proj / ".env"
    env_file.write_text("DATABASE_PASSWORD=supersecret_pass123\n", encoding="utf-8")
    context.current_dir = proj

    original_open = open
    opened_files: list[str] = []

    def spy_open(*args, **kwargs):
        path_str = str(args[0])
        opened_files.append(path_str)
        if path_str.endswith(".env"):
            raise AssertionError(".env file was opened directly! This is strictly forbidden.")
        return original_open(*args, **kwargs)

    with patch("builtins.open", side_effect=spy_open):
        res = handle_project(context, ["env"])
        assert res.ok

        res_doc = handle_project(context, ["doctor"])
        assert res_doc.ok

    # Verify secret was never printed
    output = capture.getvalue()
    assert "supersecret_pass123" not in output
    assert ".env file found" in output


def test_project_doctor_checks_and_fix_commands(tmp_path: Path):
    """project doctor runs 10 checks and provides actionable plain-text fixes without modifying files."""
    proj = tmp_path / "incomplete_proj"
    proj.mkdir()
    (proj / "manage.py").write_text("# django\n", encoding="utf-8")

    checks = run_project_doctor_checks(proj)
    assert len(checks) == 10

    # Checks should produce recommendations
    check_names = {c.name: c for c in checks}
    assert check_names["Virtual environment"].status == "WARN"
    assert check_names["Virtual environment"].fix == "python -m venv .venv"
    assert check_names["Test suite folder"].status == "WARN"
    assert check_names["Test suite folder"].fix == "mkdir tests"
    assert check_names["Documentation README"].status == "WARN"
    assert check_names["Documentation README"].fix == "touch README.md"

    # Confirm nothing was modified or created
    assert not (proj / "tests").exists()
    assert not (proj / "README.md").exists()
    assert not (proj / ".venv").exists()


def test_no_project_detected_hint(isolated_context, tmp_path: Path):
    """When outside any project, reports 'No project detected here' with hint."""
    context, capture = isolated_context
    empty_dir = tmp_path / "empty_folder"
    empty_dir.mkdir()
    context.current_dir = empty_dir

    res = handle_project(context, ["info"])
    assert not res.ok
    assert "No project detected here" in capture.getvalue()
    assert res.hint is not None
    assert "cd" in res.hint or "create-project" in res.hint
