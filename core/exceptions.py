"""Domain exceptions for MayuriShell."""

class MayuriShellError(Exception):
    """Base exception for all MayuriShell errors."""
    pass


class ConfigError(MayuriShellError):
    """Raised when configuration operations fail or config is invalid."""
    pass


class ParseError(MayuriShellError):
    """Raised when parsing user input fails (e.g. unclosed quotes)."""
    pass


class CommandNotFoundError(MayuriShellError):
    """Raised when a command is not registered."""
    def __init__(self, command_name: str, suggestions: list[str] | None = None) -> None:
        super().__init__(f"Command not found: '{command_name}'")
        self.command_name = command_name
        self.suggestions = suggestions or []


class CommandExecutionError(MayuriShellError):
    """Raised when command execution encounters an error."""
    pass


class ArgumentError(MayuriShellError):
    """Raised when command arguments do not meet requirements."""
    pass


class AliasLoopError(MayuriShellError):
    """Raised when an alias loop/cycle is detected."""
    pass


class AliasConflictError(MayuriShellError):
    """Raised when an alias conflicts with a registered command."""
    pass


class CommandError(MayuriShellError):
    """Raised when a command encounters an error or refusal."""
    pass


class CommandCancelled(MayuriShellError):
    """Raised when a command operation is cancelled by the user."""
    pass

