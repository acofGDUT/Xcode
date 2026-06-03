"""Presenters for transforming UI state to view models.

各 presenter 按五层布局分区：
  StatusPresenter     → BottomLayer (StatusBar)
  TaskPresenter       → ScrollLayer (task snapshots)
  TranscriptPresenter → ScrollLayer (transcript blocks)
  ActiveTurnPresenter → ScrollLayer (current turn — 只保存状态，不固定占位)
  PetPresenter        → FloatLayer
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xcode_cli.core.ui.state import (
    MessageBlock,
    UIStore,
    TurnSurface,
)


@dataclass
class PetState:
    """FloatLayer: Pet state model (placeholder)."""
    visible: bool = False
    mood: str = "neutral"
    position: tuple[int, int] = (0, 0)


@dataclass
class PetViewModel:
    """FloatLayer: Pet view model (placeholder)."""
    visible: bool = False
    sprite: str = ""
    animation: str = ""


@dataclass
class ActiveTurnViewModel:
    """ScrollLayer: 紧凑 active-turn 视图模型 — current_turn 只作为状态域，不固定占位."""
    turn_id: str | None = None
    current_task: str = ""
    next_task: str = ""


class PetPresenter:
    """FloatLayer: Pet UI presenter (placeholder)."""

    def __init__(self) -> None:
        self._state = PetState()

    def update_state(self, state: PetState) -> None:
        """Update pet state."""
        self._state = state

    def get_view_model(self) -> PetViewModel:
        """Get pet view model."""
        return PetViewModel(
            visible=self._state.visible,
            sprite="",
            animation="",
        )


class TaskPresenter:
    """ScrollLayer: Task state presenter — 从 message_blocks 提取 task snapshot."""

    def get_task_snapshot(self, store: UIStore) -> list[dict[str, Any]]:
        """Get concise task snapshot for current turn."""
        # Find the most recent task snapshot block
        for block in reversed(store.message_blocks):
            if block.kind == "task_snapshot":
                return block.tasks
        return []

    def format_task_summary(self, tasks: list[dict[str, Any]]) -> str:
        """Format task summary for display."""
        if not tasks:
            return "No active tasks"
        running = [t for t in tasks if t.get("status") == "in_progress"]
        if running:
            return f"Running: {running[0].get('subject', 'unknown')}"
        return f"{len(tasks)} tasks"

    def concise_snapshot(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only the fields needed for task/status UI."""
        snapshot: list[dict[str, Any]] = []
        for task in tasks:
            snapshot.append({
                "id": str(task.get("id", "")),
                "subject": str(task.get("subject", "")),
                "status": str(task.get("status", "")),
            })
        return snapshot


class StatusPresenter:
    """BottomLayer: StatusBar presenter — 使用新旧兼容属性访问状态."""

    def get_status_line(self, store: UIStore) -> dict[str, Any]:
        """Get status line data — 优先使用新状态域，fallback 到兼容属性."""
        return {
            "turn_id": store.current_turn.turn_id,  # 新状态域
            "has_pending_permission": store.pending_interaction.permission is not None,  # 新状态域
            "is_at_bottom": store.viewport.is_at_bottom,  # 新状态域
            "message_count": len(store.message_blocks),
        }

    def get_status_text(self, store: UIStore) -> str:
        """BottomLayer: 单行状态文本."""
        data = self.get_status_line(store)
        permission = " approval" if data["has_pending_permission"] else ""
        viewport = "bottom" if data["is_at_bottom"] else "history"
        turn_id = data["turn_id"] or "idle"
        return f"turn:{turn_id}{permission} messages:{data['message_count']} view:{viewport}"


class ActiveTurnPresenter:
    """ScrollLayer: active turn presenter — current_turn 只作为状态域，不固定占位."""

    def get_view_model(self, store: UIStore) -> ActiveTurnViewModel:
        """Build active-turn view model from current task snapshots."""
        tasks = TaskPresenter().get_task_snapshot(store)
        running = next(
            (task for task in tasks if task.get("status") == "in_progress"),
            None,
        )
        pending = next(
            (task for task in tasks if task.get("status") == "pending"),
            None,
        )
        return ActiveTurnViewModel(
            turn_id=store.current_turn.turn_id,
            current_task=str(running.get("subject", "")) if running else "",
            next_task=str(pending.get("subject", "")) if pending else "",
        )


class TranscriptPresenter:
    """ScrollLayer: transcript presenter — 管理可见 message blocks."""

    def get_visible_blocks(self, store: UIStore, max_blocks: int = 100) -> list[MessageBlock]:
        """Get visible message blocks."""
        return store.message_blocks[-max_blocks:]

    def should_auto_scroll(self, store: UIStore) -> bool:
        """Check if should auto-scroll to bottom."""
        return store.viewport.is_at_bottom
