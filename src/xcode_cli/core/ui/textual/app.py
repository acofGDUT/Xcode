"""Textual ChatApp for terminal UI."""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical

from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.ui.commands import (
    CancelTurnCommand,
    ExitCommand,
    PermissionDecisionCommand,
    ResumeSessionCommand,
    RunSlashCommandCommand,
    SubmitUserInputCommand,
    ViewportStateChangedCommand,
)
from xcode_cli.core.ui.events import (
    AssistantDelta,
    AssistantFinal,
    CommandPreviewAvailable,
    CompactionStarted,
    CompactionCompleted,
    CompactionSkipped,
    CompactionFailed,
    ConfigUpdated,
    DiffPreviewAvailable,
    PermissionClearedEvent,
    PermissionRequestEvent,
    PlanApprovalRequested,
    PlanUpdated,
    ResumeListLoaded,
    ResumeCompleted,
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
from xcode_cli.core.ui.state import (
    AssistantMessageBlock,
    PermissionPromptSurface,
    SystemNoticeBlock,
    TaskSnapshotBlock,
    ToolErrorBlock,
    ToolRejectedBlock,
    ToolResultBlock,
    ToolSummaryBlock,
    UIStore,
    UserMessageBlock,
)
from xcode_cli.core.ui.presenters import StatusPresenter, TaskPresenter

from xcode_cli.core.ui.textual.renderers import RichLogRenderer
from xcode_cli.core.ui.textual.widgets import (
    ActiveToolIndicator,
    ApprovalCard,
    CommandSuggestions,
    InputBox,
    NewMessagesPill,
    PetSurface,
    ResumeSelector,
    RichLogHistory,
    StatusBar,
    StreamingWidget,
    TranscriptArea,
    UserInputSubmitted,
)


class ChatApp(App):
    """Textual ChatApp for terminal UI."""

    CSS = """
    Screen {
        background: transparent;
    }

    #main-container {
        height: 100%;
        margin: 0 1;
    }

    #transcript {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #streaming {
        height: auto;
        max-height: 50%;
        color: $text;
    }

    #bottom-area {
        height: auto;
        dock: bottom;
        background: transparent;
        padding-top: 1;
    }

    #input-box {
        height: auto;
    }

    #status-bar {
        height: 1;
    }

    #new-messages {
        height: auto;
    }

    #suggestions {
        height: auto;
        max-height: 10;
    }

    #pet {
        display: none;
        height: 0;
        width: 0;
    }

    #resume-selector {
        height: auto;
        max-height: 12;
    }

    #approval-card {
        height: auto;
        max-height: 24;
    }

    #active-tool {
        height: 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "cancel", "Cancel"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, controller: RuntimeController | None = None) -> None:
        super().__init__()
        self.controller = controller or RuntimeController()
        self.store = UIStore()
        self._is_at_bottom = True
        self._renderer: RichLogRenderer | None = None
        self._pending_permission: bool = False
        self._tasks_by_id: dict[str, dict[str, str]] = {}
        self._is_resume_selecting: bool = False
        self._is_compacting: bool = False

    def compose(self) -> ComposeResult:
        """Compose the app."""
        with Vertical(id="main-container"):
            yield TranscriptArea(id="transcript")
            yield StreamingWidget(id="streaming")
            # Transient surfaces between streaming and bottom area
            yield ActiveToolIndicator(id="active-tool")
            yield ApprovalCard(id="approval-card")
            yield ResumeSelector(id="resume-selector")
            with Vertical(id="bottom-area"):
                yield NewMessagesPill(id="new-messages")
                yield CommandSuggestions(id="suggestions")
                yield InputBox(id="input-box")
                yield StatusBar(id="status-bar")
            yield PetSurface(id="pet")

    def on_mount(self) -> None:
        """Initialize the app."""
        # Initialize renderer
        history = self.query_one("#history", RichLogHistory)
        self._renderer = RichLogRenderer(history)
        self.update_status_bar()
        self.set_interval(0.1, self.poll_events)

        # Keep focus in the input when the app starts.
        self.query_one("#input").focus()

    def poll_events(self) -> None:
        """Poll events from the controller."""
        events = self.controller.drain_events()
        for event in events:
            self.handle_event(event)

    def handle_event(self, event: UIEvent) -> None:
        """Handle a UI event."""
        if isinstance(event, UserMessageAdded):
            self._handle_user_message_added(event)
        elif isinstance(event, AssistantDelta):
            self._handle_assistant_delta(event)
        elif isinstance(event, AssistantFinal):
            self._handle_assistant_final(event)
        elif isinstance(event, StatusUpdated):
            self._handle_status_updated(event)
        elif isinstance(event, SystemNoticeAdded):
            self._handle_system_notice(event)
        elif isinstance(event, UICommandFailed):
            self._handle_command_failed(event)
        # Batch 2: Tool events
        elif isinstance(event, ToolCallStarted):
            self._handle_tool_call_started(event)
        elif isinstance(event, ToolCallFinished):
            self._handle_tool_call_finished(event)
        elif isinstance(event, ToolOutputProduced):
            self._handle_tool_output(event)
        elif isinstance(event, ToolRejected):
            self._handle_tool_rejected(event)
        elif isinstance(event, ToolError):
            self._handle_tool_error(event)
        # Batch 2: Turn lifecycle
        elif isinstance(event, TurnCancelled):
            self._handle_turn_cancelled(event)
        # Batch 3: Permission and previews
        elif isinstance(event, PermissionRequestEvent):
            self._handle_permission_request(event)
        elif isinstance(event, PermissionClearedEvent):
            self._handle_permission_cleared(event)
        elif isinstance(event, DiffPreviewAvailable):
            self._handle_diff_preview(event)
        elif isinstance(event, CommandPreviewAvailable):
            self._handle_command_preview(event)
        # Batch 3: Compaction
        elif isinstance(event, CompactionStarted):
            self._handle_compaction_started(event)
        elif isinstance(event, CompactionCompleted):
            self._handle_compaction_completed(event)
        elif isinstance(event, CompactionSkipped):
            self._handle_compaction_skipped(event)
        elif isinstance(event, CompactionFailed):
            self._handle_compaction_failed(event)
        elif isinstance(event, TaskStateChanged):
            self._handle_task_state_changed(event)
        elif isinstance(event, ResumeListLoaded):
            self._handle_resume_list_loaded(event)
        elif isinstance(event, ResumeCompleted):
            self._handle_resume_completed(event)
        elif isinstance(event, ConfigUpdated):
            self._handle_config_updated(event)
        elif isinstance(event, PlanUpdated):
            self._handle_plan_updated(event)
        elif isinstance(event, PlanApprovalRequested):
            self._handle_plan_approval_requested(event)

    # User messages

    def _handle_user_message_added(self, event: UserMessageAdded) -> None:
        """Add a user message to the transcript."""
        block = UserMessageBlock(
            id=event.message_id,
            kind="user_message",
            content=event.content,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    # Assistant streaming

    def _handle_assistant_delta(self, event: AssistantDelta) -> None:
        """Update streaming text."""
        streaming = self.query_one("#streaming", StreamingWidget)
        streaming.update_text(streaming.text + event.delta)

    def _handle_assistant_final(self, event: AssistantFinal) -> None:
        """Finalize an assistant message."""
        streaming = self.query_one("#streaming", StreamingWidget)
        streaming.clear_text()

        block = AssistantMessageBlock(
            id=event.message_id,
            kind="assistant_message",
            content=event.content,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

        # Show new messages pill if user scrolled away
        if not self._is_at_bottom:
            pill = self.query_one("#new-messages", NewMessagesPill)
            pill.show_pill(pill.message_count + 1)

    # Tool events

    def _handle_tool_call_started(self, event: ToolCallStarted) -> None:
        """Show active tool indicator."""
        indicator = self.query_one("#active-tool", ActiveToolIndicator)
        indicator.show_tool(event.tool_call_id, event.tool_name)

        # Add tool summary block
        summary_text = f"{event.tool_name}"
        if event.arguments:
            safe_args = {k: v for k, v in event.arguments.items()
                         if k not in ("api_key", "password", "token", "secret")}
            args_str = " ".join(
                f"{k}={str(v)[:60]}" for k, v in safe_args.items()
            )
            if args_str:
                summary_text += f" {args_str}"

        block = ToolSummaryBlock(
            id=f"tool_sum_{event.tool_call_id}",
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
            summary=summary_text,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    def _handle_tool_call_finished(self, event: ToolCallFinished) -> None:
        """Hide active tool indicator."""
        indicator = self.query_one("#active-tool", ActiveToolIndicator)
        indicator.hide_tool()

    def _handle_tool_output(self, event: ToolOutputProduced) -> None:
        """Show tool output."""
        if event.output_type == "rejected":
            return  # Handled by ToolRejected event

        block = ToolResultBlock(
            id=f"tool_res_{event.tool_call_id}",
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
            result=event.content[:500],
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    def _handle_tool_rejected(self, event: ToolRejected) -> None:
        """Show tool rejection."""
        block = ToolRejectedBlock(
            id=f"tool_rej_{event.tool_call_id}",
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    def _handle_tool_error(self, event: ToolError) -> None:
        """Show tool error."""
        block = ToolErrorBlock(
            id=f"tool_err_{event.tool_call_id}",
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
            error=event.error,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    def _handle_task_state_changed(self, event: TaskStateChanged) -> None:
        """Persist a concise task snapshot in UI history."""
        if event.new_state == "deleted":
            self._tasks_by_id.pop(event.task_id, None)
        else:
            self._tasks_by_id[event.task_id] = {
                "id": event.task_id,
                "subject": event.description,
                "status": event.new_state,
            }
        tasks = TaskPresenter().concise_snapshot(list(self._tasks_by_id.values()))
        block = TaskSnapshotBlock(
            id=f"task_snapshot_{event.task_id}",
            tasks=tasks,
            model_visible=False,
            persist_ui=True,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)
        running = next(
            (task for task in tasks if task.get("status") == "in_progress"),
            None,
        )
        try:
            indicator = self.query_one("#active-tool", ActiveToolIndicator)
            if running:
                indicator.show_task(str(running.get("subject", "")))
            else:
                indicator.hide_tool()
        except Exception:
            pass

    # Turn lifecycle

    def _handle_turn_cancelled(self, event: TurnCancelled) -> None:
        """Handle turn cancellation."""
        # Clear streaming
        streaming = self.query_one("#streaming", StreamingWidget)
        streaming.clear_text()

        # Clear active tool
        indicator = self.query_one("#active-tool", ActiveToolIndicator)
        indicator.hide_tool()

        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.hide_card()

        self._pending_permission = False
        self.update_status_bar()

    # Permission

    def _handle_permission_request(self, event: PermissionRequestEvent) -> None:
        """Show permission prompt."""
        self._pending_permission = True
        self.store.set_pending_permission(PermissionPromptSurface(
            id=f"permission_{event.request_id}",
            turn_id=event.turn_id,
            tool_call_id=event.tool_call_id,
            request_id=event.request_id,
            tool_name=event.tool_name,
            scope=event.scope,
            risk_summary=event.risk_summary,
        ))
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.show_request(
            request_id=event.request_id,
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_name,
            scope=event.scope,
            risk_summary=event.risk_summary,
        )
        self.update_status_bar()

    def _handle_permission_cleared(self, event: PermissionClearedEvent) -> None:
        """Clear permission prompt."""
        self._pending_permission = False
        self.store.set_pending_permission(None)
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.hide_card()
        self._clear_input_value()
        self.update_status_bar()

        # Restore input focus after the permission interaction closes.
        self.query_one("#input").focus()

    def on_approval_card_decision(self, event: ApprovalCard.Decision) -> None:
        """Handle permission decision from approval card."""
        self.controller.dispatch(PermissionDecisionCommand(
            request_id=event.request_id,
            tool_call_id=event.tool_call_id,
            choice=event.choice,  # type: ignore[arg-type]
        ))

    def on_key(self, event: "textual.events.Key") -> None:  # type: ignore[name-defined]
        """Global key handler for y/n/a when permission is pending, or resume selection."""
        if self._is_resume_selecting:
            if self._handle_resume_key(event.key.lower()):
                event.stop()
            return

        if not self._pending_permission:
            return

        if self.handle_permission_key(event.key.lower()):
            event.stop()

    # Diff/command preview

    def handle_permission_key(self, key: str) -> bool:
        """Handle approval shortcuts and selection keys.

        Returns True when the key was consumed.
        """
        if not self._pending_permission:
            return False

        approval_card = self.query_one("#approval-card", ApprovalCard)

        if key in ("up", "k"):
            approval_card.move_selection(-1)
            return True
        if key in ("down", "j"):
            approval_card.move_selection(1)
            return True
        if key in ("enter", "space"):
            return self._dispatch_permission_choice(approval_card.selected_choice)

        choice_map = {"y": "yes", "n": "no", "a": "yes_all"}
        choice = choice_map.get(key)
        if not choice:
            return False
        approval_card.select_choice(choice)
        return self._dispatch_permission_choice(choice)

    def _dispatch_permission_choice(self, choice: str) -> bool:
        """Dispatch the selected permission choice."""
        approval_card = self.query_one("#approval-card", ApprovalCard)
        if not approval_card.request_id or not approval_card.tool_call_id:
            return False
        self.controller.dispatch(PermissionDecisionCommand(
            request_id=approval_card.request_id,
            tool_call_id=approval_card.tool_call_id,
            choice=choice,  # type: ignore[arg-type]
        ))
        try:
            self._clear_input_value()
        except Exception:
            pass
        return True

    # Resume selection

    def _handle_resume_key(self, key: str) -> bool:
        """Handle keys during resume selection.

        Returns True when the key was consumed.
        """
        if not self._is_resume_selecting:
            return False

        selector = self.query_one("#resume-selector", ResumeSelector)

        if key in ("up", "k"):
            selector.move_selection(-1)
            return True
        if key in ("down", "j"):
            selector.move_selection(1)
            return True
        if key == "enter":
            self._confirm_resume_selection()
            return True
        if key == "escape":
            self._cancel_resume_selection()
            return True

        return False

    def _confirm_resume_selection(self) -> None:
        """Confirm the current resume selection."""
        selector = self.query_one("#resume-selector", ResumeSelector)
        if 0 <= selector.selected_index < len(selector.sessions):
            session_id = str(selector.sessions[selector.selected_index].get("session_id", ""))
            if session_id:
                selector.hide_selector()
                self._is_resume_selecting = False
                self.controller.dispatch(ResumeSessionCommand(session_id=session_id))

    def _cancel_resume_selection(self) -> None:
        """Cancel resume selection."""
        selector = self.query_one("#resume-selector", ResumeSelector)
        selector.hide_selector()
        self._is_resume_selecting = False
        self.add_system_notice("resume_cancelled", "Cancelled.")

    def _clear_input_value(self) -> None:
        """Clear the text input if it is mounted."""
        input_box = self.query_one("#input")
        if hasattr(input_box, "value"):
            input_box.value = ""

    def _handle_diff_preview(self, event: DiffPreviewAvailable) -> None:
        """Show diff preview."""
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.show_diff(event.file_path, event.diff_content)

    def _handle_command_preview(self, event: CommandPreviewAvailable) -> None:
        """Show command preview."""
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.show_command(event.command)

    # Compaction

    def _handle_compaction_started(self, event: CompactionStarted) -> None:
        """Handle compaction started."""
        self._is_compacting = True
        self.add_system_notice("compaction_started", "Context compaction started...")

    def _handle_compaction_completed(self, event: CompactionCompleted) -> None:
        """Handle compaction completed."""
        self._is_compacting = False
        self.add_system_notice(
            f"compaction_{id(event)}",
            f"Context compacted: {event.source_message_count} messages -> {event.summary[:100]}",
        )

    def _handle_compaction_skipped(self, event: CompactionSkipped) -> None:
        """Handle compaction skipped."""
        self._is_compacting = False
        self.add_system_notice(f"compaction_skip_{id(event)}", "Nothing to compact.")

    def _handle_compaction_failed(self, event: CompactionFailed) -> None:
        """Handle compaction failed."""
        self._is_compacting = False
        self.add_system_notice(
            f"compaction_err_{id(event)}",
            f"Compaction failed: {event.error}",
        )

    # Resume / config / plan

    def _handle_resume_list_loaded(self, event: ResumeListLoaded) -> None:
        """Enter resume selection state or show no-session notice."""
        if not event.sessions:
            self.add_system_notice("resume_empty", "No recent sessions found for this project.")
            return

        selector = self.query_one("#resume-selector", ResumeSelector)
        selector.show_sessions(event.sessions)
        selector.scroll_visible()
        self._is_resume_selecting = True

    def _handle_resume_completed(self, event: ResumeCompleted) -> None:
        """Render legacy-aligned resume completion."""
        lines = [
            f"Resumed session {event.session_id}",
            f"Restored from checkpoint: {'yes' if event.restored_from_checkpoint else 'no'}",
            f"Restored messages: {event.message_count}",
            f"Estimated context: ~{event.estimated_tokens} tokens",
        ]
        if event.last_user_input:
            lines.append(f"Latest user input: {event.last_user_input[:100]}")

        self.add_system_notice(
            f"resume_{event.session_id}",
            "\n".join(lines),
        )

    def _handle_config_updated(self, event: ConfigUpdated) -> None:
        """Render redacted config update."""
        self.add_system_notice(
            f"config_{event.key}",
            f"Config updated: {event.key}={event.value}",
        )

    def _handle_plan_updated(self, event: PlanUpdated) -> None:
        """Render plan state update."""
        self.add_system_notice(
            f"plan_{id(event)}",
            event.plan_content,
        )

    def _handle_plan_approval_requested(self, event: PlanApprovalRequested) -> None:
        """Render plan approval request."""
        self.add_system_notice(
            f"plan_approval_{id(event)}",
            event.plan_content,
        )

    # Status and system

    def update_status_bar(self) -> None:
        """Update the status bar."""
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_status(StatusPresenter().get_status_text(self.store))

    def _handle_status_updated(self, event: StatusUpdated) -> None:
        """Update status bar from a status event."""
        if event.field == "turn":
            value = str(event.value)
            if value.startswith("busy:"):
                self.store.current_turn_id = value.split("busy:", 1)[1]
            elif value == "idle":
                self.store.current_turn_id = None
        if event.field == "surfaces" and event.value == "clear":
            self.store.clear_all_turn_surfaces()
            self._pending_permission = False
            try:
                self.query_one("#active-tool", ActiveToolIndicator).hide_tool()
                self.query_one("#approval-card", ApprovalCard).hide_card()
            except Exception:
                pass
        self.update_status_bar()
        if event.field == "command":
            self.add_system_notice(
                f"command_{id(event)}",
                f"Command received: {event.value}",
            )

    def _handle_system_notice(self, event: SystemNoticeAdded) -> None:
        """Handle system notice event."""
        self.add_system_notice(event.message_id, event.content)

    def _handle_command_failed(self, event: UICommandFailed) -> None:
        """Handle command failed event."""
        self.add_system_notice(
            f"cmd_failed_{id(event)}",
            f"Command failed: {event.error}",
        )

    def add_system_notice(self, message_id: str, content: str) -> None:
        """Add a system notice to the transcript."""
        block = SystemNoticeBlock(
            id=message_id,
            kind="system_notice",
            content=content,
            model_visible=False,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    # Input handling

    def on_user_input_submitted(self, event: UserInputSubmitted) -> None:
        """Handle input submission."""
        # Block input while permission is pending
        if self._pending_permission:
            self.add_system_notice(
                f"blocked_{id(event)}",
                "Please respond to the permission prompt first (y/n/a).",
            )
            return

        # Block input while resume selection is active
        if self._is_resume_selecting:
            self.add_system_notice(
                f"blocked_resume_{id(event)}",
                "Please select a session to resume (up/down/enter) or press escape to cancel.",
            )
            return

        # Block input while compacting
        if self._is_compacting:
            self.add_system_notice(
                f"blocked_compact_{id(event)}",
                "Compacting context... please wait.",
            )
            return

        text = event.text.strip()
        if not text:
            return

        if text.startswith("/"):
            self.controller.dispatch(RunSlashCommandCommand(raw=text))
        else:
            self.controller.dispatch(SubmitUserInputCommand(text=text))

    # Actions

    def action_cancel(self) -> None:
        """Cancel the current turn."""
        self.controller.dispatch(CancelTurnCommand(reason="user"))

    def action_quit(self) -> None:
        """Quit the app."""
        self.controller.dispatch(ExitCommand())
        self.exit()

    def on_scroll(self, event: Any) -> None:
        """Handle scroll events."""
        # Update controller with current viewport state
        self.controller.dispatch(ViewportStateChangedCommand(is_at_bottom=self._is_at_bottom))

        # Hide new messages pill if at bottom
        if self._is_at_bottom:
            pill = self.query_one("#new-messages", NewMessagesPill)
            pill.hide_pill()
