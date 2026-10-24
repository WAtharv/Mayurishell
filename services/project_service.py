"""Project service for MayuriShell.

Provides read-only inspection of project roots, detected stacks, directory trees,
environment configurations, and health diagnostics. Never executes, imports,
or installs anything from inspected projects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Sequence
try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None  # type: ignore

from core.logging_config import get_logger

logger = get_logger()

MAX_WALK_LEVELS = 8
MAX_FILE_READ_BYTES = 256 * 1024  # 256 KB
MAX_TREE_ENTRIES = 300
MAX_TREE_SECONDS = 3.0
MAX_PYTHON_FILE_COUNT = 500

PROJECT_MARKERS = (
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
)

SKIPPED_TREE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}

FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


@dataclass
class ProjectInfo:
    """Metadata describing a detected project."""
    name: str
    root: Path
    kinds: list[str]
    is_git: bool
    python_files_count: int
    has_tests: bool
    has_readme: bool
    dependency_count: int


@dataclass
class ProjectDoctorCheck:
    """Individual project doctor finding."""
    name: str
    status: str  # "OK", "WARN", "FAIL", "UNKNOWN"
    message: str
    fix: str = ""


def is_reparse_point_or_symlink(path: Path) -> bool:
    """Check if a path is a symlink, junction, or reparse point.
    
    Uses lstat and Windows FILE_ATTRIBUTE_REPARSE_POINT to detect junctions
    as well as standard symlinks without following them.
    """
    try:
        st = path.lstat()
        mode = getattr(st, "st_mode", 0)
        if stat.S_ISLNK(mode):
            return True
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    except (OSError, ValueError):
        pass
    return False


def is_drive_root(path: Path) -> bool:
    """Check if path is a filesystem drive root (e.g. C:\\ or /)."""
    try:
        resolved = path.resolve()
        return len(resolved.parts) <= 1 or resolved.parent == resolved
    except Exception:
        return False


def find_project_root(start_dir: Path) -> Path | None:
    """Walk up from start_dir at most 8 levels to detect the project root.
    
    Stops at drive root. Never uses os.getcwd().
    """
    try:
        curr = start_dir.resolve()
    except Exception:
        curr = start_dir

    for _ in range(MAX_WALK_LEVELS + 1):
        # Check for markers in curr
        for marker in PROJECT_MARKERS:
            try:
                candidate = curr / marker
                # Check existence without raising on permission errors
                if candidate.exists() or candidate.is_symlink():
                    return curr
            except (OSError, PermissionError):
                continue

        # Stop at drive root
        if is_drive_root(curr):
            break
        parent = curr.parent
        if parent == curr:
            break
        curr = parent

    return None


def _read_capped_text(file_path: Path, max_bytes: int = MAX_FILE_READ_BYTES) -> str:
    """Safely read at most max_bytes of text from a file."""
    try:
        with open(file_path, "rb") as f:
            raw = f.read(max_bytes)
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def detect_project_kinds(root: Path) -> list[str]:
    """Inspect markers and dependency files (capped read) to classify project kinds."""
    kinds: set[str] = set()

    # 1. Check file markers
    has_pyproject = (root / "pyproject.toml").is_file()
    has_requirements = (root / "requirements.txt").is_file()
    has_setup_py = (root / "setup.py").is_file()
    has_setup_cfg = (root / "setup.cfg").is_file()
    has_pipfile = (root / "Pipfile").is_file()
    has_manage_py = (root / "manage.py").is_file()
    has_package_json = (root / "package.json").is_file()
    has_dockerfile = (root / "Dockerfile").is_file()

    if has_package_json:
        kinds.add("node")
    if has_dockerfile:
        kinds.add("docker")

    # Python stack check
    is_python = (
        has_pyproject
        or has_requirements
        or has_setup_py
        or has_setup_cfg
        or has_pipfile
        or has_manage_py
    )
    if not is_python:
        # Check if any .py files or .venv exist in root
        try:
            for item in root.iterdir():
                if item.is_file() and item.suffix.lower() == ".py":
                    is_python = True
                    break
                if item.is_dir() and item.name in (".venv", "venv", "env"):
                    if (item / "pyvenv.cfg").is_file():
                        is_python = True
                        break
        except (OSError, PermissionError):
            pass

    if is_python:
        kinds.add("python")

    # Read requirements.txt and pyproject.toml capped at 256 KB
    req_text = ""
    if has_requirements:
        req_text += _read_capped_text(root / "requirements.txt").lower() + "\n"

    # Also inspect pyproject.toml
    pyproject_text = ""
    if has_pyproject:
        pyproject_text = _read_capped_text(root / "pyproject.toml").lower()
        req_text += pyproject_text + "\n"

    # ML packages
    ml_keywords = ("numpy", "pandas", "torch", "tensorflow", "scikit-learn")
    if any(re.search(rf"\b{kw}\b", req_text) for kw in ml_keywords):
        kinds.add("ml")

    # Web frameworks
    if re.search(r"\bflask\b", req_text):
        kinds.add("flask")
    if re.search(r"\bfastapi\b", req_text):
        kinds.add("fastapi")

    # Sort deterministically with 'python' or primary first
    order = ["python", "ml", "fastapi", "flask", "node", "docker"]
    return sorted(kinds, key=lambda k: order.index(k) if k in order else 99)


def count_python_files(root: Path, limit: int = MAX_PYTHON_FILE_COUNT) -> int:
    """Count Python (.py) files in project, skipping excluded folders and capping search."""
    count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Modify dirnames in-place to avoid descending into skipped or reparse directories
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIPPED_TREE_DIRS
                and not is_reparse_point_or_symlink(Path(dirpath) / d)
            ]
            for fn in filenames:
                if fn.lower().endswith(".py"):
                    count += 1
                    if count >= limit:
                        return count
    except (OSError, PermissionError):
        pass
    return count


def parse_dependency_entries(root: Path) -> list[str]:
    """Parse declared dependency names, safely redacting any containing URLs or credentials."""
    deps: list[str] = []

    # Parse requirements.txt
    req_path = root / "requirements.txt"
    if req_path.is_file():
        text = _read_capped_text(req_path)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Redact or skip any line containing credentials or URL schemas
            if "://" in line or "@" in line:
                continue
            # Extract package name before operators (==, >=, <=, ~=, !=, <, >, ;)
            m = re.match(r"^([a-zA-Z0-9_\-\.]+)", line)
            if m:
                deps.append(m.group(1))

    # Parse pyproject.toml with tomllib
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.is_file() and tomllib is not None:
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            # Standard [project.dependencies]
            proj_deps = data.get("project", {}).get("dependencies", [])
            if isinstance(proj_deps, list):
                for entry in proj_deps:
                    if isinstance(entry, str):
                        clean_entry = entry.strip()
                        if "://" in clean_entry or "@" in clean_entry:
                            continue
                        m = re.match(r"^([a-zA-Z0-9_\-\.]+)", clean_entry)
                        if m:
                            deps.append(m.group(1))
            # Poetry [tool.poetry.dependencies]
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for dep_name in poetry_deps.keys():
                    if dep_name.lower() != "python" and "://" not in dep_name and "@" not in dep_name:
                        deps.append(str(dep_name))
        except Exception:
            pass

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for d in deps:
        d_lower = d.lower()
        if d_lower not in seen:
            seen.add(d_lower)
            result.append(d)
    return result


def get_project_name(root: Path) -> str:
    """Extract project name from pyproject.toml, package.json, or fallback to folder name."""
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.is_file() and tomllib is not None:
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            p_name = data.get("project", {}).get("name")
            if p_name and isinstance(p_name, str):
                return p_name.strip()
            poetry_name = data.get("tool", {}).get("poetry", {}).get("name")
            if poetry_name and isinstance(poetry_name, str):
                return poetry_name.strip()
        except Exception:
            pass

    return root.name


def get_project_info(root: Path) -> ProjectInfo:
    """Collect high-level project summary."""
    name = get_project_name(root)
    kinds = detect_project_kinds(root)
    is_git = (root / ".git").exists()
    py_files = count_python_files(root)

    # Check tests directory
    tests_dir = root / "tests"
    has_tests = tests_dir.is_dir()

    # Check README
    has_readme = False
    for r in ("README.md", "README.rst", "README.txt", "README"):
        if (root / r).is_file():
            has_readme = True
            break

    deps = parse_dependency_entries(root)

    return ProjectInfo(
        name=name,
        root=root,
        kinds=kinds,
        is_git=is_git,
        python_files_count=py_files,
        has_tests=has_tests,
        has_readme=has_readme,
        dependency_count=len(deps),
    )


@dataclass
class TreeNode:
    """Represents a file or directory node in project tree."""
    name: str
    is_dir: bool
    is_symlink: bool
    is_skipped: bool
    children: list[TreeNode] = field(default_factory=list)


def build_project_tree(
    target_path: Path,
    depth: int = 3,
    show_all: bool = False,
    max_entries: int = MAX_TREE_ENTRIES,
    timeout_sec: float = MAX_TREE_SECONDS,
) -> tuple[TreeNode, int, bool]:
    """Build a directory tree up to depth, capped by entry count and time budget.
    
    Directories are sorted first, followed by alphabetical file entries.
    Returns (root_node, total_entries, hit_limit_bool).
    """
    start_time = time.time()
    entry_count = 0
    hit_limit = False

    def _walk(curr_path: Path, current_depth: int) -> TreeNode:
        nonlocal entry_count, hit_limit

        name = curr_path.name or str(curr_path)
        is_link = is_reparse_point_or_symlink(curr_path)
        is_skipped = not show_all and curr_path.name in SKIPPED_TREE_DIRS

        node = TreeNode(
            name=name,
            is_dir=True,
            is_symlink=is_link,
            is_skipped=is_skipped,
        )

        if is_link or is_skipped or current_depth >= depth:
            return node

        if time.time() - start_time > timeout_sec or entry_count >= max_entries:
            hit_limit = True
            return node

        try:
            entries = list(curr_path.iterdir())
        except (OSError, PermissionError):
            return node

        # Separate dirs and files, sorting alphabetically
        dirs: list[Path] = []
        files: list[Path] = []
        for e in entries:
            try:
                if e.is_dir():
                    dirs.append(e)
                else:
                    files.append(e)
            except (OSError, PermissionError):
                continue

        dirs.sort(key=lambda p: p.name.lower())
        files.sort(key=lambda p: p.name.lower())

        # Recurse dirs
        for d in dirs:
            if time.time() - start_time > timeout_sec or entry_count >= max_entries:
                hit_limit = True
                break
            entry_count += 1
            child_node = _walk(d, current_depth + 1)
            node.children.append(child_node)

        # Append files
        for f in files:
            if time.time() - start_time > timeout_sec or entry_count >= max_entries:
                hit_limit = True
                break
            entry_count += 1
            node.children.append(
                TreeNode(
                    name=f.name,
                    is_dir=False,
                    is_symlink=is_reparse_point_or_symlink(f),
                    is_skipped=False,
                )
            )

        return node

    root_node = _walk(target_path, 0)
    return root_node, entry_count, hit_limit


def render_tree_lines(
    node: TreeNode,
    is_plain: bool = False,
    is_root: bool = True,
    prefix: str = "",
) -> list[str]:
    """Format tree nodes into displayable strings with themed or plain ASCII branch guides."""
    lines: list[str] = []

    if is_root:
        lines.append(f"{node.name}/")
    
    child_count = len(node.children)
    for idx, child in enumerate(node.children):
        is_last = (idx == child_count - 1)
        if is_plain:
            connector = "\\-- " if is_last else "+-- "
            child_prefix = "    " if is_last else "|   "
        else:
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

        suffix = ""
        if child.is_symlink:
            suffix = " [symlink]"
        elif child.is_skipped:
            suffix = " [skipped]"
        elif child.is_dir:
            suffix = "/"

        lines.append(f"{prefix}{connector}{child.name}{suffix}")
        if child.children:
            sub_lines = render_tree_lines(
                child,
                is_plain=is_plain,
                is_root=False,
                prefix=prefix + child_prefix,
            )
            lines.extend(sub_lines)

    return lines


def inspect_venv_cfg(venv_dir: Path) -> dict[str, str]:
    """Read ONLY pyvenv.cfg from a venv directory. Does not run python or pip."""
    cfg_path = venv_dir / "pyvenv.cfg"
    result: dict[str, str] = {}
    if not cfg_path.is_file():
        return result

    try:
        with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                result[k.strip().lower()] = v.strip()
    except Exception:
        pass
    return result


def find_venv_directory(root: Path) -> tuple[str, Path, dict[str, str]] | None:
    """Find .venv, venv, or env containing pyvenv.cfg."""
    for cand in (".venv", "venv", "env"):
        cand_path = root / cand
        if cand_path.is_dir():
            cfg_file = cand_path / "pyvenv.cfg"
            if cfg_file.is_file():
                info = inspect_venv_cfg(cand_path)
                return cand, cand_path, info
    return None


def run_project_doctor_checks(root: Path) -> list[ProjectDoctorCheck]:
    """Execute 10 health checks on the project root. Never modifies anything."""
    checks: list[ProjectDoctorCheck] = []

    # 1. Project root found
    checks.append(ProjectDoctorCheck(
        name="Project root found",
        status="OK",
        message=f"Root detected at {root.name}",
    ))

    # 2. Python project detected
    kinds = detect_project_kinds(root)
    if "python" in kinds:
        checks.append(ProjectDoctorCheck(
            name="Python project detected",
            status="OK",
            message=f"Python project ({', '.join(kinds)})",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Python project detected",
            status="WARN",
            message=f"Project stack: {', '.join(kinds) if kinds else 'non-Python'}",
            fix="Run 'create-project' to scaffold a Python project.",
        ))

    # 3. Virtual environment exists
    venv_data = find_venv_directory(root)
    if venv_data:
        v_name, _, v_cfg = venv_data
        ver = v_cfg.get("version", "unknown")
        checks.append(ProjectDoctorCheck(
            name="Virtual environment",
            status="OK",
            message=f"Found '{v_name}' (Python {ver})",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Virtual environment",
            status="WARN",
            message="No active virtual environment found (.venv, venv, env)",
            fix="python -m venv .venv",
        ))

    # 4. Requirements or pyproject.toml
    has_req = (root / "requirements.txt").is_file()
    has_pyproj = (root / "pyproject.toml").is_file()
    if has_req or has_pyproj:
        files = []
        if has_pyproj:
            files.append("pyproject.toml")
        if has_req:
            files.append("requirements.txt")
        checks.append(ProjectDoctorCheck(
            name="Package manifest",
            status="OK",
            message=f"Found: {', '.join(files)}",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Package manifest",
            status="WARN",
            message="Missing requirements.txt or pyproject.toml",
            fix="touch requirements.txt",
        ))

    # 5. Git repository
    if (root / ".git").exists():
        checks.append(ProjectDoctorCheck(
            name="Git repository",
            status="OK",
            message="Git tracking initialized (.git exists)",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Git repository",
            status="WARN",
            message="Folder is not tracked by Git",
            fix="git init (in your terminal)",
        ))

    # 6. Tests directory
    if (root / "tests").is_dir():
        checks.append(ProjectDoctorCheck(
            name="Test suite folder",
            status="OK",
            message="tests/ directory exists",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Test suite folder",
            status="WARN",
            message="tests/ directory not found",
            fix="mkdir tests",
        ))

    # 7. README file
    has_readme = any((root / r).is_file() for r in ("README.md", "README.rst", "README.txt", "README"))
    if has_readme:
        checks.append(ProjectDoctorCheck(
            name="Documentation README",
            status="OK",
            message="README file exists",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Documentation README",
            status="WARN",
            message="No README file found",
            fix="touch README.md",
        ))

    # Read .gitignore text if present
    gitignore_path = root / ".gitignore"
    has_gitignore = gitignore_path.is_file()
    gitignore_text = ""
    if has_gitignore:
        gitignore_text = _read_capped_text(gitignore_path)
        checks.append(ProjectDoctorCheck(
            name=".gitignore file",
            status="OK",
            message=".gitignore file exists",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name=".gitignore file",
            status="WARN",
            message=".gitignore file not found",
            fix="touch .gitignore",
        ))

    # Helper to check if a pattern/name is matched in .gitignore lines
    def _is_in_gitignore(target: str) -> bool:
        if not gitignore_text:
            return False
        for raw_line in gitignore_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            line = line.rstrip("/")
            if fnmatch.fnmatch(target, line) or target == line or line in target:
                return True
        return False

    # 9. .env file existence and gitignore check
    env_file_exists = (root / ".env").is_file()
    if env_file_exists:
        if _is_in_gitignore(".env"):
            checks.append(ProjectDoctorCheck(
                name="Environment secrets (.env)",
                status="OK",
                message=".env exists and is ignored by .gitignore",
            ))
        else:
            checks.append(ProjectDoctorCheck(
                name="Environment secrets (.env)",
                status="FAIL",
                message=".env exists but is NOT ignored by .gitignore (security risk!)",
                fix="echo .env >> .gitignore (in your terminal)",
            ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Environment secrets (.env)",
            status="OK",
            message="No exposed .env secrets file found",
        ))

    # 10. venv folder is ignored
    venv_name = venv_data[0] if venv_data else ".venv"
    if _is_in_gitignore(venv_name) or _is_in_gitignore(".venv") or _is_in_gitignore("venv"):
        checks.append(ProjectDoctorCheck(
            name="Virtual environment ignored",
            status="OK",
            message=f"Virtual environment directory is ignored in .gitignore",
        ))
    else:
        checks.append(ProjectDoctorCheck(
            name="Virtual environment ignored",
            status="WARN",
            message=f"'{venv_name}' folder is not listed in .gitignore",
            fix=f"echo {venv_name}/ >> .gitignore (in your terminal)",
        ))

    return checks
