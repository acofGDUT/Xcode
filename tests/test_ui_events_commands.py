"""Tests for UIEvent and UICommand types."""
import pytest

from xcode_cli.core.ui.commands import (
    CancelTurnCommand,
    CompactCommand,
    ExitCommand,
    PermissionDecisionCommand,
    PlanDecisionCommand,
    ResumeSessionCommand,
    RunSlashCommandCommand,
    SaveEnvCommand,
    SubmitUserInputCommand,
    UICommand,
    ViewportStateChangedCommand,
)
from xcode_cli.core.ui.events import (
    AssistantDelta,
    AssistantFinal,
    CompactionCompleted,
    CompactionFailed,
    CompactionSkipped,
    CompactionStarted,
    ConfigUpdated,
    DiffPreviewAvailable,
    CommandPreviewAvailable,
    PermissionClearedEvent,
    PermissionRequestEvent,
    PlanApprovalRequested,
    PlanUpdated,
    ResumeCompleted,
    ResumeListLoaded,
    StatusUpdated,
    SystemNoticeAdded,
    TaskStateChanged,
    ToolCallFinished,
    ToolCallStarted,
    ToolError,
    ToolOutputProduced,
    ToolRejected,
    TurnCancelled,
    UICommandFailed,
    UIEvent,
    UserMessageAdded,
)


class TestUICommands:
    """Tests for UICommand types."""

    def test_submit_user_input_command(self):
        """Test SubmitUserInputCommand carries expected fields."""
        cmd = SubmitUserInputCommand(text="hello")
        assert cmd.text == "hello"
        assert isinstance(cmd, UICommand)

    def test_run_slash_command_command(self):
        """Test RunSlashCommandCommand carries expected fields."""
        cmd = RunSlashCommandCommand(raw="/help")
        assert cmd.raw == "/help"
        assert isinstance(cmd, UICommand)

    def test_permission_decision_command(self):
        """Test PermissionDecisionCommand carries expected fields."""
        cmd = PermissionDecisionCommand(
            request_id="req_123",
            tool_call_id="call_456",
            choice="yes",
        )
        assert cmd.request_id == "req_123"
        assert cmd.tool_call_id == "call_456"
        assert cmd.choice == "yes"

    def test_permission_decision_command_choices(self):
        """Test PermissionDecisionCommand accepts valid choices."""
        for choice in ["yes", "no", "yes_all"]:
            cmd = PermissionDecisionCommand(
                request_id="req_123",
                tool_call_id="call_456",
                choice=choice,
            )
            assert cmd.choice == choice

    def test_cancel_turn_command(self):
        """Test CancelTurnCommand carries expected fields."""
        cmd = CancelTurnCommand(reason="user")
        assert cmd.reason == "user"
        assert isinstance(cmd, UICommand)

    def test_cancel_turn_command_default_reason(self):
        """Test CancelTurnCommand has default reason."""
        cmd = CancelTurnCommand()
        assert cmd.reason == "user"

    def test_resume_session_command(self):
        """Test ResumeSessionCommand carries expected fields."""
        cmd = ResumeSessionCommand(session_id="session_123")
        assert cmd.session_id == "session_123"

    def test_compact_command(self):
        """Test CompactCommand is a UICommand."""
        cmd = CompactCommand()
        assert isinstance(cmd, UICommand)

    def test_save_env_command(self):
        """Test SaveEnvCommand carries expected fields."""
        cmd = SaveEnvCommand(changes={"max_tokens": 1000, "theme": "dark"})
        assert cmd.changes == {"max_tokens": 1000, "theme": "dark"}

    def test_save_env_command_default_changes(self):
        """Test SaveEnvCommand has default empty changes."""
        cmd = SaveEnvCommand()
        assert cmd.changes == {}

    def test_plan_decision_command(self):
        """Test PlanDecisionCommand carries expected fields."""
        cmd = PlanDecisionCommand(decision="approve")
        assert cmd.decision == "approve"

    def test_plan_decision_command_choices(self):
        """Test PlanDecisionCommand accepts valid choices."""
        for decision in ["approve", "reject"]:
            cmd = PlanDecisionCommand(decision=decision)
            assert cmd.decision == decision

    def test_exit_command(self):
        """Test ExitCommand is a UICommand."""
        cmd = ExitCommand()
        assert isinstance(cmd, UICommand)

    def test_viewport_state_changed_command(self):
        """Test ViewportStateChangedCommand carries expected fields."""
        cmd = ViewportStateChangedCommand(is_at_bottom=True)
        assert cmd.is_at_bottom is True

    def test_viewport_state_changed_command_false(self):
        """Test ViewportStateChangedCommand with is_at_bottom=False."""
        cmd = ViewportStateChangedCommand(is_at_bottom=False)
        assert cmd.is_at_bottom is False

    def test_commands_are_frozen(self):
        """Test that commands are frozen dataclasses."""
        cmd = SubmitUserInputCommand(text="hello")
        with pytest.raises(AttributeError):
            cmd.text = "world"  # type: ignore

    def test_commands_carry_expected_fields(self):
        """Test that all commands carry expected fields."""
        commands = [
            SubmitUserInputCommand(text="hello"),
            RunSlashCommandCommand(raw="/help"),
            PermissionDecisionCommand(request_id="r", tool_call_id="t", choice="yes"),
            CancelTurnCommand(reason="user"),
            ResumeSessionCommand(session_id="s"),
            CompactCommand(),
            SaveEnvCommand(changes={}),
            PlanDecisionCommand(decision="approve"),
            ExitCommand(),
            ViewportStateChangedCommand(is_at_bottom=True),
        ]
        for cmd in commands:
            assert isinstance(cmd, UICommand)


