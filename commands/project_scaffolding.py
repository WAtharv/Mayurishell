"""Project scaffolding command: create-project, templates."""
from __future__ import annotations

import ast
import keyword
import os
from pathlib import Path
import re
import sys
from typing import Any

from rich.markup import escape
from rich.table import Table

from core.executor import CommandResult
from core.logging_config import get_logger
from core.registry import ArgumentRules, CommandInfo, CommandRegistry
from services.file_service import EXECUTABLE_EXTENSIONS, format_bytes

logger = get_logger()

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

BUILTIN_TEMPLATES: dict[str, str] = {
    "python": "Standard modern Python package with src layout and pytest",
    "ml": "Machine Learning project with data, models, notebooks, and starter model",
    "datascience": "Data Science project with raw/processed data, analysis modules, and notebooks",
    "flask": "Flask web application starter with app factory, blueprints, and templates",
    "fastapi": "FastAPI REST API application with health endpoints and ASGI setup",
}

MAX_CUSTOM_TEMPLATE_FILES = 500
MAX_CUSTOM_TEMPLATE_SIZE = 5 * 1024 * 1024  # 5 MB


def get_custom_templates_dir(context: Any) -> Path:
    """Return path to user custom templates in appdata directory."""
    return context.config.base_dir / "templates"


