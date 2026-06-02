"""SlashCommandResult for structured command results.

Defines how slash command results should be displayed and processed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Redaction:
    """Redaction metadata for sensitive values."""
    start: int
    end: int
    replacement: str = "***"


@dataclass
class SlashCommandResult:
    """Structured result from a slash command.

    Rules:
    - display: decides how result appears to user
    - model_visible: decides whether result enters model context
    - persist_ui: decides whether it becomes long-term UI history
    - should_start_agent_turn: decides whether command triggers an agent turn
    - next_input / submit_next_input: supports prompt-expansion commands
    - redactions: sensitive values must be redacted before becoming UIEvent or MessageBlock
    """
    display: Literal["skip", "system", "user"] = "system"
    model_visible: bool = False
    persist_ui: bool = True
    should_start_agent_turn: bool = False
    next_input: str | None = None
    submit_next_input: bool = False
    redactions: list[Redaction] | None = None
    content: str = ""
    error: str | None = None

    @classmethod
    def skip(cls) -> SlashCommandResult:
        """Create a skip result (not displayed)."""
        return cls(display="skip", persist_ui=False)

    @classmethod
    def system(cls, content: str, model_visible: bool = False) -> SlashCommandResult:
        """Create a system display result."""
        return cls(
            display="system",
            content=content,
            model_visible=model_visible,
            persist_ui=True,
        )

    @classmethod
    def user(cls, content: str, model_visible: bool = True) -> SlashCommandResult:
        """Create a user display result."""
        return cls(
            display="user",
            content=content,
            model_visible=model_visible,
            persist_ui=True,
        )

    @classmethod
    def prompt_expansion(
        cls,
        next_input: str,
        submit: bool = False,
        display: Literal["skip", "system", "user"] = "skip",
    ) -> SlashCommandResult:
        """Create a prompt expansion result."""
        return cls(
            display=display,
            next_input=next_input,
            submit_next_input=submit,
            persist_ui=False,
        )

    @classmethod
    def agent_turn(
        cls,
        content: str = "",
        display: Literal["skip", "system", "user"] = "system",
    ) -> SlashCommandResult:
        """Create a result that starts an agent turn."""
        return cls(
            display=display,
            content=content,
            should_start_agent_turn=True,
            persist_ui=True,
        )

    @classmethod
    def error_result(cls, error_message: str) -> SlashCommandResult:
        """Create an error result."""
        return cls(
            display="system",
            error=error_message,
            persist_ui=True,
        )

    def with_redaction(self, redactions: list[Redaction]) -> SlashCommandResult:
        """Add redaction metadata."""
        self.redactions = redactions
        return self

    def apply_redactions(self, text: str) -> str:
        """Apply redactions to text."""
        if not self.redactions:
            return text
        result = text
        for redaction in sorted(self.redactions, key=lambda r: r.start, reverse=True):
            result = result[:redaction.start] + redaction.replacement + result[redaction.end:]
        return result
