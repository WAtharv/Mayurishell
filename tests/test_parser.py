"""Unit tests for command parser."""
import pytest

from core.exceptions import ParseError
from core.parser import parse_command_line


def test_empty_input() -> None:
    """Empty or whitespace-only strings return None."""
    assert parse_command_line("") is None
    assert parse_command_line("   ") is None
    assert parse_command_line("\t\n") is None


def test_single_command_no_args() -> None:
    """Test single command parsing and case normalization."""
    parsed = parse_command_line("HELP")
    assert parsed is not None
    assert parsed.name == "help"
    assert parsed.args == []


def test_command_with_simple_args() -> None:
    """Test command with space-separated arguments."""
    parsed = parse_command_line("history clear")
    assert parsed is not None
    assert parsed.name == "history"
    assert parsed.args == ["clear"]


def test_quoted_arguments_with_spaces() -> None:
    """Test double and single quoted arguments."""
    parsed = parse_command_line('find "machine learning" \'deep neural nets\'')
    assert parsed is not None
    assert parsed.name == "find"
    assert parsed.args == ["machine learning", "deep neural nets"]


def test_windows_paths_with_backslashes() -> None:
    """Test that Windows paths with backslashes are preserved intact."""
    parsed = parse_command_line(r'open "C:\Users\Mayuri\Study Notes\report.pdf"')
    assert parsed is not None
    assert parsed.name == "open"
    assert parsed.args == [r"C:\Users\Mayuri\Study Notes\report.pdf"]


def test_unquoted_windows_path() -> None:
    """Test unquoted Windows path."""
    parsed = parse_command_line(r"cd C:\Users\Mayuri\Desktop")
    assert parsed is not None
    assert parsed.name == "cd"
    assert parsed.args == [r"C:\Users\Mayuri\Desktop"]


def test_unclosed_quotes_raise_parse_error() -> None:
    """Test that unclosed quotes raise ParseError instead of crashing."""
    with pytest.raises(ParseError) as exc_info:
        parse_command_line('find "unclosed quote')
    assert "Parsing error" in str(exc_info.value)
