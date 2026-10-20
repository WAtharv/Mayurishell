"""Command line parser for MayuriShell."""
from __future__ import annotations

from dataclasses import dataclass, field
import shlex

from core.exceptions import ParseError


@dataclass(frozen=True)
class ParsedCommand:
    """Represents a successfully parsed command line."""
    name: str
    args: list[str] = field(default_factory=list)
    raw: str = ""


def parse_command_line(raw_line: str) -> ParsedCommand | None:
    """Parse raw user input into command name and arguments.
    
    Uses shlex with posix=False to preserve Windows path backslashes while
    correctly supporting single and double quoted arguments.
    
    Returns:
        ParsedCommand if input contains a command, or None if input was empty.
        
    Raises:
        ParseError: If syntax is invalid (e.g. unclosed quotation marks).
    """
    stripped = raw_line.strip()
    if not stripped:
        return None

    lexer = shlex.shlex(stripped, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""  # Do not treat '#' as shell comments

    tokens: list[str] = []
    try:
        while True:
            token = lexer.get_token()
            if token == lexer.eof:
                break

            # Strip matching enclosing quotes while leaving interior content intact
            if len(token) >= 2 and (
                (token.startswith('"') and token.endswith('"'))
                or (token.startswith("'") and token.endswith("'"))
            ):
                token = token[1:-1]

            tokens.append(token)
    except ValueError as exc:
        raise ParseError(f"Parsing error: {exc}") from exc

    if not tokens:
        return None

    cmd_name = tokens[0].lower()
    args = tokens[1:]

    return ParsedCommand(name=cmd_name, args=args, raw=raw_line)