class TestUIEvents:
    """Tests for UIEvent types."""

    def test_user_message_added(self):
        """Test UserMessageAdded carries expected fields."""
        event = UserMessageAdded(message_id="msg_123", content="hello")
        assert event.message_id == "msg_123"
        assert event.content == "hello"
        assert isinstance(event, UIEvent)

    def test_assistant_delta(self):
        """Test AssistantDelta carries expected fields."""
        event = AssistantDelta(turn_id="turn_123", delta="hello")
        assert event.turn_id == "turn_123"
        assert event.delta == "hello"

    def test_assistant_final(self):
        """Test AssistantFinal carries expected fields."""
        event = AssistantFinal(turn_id="turn_123", message_id="msg_456", content="hello world")
        assert event.turn_id == "turn_123"
        assert event.message_id == "msg_456"
        assert event.content == "hello world"

    def test_tool_call_started(self):
        """Test ToolCallStarted carries expected fields."""
        event = ToolCallStarted(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
            arguments={"path": "/test"},
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.tool_name == "read_file"
        assert event.arguments == {"path": "/test"}

    def test_tool_call_started_default_arguments(self):
        """Test ToolCallStarted has default empty arguments."""
        event = ToolCallStarted(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
        )
        assert event.arguments == {}

    def test_tool_call_finished(self):
        """Test ToolCallFinished carries expected fields."""
        event = ToolCallFinished(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
            success=True,
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.tool_name == "read_file"
        assert event.success is True

    def test_tool_output_produced(self):
        """Test ToolOutputProduced carries expected fields."""
        event = ToolOutputProduced(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
            output_type="result",
            content="file content",
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.tool_name == "read_file"
        assert event.output_type == "result"
        assert event.content == "file content"

    def test_tool_rejected(self):
        """Test ToolRejected carries expected fields."""
        event = ToolRejected(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="write_file",
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.tool_name == "write_file"

    def test_tool_error(self):
        """Test ToolError carries expected fields."""
        event = ToolError(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
            error="File not found",
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.tool_name == "read_file"
        assert event.error == "File not found"

    def test_diff_preview_available(self):
        """Test DiffPreviewAvailable carries expected fields."""
        event = DiffPreviewAvailable(
            turn_id="turn_123",
            tool_call_id="call_456",
            file_path="/test.py",
            diff_content="-old\n+new",
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.file_path == "/test.py"
        assert event.diff_content == "-old\n+new"

    def test_command_preview_available(self):
        """Test CommandPreviewAvailable carries expected fields."""
        event = CommandPreviewAvailable(
            turn_id="turn_123",
            tool_call_id="call_456",
            command="ls -la",
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.command == "ls -la"

    def test_permission_request_event(self):
        """Test PermissionRequestEvent carries expected fields."""
        event = PermissionRequestEvent(
            request_id="req_123",
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="write_file",
            scope="file",
            risk_summary="Write to file",
        )
        assert event.request_id == "req_123"
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
        assert event.tool_name == "write_file"
        assert event.scope == "file"
        assert event.risk_summary == "Write to file"

    def test_permission_cleared_event(self):
        """Test PermissionClearedEvent carries expected fields."""
        event = PermissionClearedEvent(
            request_id="req_123",
            tool_call_id="call_456",
        )
        assert event.request_id == "req_123"
        assert event.tool_call_id == "call_456"

    def test_task_state_changed(self):
        """Test TaskStateChanged carries expected fields."""
        event = TaskStateChanged(
            task_id="task_123",
            old_state="pending",
            new_state="in_progress",
            description="Implement feature",
        )
        assert event.task_id == "task_123"
        assert event.old_state == "pending"
        assert event.new_state == "in_progress"
        assert event.description == "Implement feature"

    def test_status_updated(self):
        """Test StatusUpdated carries expected fields."""
        event = StatusUpdated(field="tokens", value=1000)
        assert event.field == "tokens"
        assert event.value == 1000

    def test_compaction_events(self):
        """Test compaction events carry expected fields."""
        started = CompactionStarted()
        assert isinstance(started, UIEvent)

        completed = CompactionCompleted(summary="Summary", source_message_count=10)
        assert completed.summary == "Summary"
        assert completed.source_message_count == 10

        skipped = CompactionSkipped()
        assert isinstance(skipped, UIEvent)

        failed = CompactionFailed(error="Error")
        assert failed.error == "Error"

    def test_resume_events(self):
        """Test resume events carry expected fields."""
        loaded = ResumeListLoaded(sessions=[{"id": "s1"}])
        assert loaded.sessions == [{"id": "s1"}]

        completed = ResumeCompleted(
            session_id="s1",
            restored_from_checkpoint=True,
            message_count=10,
            estimated_tokens=1234,
            last_user_input="continue work",
        )
        assert completed.session_id == "s1"
        assert completed.restored_from_checkpoint is True
        assert completed.message_count == 10
        assert completed.estimated_tokens == 1234
        assert completed.last_user_input == "continue work"

    def test_resume_completed_event_carries_legacy_restore_metadata(self):
        """Test ResumeCompleted carries all legacy restore fields."""
        completed = ResumeCompleted(
            session_id="s1",
            restored_from_checkpoint=True,
            message_count=10,
            estimated_tokens=1234,
            last_user_input="continue the UI migration",
        )

        assert completed.session_id == "s1"
        assert completed.restored_from_checkpoint is True
        assert completed.message_count == 10
        assert completed.estimated_tokens == 1234
        assert completed.last_user_input == "continue the UI migration"

    def test_resume_completed_event_without_last_user_input(self):
        """Test ResumeCompleted allows last_user_input to be None."""
        completed = ResumeCompleted(
            session_id="s1",
            restored_from_checkpoint=False,
            message_count=5,
            estimated_tokens=500,
        )

        assert completed.session_id == "s1"
        assert completed.restored_from_checkpoint is False
        assert completed.message_count == 5
        assert completed.estimated_tokens == 500
        assert completed.last_user_input is None

    def test_config_updated(self):
        """Test ConfigUpdated carries expected fields."""
        event = ConfigUpdated(key="max_tokens", value=1000)
        assert event.key == "max_tokens"
        assert event.value == 1000

    def test_plan_events(self):
        """Test plan events carry expected fields."""
        approval = PlanApprovalRequested(plan_content="Plan")
        assert approval.plan_content == "Plan"

        updated = PlanUpdated(plan_content="Updated plan")
        assert updated.plan_content == "Updated plan"

    def test_system_notice_added(self):
        """Test SystemNoticeAdded carries expected fields."""
        event = SystemNoticeAdded(message_id="msg_123", content="Notice")
        assert event.message_id == "msg_123"
        assert event.content == "Notice"

    def test_ui_command_failed(self):
        """Test UICommandFailed carries expected fields."""
        event = UICommandFailed(command_type="SubmitUserInputCommand", error="Error")
        assert event.command_type == "SubmitUserInputCommand"
        assert event.error == "Error"

    def test_turn_cancelled(self):
        """Test TurnCancelled carries expected fields."""
        event = TurnCancelled(turn_id="turn_123", reason="user")
        assert event.turn_id == "turn_123"
        assert event.reason == "user"

    def test_events_are_frozen(self):
        """Test that events are frozen dataclasses."""
        event = UserMessageAdded(message_id="msg_123", content="hello")
        with pytest.raises(AttributeError):
            event.content = "world"  # type: ignore

    def test_tool_error_vs_ui_command_failed(self):
        """Test that ToolError and UICommandFailed are distinct."""
        tool_error = ToolError(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
            error="File not found",
        )
        ui_error = UICommandFailed(
            command_type="SubmitUserInputCommand",
            error="Error",
        )
        assert type(tool_error) != type(ui_error)
        assert isinstance(tool_error, UIEvent)
        assert isinstance(ui_error, UIEvent)

    def test_event_ids_are_stable(self):
        """Test that events carry stable ids where needed."""
        event = ToolCallStarted(
            turn_id="turn_123",
            tool_call_id="call_456",
            tool_name="read_file",
        )
        assert event.turn_id == "turn_123"
        assert event.tool_call_id == "call_456"
