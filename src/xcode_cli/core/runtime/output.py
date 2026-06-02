"""ToolOutputSink and RuntimeLogSink for capturing tool output and runtime logs.

Ensures tool stdout/stderr/logging enter proper sinks before UIEvent generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


# Tool output events

@dataclass(frozen=True)
class ToolOutputEvent:
    """Base class for tool output events."""
    tool_call_id: str
    tool_name: str


@dataclass(frozen=True)
class ToolSummaryProduced(ToolOutputEvent):
    """Tool summary was produced."""
    summary: str = ""


@dataclass(frozen=True)
class ToolStdoutProduced(ToolOutputEvent):
    """Tool stdout output."""
    content: str = ""


@dataclass(frozen=True)
class ToolStderrProduced(ToolOutputEvent):
    """Tool stderr output."""
    content: str = ""


@dataclass(frozen=True)
class DiffPreviewProduced(ToolOutputEvent):
    """Diff preview produced."""
    file_path: str = ""
    diff_content: str = ""


@dataclass(frozen=True)
class CommandPreviewProduced(ToolOutputEvent):
    """Command preview produced."""
    command: str = ""


@dataclass(frozen=True)
class ToolResultProduced(ToolOutputEvent):
    """Tool result produced."""
    result: str = ""


@dataclass(frozen=True)
class ToolErrorProduced(ToolOutputEvent):
    """Tool error produced."""
    error: str = ""


# Runtime log events

@dataclass(frozen=True)
class RuntimeLogEvent:
    """Base class for runtime log events."""
    level: str
    message: str
    source: str = ""


class ToolOutputSink(Protocol):
    """Protocol for tool output sinks."""

    def emit(self, event: ToolOutputEvent) -> None:
        """Emit a tool output event.

        Args:
            event: The tool output event.
        """
        ...


class RuntimeLogSink(Protocol):
    """Protocol for runtime log sinks."""

    def emit(self, event: RuntimeLogEvent) -> None:
        """Emit a runtime log event.

        Args:
            event: The runtime log event.
        """
        ...


class NullToolOutputSink:
    """Null tool output sink that discards all events."""

    def emit(self, event: ToolOutputEvent) -> None:
        """Discard the event."""
        pass


class NullRuntimeLogSink:
    """Null runtime log sink that discards all events."""

    def emit(self, event: RuntimeLogEvent) -> None:
        """Discard the event."""
        pass


class CollectingToolOutputSink:
    """Tool output sink that collects events for testing."""

    def __init__(self) -> None:
        self.events: list[ToolOutputEvent] = []

    def emit(self, event: ToolOutputEvent) -> None:
        """Collect the event."""
        self.events.append(event)


class CollectingRuntimeLogSink:
    """Runtime log sink that collects events for testing."""

    def __init__(self) -> None:
        self.events: list[RuntimeLogEvent] = []

    def emit(self, event: RuntimeLogEvent) -> None:
        """Collect the event."""
        self.events.append(event)
