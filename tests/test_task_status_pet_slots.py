"""Batch 5 tests for task, status, pet, and active turn slots."""
from __future__ import annotations

import json

from xcode_cli.core.llm import ToolCall
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.runtime.cancellation import CancellationToken
from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.task_tracker import TaskTracker, create_task_tools
from xcode_cli.core.tool_registry import ToolRegistry
from xcode_cli.core.ui.events import StatusUpdated, TaskStateChanged
from xcode_cli.core.ui import presenters
from xcode_cli.core.ui.presenters import PetPresenter, StatusPresenter, TaskPresenter
from xcode_cli.core.ui.state import TaskSnapshotBlock, UIStore
from xcode_cli.core.ui.textual.app import ChatApp


def _task_controller(task_tracker: TaskTracker) -> RuntimeController:
    registry = ToolRegistry()
    for tool in create_task_tools(task_tracker):
        registry.register(tool)
    return RuntimeController(
        tool_registry=registry,
        permission_manager=PermissionManager(cwd="."),
        task_tracker=task_tracker,
        headless=True,
    )


def test_task_create_tool_emits_task_state_changed_event() -> None:
    tracker = TaskTracker()
    controller = _task_controller(tracker)

    controller._execute_tools_in_turn(
        [
            ToolCall(
                id="call_1",
                name="task_create",
                args={"subject": "Implement batch5", "description": "Task slots"},
            )
        ],
        "turn_1",
        CancellationToken(),
    )

    events = controller.drain_events()
    task_event = next(event for event in events if isinstance(event, TaskStateChanged))
    assert task_event.old_state == "none"
    assert task_event.new_state == "pending"
    assert task_event.description == "Implement batch5"


def test_task_update_tool_emits_task_state_changed_event() -> None:
    tracker = TaskTracker()
    task = tracker.create("Implement batch5", "Task slots")
    controller = _task_controller(tracker)

    controller._execute_tools_in_turn(
        [
            ToolCall(
                id="call_1",
                name="task_update",
                args={"task_id": task.id, "status": "in_progress"},
            )
        ],
        "turn_1",
        CancellationToken(),
    )

    events = controller.drain_events()
    task_event = next(event for event in events if isinstance(event, TaskStateChanged))
    assert task_event.task_id == task.id
    assert task_event.old_state == "pending"
    assert task_event.new_state == "in_progress"


def test_chat_app_task_event_adds_concise_snapshot_block() -> None:
    controller = RuntimeController(headless=True)
    app = ChatApp(controller=controller)
    indicator = type("Indicator", (), {"show_task": lambda self, subject: None, "hide_tool": lambda self: None})()
    app.query_one = lambda *args, **kwargs: indicator

    app.handle_event(TaskStateChanged(
        task_id="task_1",
        old_state="pending",
        new_state="in_progress",
        description="Implement batch5",
    ))

    snapshots = [
        block for block in app.store.message_blocks
        if isinstance(block, TaskSnapshotBlock)
    ]
    assert len(snapshots) == 1
    assert snapshots[0].tasks == [
        {
            "id": "task_1",
            "subject": "Implement batch5",
            "status": "in_progress",
        }
    ]


def test_chat_app_task_events_maintain_current_task_list_and_active_turn_ui() -> None:
    controller = RuntimeController(headless=True)
    app = ChatApp(controller=controller)
    calls: list[tuple[str, str]] = []

    class Indicator:
        def show_task(self, subject: str) -> None:
            calls.append(("show_task", subject))

        def hide_tool(self) -> None:
            calls.append(("hide_tool", ""))

    app.query_one = lambda *args, **kwargs: Indicator()

    app.handle_event(TaskStateChanged(
        task_id="task_1",
        old_state="none",
        new_state="pending",
        description="Queued task",
    ))
    app.handle_event(TaskStateChanged(
        task_id="task_2",
        old_state="none",
        new_state="in_progress",
        description="Running task",
    ))

    latest = [
        block for block in app.store.message_blocks
        if isinstance(block, TaskSnapshotBlock)
    ][-1]
    assert latest.tasks == [
        {"id": "task_1", "subject": "Queued task", "status": "pending"},
        {"id": "task_2", "subject": "Running task", "status": "in_progress"},
    ]
    assert ("show_task", "Running task") in calls


def test_task_presenter_prefers_running_task_and_keeps_snapshot_concise() -> None:
    store = UIStore()
    store.add_message_block(TaskSnapshotBlock(
        id="tasks_1",
        tasks=[
            {"id": "a", "subject": "Queued", "status": "pending", "extra": "drop me"},
            {"id": "b", "subject": "Running", "status": "in_progress"},
        ],
    ))

    presenter = TaskPresenter()

    assert presenter.format_task_summary(presenter.get_task_snapshot(store)) == "Running: Running"
    assert presenter.concise_snapshot([
        {"id": "a", "subject": "Queued", "status": "pending", "description": "long"},
    ]) == [{"id": "a", "subject": "Queued", "status": "pending"}]


def test_status_presenter_returns_single_line_text() -> None:
    store = UIStore(current_turn_id="turn_1", is_at_bottom=False)
    presenter = StatusPresenter()

    status_text = presenter.get_status_text(store)

    assert "\n" not in status_text
    assert "turn_1" in status_text
    assert "messages:0" in status_text


def test_pet_presenter_hidden_without_resources() -> None:
    view_model = PetPresenter().get_view_model()

    assert view_model.visible is False
    assert view_model.sprite == ""
    assert view_model.animation == ""


def test_active_turn_presenter_uses_current_running_task() -> None:
    assert hasattr(presenters, "ActiveTurnPresenter")
    ActiveTurnPresenter = presenters.ActiveTurnPresenter
    store = UIStore(current_turn_id="turn_1")
    store.add_message_block(TaskSnapshotBlock(
        id="tasks_1",
        tasks=[
            {"id": "a", "subject": "Queued", "status": "pending"},
            {"id": "b", "subject": "Running", "status": "in_progress"},
        ],
    ))

    view_model = ActiveTurnPresenter().get_view_model(store)

    assert view_model.turn_id == "turn_1"
    assert view_model.current_task == "Running"
    assert view_model.next_task == "Queued"


def test_chat_app_status_bar_uses_status_presenter() -> None:
    from xcode_cli.core.ui.textual.widgets import StatusBar

    controller = RuntimeController(headless=True)
    app = ChatApp(controller=controller)
    status_bar = StatusBar()
    app.query_one = lambda *args, **kwargs: status_bar

    app.handle_event(StatusUpdated(field="turn", value="busy:turn_1"))

    assert status_bar.status_text == "turn:turn_1 messages:0 view:bottom"
