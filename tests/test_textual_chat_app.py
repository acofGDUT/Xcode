"""Tests for Textual ChatApp."""
import pytest
from unittest.mock import MagicMock, patch

from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.ui.commands import (
    CancelTurnCommand,
    ExitCommand,
    PermissionDecisionCommand,
    RunSlashCommandCommand,
    SubmitUserInputCommand,
    ViewportStateChangedCommand,
)
from xcode_cli.core.ui.events import (
    AssistantDelta,
    AssistantFinal,
    CommandPreviewAvailable,
    CompactionCompleted,
    CompactionFailed,
    CompactionSkipped,
    CompactionStarted,
    DiffPreviewAvailable,
    ConfigUpdated,
    PermissionClearedEvent,
    PermissionRequestEvent,
    PlanApprovalRequested,
    PlanUpdated,
    ResumeCompleted,
    ResumeListLoaded,
    ToolCallFinished,
    ToolCallStarted,
    ToolOutputProduced,
    TurnCancelled,
    SystemNoticeAdded,
    UICommandFailed,
    UserMessageAdded,
)
from xcode_cli.core.ui.state import UserMessageBlock
from xcode_cli.core.ui.textual.app import ChatApp
from xcode_cli.core.ui.textual.renderers import RichLogRenderer
from xcode_cli.core.ui.textual.widgets import (
    ApprovalCard,
    InputBox,
    NewMessagesPill,
    PermissionPrompt,
    PetSurface,
    StatusBar,
    StreamingWidget,
    TranscriptArea,
    UserInputSubmitted,
)


def _make_controller(**kwargs) -> RuntimeController:
    """Create a headless controller for testing."""
    return RuntimeController(headless=True, **kwargs)


class TestChatApp:
    """Tests for ChatApp."""

    def test_app_initialization(self):
        """Test ChatApp initialization."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        assert app.controller is controller
        assert app.store is not None
        assert app._is_at_bottom is True

    def test_app_composition(self):
        """Test ChatApp composition."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        assert app is not None

    def test_app_bindings(self):
        """Test ChatApp bindings."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        assert ("ctrl+c", "cancel", "Cancel") in app.BINDINGS
        assert ("ctrl+q", "quit", "Quit") in app.BINDINGS


class TestWidgets:
    """Tests for Textual widgets."""

    def test_streaming_widget(self):
        """Test StreamingWidget."""
        widget = StreamingWidget()
        assert widget.text == ""
        widget.update_text("hello")
        assert widget.text == "hello"
        widget.clear_text()
        assert widget.text == ""

    def test_new_messages_pill(self):
        """Test NewMessagesPill."""
        widget = NewMessagesPill()
        assert widget.message_count == 0
        assert widget.display is True
        widget.show_pill(5)
        assert widget.message_count == 5
        assert widget.display is True
        assert widget.render() == "5 new messages"
        widget.hide_pill()
        assert widget.message_count == 0
        assert widget.display is False

    def test_status_bar(self):
        """Test StatusBar."""
        widget = StatusBar()
        assert widget.status_text == ""
        widget.update_status("Test status")
        assert widget.status_text == "Test status"

    def test_pet_surface(self):
        """Test PetSurface is hidden by default."""
        widget = PetSurface()
        assert widget.display is True


class TestEventHandler:
    """Tests for ChatApp event handling."""

    def test_handle_user_message_added(self):
        """Test handling UserMessageAdded event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = UserMessageAdded(message_id="msg_123", content="Hello")
        assert event.message_id == "msg_123"

    def test_handle_assistant_delta(self):
        """Test handling AssistantDelta event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = AssistantDelta(turn_id="turn_123", delta="Hello")
        assert event.turn_id == "turn_123"

    def test_handle_assistant_final(self):
        """Test handling AssistantFinal event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = AssistantFinal(turn_id="turn_123", message_id="msg_456", content="Hello world")
        assert event.content == "Hello world"

    def test_handle_resume_list_loaded_adds_system_notice(self):
        """Test ResumeListLoaded enters resume selection state."""
        controller = _make_controller()
        app = ChatApp(controller=controller)

        # Mock query_one to return a fake ResumeSelector
        from xcode_cli.core.ui.textual.widgets import ResumeSelector
        fake_selector = ResumeSelector()
        app.query_one = lambda *args, **kwargs: fake_selector

        app.handle_event(ResumeListLoaded(sessions=[
            {
                "session_id": "session_1",
                "last_user_input": "hello",
                "message_count": 3,
                "has_checkpoint": True,
            }
        ]))

        assert app._is_resume_selecting is True
        assert len(fake_selector.sessions) == 1
        assert fake_selector.sessions[0]["session_id"] == "session_1"

    def test_handle_config_updated_redacts_visible_secret(self):
        """Test ConfigUpdated is consumed without leaking secret values."""
        controller = _make_controller()
        app = ChatApp(controller=controller)

        app.handle_event(ConfigUpdated(key="api_key", value="***"))

        assert any(
            getattr(block, "kind", None) == "system_notice"
            and "api_key" in getattr(block, "content", "")
            and "***" in getattr(block, "content", "")
            for block in app.store.message_blocks
        )

    def test_handle_plan_events_add_system_notices(self):
        """Test plan update and approval events are visible."""
        controller = _make_controller()
        app = ChatApp(controller=controller)

        app.handle_event(PlanUpdated(plan_content="Planning mode entered."))
        app.handle_event(PlanApprovalRequested(plan_content="Review this plan."))

        contents = [
            getattr(block, "content", "")
            for block in app.store.message_blocks
            if getattr(block, "kind", None) == "system_notice"
        ]
        assert any("Planning mode entered" in content for content in contents)
        assert any("Review this plan" in content for content in contents)

    def test_handle_resume_completed_adds_system_notice(self):
        """Test ResumeCompleted is visible."""
        controller = _make_controller()
        app = ChatApp(controller=controller)

        app.handle_event(ResumeCompleted(
            session_id="session_1",
            restored_from_checkpoint=True,
            message_count=5,
            estimated_tokens=678,
            last_user_input="continue from last turn",
        ))

        assert any(
            getattr(block, "kind", None) == "system_notice"
            and "session_1" in getattr(block, "content", "")
            and "5" in getattr(block, "content", "")
            for block in app.store.message_blocks
        )


