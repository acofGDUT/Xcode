"""Batch 4 tests for Textual slash commands."""
from __future__ import annotations

from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.runtime.permissions import PermissionRequest
from xcode_cli.core.ui.commands import (
    CompactCommand,
    RunSlashCommandCommand,
    SaveEnvCommand,
    SubmitUserInputCommand,
)
from xcode_cli.core.ui.events import (
    CompactionCompleted,
    CompactionFailed,
    CompactionSkipped,
    CompactionStarted,
    ConfigUpdated,
    PlanUpdated,
    ResumeListLoaded,
    StatusUpdated,
    SystemNoticeAdded,
    UICommandFailed,
    UserMessageAdded,
)


def _make_controller(**kwargs) -> RuntimeController:
    return RuntimeController(headless=True, **kwargs)


def test_help_slash_command_emits_local_system_notice() -> None:
    controller = _make_controller()

    controller.dispatch(RunSlashCommandCommand(raw="/help"))

    events = controller.drain_events()
    notices = [event for event in events if isinstance(event, SystemNoticeAdded)]
    assert len(notices) == 1
    assert "/context" in notices[0].content
    assert "/tasks" in notices[0].content
    assert "editable" not in notices[0].content.lower()
    assert "read-only" in notices[0].content
    assert not any(
        isinstance(event, StatusUpdated) and event.field == "command"
        for event in events
    )


def test_context_slash_command_reports_local_context_budget() -> None:
    controller = _make_controller()
    controller._history.extend([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ])

    controller.dispatch(RunSlashCommandCommand(raw="/context"))

    events = controller.drain_events()
    notice = next(event for event in events if isinstance(event, SystemNoticeAdded))
    assert "messages: 2" in notice.content
    assert "max_tokens:" in notice.content


def test_tasks_slash_command_lists_current_task_tracker_state() -> None:
    from xcode_cli.core.task_tracker import TaskTracker

    tracker = TaskTracker()
    tracker.create("Batch 4", "Migrate slash commands")
    controller = _make_controller(task_tracker=tracker)

    controller.dispatch(RunSlashCommandCommand(raw="/tasks"))

    events = controller.drain_events()
    notice = next(event for event in events if isinstance(event, SystemNoticeAdded))
    assert "Batch 4" in notice.content
    assert "pending" in notice.content


def test_compact_slash_command_blocks_during_active_turn() -> None:
    controller = _make_controller()
    controller._start_turn("turn_busy")

    controller.dispatch(RunSlashCommandCommand(raw="/compact"))

    events = controller.drain_events()
    assert any(isinstance(event, UICommandFailed) for event in events)
    assert not any(isinstance(event, CompactionStarted) for event in events)


def test_compact_command_blocks_during_active_turn() -> None:
    controller = _make_controller()
    controller._start_turn("turn_busy")

    controller.dispatch(CompactCommand())

    events = controller.drain_events()
    assert any(isinstance(event, UICommandFailed) for event in events)
    assert not any(isinstance(event, CompactionStarted) for event in events)


def test_resume_slash_command_clears_surfaces_and_loads_list() -> None:
    controller = _make_controller()
    controller._pending_permission_requests["req_1"] = PermissionRequest(
        request_id="req_1",
        turn_id="turn_1",
        tool_call_id="call_1",
        tool_name="write_file",
        scope="write",
        risk_summary="Write file",
    )

    controller.dispatch(RunSlashCommandCommand(raw="/resume"))

    events = controller.drain_events()
    assert controller._pending_permission_requests == {}
    assert any(
        isinstance(event, StatusUpdated)
        and event.field == "surfaces"
        and event.value == "clear"
        for event in events
    )
    assert any(isinstance(event, ResumeListLoaded) for event in events)


def test_resume_slash_command_uses_real_session_store(tmp_path, monkeypatch) -> None:
    from xcode_cli.core import session as session_module
    from xcode_cli.core.session import SessionStore

    monkeypatch.setattr(session_module, "ensure_xcode_home", lambda: tmp_path / ".xcode")
    store = SessionStore(cwd=str(tmp_path / "project"))
    store.append_message("session_a", {"role": "user", "content": "first session"})
    store.append_message("session_b", {"role": "user", "content": "second session"})
    controller = _make_controller(session_store=store)

    controller.dispatch(RunSlashCommandCommand(raw="/resume"))

    events = controller.drain_events()
    loaded = next(event for event in events if isinstance(event, ResumeListLoaded))
    assert len(loaded.sessions) == 2
    assert loaded.sessions[0]["session_id"] in {"session_a", "session_b"}
    assert "last_user_input" in loaded.sessions[0]


def test_compact_command_runs_real_context_compression() -> None:
    from xcode_cli.core.context import ContextManager
    from xcode_cli.core.llm import LLMResponse

    class FakeLLM:
        def complete(self, system_prompt, messages, tool_schemas, **kwargs):
            return LLMResponse(content="compact summary", tool_calls=[])

    controller = RuntimeController(
        llm_client=FakeLLM(),
        context_manager=ContextManager(max_tokens=1000),
        headless=True,
    )
    controller._history.extend(
        [{"role": "user", "content": f"message {idx}"} for idx in range(25)]
    )

    controller.dispatch(CompactCommand())

    events = controller.drain_events()
    assert isinstance(events[0], CompactionStarted)
    completed = next(event for event in events if isinstance(event, CompactionCompleted))
    assert completed.summary == "compact summary"
    assert completed.source_message_count == 25
    assert len(controller._history) < 25


