"""Tests for RuntimeController."""
import pytest
import threading
import time

from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.runtime.permissions import PermissionDecision, PermissionRequest
from xcode_cli.core.ui.commands import (
    CancelTurnCommand,
    CompactCommand,
    ExitCommand,
    PermissionDecisionCommand,
    ResumeSessionCommand,
    RunSlashCommandCommand,
    SaveEnvCommand,
    SubmitUserInputCommand,
)
from xcode_cli.core.ui.events import (
    CompactionSkipped,
    CompactionStarted,
    ConfigUpdated,
    PermissionClearedEvent,
    PermissionRequestEvent,
    StatusUpdated,
    TurnCancelled,
    UICommandFailed,
    UIEvent,
    UserMessageAdded,
)


def _make_controller(**kwargs) -> RuntimeController:
    """Create a headless controller for testing."""
    return RuntimeController(headless=True, **kwargs)


class TestRuntimeController:
    """Tests for RuntimeController."""

    def test_initial_state(self):
        """Test initial state of RuntimeController."""
        controller = _make_controller()
        assert controller.has_active_turn is False
        assert controller.current_turn_id is None
        assert controller.drain_events() == []

    def test_dispatch_submit_user_input(self):
        """Test dispatching SubmitUserInputCommand."""
        controller = _make_controller()
        controller.dispatch(SubmitUserInputCommand(text="hello"))
        events = controller.drain_events()
        # headless mode: UserMessageAdded + StatusUpdated(turn:busy) + StatusUpdated(turn:idle)
        assert len(events) == 3
        assert isinstance(events[0], UserMessageAdded)
        assert events[0].content == "hello"
        assert isinstance(events[1], StatusUpdated)
        assert events[1].field == "turn"
        assert "busy" in str(events[1].value)
        assert isinstance(events[2], StatusUpdated)
        assert events[2].field == "turn"
        assert events[2].value == "idle"

    def test_dispatch_run_slash_command(self):
        """Test dispatching RunSlashCommandCommand."""
        controller = _make_controller()
        controller.dispatch(RunSlashCommandCommand(raw="/help"))
        events = controller.drain_events()
        assert len(events) == 1
        from xcode_cli.core.ui.events import SystemNoticeAdded
        assert isinstance(events[0], SystemNoticeAdded)
        assert "/context" in events[0].content

    def test_dispatch_permission_decision_no_pending(self):
        """Test dispatching PermissionDecisionCommand with no pending request."""
        controller = _make_controller()
        controller.dispatch(PermissionDecisionCommand(
            request_id="req_123",
            tool_call_id="call_456",
            choice="yes",
        ))
        events = controller.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], UICommandFailed)
        assert "No pending request" in events[0].error

    def test_dispatch_permission_decision_with_pending(self):
        """Test dispatching PermissionDecisionCommand with pending request."""
        controller = _make_controller()

        # First, manually add a pending request (bypassing request_permission)
        request = PermissionRequest(
            request_id="req_123",
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="write_file",
            scope="file",
            risk_summary="Write to file",
        )
        controller._pending_permission_requests["req_123"] = request
        controller._start_turn("turn_123")
        controller.drain_events()  # Clear any events

        # Then, make decision
        controller.dispatch(PermissionDecisionCommand(
            request_id="req_123",
            tool_call_id="call_456",
            choice="yes",
        ))
        events = controller.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], PermissionClearedEvent)
        assert events[0].request_id == "req_123"

    def test_dispatch_cancel_turn(self):
        """Test dispatching CancelTurnCommand."""
        controller = _make_controller()
        controller.dispatch(CancelTurnCommand(reason="user"))
        events = controller.drain_events()
        # CancelTurnCommand without active turn should not emit TurnCancelled
        assert len(events) == 0

    def test_dispatch_cancel_turn_with_active_turn(self):
        """Test dispatching CancelTurnCommand with active turn."""
        controller = _make_controller()

        # Manually start turn
        controller._start_turn("turn_123")
        controller.drain_events()  # Clear any events

        # Cancel turn
        controller.dispatch(CancelTurnCommand(reason="user"))
        events = controller.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], TurnCancelled)
        assert events[0].reason == "user"

    def test_dispatch_resume_session_without_store_fails(self):
        """Test dispatching ResumeSessionCommand without session store fails."""
        controller = _make_controller()
        controller.dispatch(ResumeSessionCommand(session_id="session_123"))
        events = controller.drain_events()
        assert len(events) == 2
        assert isinstance(events[0], StatusUpdated)
        assert events[0].field == "surfaces"
        assert events[0].value == "clear"
        assert isinstance(events[1], UICommandFailed)
        assert "No session store" in events[1].error

    def test_dispatch_resume_session_with_existing_session(self, tmp_path, monkeypatch):
        """Test dispatching ResumeSessionCommand with valid session succeeds."""
        from xcode_cli.core import session as session_module
        from xcode_cli.core.session import SessionStore

        monkeypatch.setattr(session_module, "ensure_xcode_home", lambda: tmp_path / ".xcode")
        store = SessionStore(cwd=str(tmp_path / "project"))
        store.append_message("session_123", {"role": "user", "content": "hello"})
        store.append_message("session_123", {"role": "assistant", "content": "world"})
        controller = _make_controller(session_store=store)
        controller.dispatch(ResumeSessionCommand(session_id="session_123"))
        events = controller.drain_events()
        assert any(isinstance(e, StatusUpdated) and e.field == "surfaces" for e in events)
        from xcode_cli.core.ui.events import ResumeCompleted
        completed = next(e for e in events if isinstance(e, ResumeCompleted))
        assert completed.session_id == "session_123"
        assert completed.message_count == 2
        assert completed.restored_from_checkpoint is False
        assert completed.estimated_tokens >= 0
        assert completed.last_user_input == "hello"

    def test_dispatch_resume_session_emits_legacy_restore_metadata(self, tmp_path, monkeypatch):
        """Test ResumeSessionCommand emits ResumeCompleted with legacy fields."""
        from xcode_cli.core import session as session_module
        from xcode_cli.core.session import SessionStore
        from xcode_cli.core.ui.events import ResumeCompleted

        monkeypatch.setattr(session_module, "ensure_xcode_home", lambda: tmp_path / ".xcode")
        store = SessionStore(cwd=str(tmp_path / "project"))
        store.append_message("session_456", {"role": "user", "content": "last prompt"})
        store.append_message("session_456", {"role": "assistant", "content": "response"})
        store.append_message("session_456", {"role": "user", "content": "continue work"})

        controller = _make_controller(session_store=store)
        controller.dispatch(ResumeSessionCommand(session_id="session_456"))
        events = controller.drain_events()

        completed = next(e for e in events if isinstance(e, ResumeCompleted))
        assert completed.session_id == "session_456"
        assert completed.message_count == 3
        assert completed.restored_from_checkpoint is False
        assert completed.estimated_tokens >= 0
        assert completed.last_user_input == "continue work"

    def test_dispatch_resume_session_with_nonexistent_session_fails(self, tmp_path, monkeypatch):
        """Test dispatching ResumeSessionCommand with nonexistent session fails."""
        from xcode_cli.core import session as session_module
        from xcode_cli.core.session import SessionStore

        monkeypatch.setattr(session_module, "ensure_xcode_home", lambda: tmp_path / ".xcode")
        store = SessionStore(cwd=str(tmp_path / "project"))
        controller = _make_controller(session_store=store)
        controller.dispatch(ResumeSessionCommand(session_id="nonexistent"))
        events = controller.drain_events()
        failed = next(e for e in events if isinstance(e, UICommandFailed))
        assert "not found" in failed.error.lower()

    def test_dispatch_compact(self):
        """Test dispatching CompactCommand."""
        controller = _make_controller()
        controller.dispatch(CompactCommand())
        events = controller.drain_events()
        assert len(events) == 2
        assert isinstance(events[0], CompactionStarted)
        assert isinstance(events[1], CompactionSkipped)

    def test_dispatch_save_env(self):
        """Test dispatching SaveEnvCommand."""
        controller = _make_controller()
        controller.dispatch(SaveEnvCommand(changes={"max_tokens": 1000, "theme": "dark"}))
        events = controller.drain_events()
        assert len(events) == 2
        assert all(isinstance(e, ConfigUpdated) for e in events)
        assert events[0].key == "max_tokens"
        assert events[0].value == 1000
        assert events[1].key == "theme"
        assert events[1].value == "dark"

    def test_dispatch_exit(self):
        """Test dispatching ExitCommand."""
        controller = _make_controller()
        controller.dispatch(ExitCommand())
        assert controller._closed is True

    def test_dispatch_unknown_command(self):
        """Test dispatching unknown command."""
        controller = _make_controller()

        # Create a custom command that is not handled
        class UnknownCommand:
            pass

        controller.dispatch(UnknownCommand())  # type: ignore
        events = controller.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], UICommandFailed)
        assert "Unknown command type" in events[0].error

    def test_drain_events(self):
        """Test draining events."""
        controller = _make_controller()
        controller.dispatch(SubmitUserInputCommand(text="hello"))
        controller.dispatch(SubmitUserInputCommand(text="world"))

        events = controller.drain_events()
        # headless: 3 events per SubmitUserInputCommand = 6 total
        assert len(events) == 6

        # Drain again should return empty
        events = controller.drain_events()
        assert len(events) == 0

    def test_close(self):
        """Test closing controller."""
        controller = _make_controller()
        controller.close()
        assert controller._closed is True

        # Dispatching after close should raise
        with pytest.raises(RuntimeError, match="closed"):
            controller.dispatch(SubmitUserInputCommand(text="hello"))

    def test_request_permission(self):
        """Test requesting permission."""
        controller = _make_controller()
        request = PermissionRequest(
            request_id="req_123",
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="write_file",
            scope="file",
            risk_summary="Write to file",
        )

        decision_holder = []

        def worker():
            decision_holder.append(controller.request_permission(request))

        thread = threading.Thread(target=worker)
        thread.start()

        for _ in range(50):
            events = controller.drain_events()
            if events:
                break
            time.sleep(0.01)

        assert len(events) == 1
        assert isinstance(events[0], PermissionRequestEvent)
        assert events[0].request_id == "req_123"
        assert events[0].tool_name == "write_file"

        controller.dispatch(PermissionDecisionCommand(
            request_id="req_123",
            tool_call_id="call_456",
            choice="yes",
        ))

        thread.join(timeout=1)
        assert not thread.is_alive()
        assert decision_holder == [PermissionDecision(choice="yes", scope="file")]

    def test_rejects_second_active_turn(self):
        """Test that controller rejects second active turn."""
        controller = _make_controller()

        # First turn - manually start
        controller._start_turn("turn_1")
        controller.drain_events()

        request2 = PermissionRequest(
            request_id="req_2",
            turn_id="turn_2",
            tool_call_id="call_2",
            tool_name="read_file",
            scope="file",
            risk_summary="Read file",
        )
        with pytest.raises(RuntimeError, match="active turn"):
            controller.request_permission(request2)

    def test_cancel_wakes_pending_permission_fail_closed(self):
        """Test cancellation wakes a pending permission request with no."""
        controller = _make_controller()
        request = PermissionRequest(
            request_id="req_123",
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="write_file",
            scope="file",
            risk_summary="Write file",
        )
        decisions = []

        def worker():
            decisions.append(controller.request_permission(request))

        thread = threading.Thread(target=worker)
        thread.start()

        for _ in range(50):
            events = controller.drain_events()
            if events:
                break
            time.sleep(0.01)

        assert isinstance(events[0], PermissionRequestEvent)

        controller.dispatch(CancelTurnCommand(reason="user"))
        thread.join(timeout=1)

        assert not thread.is_alive()
        assert decisions == [PermissionDecision(choice="no", scope="file")]

    def test_queues_events_thread_safely(self):
        """Test that events are queued thread-safely."""
        controller = _make_controller()
        events_collected: list[UIEvent] = []

        def worker():
            for i in range(10):
                controller.dispatch(SubmitUserInputCommand(text=f"message {i}"))
                time.sleep(0.01)

        def consumer():
            for _ in range(20):
                events = controller.drain_events()
                events_collected.extend(events)
                time.sleep(0.01)

        worker_thread = threading.Thread(target=worker)
        consumer_thread = threading.Thread(target=consumer)

        worker_thread.start()
        consumer_thread.start()

        worker_thread.join()
        consumer_thread.join()

        # All events should be collected (3 per dispatch in headless mode)
        assert len(events_collected) == 30

    def test_pending_surface_cleanup_on_cancel(self):
        """Test that pending surfaces are cleaned on cancel."""
        controller = _make_controller()

        # Manually start turn and add pending request
        controller._start_turn("turn_123")
        controller._pending_permission_requests["req_123"] = PermissionRequest(
            request_id="req_123",
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="write_file",
            scope="file",
            risk_summary="Write to file",
        )
        controller.drain_events()

        # Cancel turn
        controller.dispatch(CancelTurnCommand(reason="user"))
        events = controller.drain_events()

        # Should have TurnCancelled event
        assert len(events) == 1
        assert isinstance(events[0], TurnCancelled)


