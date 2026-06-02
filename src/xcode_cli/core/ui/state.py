"""UI state models for Textual-based terminal UI.

Long-term UI history and current-turn UI surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# MessageBlock types - long-term UI history

@dataclass
class MessageBlock:
    """Base class for message blocks in UI history."""
    id: str
    kind: str
    created_at: float = 0.0
    model_visible: bool = False
    persist_ui: bool = True


@dataclass
class UserMessageBlock(MessageBlock):
    """User message block."""
    content: str = ""
    kind: str = "user_message"


@dataclass
class AssistantMessageBlock(MessageBlock):
    """Assistant message block."""
    content: str = ""
    kind: str = "assistant_message"


@dataclass
class ToolSummaryBlock(MessageBlock):
    """Tool call summary block."""
    tool_name: str = ""
    tool_call_id: str = ""
    summary: str = ""
    kind: str = "tool_summary"


@dataclass
class ToolResultBlock(MessageBlock):
    """Tool result block."""
    tool_name: str = ""
    tool_call_id: str = ""
    result: str = ""
    kind: str = "tool_result"


@dataclass
class ToolRejectedBlock(MessageBlock):
    """Tool rejected block."""
    tool_name: str = ""
    tool_call_id: str = ""
    kind: str = "tool_rejected"


@dataclass
class TaskSnapshotBlock(MessageBlock):
    """Task snapshot block."""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "task_snapshot"


@dataclass
class SystemNoticeBlock(MessageBlock):
    """System notice block."""
    content: str = ""
    kind: str = "system_notice"


@dataclass
class ToolErrorBlock(MessageBlock):
    """Tool error block."""
    tool_name: str = ""
    tool_call_id: str = ""
    error: str = ""
    kind: str = "tool_error"


@dataclass
class ContextSummaryBlock(MessageBlock):
    """Context summary block (after compaction)."""
    summary: str = ""
    kind: str = "context_summary"


@dataclass
class TaskListBlock(MessageBlock):
    """Task list block."""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "task_list"


@dataclass
class MemoryStatusBlock(MessageBlock):
    """Memory status block."""
    status: str = ""
    kind: str = "memory_status"


# TurnSurface types - current-turn UI surface

@dataclass
class TurnSurface:
    """Base class for current-turn UI surfaces."""
    id: str
    turn_id: str
    tool_call_id: str | None = None
    kind: str = ""


@dataclass
class DiffPreviewSurface(TurnSurface):
    """Diff preview surface."""
    file_path: str = ""
    diff_content: str = ""
    kind: str = "diff_preview"


@dataclass
class CommandPreviewSurface(TurnSurface):
    """Command preview surface."""
    command: str = ""
    kind: str = "command_preview"


@dataclass
class PermissionPromptSurface(TurnSurface):
    """Permission prompt surface."""
    request_id: str = ""
    tool_name: str = ""
    scope: str = ""
    risk_summary: str = ""
    kind: str = "permission_prompt"


@dataclass
class ActiveToolSurface(TurnSurface):
    """Active tool execution surface."""
    tool_name: str = ""
    status: str = ""
    kind: str = "active_tool"


# UIStore - central UI state

@dataclass
class UIStore:
    """Central UI state store."""
    # Long-term message history
    message_blocks: list[MessageBlock] = field(default_factory=list)

    # Current-turn temporary surfaces
    # Key: tool_call_id, Value: list of TurnSurface
    current_turn_surfaces: dict[str, list[TurnSurface]] = field(default_factory=dict)

    # Pending permission request
    pending_permission: PermissionPromptSurface | None = None

    # Current turn id
    current_turn_id: str | None = None

    # Viewport state
    is_at_bottom: bool = True

    def add_message_block(self, block: MessageBlock) -> None:
        """Add a message block to history."""
        self.message_blocks.append(block)

    def add_turn_surface(self, surface: TurnSurface) -> None:
        """Add a turn surface to current turn."""
        if surface.tool_call_id not in self.current_turn_surfaces:
            self.current_turn_surfaces[surface.tool_call_id] = []
        self.current_turn_surfaces[surface.tool_call_id].append(surface)

    def clear_turn_surfaces(self, tool_call_id: str | None = None) -> None:
        """Clear turn surfaces for a tool call or all."""
        if tool_call_id is None:
            self.current_turn_surfaces.clear()
        else:
            self.current_turn_surfaces.pop(tool_call_id, None)

    def clear_all_turn_surfaces(self) -> None:
        """Clear all turn surfaces."""
        self.current_turn_surfaces.clear()
        self.pending_permission = None

    def set_pending_permission(self, surface: PermissionPromptSurface | None) -> None:
        """Set or clear pending permission."""
        self.pending_permission = surface

    def get_pending_permission(self) -> PermissionPromptSurface | None:
        """Get pending permission."""
        return self.pending_permission