class TestInputHandling:
    """Tests for input handling."""

    def test_on_input_submitted_user_input(self):
        """Test handling user input submission."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = UserInputSubmitted("Hello")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)
        events = controller.drain_events()
        # headless: 3 events (UserMessageAdded + StatusUpdated(busy) + StatusUpdated(idle))
        assert len(events) == 3
        assert events[0].content == "Hello"

    def test_on_input_submitted_slash_command(self):
        """Test handling slash command submission."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = UserInputSubmitted("/help")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)
        events = controller.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], SystemNoticeAdded)
        assert "/context" in events[0].content

    def test_on_input_submitted_empty(self):
        """Test handling empty input submission."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = UserInputSubmitted("")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)
        events = controller.drain_events()
        assert len(events) == 0

    def test_input_blocked_during_permission(self):
        """Test input is blocked while permission is pending."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._pending_permission = True
        event = UserInputSubmitted("hello")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)
        # Should get a system notice about permission
        blocks = app.store.message_blocks
        assert any("permission" in b.content.lower() for b in blocks
                   if hasattr(b, 'content') and isinstance(b.content, str))


class TestRichLogRenderer:
    """Tests for RichLog rendering safety."""

    def test_user_message_content_is_not_written_as_markup_string(self):
        """Test user content is rendered as Text, not raw Rich markup."""
        rich_log = MagicMock()
        renderer = RichLogRenderer(rich_log)
        renderer.append(UserMessageBlock(id="msg_1", content="[red]bad[/red]"))
        written = rich_log.write.call_args.args[0]
        assert written.plain == "You: [red]bad[/red]"


