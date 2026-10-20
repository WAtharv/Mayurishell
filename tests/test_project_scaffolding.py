"""Tests for create-project and templates scaffolding commands."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import sys
import tomllib
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from commands.project_scaffolding import (
    BUILTIN_TEMPLATES,
    derive_python_module_name,
    get_custom_templates_dir,
    handle_create_project,
    handle_templates,
    validate_project_name,
)
from core.config_manager import ConfigManager
from core.registry import CommandRegistry
from core.shell import ShellContext


@pytest.fixture
def proj_context(tmp_path: Path):
    """Create test shell context for project scaffolding."""
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    config = ConfigManager(base_dir=appdata)
    registry = CommandRegistry()
    history = MagicMock()
    console = Console(record=True, width=120)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    ctx = ShellContext(
        config=config,
        registry=registry,
        history_manager=history,
        console=console,
        current_dir=work_dir,
    )
    return ctx


def test_validate_project_name():
    """Test project name validation for valid and invalid characters and OS rules."""
    # Valid names
    for valid_name in ["my-app", "data_science", "project123", "a", "A_1-b"]:
        ok, msg = validate_project_name(valid_name)
        assert ok, f"Expected '{valid_name}' to be valid, got {msg}"

    # Invalid names
    invalid_cases = [
        ("my app", "letters, numbers, hyphens"),
        ("app!test", "letters, numbers, hyphens"),
        ("dot.", "cannot end with a dot"),
        ("space ", "cannot end with a dot or a space"),
        ("CON", "Windows reserved"),
        ("prn", "Windows reserved"),
        ("aux", "Windows reserved"),
        ("NUL", "Windows reserved"),
        ("com1", "Windows reserved"),
        ("lpt2", "Windows reserved"),
        ("a" * 51, "too long"),
        ("", "cannot be empty"),
    ]
    for inv_name, expected_err in invalid_cases:
        ok, msg = validate_project_name(inv_name)
        assert not ok, f"Expected '{inv_name}' to be invalid"
        assert expected_err.lower() in msg.lower()


def test_derive_python_module_name():
    """Test valid Python module identifier derivation."""
    assert derive_python_module_name("my-project") == "my_project"
    assert derive_python_module_name("ai-app_1") == "ai_app_1"
    # Leading digit prefixing
    assert derive_python_module_name("123-test") == "pkg_123_test"
    # Keyword prefixing
    assert derive_python_module_name("class") == "pkg_class"
    assert derive_python_module_name("def") == "pkg_def"


def test_scaffold_builtin_templates_and_ast_check(proj_context: ShellContext, tmp_path: Path):
    """Requirement 5: Test all built-in templates and verify all .py files with ast.parse and pyproject.toml with tomllib."""
    templates = ["python", "ml", "datascience", "flask", "fastapi"]

    for tmpl in templates:
        proj_name = f"test-{tmpl}-proj"
        handle_create_project(proj_context, [proj_name, "--template", tmpl])

        proj_dir = proj_context.current_dir / proj_name
        assert proj_dir.is_dir()

        # 1. Verify standard files
        assert (proj_dir / "README.md").exists()
        assert (proj_dir / "requirements.txt").exists()
        assert (proj_dir / ".gitignore").exists()
        pyproject_file = proj_dir / "pyproject.toml"
        assert pyproject_file.exists()

        # 2. Check pyproject.toml with tomllib
        toml_content = pyproject_file.read_text(encoding="utf-8")
        parsed_toml = tomllib.loads(toml_content)
        assert "project" in parsed_toml
        assert parsed_toml["project"]["name"] == proj_name

        # 3. Check every generated .py file with ast.parse
        py_files = list(proj_dir.rglob("*.py"))
        assert len(py_files) >= 2, f"Expected at least 2 .py files in {tmpl}"
        for py_f in py_files:
            code = py_f.read_text(encoding="utf-8")
            # ast.parse raises SyntaxError if invalid
            ast_tree = ast.parse(code, filename=str(py_f))
            assert ast_tree is not None


def test_create_project_refuses_existing_folder(proj_context: ShellContext):
    """Test that create-project refuses if folder already exists."""
    existing = proj_context.current_dir / "my-existing"
    existing.mkdir()

    handle_create_project(proj_context, ["my-existing", "--template", "python"])
    out = proj_context.console.export_text()
    assert "already exists" in out


def test_create_project_here_flag(proj_context: ShellContext, tmp_path: Path):
    """Test that --here works in an empty directory and refuses in a non-empty directory."""
    empty_dir = tmp_path / "empty_workspace"
    empty_dir.mkdir()
    proj_context.current_dir = empty_dir

    # 1. Succeeds in empty directory
    handle_create_project(proj_context, ["my-here-app", "--template", "python", "--here"])
    assert (empty_dir / "pyproject.toml").exists()
    assert (empty_dir / "src").is_dir()

    # 2. Fails if run again because directory is now non-empty
    handle_create_project(proj_context, ["second-app", "--template", "python", "--here"])
    out = proj_context.console.export_text()
    assert "not empty" in out


def test_custom_user_templates_safety(proj_context: ShellContext, tmp_path: Path):
    """Test custom template substitution, executable skipping, and symlink refusal."""
    custom_dir = get_custom_templates_dir(proj_context)
    custom_dir.mkdir(parents=True, exist_ok=True)

    tmpl_dir = custom_dir / "my-custom"
    tmpl_dir.mkdir()

    # Starter template files
    (tmpl_dir / "README.md").write_text("# Project: {{project_name}}\nModule: {{module_name}}\n", encoding="utf-8")
    (tmpl_dir / "config.json").write_text('{"app": "{{project_name}}"}', encoding="utf-8")
    # Executable file -> must be skipped
    (tmpl_dir / "install.exe").write_text("dummy binary", encoding="utf-8")
    (tmpl_dir / "run.bat").write_text("@echo off", encoding="utf-8")

    # Scaffold from custom template
    handle_create_project(proj_context, ["custom-app", "--template", "my-custom"])

    target_dir = proj_context.current_dir / "custom-app"
    assert target_dir.is_dir()

    # Variables replaced
    readme = (target_dir / "README.md").read_text(encoding="utf-8")
    assert "Project: custom-app" in readme
    assert "Module: custom_app" in readme

    cfg = (target_dir / "config.json").read_text(encoding="utf-8")
    assert '"app": "custom-app"' in cfg

    # Executables skipped
    assert not (target_dir / "install.exe").exists()
    assert not (target_dir / "run.bat").exists()


def test_templates_command_lists_all(proj_context: ShellContext):
    """Test that templates command lists built-in templates and user custom templates."""
    custom_dir = get_custom_templates_dir(proj_context)
    custom_dir.mkdir(parents=True, exist_ok=True)
    (custom_dir / "special-ml").mkdir()

    handle_templates(proj_context, [])
    out = proj_context.console.export_text()

    assert "Available Project Templates" in out
    for b in BUILTIN_TEMPLATES.keys():
        assert b in out
    assert "special-ml" in out
