"""Unit tests for command registry and argument validation."""
import pytest
from rich.console import Console

from core.exceptions import ArgumentError
from core.executor import CommandExecutor
from core.parser import ParsedCommand
from core.registry import ArgumentRules, CommandInfo, CommandRegistry


def test_command_registration_and_retrieval() -> None:
    """Test registering and retrieving commands."""
    reg = CommandRegistry()
    dummy_handler = lambda ctx, args: None
    info = CommandInfo(
        name="testcmd",
        description="A test command",
        handler=dummy_handler,
        usage="testcmd [arg]",
        category="Testing",
    )
    reg.register(info)

    assert reg.has_command("testcmd")
    assert reg.has_command("TESTCMD")  # Case insensitive
    cmd = reg.get("testcmd")
    assert cmd is not None
    assert cmd.description == "A test command"


def test_argument_rules_min_max() -> None:
    """Test min_args and max_args validation."""
    rules = ArgumentRules(min_args=1, max_args=2)
    
    with pytest.raises(ArgumentError):
        rules.validate([])

    # Valid
    rules.validate(["one"])
    rules.validate(["one", "two"])

    with pytest.raises(ArgumentError):
        rules.validate(["one", "two", "three"])


def test_custom_argument_validator() -> None:
    """Test custom argument validator."""
    def only_digits(args: list[str]) -> str | None:
        if not args[0].isdigit():
            return "First argument must be numeric."
        return None

    rules = ArgumentRules(min_args=1, max_args=1, custom_validator=only_digits)
    rules.validate(["42"])

    with pytest.raises(ArgumentError) as exc_info:
        rules.validate(["forty-two"])
    assert "First argument must be numeric" in str(exc_info.value)


def test_command_suggestions() -> None:
    """Test close match suggestions for mistyped commands."""
    reg = CommandRegistry()
    dummy = lambda ctx, args: None
    reg.register(CommandInfo("version", "desc", dummy, "version"))
    reg.register(CommandInfo("history", "desc", dummy, "history"))
    reg.register(CommandInfo("help", "desc", dummy, "help"))

    # Mistyped 'histroy'
    sugg = reg.suggest("histroy")
    assert "history" in sugg

    # Mistyped 'versio'
    sugg = reg.suggest("versio")
    assert "version" in sugg


def test_executor_handles_unknown_command() -> None:
    """Test that executor gracefully reports unknown command without throwing exception."""
    reg = CommandRegistry()
    console = Console(record=True)
    executor = CommandExecutor(registry=reg, console=console)

    success = executor.execute(ParsedCommand(name="unknowncmd"), context=None)
    assert success is False
    output = console.export_text()
    assert "Command not found:" in output and "unknowncmd" in output