class TestActions:
    """Tests for ChatApp actions."""

    def test_action_cancel(self):
        """Test cancel action."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app.action_cancel()
        events = controller.drain_events()
        assert len(events) == 0  # CancelTurnCommand without active turn

    def test_action_quit(self):
        """Test quit action."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app.exit = MagicMock()
        app.action_quit()
        assert controller._closed is True
        app.exit.assert_called_once()


class TestEventPolling:
    """Tests for event polling."""

    def test_poll_events(self):
        """Test polling events from controller."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        controller.dispatch(SubmitUserInputCommand(text="Hello"))
        events = controller.drain_events()
        assert len(events) == 3  # UserMessageAdded + StatusUpdated(busy) + StatusUpdated(idle)


class TestViewportState:
    """Tests for viewport state handling."""

    def test_on_scroll_at_bottom(self):
        """Test scroll event when at bottom."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_at_bottom = True
        dispatched_commands = []
        original_dispatch = controller.dispatch
        def mock_dispatch(command):
            dispatched_commands.append(command)
            original_dispatch(command)
        controller.dispatch = mock_dispatch
        event = MagicMock()
        mock_pill = MagicMock()
        app.query_one = MagicMock(return_value=mock_pill)
        app.on_scroll(event)
        assert len(dispatched_commands) == 1
        assert isinstance(dispatched_commands[0], ViewportStateChangedCommand)
        assert dispatched_commands[0].is_at_bottom is True
        mock_pill.hide_pill.assert_called_once()

    def test_on_scroll_not_at_bottom(self):
        """Test scroll event when not at bottom."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_at_bottom = False
        dispatched_commands = []
        original_dispatch = controller.dispatch
        def mock_dispatch(command):
            dispatched_commands.append(command)
            original_dispatch(command)
        controller.dispatch = mock_dispatch
        event = MagicMock()
        mock_pill = MagicMock()
        app.query_one = MagicMock(return_value=mock_pill)
        app.on_scroll(event)
        assert len(dispatched_commands) == 1
        assert isinstance(dispatched_commands[0], ViewportStateChangedCommand)
        assert dispatched_commands[0].is_at_bottom is False
        mock_pill.hide_pill.assert_not_called()


# ── Batch 2: Tool events ─────────────────────────────────────────

class TestToolEventHandling:
    """Tests for Batch 2 tool event handling."""

    def test_handle_tool_call_started(self):
        """Test ToolCallStarted event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = ToolCallStarted(
            turn_id="turn_1",
            tool_call_id="call_1",
            tool_name="read_file",
            arguments={"path": "/test.txt"},
        )
        assert event.tool_name == "read_file"
        assert event.tool_call_id == "call_1"

    def test_handle_tool_call_finished(self):
        """Test ToolCallFinished event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = ToolCallFinished(
            turn_id="turn_1",
            tool_call_id="call_1",
            tool_name="read_file",
            success=True,
        )
        assert event.success is True

    def test_handle_tool_output(self):
        """Test ToolOutputProduced event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = ToolOutputProduced(
            turn_id="turn_1",
            tool_call_id="call_1",
            tool_name="read_file",
            output_type="result",
            content="file contents",
        )
        assert event.output_type == "result"
        assert event.content == "file contents"


# ── Batch 3: Permission and preview surfaces ──────────────────────

