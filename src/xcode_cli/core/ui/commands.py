"""UICommand types for Textual-based terminal UI.

Commands represent user/UI intentions, not rendered content.
Commands must not contain raw secrets unless unavoidable.
Sensitive fields must support redaction before logging or UI display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class UICommand:
    """Base class for all UI commands."""
    pass


@dataclass(frozen=True)
class SubmitUserInputCommand(UICommand):
    """User submits text input."""
    text: str


@dataclass(frozen=True)
class RunSlashCommandCommand(UICommand):
    """User runs a slash command."""
    raw: str


@dataclass(frozen=True)
class PermissionDecisionCommand(UICommand):
    """User makes a permission decision for a tool call."""
    request_id: str
    tool_call_id: str
    choice: Literal["yes", "no", "yes_all"]


@dataclass(frozen=True)
class CancelTurnCommand(UICommand):
    """User cancels the current turn."""
    reason: str = "user"


@dataclass(frozen=True)
class ResumeSessionCommand(UICommand):
    """User resumes a previous session."""
    session_id: str


@dataclass(frozen=True)
class CompactCommand(UICommand):
    """User triggers context compaction."""
    pass


@dataclass(frozen=True)
class SaveEnvCommand(UICommand):
    """User saves environment changes."""
    changes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanDecisionCommand(UICommand):
    """User makes a plan decision."""
    decision: Literal["approve", "reject"]


@dataclass(frozen=True)
class ExitCommand(UICommand):
    """User exits the application."""
    pass


@dataclass(frozen=True)
class ViewportStateChangedCommand(UICommand):
    """Viewport scroll position changed."""
    is_at_bottom: bool
