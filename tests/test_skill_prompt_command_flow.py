from pathlib import Path
from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from xcode_cli.core.commands.registry import CommandRegistry
from xcode_cli.core.commands.dispatcher import SlashCommandDispatcher
from xcode_cli.skills.model import Skill


def _console() -> Console:
    return Console(file=StringIO(), force_terminal=True, width=120)


def _handlers() -> dict:
    return {
        "help_handler": MagicMock(),
        "context_handler": MagicMock(),
        "dashboard_handler": MagicMock(),
        "skill_handler": MagicMock(),
        "env_handler": MagicMock(),
        "plan_handler": MagicMock(),
        "memory_handler": MagicMock(),
        "resume_handler": MagicMock(),
        "compact_handler": MagicMock(),
    }


def test_skill_dispatch_returns_user_turn_input_with_display_and_model_content():
    skill = Skill(
        name="review",
        display_name=None,
        description="Review code",
        body="Review this: $ARGUMENTS",
        root=Path("D:/Xcode/.xcode/skills/review"),
    )
    registry = CommandRegistry.from_skills([skill])
    dispatcher = SlashCommandDispatcher(
        console=_console(),
        registry=registry,
        **_handlers(),
    )

    result = dispatcher.dispatch("/review src/foo.py")

    assert result.kind == "prompt"
    assert result.turn_input.display_content == "/review src/foo.py"
    assert result.turn_input.model_content == "Review this: src/foo.py"
    assert result.turn_input.metadata["skill"] == "review"