def validate_project_name(name: str) -> tuple[bool, str]:
    """Validate project directory name against security and OS rules."""
    if not name:
        return False, "Project name cannot be empty."

    if name.endswith(".") or name.endswith(" "):
        return False, "Project name cannot end with a dot or a space."

    clean = name.strip()
    if not clean:
        return False, "Project name cannot be empty."

    if len(clean) > 50:
        return False, f"Project name is too long ({len(clean)} characters). Maximum is 50 characters."

    # Windows reserved device names
    stem = clean.split(".")[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        return False, f"'{name}' is a Windows reserved device name and cannot be used."

    # Allowed characters: letters, numbers, hyphen, underscore
    if not re.match(r"^[a-zA-Z0-9_-]+$", clean):
        return False, "Project name may only contain letters, numbers, hyphens, and underscores."

    return True, ""


def derive_python_module_name(project_name: str) -> str:
    """Derive a clean and valid Python package identifier from project name."""
    # Replace hyphens with underscores
    mod_name = project_name.replace("-", "_").lower()

    # Prepend 'pkg_' if starts with a digit
    if mod_name and mod_name[0].isdigit():
        mod_name = f"pkg_{mod_name}"

    # If it is a keyword or not an identifier, prefix with 'pkg_'
    if not mod_name.isidentifier() or keyword.iskeyword(mod_name):
        mod_name = f"pkg_{mod_name}"

    return mod_name


STANDARD_GITIGNORE = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Distribution / packaging
dist/
build/
*.egg-info/
.eggs/

# Environments
.venv/
env/
venv/
ENV/

# IDE and Editor
.idea/
.vscode/
*.swp
*.swo

# Testing and coverage
.pytest_cache/
.coverage
htmlcov/

# Environment variables
.env
.env.local
"""


def generate_python_template(project_dir: Path, proj_name: str, mod_name: str) -> None:
    """Generate standard Python package starter files."""
    src_pkg = project_dir / "src" / mod_name
    src_pkg.mkdir(parents=True, exist_ok=True)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # README.md
    (project_dir / "README.md").write_text(
        f"# {proj_name}\n\nA modern Python package created with MayuriShell.\n\n"
        f"## Development\n\n```bash\npython -m venv .venv\n"
        f".venv\\Scripts\\activate\npip install -r requirements.txt\npytest\n```\n",
        encoding="utf-8",
    )

    # requirements.txt
    (project_dir / "requirements.txt").write_text("pytest>=8.0.0\n", encoding="utf-8")

    # .gitignore
    (project_dir / ".gitignore").write_text(STANDARD_GITIGNORE, encoding="utf-8")

    # pyproject.toml
    pyproject = f"""[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{proj_name}"
version = "0.1.0"
description = "A Python project created with MayuriShell"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    (project_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    # src/
    (src_pkg / "__init__.py").write_text(
        f'"""{proj_name} package."""\n\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (src_pkg / "core.py").write_text(
        f'"""Core functionality for {proj_name}."""\nfrom __future__ import annotations\n\n\n'
        f'def hello(name: str = "world") -> str:\n'
        f'    """Return a friendly greeting."""\n'
        f'    return f"Hello, {{name}}!"\n',
        encoding="utf-8",
    )

    # tests/
    (tests_dir / "__init__.py").write_text(f'"""Tests for {proj_name}."""\n', encoding="utf-8")
    (tests_dir / "test_core.py").write_text(
        f'"""Unit tests for {proj_name} core module."""\n'
        f'from {mod_name}.core import hello\n\n\n'
        f'def test_hello() -> None:\n'
        f'    assert hello("Mayuri") == "Hello, Mayuri!"\n'
        f'    assert hello() == "Hello, world!"\n',
        encoding="utf-8",
    )


def generate_ml_template(project_dir: Path, proj_name: str, mod_name: str) -> None:
    """Generate Machine Learning starter files."""
    src_pkg = project_dir / "src" / mod_name
    src_pkg.mkdir(parents=True, exist_ok=True)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "data").mkdir(parents=True, exist_ok=True)
    (project_dir / "models").mkdir(parents=True, exist_ok=True)
    (project_dir / "notebooks").mkdir(parents=True, exist_ok=True)

    (project_dir / "data" / ".gitkeep").write_text("", encoding="utf-8")
    (project_dir / "models" / ".gitkeep").write_text("", encoding="utf-8")
    (project_dir / "notebooks" / "README.md").write_text("# Notebooks\n\nPlace exploratory Jupyter notebooks here.\n", encoding="utf-8")

    (project_dir / "README.md").write_text(f"# {proj_name}\n\nMachine learning project created with MayuriShell.\n", encoding="utf-8")
    (project_dir / "requirements.txt").write_text(
        "numpy>=1.26.0\npandas>=2.2.0\nscikit-learn>=1.4.0\nmatplotlib>=3.8.0\npytest>=8.0.0\n",
        encoding="utf-8",
    )
    (project_dir / ".gitignore").write_text(
        STANDARD_GITIGNORE + "\n# Data and model artifacts\ndata/*\n!data/.gitkeep\nmodels/*\n!models/.gitkeep\n*.pkl\n*.pt\n*.onnx\n",
        encoding="utf-8",
    )

    pyproject = f"""[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{proj_name}"
version = "0.1.0"
description = "A Machine Learning project created with MayuriShell"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "numpy>=1.26.0",
    "pandas>=2.2.0",
    "scikit-learn>=1.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "matplotlib>=3.8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    (project_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    (src_pkg / "__init__.py").write_text(f'"""{proj_name} ML package."""\n\n__version__ = "0.1.0"\n', encoding="utf-8")
    (src_pkg / "dataset.py").write_text(
        '"""Data loading and preprocessing."""\nfrom __future__ import annotations\n\n\ndef load_sample_data() -> list[float]:\n    return [1.0, 2.0, 3.0, 4.0, 5.0]\n',
        encoding="utf-8",
    )
    (src_pkg / "model.py").write_text(
        '"""Model definitions and inference."""\nfrom __future__ import annotations\n\n\nclass BaselinePredictor:\n    def predict(self, value: float) -> float:\n        return value * 2.0\n',
        encoding="utf-8",
    )

    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_model.py").write_text(
        f'"""Unit tests for ML model."""\nfrom {mod_name}.model import BaselinePredictor\nfrom {mod_name}.dataset import load_sample_data\n\n\n'
        f'def test_baseline_predictor() -> None:\n'
        f'    model = BaselinePredictor()\n'
        f'    assert model.predict(5.0) == 10.0\n'
        f'    data = load_sample_data()\n'
        f'    assert len(data) == 5\n',
        encoding="utf-8",
    )


def generate_datascience_template(project_dir: Path, proj_name: str, mod_name: str) -> None:
    """Generate Data Science starter files."""
    src_pkg = project_dir / "src" / mod_name
    src_pkg.mkdir(parents=True, exist_ok=True)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (project_dir / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (project_dir / "notebooks").mkdir(parents=True, exist_ok=True)

    (project_dir / "data" / "raw" / ".gitkeep").write_text("", encoding="utf-8")
    (project_dir / "data" / "processed" / ".gitkeep").write_text("", encoding="utf-8")
    (project_dir / "notebooks" / "README.md").write_text("# Notebooks\n\nJupyter notebooks for exploratory data analysis.\n", encoding="utf-8")

    (project_dir / "README.md").write_text(f"# {proj_name}\n\nData science project created with MayuriShell.\n", encoding="utf-8")
    (project_dir / "requirements.txt").write_text(
        "pandas>=2.2.0\nnumpy>=1.26.0\nscipy>=1.12.0\nmatplotlib>=3.8.0\nseaborn>=0.13.0\njupyter>=1.0.0\npytest>=8.0.0\n",
        encoding="utf-8",
    )
    (project_dir / ".gitignore").write_text(
        STANDARD_GITIGNORE + "\n# Data\ndata/raw/*\n!data/raw/.gitkeep\ndata/processed/*\n!data/processed/.gitkeep\n",
        encoding="utf-8",
    )

    pyproject = f"""[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{proj_name}"
version = "0.1.0"
description = "A Data Science project created with MayuriShell"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "scipy>=1.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "matplotlib>=3.8.0",
    "seaborn>=0.13.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    (project_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    (src_pkg / "__init__.py").write_text(f'"""{proj_name} Data Science package."""\n\n__version__ = "0.1.0"\n', encoding="utf-8")
    (src_pkg / "analysis.py").write_text(
        '"""Data processing and summary metrics."""\nfrom __future__ import annotations\n\n\ndef compute_mean(values: list[float]) -> float:\n    if not values:\n        return 0.0\n    return sum(values) / len(values)\n',
        encoding="utf-8",
    )

    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_analysis.py").write_text(
        f'"""Unit tests for analysis module."""\nfrom {mod_name}.analysis import compute_mean\n\n\n'
        f'def test_compute_mean() -> None:\n'
        f'    assert compute_mean([1.0, 2.0, 3.0]) == 2.0\n'
        f'    assert compute_mean([]) == 0.0\n',
        encoding="utf-8",
    )


def generate_flask_template(project_dir: Path, proj_name: str, mod_name: str) -> None:
    """Generate Flask application starter files."""
    src_pkg = project_dir / "src" / mod_name
    src_pkg.mkdir(parents=True, exist_ok=True)
    templates_dir = src_pkg / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    static_css = src_pkg / "static" / "css"
    static_css.mkdir(parents=True, exist_ok=True)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "README.md").write_text(f"# {proj_name}\n\nFlask web application created with MayuriShell.\n", encoding="utf-8")
    (project_dir / "requirements.txt").write_text("flask>=3.0.0\npytest>=8.0.0\n", encoding="utf-8")
    (project_dir / ".gitignore").write_text(STANDARD_GITIGNORE + "\ninstance/\n", encoding="utf-8")

    pyproject = f"""[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{proj_name}"
version = "0.1.0"
description = "A Flask web app created with MayuriShell"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    (project_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    (src_pkg / "__init__.py").write_text(
        '"""Flask application factory."""\nfrom __future__ import annotations\n\nfrom flask import Flask\n\n\n'
        'def create_app() -> Flask:\n'
        '    app = Flask(__name__)\n'
        f'    from {mod_name}.routes import bp\n'
        '    app.register_blueprint(bp)\n'
        '    return app\n',
        encoding="utf-8",
    )
    (src_pkg / "routes.py").write_text(
        '"""Application web routes."""\nfrom __future__ import annotations\n\n'
        'from flask import Blueprint, jsonify, render_template\n\n'
        'bp = Blueprint("main", __name__)\n\n\n'
        '@bp.route("/")\n'
        'def index() -> str:\n'
        '    return render_template("index.html")\n\n\n'
        '@bp.route("/health")\n'
        'def health():\n'
        '    return jsonify({"status": "ok"})\n',
        encoding="utf-8",
    )
    (templates_dir / "index.html").write_text(
        f"<!DOCTYPE html>\n<html>\n<head><title>{proj_name}</title></head>\n<body><h1>Welcome to {proj_name}!</h1></body>\n</html>\n",
        encoding="utf-8",
    )
    (static_css / "style.css").write_text("body { font-family: sans-serif; margin: 2rem; }\n", encoding="utf-8")

    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_app.py").write_text(
        f'"""Flask tests."""\nfrom {mod_name} import create_app\n\n\n'
        f'def test_health() -> None:\n'
        f'    app = create_app()\n'
        f'    app.config["TESTING"] = True\n'
        f'    client = app.test_client()\n'
        f'    res = client.get("/health")\n'
        f'    assert res.status_code == 200\n'
        f'    assert res.json == {{"status": "ok"}}\n',
        encoding="utf-8",
    )


def generate_fastapi_template(project_dir: Path, proj_name: str, mod_name: str) -> None:
    """Generate FastAPI starter files."""
    src_pkg = project_dir / "src" / mod_name
    src_pkg.mkdir(parents=True, exist_ok=True)
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "README.md").write_text(f"# {proj_name}\n\nFastAPI REST API created with MayuriShell.\n", encoding="utf-8")
    (project_dir / "requirements.txt").write_text("fastapi>=0.110.0\nuvicorn>=0.28.0\npytest>=8.0.0\nhttpx>=0.27.0\n", encoding="utf-8")
    (project_dir / ".gitignore").write_text(STANDARD_GITIGNORE, encoding="utf-8")

    pyproject = f"""[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{proj_name}"
version = "0.1.0"
description = "A FastAPI web application created with MayuriShell"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn>=0.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    (project_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    (src_pkg / "__init__.py").write_text(f'"""{proj_name} package."""\n\n__version__ = "0.1.0"\n', encoding="utf-8")
    (src_pkg / "main.py").write_text(
        '"""FastAPI entry point."""\nfrom __future__ import annotations\n\nfrom fastapi import FastAPI\n\n'
        f'app = FastAPI(title="{proj_name}", version="0.1.0")\n\n\n'
        '@app.get("/")\n'
        f'def read_root() -> dict[str, str]:\n    return {{"message": "Hello from {proj_name}!"}}\n\n\n'
        '@app.get("/health")\n'
        'def health() -> dict[str, str]:\n    return {"status": "ok"}\n',
        encoding="utf-8",
    )

    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_main.py").write_text(
        f'"""FastAPI tests."""\nfrom {mod_name}.main import app\n\n\n'
        f'def test_app_title() -> None:\n'
        f'    assert app.title == "{proj_name}"\n',
        encoding="utf-8",
    )


def apply_custom_template(template_dir: Path, target_dir: Path, proj_name: str, mod_name: str) -> None:
    """Copy user custom template into target_dir with safety and variable replacements."""
    if not template_dir.exists() or not template_dir.is_dir():
        raise FileNotFoundError(f"Template directory does not exist: {template_dir}")

    total_files = 0
    total_bytes = 0

    # 1. Pre-scan for size, file count, symlinks, and executables
    entries_to_copy: list[tuple[Path, Path]] = []
    for root, dirs, files in os.walk(template_dir, followlinks=False):
        root_path = Path(root)

        for d in dirs:
            dir_path = root_path / d
            if dir_path.is_symlink():
                raise ValueError(f"Custom template contains symlink directory '{dir_path.name}'. Symlinks are forbidden.")

        for f in files:
            file_path = root_path / f
            if file_path.is_symlink():
                raise ValueError(f"Custom template contains symlink file '{file_path.name}'. Symlinks are forbidden.")

            # Skip executables
            if file_path.suffix.lower() in EXECUTABLE_EXTENSIONS:
                logger.info("Skipping executable file '%s' in custom template", file_path.name)
                continue

            try:
                st = file_path.stat()
                total_bytes += st.st_size
                total_files += 1
            except OSError:
                continue

            rel = file_path.relative_to(template_dir)
            entries_to_copy.append((file_path, rel))

    if total_files > MAX_CUSTOM_TEMPLATE_FILES:
        raise ValueError(f"Template has {total_files} files, exceeding maximum allowed ({MAX_CUSTOM_TEMPLATE_FILES}).")

    if total_bytes > MAX_CUSTOM_TEMPLATE_SIZE:
        raise ValueError(f"Template size is {format_bytes(total_bytes)}, exceeding maximum allowed (5 MB).")

    # 2. Copy and replace variables
    target_dir_res = target_dir.resolve()
    for src_file, rel_path in entries_to_copy:
        # Replace variables in relative path string
        rel_str = str(rel_path).replace("{{project_name}}", proj_name).replace("{{module_name}}", mod_name)
        dst_file = target_dir / rel_str

        # Traversal protection
        try:
            dst_res = dst_file.resolve()
            if not dst_res.is_relative_to(target_dir_res):
                raise ValueError(f"Template path '{rel_str}' traverses outside project directory.")
        except AttributeError:
            if not str(dst_res).startswith(str(target_dir_res)):
                raise ValueError(f"Template path '{rel_str}' traverses outside project directory.")

        dst_file.parent.mkdir(parents=True, exist_ok=True)

        # Try to read and substitute as text; if binary, copy directly
        try:
            content = src_file.read_text(encoding="utf-8")
            rendered = (
                content.replace("{{project_name}}", proj_name)
                .replace("{{module_name}}", mod_name)
            )
            dst_file.write_text(rendered, encoding="utf-8")
        except UnicodeDecodeError:
            # Binary file
            dst_file.write_bytes(src_file.read_bytes())


def handle_templates(context: Any, args: list[str]) -> None:
    """List available project templates."""
    console = context.console
    theme = context.theme

    table = theme.create_table(title="Available Project Templates")
    table.add_column("Template", style=theme.bold_primary_style, no_wrap=True)
    table.add_column("Type", style=theme.success_style)
    table.add_column("Description", style=theme.text_style)

    # Builtin templates
    for t_name, t_desc in sorted(BUILTIN_TEMPLATES.items()):
        table.add_row(escape(t_name), "Built-in", escape(t_desc))

    # Custom templates
    custom_dir = get_custom_templates_dir(context)
    if custom_dir.exists() and custom_dir.is_dir():
        for item in sorted(custom_dir.iterdir()):
            if item.is_dir() and not item.is_symlink():
                table.add_row(escape(item.name), "Custom (User)", f"Folder in {escape(str(custom_dir))}")

    console.print(table)
    console.print(
        f"{theme.format_muted('Create a project with ')}"
        f"{theme.format_primary('create-project <name> --template <template>', bold=True)}"
        f"{theme.format_muted('.')}\n"
        f"{theme.format_muted('Add custom templates as plain folders in: ')}"
        f"{theme.format_warning(escape(str(custom_dir)))}\n"
    )
    return CommandResult.success()


def handle_create_project(context: Any, args: list[str]) -> CommandResult:
    """Scaffold a new project directory from a template."""
    console = context.console
    theme = context.theme

    if not args:
        console.print(
            f"{theme.format_warning('Usage:')} "
            f"{theme.format_primary('create-project <name> [--template <t>] [--here]', bold=True)}"
        )
        return CommandResult.fail("Missing arguments")

    # Parse arguments
    proj_name: str | None = None
    template_name: str | None = None
    is_here: bool = False

    i = 0
    while i < len(args):
        arg = args[i].strip()
        if arg.lower() in ("--template", "-t"):
            if i + 1 < len(args):
                template_name = args[i + 1].strip().lower()
                i += 1
            else:
                console.print(f"{theme.format_error('Error:')} Missing value for --template.")
                return CommandResult.fail("Missing value for --template")
        elif arg.lower() == "--here":
            is_here = True
        elif not arg.startswith("-") and proj_name is None:
            proj_name = arg
        i += 1

    if not proj_name:
        console.print(f"{theme.format_error('Error:')} Project name is required.")
        return CommandResult.fail("Project name is required")

    # Validate project name
    is_valid, err_msg = validate_project_name(proj_name)
    if not is_valid:
        console.print(f"{theme.format_error('Invalid project name:')} {escape(err_msg)}")
        return CommandResult.fail(err_msg)

    # Target directory resolution
    if is_here:
        target_dir = context.current_dir.resolve()
        # Verify directory is empty
        try:
            contents = list(target_dir.iterdir())
            if contents:
                console.print(
                    f"{theme.format_error('Error:')} Cannot scaffold with --here: "
                    f"current directory '{escape(target_dir.name)}' is not empty."
                )
                return CommandResult.fail("Current directory is not empty")
        except OSError as exc:
            console.print(f"{theme.format_error('Error accessing current directory:')} {escape(str(exc))}")
            return CommandResult.fail("Error accessing current directory")
    else:
        target_dir = (context.current_dir / proj_name).resolve()
        if target_dir.exists():
            console.print(
                f"{theme.format_error('Error:')} Folder '{escape(target_dir.name)}' already exists."
            )
            return CommandResult.fail("Folder already exists")

    # Template selection
    custom_dir = get_custom_templates_dir(context)
    all_templates = dict(BUILTIN_TEMPLATES)
    custom_template_map: dict[str, Path] = {}

    if custom_dir.exists() and custom_dir.is_dir():
        for item in custom_dir.iterdir():
            if item.is_dir() and not item.is_symlink():
                t_key = item.name.lower()
                all_templates[t_key] = f"Custom template from {item.name}"
                custom_template_map[t_key] = item

    if not template_name:
        # Prompt user interactively
        console.print(theme.format_accent("Available templates:", bold=True))
        for t_k, t_d in sorted(all_templates.items()):
            console.print(f"  • {theme.format_primary(t_k, bold=True)}: {escape(t_d)}")

        console.print(f"\nWhich template would you like to use? [default: {theme.format_primary('python')}]: ", end="")
        if not sys.stdin.isatty():
            console.print("python")
            template_name = "python"
        else:
            try:
                choice = input().strip().lower()
                template_name = choice if choice else "python"
            except (EOFError, KeyboardInterrupt):
                console.print(theme.format_muted("\nProject creation cancelled."))
                return CommandResult.cancel()

    if template_name not in all_templates:
        console.print(
            f"{theme.format_error('Unknown template:')} '{escape(template_name)}'. "
            f"Use {theme.format_primary('templates', bold=True)} to view options."
        )
        return CommandResult.fail("Unknown template")

    # Derive valid Python module name
    mod_name = derive_python_module_name(proj_name)

    # Create target directory
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        console.print(f"{theme.format_error('Failed to create project folder:')} {escape(str(exc))}")
        return CommandResult.fail("Failed to create project folder")

    # Generate files
    try:
        if template_name in custom_template_map:
            apply_custom_template(custom_template_map[template_name], target_dir, proj_name, mod_name)
        elif template_name == "python":
            generate_python_template(target_dir, proj_name, mod_name)
        elif template_name == "ml":
            generate_ml_template(target_dir, proj_name, mod_name)
        elif template_name == "datascience":
            generate_datascience_template(target_dir, proj_name, mod_name)
        elif template_name == "flask":
            generate_flask_template(target_dir, proj_name, mod_name)
        elif template_name == "fastapi":
            generate_fastapi_template(target_dir, proj_name, mod_name)

        console.print(
            f"{theme.format_success('Created project')} "
            f"{theme.format_primary(escape(proj_name), bold=True)} "
            f"using template {theme.format_accent(escape(template_name))} at:"
        )
        console.print(f"  {theme.format_muted(escape(str(target_dir)))}\n")

        # Print next steps
        cd_step = f"cd {escape(proj_name)}" if not is_here else "# already in directory"
        win_act = r".venv\Scripts\activate"
        console.print(theme.format_accent("Next steps to run yourself:", bold=True))
        console.print(f"  1. {theme.format_primary(cd_step)}")
        console.print(f"  2. {theme.format_primary('python -m venv .venv')}")
        console.print(f"  3. {theme.format_primary(win_act)} (Windows) or {theme.format_primary('source .venv/bin/activate')}")
        console.print(f"  4. {theme.format_primary('pip install -r requirements.txt')}")
        console.print(f"  5. {theme.format_primary('pytest')}\n")

        return CommandResult.success()

    except Exception as exc:
        logger.error("Project generation failed: %s", exc)
        console.print(f"{theme.format_error('Failed to generate project:')} {escape(str(exc))}")
        return CommandResult.fail("Failed to generate project")


def register_project_commands(registry: CommandRegistry, config: Any) -> None:
    """Register create-project and templates commands."""
    registry.register(
        CommandInfo(
            name="create-project",
            description="Create a project directory from a configurable starter template",
            handler=handle_create_project,
            usage="create-project <name> [--template <t>] [--here]",
            category="Productivity",
            arg_rules=ArgumentRules(min_args=1, max_args=5),
        )
    )

    registry.register(
        CommandInfo(
            name="templates",
            description="List available built-in and custom project scaffolding templates",
            handler=handle_templates,
            usage="templates",
            category="Productivity",
            arg_rules=ArgumentRules(min_args=0, max_args=0),
        )
    )
