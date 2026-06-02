"""Presenters for transforming UI state to view models."""
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
    """Pet state model (placeholder for future pet UI)."""
    visible: bool = False
    mood: str = "neutral"
    position: tuple[int, int] = (0, 0)


@dataclass
class PetViewModel:
    """Pet view model (placeholder for future pet UI)."""
    visible: bool = False
    sprite: str = ""
    animation: str = ""


@dataclass
class ActiveTurnViewModel:
    """Compact active-turn view model."""
    turn_id: str | None = None
    current_task: str = ""
    next_task: str = ""


class PetPresenter:
    """Presenter for pet UI (placeholder for future pet UI)."""

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
    """Presenter for task state."""

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
    """Presenter for status bar."""

    def get_status_line(self, store: UIStore) -> dict[str, Any]:
        """Get status line data."""
        return {
            "turn_id": store.current_turn_id,
            "has_pending_permission": store.pending_permission is not None,
            "is_at_bottom": store.is_at_bottom,
            "message_count": len(store.message_blocks),
        }

    def get_status_text(self, store: UIStore) -> str:
        """Get a one-line status string suitable for the status bar."""
        data = self.get_status_line(store)
        permission = " approval" if data["has_pending_permission"] else ""
        viewport = "bottom" if data["is_at_bottom"] else "history"
        turn_id = data["turn_id"] or "idle"
        return f"turn:{turn_id}{permission} messages:{data['message_count']} view:{viewport}"


class ActiveTurnPresenter:
    """Presenter for the active turn slot."""

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
            turn_id=store.current_turn_id,
            current_task=str(running.get("subject", "")) if running else "",
            next_task=str(pending.get("subject", "")) if pending else "",
        )


class TranscriptPresenter:
    """Presenter for transcript area."""

    def get_visible_blocks(self, store: UIStore, max_blocks: int = 100) -> list[MessageBlock]:
        """Get visible message blocks."""
        return store.message_blocks[-max_blocks:]

    def should_auto_scroll(self, store: UIStore) -> bool:
        """Check if should auto-scroll to bottom."""
        return store.is_at_bottom