class TestPermissionHandling:
    """Tests for Batch 3 permission handling."""

    def test_permission_request_event(self):
        """Test PermissionRequestEvent."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = PermissionRequestEvent(
            request_id="req_1",
            turn_id="turn_1",
            tool_call_id="call_1",
            tool_name="write_file",
            scope="write",
            risk_summary="Write to /test.txt",
        )
        assert event.tool_name == "write_file"
        assert event.scope == "write"

    def test_permission_cleared_event(self):
        """Test PermissionClearedEvent."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = PermissionClearedEvent(
            request_id="req_1",
            tool_call_id="call_1",
        )
        assert event.request_id == "req_1"

    def test_diff_preview_event(self):
        """Test DiffPreviewAvailable event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = DiffPreviewAvailable(
            turn_id="turn_1",
            tool_call_id="call_1",
            file_path="/test.txt",
            diff_content="old\nnew",
        )
        assert event.file_path == "/test.txt"
        assert event.diff_content == "old\nnew"

    def test_command_preview_event(self):
        """Test CommandPreviewAvailable event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = CommandPreviewAvailable(
            turn_id="turn_1",
            tool_call_id="call_1",
            command="ls -la",
        )
        assert event.command == "ls -la"

    def test_permission_prompt_widget(self):
        """Test PermissionPrompt widget."""
        widget = PermissionPrompt()
        assert widget.display is True
        widget.show_prompt("req_1", "call_1", "write_file", "write", "Risk")
        assert widget.request_id == "req_1"
        assert widget.tool_name == "write_file"
        assert widget.scope == "write"
        rendered = widget.render()
        assert "write_file" in rendered
        assert "write" in rendered
        widget.hide_prompt()
        assert widget.display is False
        assert widget.render() == ""

    def test_approval_card_renders_colored_diff_and_actions(self):
        """Test approval card renders compact diff with selectable rows."""
        card = ApprovalCard()
        card.show_request(
            request_id="req_1",
            tool_call_id="call_1",
            tool_name="write_file",
            scope="write",
            risk_summary="Write file",
        )
        card.show_diff("file.txt", "- old\n+ new\n unchanged")

        rendered = card.render()

        assert "write_file" in rendered.plain
        assert "\n> Yes" in rendered.plain
        assert "\n  No" in rendered.plain
        assert "\n  Yes, this conversation" in rendered.plain
        assert "- old" in rendered.plain
        assert "+ new" in rendered.plain
        assert rendered.spans

    def test_approval_card_reserves_space_for_all_choices(self):
        """Test long diffs are compacted so all choices remain visible."""
        card = ApprovalCard()
        card.show_request(
            request_id="req_1",
            tool_call_id="call_1",
            tool_name="edit_file",
            scope="write",
            risk_summary="Edit file",
        )
        card.show_diff(
            "file.txt",
            "\n".join([
                "--- file.txt",
                "+++ file.txt",
                "@@ -1,6 +1,6 @@",
                "- old one",
                "+ new one",
                " context",
                "- old two",
                "+ new two",
            ]),
        )

        rendered = card.render()

        assert len(rendered.plain.splitlines()) <= 9
        assert "- old one" in rendered.plain
        assert "+ new one" in rendered.plain
        assert "\n> Yes" in rendered.plain
        assert "\n  No" in rendered.plain
        assert "\n  Yes, this conversation" in rendered.plain

    def test_approval_card_selection_moves(self):
        """Test approval card moves selection like the legacy approval UI."""
        card = ApprovalCard()
        card.show_request(
            request_id="req_1",
            tool_call_id="call_1",
            tool_name="write_file",
            scope="write",
            risk_summary="Write file",
        )

        assert card.selected_choice == "yes"
        card.move_selection(1)
        assert card.selected_choice == "no"
        assert "\n> No" in card.render().plain
        card.move_selection(1)
        assert card.selected_choice == "yes_all"
        assert "\n> Yes, this conversation" in card.render().plain
        card.move_selection(1)
        assert card.selected_choice == "yes"

    def test_turn_cancelled_event(self):
        """Test TurnCancelled event."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        event = TurnCancelled(turn_id="turn_1", reason="user")
        assert event.turn_id == "turn_1"
        assert event.reason == "user"


class TestTextualPilot:
    """Tests using Textual pilot."""

    def test_app_starts(self):
        """Test that app starts without error."""
        import asyncio

        async def run_test():
            controller = _make_controller()
            app = ChatApp(controller=controller)
            async with app.run_test() as pilot:
                assert app.is_running

        asyncio.run(run_test())

    def test_app_input(self):
        """Test that app can receive input."""
        import asyncio

        async def run_test():
            controller = _make_controller()
            app = ChatApp(controller=controller)
            async with app.run_test() as pilot:
                input_widget = app.query_one("#input")
                input_widget.focus()
                await pilot.press("h", "e", "l", "l", "o")
                assert input_widget.value == "hello"

        asyncio.run(run_test())

    def test_app_submit_input_adds_message_block(self):
        """Test that pressing Enter submits input without crashing."""
        import asyncio
        from textual.widgets import Input

        async def run_test():
            controller = _make_controller()
            app = ChatApp(controller=controller)
            async with app.run_test() as pilot:
                input_widget = app.query_one("#input", Input)
                input_widget.focus()
                await pilot.press("h", "i", "enter")
                await pilot.pause(0.2)

                assert input_widget.value == ""
                assert [(b.kind, b.content) for b in app.store.message_blocks] == [
                    ("user_message", "hi")
                ]

        asyncio.run(run_test())

    def test_permission_key_approves_pending_tool(self):
        """Test y approves a pending permission while input is focused."""
        import asyncio
        from textual.widgets import Input
        from xcode_cli.core.llm import LLMResponse, ToolCall
        from xcode_cli.core.tool_registry import ToolDef, ToolRegistry

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
                            ToolCall(
                                id="call_1",
                                name="write_file",
                                args={"path": "x", "content": "hi"},
                            )
                        ],
                    )
                return LLMResponse(content="done", tool_calls=[])

        async def run_test():
            registry = ToolRegistry()
            registry.register(ToolDef(
                name="write_file",
                description="Write a file",
                parameters={},
                required=[],
                execute=lambda path, content: "wrote",
                is_read_only=False,
            ))
            controller = RuntimeController(llm_client=FakeLLM(), tool_registry=registry)
            app = ChatApp(controller=controller)
            try:
                async with app.run_test() as pilot:
                    input_widget = app.query_one("#input", Input)
                    input_widget.focus()
                    await pilot.press("w", "r", "i", "t", "e", "enter")

                    for _ in range(30):
                        await pilot.pause(0.1)
                        if app._pending_permission:
                            break

                    assert app._pending_permission is True
                    await pilot.press("y")

                    for _ in range(30):
                        await pilot.pause(0.1)
                        if any(
                            getattr(block, "kind", None) == "assistant_message"
                            for block in app.store.message_blocks
                        ):
                            break

                    assert app._pending_permission is False
                    assert input_widget.value == ""
                    assert any(
                        getattr(block, "kind", None) == "assistant_message"
                        and getattr(block, "content", None) == "done"
                        for block in app.store.message_blocks
                    )
            finally:
                controller.close()

        asyncio.run(run_test())

    def test_permission_arrows_and_enter_approve_pending_tool(self):
        """Test arrow keys select a permission option and Enter confirms it."""
        import asyncio
        from textual.widgets import Input
        from xcode_cli.core.llm import LLMResponse, ToolCall
        from xcode_cli.core.tool_registry import ToolDef, ToolRegistry

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
                            ToolCall(
                                id="call_1",
                                name="write_file",
                                args={"path": "x", "content": "hi"},
                            )
                        ],
                    )
                return LLMResponse(content="done", tool_calls=[])

        async def run_test():
            registry = ToolRegistry()
            registry.register(ToolDef(
                name="write_file",
                description="Write a file",
                parameters={},
                required=[],
                execute=lambda path, content: "wrote",
                is_read_only=False,
            ))
            controller = RuntimeController(llm_client=FakeLLM(), tool_registry=registry)
            app = ChatApp(controller=controller)
            try:
                async with app.run_test() as pilot:
                    input_widget = app.query_one("#input", Input)
                    input_widget.focus()
                    await pilot.press("w", "r", "i", "t", "e", "enter")

                    for _ in range(30):
                        await pilot.pause(0.1)
                        if app._pending_permission:
                            break

                    assert app._pending_permission is True
                    await pilot.press("down", "up", "enter")

                    for _ in range(30):
                        await pilot.pause(0.1)
                        if any(
                            getattr(block, "kind", None) == "assistant_message"
                            for block in app.store.message_blocks
                        ):
                            break

                    assert app._pending_permission is False
                    assert any(
                        getattr(block, "kind", None) == "assistant_message"
                        and getattr(block, "content", None) == "done"
                        for block in app.store.message_blocks
                    )
            finally:
                controller.close()

        asyncio.run(run_test())


# ── Batch 4/5 hardening: Resume selection ────────────────────────

class TestResumeSelection:
    """Tests for Textual resume selection interaction."""

    def test_resume_selector_renders_plain_text_list(self):
        """Test ResumeSelector renders plain text with session info."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        selector = ResumeSelector()
        selector.show_sessions([
            {
                "session_id": "session_abcdef123",
                "last_user_input": "continue work",
                "message_count": 4,
                "has_checkpoint": True,
            },
            {
                "session_id": "session_xyz987",
                "last_user_input": "review code",
                "message_count": 2,
                "has_checkpoint": False,
            },
        ])

        rendered = selector.render()
        plain = rendered.plain

        assert "Resumable sessions:" in plain
        assert "> session_" in plain
        assert "continue work" in plain
        assert "[checkpoint]" in plain
        assert "Enter confirm" in plain

    def test_resume_selector_limits_visible_sessions_to_ten(self):
        """Test long resume lists render only one terminal-sized window."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        selector = ResumeSelector()
        selector.show_sessions([
            {
                "session_id": f"session_{idx:02d}",
                "last_user_input": f"prompt {idx}",
                "message_count": idx,
                "has_checkpoint": False,
            }
            for idx in range(12)
        ])

        plain = selector.render().plain

        assert "prompt 0" in plain
        assert "prompt 9" in plain
        assert "prompt 10" not in plain
        assert "1-10 of 12" in plain

    def test_resume_selector_scrolls_window_to_keep_selection_visible(self):
        """Test selection past row ten scrolls the rendered window."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        selector = ResumeSelector()
        selector.show_sessions([
            {
                "session_id": f"session_{idx:02d}",
                "last_user_input": f"prompt {idx}",
                "message_count": idx,
                "has_checkpoint": False,
            }
            for idx in range(12)
        ])

        for _ in range(10):
            selector.move_selection(1)

        plain = selector.render().plain

        assert "prompt 0" not in plain
        assert "prompt 10" in plain
        assert "> session_" in plain
        assert "2-11 of 12" in plain

    def test_resume_list_with_sessions_enters_selection_state(self):
        """Test ResumeListLoaded with sessions enters selection state."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        controller = _make_controller()
        app = ChatApp(controller=controller)
        fake_selector = ResumeSelector()
        app.query_one = lambda *args, **kwargs: fake_selector

        app.handle_event(ResumeListLoaded(sessions=[
            {"session_id": "s1", "last_user_input": "hello", "message_count": 3, "has_checkpoint": False},
            {"session_id": "s2", "last_user_input": "world", "message_count": 5, "has_checkpoint": True},
        ]))

        assert app._is_resume_selecting is True
        assert len(fake_selector.sessions) == 2
        assert fake_selector.selected_index == 0

    def test_resume_list_empty_shows_notice(self):
        """Test ResumeListLoaded with no sessions shows notice, no selection."""
        controller = _make_controller()
        app = ChatApp(controller=controller)

        app.handle_event(ResumeListLoaded(sessions=[]))

        assert app._is_resume_selecting is False
        assert any(
            "No recent sessions found" in b.content
            for b in app.store.message_blocks
            if hasattr(b, 'content')
        )

    def test_resume_key_handler_moves_selection(self):
        """Test resume key handler moves selection up and down."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        controller = _make_controller()
        app = ChatApp(controller=controller)
        fake_selector = ResumeSelector()
        fake_selector.sessions = [
            {"session_id": "s1", "last_user_input": "a", "message_count": 1},
            {"session_id": "s2", "last_user_input": "b", "message_count": 2},
        ]
        app.query_one = lambda *args, **kwargs: fake_selector
        app._is_resume_selecting = True

        assert fake_selector.selected_index == 0
        assert app._handle_resume_key("down") is True
        assert fake_selector.selected_index == 1
        assert app._handle_resume_key("up") is True
        assert fake_selector.selected_index == 0
        assert app._handle_resume_key("k") is True
        assert fake_selector.selected_index == 1  # wrapped
        assert app._handle_resume_key("j") is True
        assert fake_selector.selected_index == 0  # wrapped back

    def test_resume_key_handler_enter_dispatches_resume(self):
        """Test enter key dispatches ResumeSessionCommand."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        controller = _make_controller()
        app = ChatApp(controller=controller)
        fake_selector = ResumeSelector()
        fake_selector.sessions = [
            {"session_id": "s1", "last_user_input": "a", "message_count": 1},
        ]
        app.query_one = lambda *args, **kwargs: fake_selector
        app._is_resume_selecting = True

        app._handle_resume_key("enter")

        events = controller.drain_events()
        assert app._is_resume_selecting is False
        # ResumeSessionCommand was dispatched - check for the resulting events
        assert any(
            isinstance(e, UICommandFailed) and "No session store" in e.error
            for e in events
        )

    def test_resume_key_handler_escape_cancels(self):
        """Test escape key cancels resume selection."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        controller = _make_controller()
        app = ChatApp(controller=controller)
        fake_selector = ResumeSelector()
        fake_selector.sessions = [
            {"session_id": "s1", "last_user_input": "a", "message_count": 1},
        ]
        app.query_one = lambda *args, **kwargs: fake_selector
        app._is_resume_selecting = True

        app._handle_resume_key("escape")

        assert app._is_resume_selecting is False
        assert fake_selector.display is False
        assert any(
            "cancelled" in b.content.lower()
            for b in app.store.message_blocks
            if hasattr(b, 'content')
        )

    def test_resume_selection_blocks_normal_input(self):
        """Test normal input is blocked during resume selection."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_resume_selecting = True

        event = UserInputSubmitted("hello while selecting")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)

        blocks = [b for b in app.store.message_blocks if hasattr(b, 'content')]
        assert any("select a session" in b.content.lower() for b in blocks)

    def test_resume_selection_does_not_dispatch_submit(self):
        """Test no SubmitUserInputCommand is dispatched during resume selection."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_resume_selecting = True

        event = UserInputSubmitted("hello")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)

        events = controller.drain_events()
        assert not any(isinstance(e, UserMessageAdded) for e in events)

    def test_resume_key_handler_returns_false_when_not_selecting(self):
        """Test resume key handler returns False when not in selection state."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_resume_selecting = False

        assert app._handle_resume_key("down") is False
        assert app._handle_resume_key("enter") is False
        assert app._handle_resume_key("escape") is False

    def test_pilot_resume_enter_selects_session(self):
        """Test headless pilot can use /resume and interact with selection."""
        import asyncio
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        async def run_test():
            controller = _make_controller()
            app = ChatApp(controller=controller)
            async with app.run_test() as pilot:
                # Inject sessions into the ResumeListLoaded handler
                sessions = [
                    {"session_id": "s1", "last_user_input": "first", "message_count": 3},
                    {"session_id": "s2", "last_user_input": "second", "message_count": 5},
                ]
                app.handle_event(ResumeListLoaded(sessions=sessions))

                assert app._is_resume_selecting is True

                # Press down to select second session
                await pilot.press("down")
                await pilot.pause(0.1)

                selector = app.query_one("#resume-selector", ResumeSelector)
                assert selector.selected_index == 1

                # Press escape to cancel
                await pilot.press("escape")
                await pilot.pause(0.1)

                assert app._is_resume_selecting is False

        asyncio.run(run_test())

    def test_resume_selection_does_not_append_dynamic_notice_on_navigation(self):
        """Test resume navigation does not write repeated notices into transcript."""
        from xcode_cli.core.ui.textual.widgets import ResumeSelector

        controller = _make_controller()
        app = ChatApp(controller=controller)
        fake_selector = ResumeSelector()
        fake_selector.sessions = [
            {"session_id": "s1", "last_user_input": "one", "message_count": 1},
            {"session_id": "s2", "last_user_input": "two", "message_count": 2},
        ]
        app.query_one = lambda *args, **kwargs: fake_selector
        app._is_resume_selecting = True

        # Track system notices added
        notices = []
        original_add = app.add_system_notice
        def track_notice(message_id, content):
            notices.append((message_id, content))
            original_add(message_id, content)
        app.add_system_notice = track_notice

        # Navigate
        app._handle_resume_key("down")
        app._handle_resume_key("up")

        # No system notices should be added for navigation
        assert len(notices) == 0

    def test_handle_resume_completed_adds_legacy_aligned_system_notice(self):
        """Test ResumeCompleted shows legacy-aligned output."""
        from xcode_cli.core.ui.textual.app import ChatApp

        app = ChatApp()
        notices = []
        app.add_system_notice = lambda message_id, content: notices.append(content)

        app.handle_event(ResumeCompleted(
            session_id="session_1",
            restored_from_checkpoint=True,
            message_count=5,
            estimated_tokens=678,
            last_user_input="continue from last turn",
        ))

        content = notices[0]
        assert "Resumed session session_1" in content
        assert "Restored from checkpoint: yes" in content
        assert "Restored messages: 5" in content
        assert "Estimated context: ~678 tokens" in content
        assert "Latest user input: continue from last turn" in content

    def test_handle_resume_completed_omits_latest_input_when_missing(self):
        """Test ResumeCompleted omits latest input when None."""
        from xcode_cli.core.ui.textual.app import ChatApp

        app = ChatApp()
        notices = []
        app.add_system_notice = lambda message_id, content: notices.append(content)

        app.handle_event(ResumeCompleted(
            session_id="session_1",
            restored_from_checkpoint=False,
            message_count=5,
            estimated_tokens=678,
            last_user_input=None,
        ))

        content = notices[0]
        assert "Restored from checkpoint: no" in content
        assert "Latest user input:" not in content


# ── Batch 4/5 hardening: Compacting state ────────────────────────

class TestCompactingState:
    """Tests for compacting state in ChatApp."""

    def test_compaction_started_sets_compacting_flag(self):
        """Test CompactionStarted sets _is_compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app.query_one = MagicMock(return_value=MagicMock())

        app.handle_event(CompactionStarted())

        assert app._is_compacting is True

    def test_compaction_completed_clears_compacting_flag(self):
        """Test CompactionCompleted clears _is_compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app.query_one = MagicMock(return_value=MagicMock())
        app._is_compacting = True

        app.handle_event(CompactionCompleted(summary="summary", source_message_count=10))

        assert app._is_compacting is False

    def test_compaction_skipped_clears_compacting_flag(self):
        """Test CompactionSkipped clears _is_compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app.query_one = MagicMock(return_value=MagicMock())
        app._is_compacting = True

        app.handle_event(CompactionSkipped())

        assert app._is_compacting is False

    def test_compaction_failed_clears_compacting_flag(self):
        """Test CompactionFailed clears _is_compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app.query_one = MagicMock(return_value=MagicMock())
        app._is_compacting = True

        app.handle_event(CompactionFailed(error="boom"))

        assert app._is_compacting is False

    def test_compacting_blocks_user_input(self):
        """Test user input is blocked during compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_compacting = True

        event = UserInputSubmitted("hello")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)

        blocks = [b for b in app.store.message_blocks if hasattr(b, 'content')]
        assert any("compacting" in b.content.lower() for b in blocks)

    def test_compacting_does_not_dispatch_submit(self):
        """Test no SubmitUserInputCommand is dispatched during compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_compacting = True

        event = UserInputSubmitted("hello")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)

        events = controller.drain_events()
        assert not any(isinstance(e, UserMessageAdded) for e in events)

    def test_compacting_blocks_slash_command(self):
        """Test slash commands are blocked during compacting."""
        controller = _make_controller()
        app = ChatApp(controller=controller)
        app._is_compacting = True

        event = UserInputSubmitted("/help")
        app.post_message = MagicMock()
        app.on_user_input_submitted(event)

        blocks = [b for b in app.store.message_blocks if hasattr(b, 'content')]
        assert any("compacting" in b.content.lower() for b in blocks)