def test_compact_command_skips_when_context_has_no_middle_to_compact() -> None:
    from xcode_cli.core.context import ContextManager

    controller = RuntimeController(context_manager=ContextManager(), headless=True)
    controller._history.extend([{"role": "user", "content": "short"}])

    controller.dispatch(CompactCommand())

    events = controller.drain_events()
    assert any(isinstance(event, CompactionStarted) for event in events)
    assert any(isinstance(event, CompactionSkipped) for event in events)


def test_compact_command_emits_failed_on_compression_error() -> None:
    class BrokenContext:
        def compress(self, history, llm, previous_summary=""):
            raise RuntimeError("compress boom")

    controller = RuntimeController(context_manager=BrokenContext(), headless=True)
    controller._history.extend([{"role": "user", "content": "x"} for _ in range(25)])

    controller.dispatch(CompactCommand())

    events = controller.drain_events()
    failed = next(event for event in events if isinstance(event, CompactionFailed))
    assert "compress boom" in failed.error


def test_env_save_redacts_sensitive_values_before_ui_event() -> None:
    controller = _make_controller()

    controller.dispatch(SaveEnvCommand(changes={"api_key": "sk-secret", "max_tokens": 42}))

    events = controller.drain_events()
    config_events = [event for event in events if isinstance(event, ConfigUpdated)]
    assert config_events[0].key == "api_key"
    assert config_events[0].value == "***"
    assert config_events[1].key == "max_tokens"
    assert config_events[1].value == 42


def test_env_slash_command_is_explicitly_read_only_display() -> None:
    controller = _make_controller()

    controller.dispatch(RunSlashCommandCommand(raw="/env"))

    events = controller.drain_events()
    notice = next(event for event in events if isinstance(event, SystemNoticeAdded))
    assert "read-only" in notice.content
    assert "api_key:" in notice.content


def test_plan_approve_slash_command_uses_runtime_event_path() -> None:
    controller = _make_controller()

    controller.dispatch(RunSlashCommandCommand(raw="/plan approve"))

    events = controller.drain_events()
    assert any(
        isinstance(event, StatusUpdated)
        and event.field == "plan_decision"
        and event.value == "approve"
        for event in events
    )


def test_plan_slash_command_uses_plan_mode_state_machine() -> None:
    from xcode_cli.core.planning import PlanMode

    plan_mode = PlanMode()
    controller = _make_controller(plan_mode=plan_mode)

    controller.dispatch(RunSlashCommandCommand(raw="/plan enter"))
    enter_events = controller.drain_events()
    assert plan_mode.is_active is True
    assert any(isinstance(event, PlanUpdated) for event in enter_events)

    controller.dispatch(RunSlashCommandCommand(raw="/plan approve"))
    approve_events = controller.drain_events()
    assert plan_mode.is_active is False
    assert any(
        isinstance(event, StatusUpdated)
        and event.field == "plan_decision"
        and event.value == "approve"
        for event in approve_events
    )


def test_exit_slash_command_closes_controller() -> None:
    controller = _make_controller()

    controller.dispatch(RunSlashCommandCommand(raw="/exit"))

    assert controller._closed is True


# ── Batch 4/5 hardening: compacting state ────────────────────────

def test_compacting_state_blocks_submit_user_input() -> None:
    controller = _make_controller()
    controller._is_compacting = True

    controller.dispatch(SubmitUserInputCommand(text="hello while compacting"))

    events = controller.drain_events()
    assert any(isinstance(e, UICommandFailed) for e in events)
    assert not any(isinstance(e, UserMessageAdded) for e in events)


def test_compacting_state_blocks_slash_command() -> None:
    controller = _make_controller()
    controller._is_compacting = True

    controller.dispatch(RunSlashCommandCommand(raw="/help"))

    events = controller.drain_events()
    assert any(isinstance(e, UICommandFailed) for e in events)
    assert not any(isinstance(e, SystemNoticeAdded) for e in events)


def test_compact_sets_and_clears_compacting_flag() -> None:
    from xcode_cli.core.context import ContextManager
    from xcode_cli.core.llm import LLMResponse

    class FakeLLM:
        def complete(self, system_prompt, messages, tool_schemas, **kwargs):
            return LLMResponse(content="compact summary", tool_calls=[])

    controller = RuntimeController(
        llm_client=FakeLLM(),
        context_manager=ContextManager(max_tokens=1000),
        headless=True,
    )
    controller._history.extend(
        [{"role": "user", "content": f"message {idx}"} for idx in range(25)]
    )

    controller.dispatch(CompactCommand())
    assert controller._is_compacting is False  # Already completed in sync path

    events = controller.drain_events()
    assert isinstance(events[0], CompactionStarted)
    assert any(isinstance(e, CompactionCompleted) for e in events)


def test_compact_error_clears_compacting_flag() -> None:
    class BrokenContext:
        def compress(self, history, llm, previous_summary=""):
            raise RuntimeError("compress boom")

    controller = RuntimeController(context_manager=BrokenContext(), headless=True)
    controller._history.extend([{"role": "user", "content": "x"} for _ in range(25)])

    controller.dispatch(CompactCommand())
    assert controller._is_compacting is False

    events = controller.drain_events()
    assert any(isinstance(e, CompactionFailed) for e in events)
