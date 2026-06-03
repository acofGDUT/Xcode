"""UIEvent types for Textual-based terminal UI.

Events describe facts that occurred.
Events must be safe for UIStore to consume.
Events should carry stable ids where needed: turn_id, message_id, tool_call_id, request_id.
Tool errors that should be visible to the model must remain distinguishable from UI command errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UIEvent:
    """Base class for all UI events."""
    pass


# Message events

@dataclass(frozen=True)
class UserMessageAdded(UIEvent):
    """A user message was added."""
    message_id: str
    content: str


@dataclass(frozen=True)
class AssistantDelta(UIEvent):
    """Streaming assistant text delta."""
    turn_id: str
    delta: str


@dataclass(frozen=True)
class ReasoningDelta(UIEvent):
    """Streaming reasoning/thinking text delta.

    属于 ScrollLayer transcript tail，不进入 current_turn 固定面板。
    """
    turn_id: str
    delta: str


@dataclass(frozen=True)
class AssistantFinal(UIEvent):
    """Assistant response finalized."""
    turn_id: str
    message_id: str
    content: str


# Tool events

@dataclass(frozen=True)
class ToolCallStarted(UIEvent):
    """A tool call started."""
    turn_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallFinished(UIEvent):
    """A tool call finished."""
    turn_id: str
    tool_call_id: str
    tool_name: str
    success: bool


@dataclass(frozen=True)
class ToolOutputProduced(UIEvent):
    """Tool output was produced."""
    turn_id: str
    tool_call_id: str
    tool_name: str
    output_type: str  # summary, stdout, stderr, diff, command, result, error
    content: str


@dataclass(frozen=True)
class ToolRejected(UIEvent):
    """A tool call was rejected by user."""
    turn_id: str
    tool_call_id: str
    tool_name: str


@dataclass(frozen=True)
class ToolError(UIEvent):
    """A tool call errored."""
    turn_id: str
    tool_call_id: str
    tool_name: str
    error: str


# Diff/Preview events

@dataclass(frozen=True)
class DiffPreviewAvailable(UIEvent):
    """A diff preview is available."""
    turn_id: str
    tool_call_id: str
    file_path: str
    diff_content: str


@dataclass(frozen=True)
class CommandPreviewAvailable(UIEvent):
    """A command preview is available."""
    turn_id: str
    tool_call_id: str
    command: str


# Permission events

@dataclass(frozen=True)
class PermissionRequestEvent(UIEvent):
    """A permission request was made."""
    request_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    scope: str
    risk_summary: str


@dataclass(frozen=True)
class PermissionClearedEvent(UIEvent):
    """A permission request was resolved."""
    request_id: str
    tool_call_id: str


# Task events

@dataclass(frozen=True)
class TaskStateChanged(UIEvent):
    """A task state changed."""
    task_id: str
    old_state: str
    new_state: str
    description: str


# Status events

@dataclass(frozen=True)
class StatusUpdated(UIEvent):
    """Status bar updated."""
    field: str
    value: Any


# Compaction events

@dataclass(frozen=True)
class CompactionStarted(UIEvent):
    """Context compaction started."""
    pass


@dataclass(frozen=True)
class CompactionCompleted(UIEvent):
    """Context compaction completed."""
    summary: str
    source_message_count: int


@dataclass(frozen=True)
class CompactionSkipped(UIEvent):
    """Context compaction skipped (nothing to compact)."""
    pass


@dataclass(frozen=True)
class CompactionFailed(UIEvent):
    """Context compaction failed."""
    error: str


# Resume events

@dataclass(frozen=True)
class ResumeListLoaded(UIEvent):
    """Resume session list loaded."""
    sessions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ResumeCompleted(UIEvent):
    """Session resume completed."""
    session_id: str
    restored_from_checkpoint: bool
    message_count: int
    estimated_tokens: int
    last_user_input: str | None = None


# Config events

@dataclass(frozen=True)
class ConfigUpdated(UIEvent):
    """Configuration updated."""
    key: str
    value: Any


# Plan events

@dataclass(frozen=True)
class PlanApprovalRequested(UIEvent):
    """Plan approval requested."""
    plan_content: str


@dataclass(frozen=True)
class PlanUpdated(UIEvent):
    """Plan updated."""
    plan_content: str


# System events

@dataclass(frozen=True)
class SystemNoticeAdded(UIEvent):
    """A system notice was added."""
    message_id: str
    content: str


@dataclass(frozen=True)
class UICommandFailed(UIEvent):
    """A UI command failed."""
    command_type: str
    error: str


@dataclass(frozen=True)
class TurnCancelled(UIEvent):
    """The current turn was cancelled."""
    turn_id: str
    reason: str