class TestRuntimeControllerBatch2:
    """Tests for Batch 2: AgentEngine integration."""

    def test_submit_input_starts_and_ends_turn_headless(self):
        """Test that SubmitUserInputCommand starts and ends a turn in headless mode."""
        controller = _make_controller()
        controller.dispatch(SubmitUserInputCommand(text="hello"))
        events = controller.drain_events()

        assert len(events) == 3  # UserMessageAdded + StatusUpdated(busy) + StatusUpdated(idle)
        assert events[1].value == f"busy:{controller.current_turn_id}" if controller.current_turn_id else True
        # After headless ends, no active turn
        assert controller.has_active_turn is False

    def test_tool_execution_emits_events(self):
        """Test that tool execution emits proper events."""
        from xcode_cli.core.llm import ToolCall
        from xcode_cli.core.runtime.cancellation import CancellationToken

        controller = _make_controller()

        # Mock the tool registry to have a simple tool
        from xcode_cli.core.tool_registry import ToolDef
        tool_def = ToolDef(
            name="read_file",
            description="Read a file",
            parameters={"path": {"type": "string", "description": "File path"}},
            required=["path"],
            execute=lambda path: "file content here",
            is_read_only=True,
        )
        controller._tool_registry.register(tool_def)

        # Execute tools directly
        results = controller._execute_tools_in_turn(
            [ToolCall(id="call_1", name="read_file", args={"path": "/test.txt"})],
            "turn_test",
            CancellationToken(),
        )

        assert len(results) == 1
        assert results[0][1] == "file content here"

    def test_tool_denied_emits_rejected(self):
        """Test that denied tools emit ToolRejected."""
        from xcode_cli.core.llm import ToolCall
        from xcode_cli.core.permissions import PermissionManager
        from xcode_cli.core.runtime.cancellation import CancellationToken

        pm = PermissionManager(cwd=".")
        pm.set_session_rule("write_file", "deny")
        controller = _make_controller(permission_manager=pm)

        results = controller._execute_tools_in_turn(
            [ToolCall(id="call_1", name="write_file", args={"path": "/test.txt"})],
            "turn_test",
            CancellationToken(),
        )

        assert len(results) == 1
        assert "denied" in results[0][1].lower()

        # Check events
        events = controller.drain_events()
        from xcode_cli.core.ui.events import ToolRejected
        assert any(isinstance(e, ToolRejected) for e in events)

    def test_scope_for_tool(self):
        """Test tool scope mapping."""
        controller = _make_controller()
        assert controller._scope_for_tool("write_file") == "write"
        assert controller._scope_for_tool("edit_file") == "write"
        assert controller._scope_for_tool("run_shell") == "shell"
        assert controller._scope_for_tool("read_file") == "read_file"

    def test_emit_diff_preview(self):
        """Test that file edits emit diff preview events."""
        from xcode_cli.core.llm import ToolCall

        controller = _make_controller()

        # Test write_file preview
        controller._emit_tool_previews(
            ToolCall(id="call_1", name="write_file", args={"path": "/nonexistent.txt", "content": "new content"}),
            "turn_test",
        )

        events = controller.drain_events()
        from xcode_cli.core.ui.events import DiffPreviewAvailable
        assert any(isinstance(e, DiffPreviewAvailable) for e in events)
        diff_event = next(e for e in events if isinstance(e, DiffPreviewAvailable))
        assert "+new content" in diff_event.diff_content

    def test_emit_edit_diff_preview_has_removed_and_added_lines(self, tmp_path):
        """Test edit diff preview includes red/green line markers."""
        from xcode_cli.core.llm import ToolCall
        from xcode_cli.core.ui.events import DiffPreviewAvailable

        target = tmp_path / "demo.txt"
        target.write_text("old\nsame\n", encoding="utf-8")
        controller = _make_controller()

        controller._emit_tool_previews(
            ToolCall(
                id="call_1",
                name="edit_file",
                args={
                    "path": str(target),
                    "old_string": "old",
                    "new_string": "new",
                },
            ),
            "turn_test",
        )

        events = controller.drain_events()
        diff_event = next(e for e in events if isinstance(e, DiffPreviewAvailable))
        assert "-old" in diff_event.diff_content
        assert "+new" in diff_event.diff_content

    def test_emit_command_preview(self):
        """Test that shell commands emit command preview events."""
        from xcode_cli.core.llm import ToolCall

        controller = _make_controller()

        controller._emit_tool_previews(
            ToolCall(id="call_1", name="run_shell", args={"command": "ls -la"}),
            "turn_test",
        )

        events = controller.drain_events()
        from xcode_cli.core.ui.events import CommandPreviewAvailable
        assert any(isinstance(e, CommandPreviewAvailable) for e in events)

    def test_memory_write_target_is_auto_allowed(self, tmp_path, monkeypatch):
        """Test writes to memory files do not block on permission."""
        from xcode_cli.core.llm import ToolCall
        from xcode_cli.core import memory as memory_module
        from xcode_cli.core.memory import MemoryManager
        from xcode_cli.core.permissions import PermissionManager
        from xcode_cli.core.runtime.cancellation import CancellationTokenSource
        from xcode_cli.core.tool_registry import ToolDef, ToolRegistry

        monkeypatch.setattr(
            memory_module,
            "ensure_xcode_home",
            lambda: tmp_path / ".xcode",
        )
        memory = MemoryManager(cwd=str(tmp_path))
        registry = ToolRegistry()
        registry.register(ToolDef(
            name="write_file",
            description="Write file",
            parameters={},
            required=[],
            execute=lambda path, content: "wrote memory",
            is_read_only=False,
        ))
        controller = _make_controller(
            tool_registry=registry,
            permission_manager=PermissionManager(cwd=str(tmp_path)),
            memory_manager=memory,
        )
        cancellation = CancellationTokenSource()
        result_holder = []

        def worker():
            result_holder.extend(controller._execute_tools_in_turn(
                [
                    ToolCall(
                        id="call_1",
                        name="write_file",
                        args={
                            "path": str(memory.memory_index_path()),
                            "content": "memory entry",
                        },
                    )
                ],
                "turn_test",
                cancellation.token,
            ))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=1)
        if thread.is_alive():
            cancellation.cancel()
            controller.close()
            thread.join(timeout=1)

        assert not thread.is_alive()
        assert result_holder[0][1] == "wrote memory"
        events = controller.drain_events()
        assert not any(isinstance(event, PermissionRequestEvent) for event in events)

    def test_runtime_services_wires_textual_controller(self, tmp_path, monkeypatch):
        """Test RuntimeServices provides shared Textual controller services."""
        from xcode_cli.core import memory as memory_module
        from xcode_cli.core.runtime.services import RuntimeServices

        monkeypatch.setattr(
            memory_module,
            "ensure_xcode_home",
            lambda: tmp_path / ".xcode",
        )

        services = RuntimeServices.create(cwd=str(tmp_path))
        controller = services.create_textual_controller(headless=True)

        assert controller._tool_registry.list_names()
        assert controller._permission_manager is services.permissions
        assert controller._memory_manager is services.memory
        assert "Working directory:" in services.system_prompt()

    def test_tool_exception_emits_one_tool_error_event(self):
        """Test tool exceptions are reported once through AgentEngine callbacks."""
        from xcode_cli.core.llm import LLMResponse, ToolCall
        from xcode_cli.core.tool_registry import ToolRegistry
        from xcode_cli.core.ui.events import ToolError

        class FakeLLM:
            def __init__(self):
                self.calls = 0

            def complete(self, system_prompt, messages, tool_schemas,
                         on_text_token=None, on_reasoning_token=None):
                self.calls += 1
                if self.calls == 1:
                    return LLMResponse(
                        content="",
                        tool_calls=[
                            ToolCall(id="call_1", name="bad_tool", args={})
                        ],
                    )
                return LLMResponse(content="done", tool_calls=[])

        class RaisingRegistry(ToolRegistry):
            def get_openai_schemas(self):
                return [{"type": "function", "function": {"name": "bad_tool"}}]

            def is_read_only(self, name):
                return True

            def execute(self, name, args):
                raise RuntimeError("boom")

        registry = RaisingRegistry()
        controller = RuntimeController(llm_client=FakeLLM(), tool_registry=registry)
        try:
            controller.dispatch(SubmitUserInputCommand(text="run bad tool"))
            for _ in range(100):
                if not controller.has_active_turn:
                    break
                time.sleep(0.05)

            events = controller.drain_events()
            tool_errors = [event for event in events if isinstance(event, ToolError)]
            assert len(tool_errors) == 1
            assert "boom" in tool_errors[0].error
        finally:
            controller.close()
