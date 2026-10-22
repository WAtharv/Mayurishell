"""Tests for single source of truth version definition."""
from __future__ import annotations

import re

from commands.builtins import VERSION as BUILTINS_VERSION
from core.config_manager import DEFAULT_CONFIG
from core.version import VERSION, __version__


def test_version_single_source_of_truth():
    """Verify that all core modules use the single source of truth version string."""
    assert VERSION == "0.1.1"
    assert __version__ == VERSION
    assert BUILTINS_VERSION == VERSION
    assert DEFAULT_CONFIG["version"] == VERSION


def test_version_format():
    """Verify that version follows semantic versioning format (MAJOR.MINOR.PATCH)."""
    assert re.match(r"^\d+\.\d+\.\d+$", VERSION) is not None
