"""Tests for MayuriShell original animal mascots, mood expressions, and dimensional constraints."""
from __future__ import annotations

from pathlib import Path

from rich.cells import cell_len

from core.mascots import (
    MASCOTS_ASCII,
    MASCOTS_UNICODE,
    VALID_MASCOTS,
    get_mascot,
    get_reactive_face,
    resolve_mascot_name,
)


def test_mascots_completeness_and_moods() -> None:
    """Verify all 6 original mascots exist with 4 distinct moods in both Unicode and ASCII datasets."""
    expected_mascots = {"cat", "bunny", "bear", "fox", "penguin", "shiba"}
    assert set(VALID_MASCOTS) == expected_mascots
    assert set(MASCOTS_UNICODE.keys()) == expected_mascots
    assert set(MASCOTS_ASCII.keys()) == expected_mascots

    required_moods = {"neutral", "happy", "worried", "sleepy"}
    for name in expected_mascots:
        # Unicode
        assert set(MASCOTS_UNICODE[name].keys()) == required_moods
        for mood in required_moods:
            art = MASCOTS_UNICODE[name][mood]
            assert art.name == name
            assert art.mood == mood
            assert len(art.art_lines) > 0
            assert art.face != ""

        # Plain ASCII
        assert set(MASCOTS_ASCII[name].keys()) == required_moods
        for mood in required_moods:
            art = MASCOTS_ASCII[name][mood]
            assert art.name == name
            assert art.mood == mood
            assert len(art.art_lines) > 0
            assert art.face != ""


def test_mascot_dimensions_within_spec() -> None:
    """Verify all mascot art is at most 12 lines high and 24 columns wide."""
    for dataset_name, dataset in [("UNICODE", MASCOTS_UNICODE), ("ASCII", MASCOTS_ASCII)]:
        for mascot_name, moods in dataset.items():
            for mood_name, art in moods.items():
                line_count = len(art.art_lines)
                assert line_count <= 12, (
                    f"Mascot '{mascot_name}' [{mood_name}] ({dataset_name}) exceeds 12 lines: {line_count}"
                )
                for line_idx, line in enumerate(art.art_lines):
                    width = cell_len(line)
                    assert width <= 24, (
                        f"Mascot '{mascot_name}' [{mood_name}] line {line_idx} ({dataset_name}) exceeds 24 cols: {width} ('{line}')"
                    )


def test_plain_mascots_strictly_ascii() -> None:
    """Ensure all plain ASCII mascots and reactive faces contain strictly ASCII characters (ord < 128)."""
    for mascot_name, moods in MASCOTS_ASCII.items():
        for mood_name, art in moods.items():
            for line in art.art_lines:
                for ch in line:
                    assert ord(ch) < 128, (
                        f"Non-ASCII character '{ch}' (ord {ord(ch)}) in mascot '{mascot_name}' mood '{mood_name}'"
                    )
            for ch in art.face:
                assert ord(ch) < 128, (
                    f"Non-ASCII character '{ch}' (ord {ord(ch)}) in face for mascot '{mascot_name}' mood '{mood_name}'"
                )


def test_resolve_mascot_name() -> None:
    """Test mascot name resolution and fallback."""
    assert resolve_mascot_name("bunny") == "bunny"
    assert resolve_mascot_name("BUNNY") == "bunny"
    assert resolve_mascot_name("penguin") == "penguin"
    # Fallback
    assert resolve_mascot_name("pikachu") == "cat"
    assert resolve_mascot_name("unknown_animal") == "cat"
    # Random
    chosen = resolve_mascot_name("random")
    assert chosen in VALID_MASCOTS


def test_mascots_originality_comment_in_file() -> None:
    """Verify core/mascots.py contains the originality disclaimer comment at the top."""
    mascots_file = Path(__file__).parent.parent / "core" / "mascots.py"
    content = mascots_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    header_block = "\n".join(lines[:5])
    assert "original" in header_block.lower()
    assert "not copies" in header_block.lower() or "not imitate" in header_block.lower() or "character" in header_block.lower()
