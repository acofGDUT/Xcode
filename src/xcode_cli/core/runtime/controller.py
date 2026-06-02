"""RuntimeController for Textual-based terminal UI.

Accepts UICommands, prevents concurrent active turns, exposes event queue,
owns pending permission state skeleton, and clears turn surfaces on boundaries.
"""
from __future__ import annotations

import difflib
import json
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable

from xcode_cli.core.config import ConfigStore
from xcode_cli.core.context import ContextManager
from xcode_cli.core.llm import LLMClient, ToolCall
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.planning import PlanMode
from xcode_cli.core.runtime.agent_engine import AgentEngine
from xcode_cli.core.runtime.cancellation import CancellationToken, CancellationTokenSource
from xcode_cli.core.runtime.permissions import (
    PermissionDecision,
    PermissionProvider,
    PermissionRequest,
)
from xcode_cli.core.session import SessionInfo, SessionStore
from xcode_cli.core.session_resume import SessionResumeBuilder
from xcode_cli.core.task_tracker import TaskTracker
from xcode_cli.core.tool_registry import ToolRegistry
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
    CommandPreviewAvailable,
    ConfigUpdated,
    DiffPreviewAvailable,
    PermissionClearedEvent,
    PermissionRequestEvent,
    PlanApprovalRequested,
    PlanUpdated,
    ResumeCompleted,
    ResumeListLoaded,
    StatusUpdated,
    SystemNoticeAdded,
    TaskStateChanged,
    ToolCallStarted,
    ToolCallFinished,
    ToolError,
    ToolOutputProduced,
    ToolRejected,
    TurnCancelled,
    UICommandFailed,
    UIEvent,
    UserMessageAdded,
)


class RuntimeController:
    """Runtime controller for Textual-based terminal UI.

    Responsibilities:
    - Accept UICommand
    - Prevent concurrent active turns
    - Expose event queue
    - Own pending permission state skeleton
    - Clear turn surfaces on cancellation/resume/compact boundaries
    - Run AgentEngine in worker thread with streaming events

    Threading rule:
    - Worker never mutates UIStore directly
    - Worker puts UIEvent into thread-safe event queue
    - Textual app loop consumes events and mutates UIStore
    """

    def __init__(
        self,
        permission_provider: PermissionProvider | None = None,
        llm_client: LLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
        permission_manager: PermissionManager | None = None,
        memory_manager: MemoryManager | None = None,
        task_tracker: TaskTracker | None = None,
        session_store: SessionStore | None = None,
        context_manager: ContextManager | None = None,
        plan_mode: PlanMode | None = None,
        config_store: ConfigStore | None = None,
        system_prompt_provider: Callable[[], str] | None = None,
        session_id: str = "",
        headless: bool = False,
    ) -> None:
        self._event_queue: deque[UIEvent] = deque()
        self._queue_lock = threading.Lock()
        self._active_turn = False
        self._active_turn_lock = threading.Lock()
        self._current_turn_id: str | None = None
        self._current_cancellation: CancellationTokenSource | None = None
        self._permission_provider = permission_provider
        self._pending_permission_requests: dict[str, PermissionRequest] = {}
        self._permission_lock = threading.Lock()
        self._permission_wait_events: dict[str, threading.Event] = {}
        self._permission_decisions: dict[str, PermissionDecision] = {}
        self._closed = False

        # Batch 2: Agent engine services
        self._llm = llm_client or LLMClient()
        self._tool_registry = tool_registry or ToolRegistry()
        self._permission_manager = permission_manager
        self._memory_manager = memory_manager
        self._task_tracker = task_tracker
        self._session_store = session_store
        self._context_manager = context_manager
        self._plan_mode = plan_mode
        self._config_store = config_store or ConfigStore()
        self._system_prompt_provider = system_prompt_provider or (lambda: "")
        self._session_id = session_id
        self._session_auto_approve: dict[str, bool] = {"write": False, "shell": False}
        self._agent_engine = AgentEngine(llm_client=self._llm)

        # Compaction state
        self._is_compacting = False

        # Worker thread management
        self._worker_thread: threading.Thread | None = None
        self._headless = headless

        # Cross-turn history (persists across SubmitUserInputCommand calls)
        self._history: list[dict[str, Any]] = []

    @property
    def has_active_turn(self) -> bool:
        """Check if there is an active turn."""
        with self._active_turn_lock:
            return self._active_turn

    @property
    def current_turn_id(self) -> str | None:
        """Get current turn id."""
        return self._current_turn_id

    def dispatch(self, command: UICommand) -> None:
        """Dispatch a UI command.

        Args:
            command: The UI command to dispatch.

        Raises:
            RuntimeError: If the controller is closed.
        """
        if self._closed:
            raise RuntimeError("RuntimeController is closed")

        if isinstance(command, SubmitUserInputCommand):
            self._handle_submit_user_input(command)
        elif isinstance(command, RunSlashCommandCommand):
            self._handle_run_slash_command(command)
        elif isinstance(command, PermissionDecisionCommand):
            self._handle_permission_decision(command)
        elif isinstance(command, CancelTurnCommand):
            self._handle_cancel_turn(command)
        elif isinstance(command, ResumeSessionCommand):
            self._handle_resume_session(command)
        elif isinstance(command, CompactCommand):
            self._handle_compact(command)
        elif isinstance(command, SaveEnvCommand):
            self._handle_save_env(command)
        elif isinstance(command, PlanDecisionCommand):
            self._handle_plan_decision(command)
        elif isinstance(command, ExitCommand):
            self._handle_exit(command)
        elif isinstance(command, ViewportStateChangedCommand):
            self._handle_viewport_state_changed(command)
        else:
            self._enqueue_event(UICommandFailed(
                command_type=type(command).__name__,
                error=f"Unknown command type: {type(command).__name__}",
            ))

    def drain_events(self) -> list[UIEvent]:
        """Drain all events from the queue.

        Returns:
            List of events from the queue.
        """
        with self._queue_lock:
            events = list(self._event_queue)
            self._event_queue.clear()
            return events

    def close(self) -> None:
        """Close the controller."""
        self._closed = True
        if self._current_cancellation:
            self._current_cancellation.cancel()
        self._fail_pending_permissions()
        # Wait for worker thread to finish
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    def set_system_prompt_provider(self, provider: Callable[[], str]) -> None:
        """Set system prompt provider."""
        self._system_prompt_provider = provider

    # Turn management

    def _start_turn(self, turn_id: str) -> bool:
        """Start a new turn.

        Args:
            turn_id: The turn id.

        Returns:
            True if turn started, False if there is already an active turn.
        """
        with self._active_turn_lock:
            if self._active_turn:
                return False
            self._active_turn = True
            self._current_turn_id = turn_id
            self._current_cancellation = CancellationTokenSource()
            return True

    def _end_turn(self) -> None:
        """End the current turn."""
        with self._active_turn_lock:
            self._active_turn = False
            self._current_turn_id = None
            self._current_cancellation = None

    def _enqueue_event(self, event: UIEvent) -> None:
        """Enqueue an event."""
        with self._queue_lock:
            self._event_queue.append(event)

    # Agent turn

    def _handle_submit_user_input(self, command: SubmitUserInputCommand) -> None:
        """Handle submit user input command - spawns worker thread."""
        if self._is_compacting:
            self._enqueue_event(UICommandFailed(
                command_type="SubmitUserInputCommand",
                error="Cannot submit input while compacting context",
            ))
            return

        turn_id = f"turn_{uuid.uuid4().hex[:8]}"

        if not self._start_turn(turn_id):
            self._enqueue_event(UICommandFailed(
                command_type="SubmitUserInputCommand",
                error="Another turn is already active",
            ))
            return

        message_id = f"msg_{turn_id}"
        self._enqueue_event(UserMessageAdded(
            message_id=message_id,
            content=command.text,
        ))
        self._enqueue_event(StatusUpdated(field="turn", value=f"busy:{turn_id}"))

        # In headless mode, skip the worker thread (for testing)
        if self._headless:
            self._end_turn()
            self._enqueue_event(StatusUpdated(field="turn", value="idle"))
            return

        # Capture cancellation for this turn
        cancellation = self._current_cancellation.token if self._current_cancellation else CancellationToken()

        # Build system prompt
        system_prompt = self._system_prompt_provider()

        # Tool schemas
        tool_schemas = self._tool_registry.get_openai_schemas()

        # Append user message to persistent cross-turn history
        self._history.append({"role": "user", "content": command.text})

        # Spawn worker thread (agent engine appends assistant/tool messages in-place)
        self._worker_thread = threading.Thread(
            target=self._run_agent_turn,
            args=(turn_id, self._history, system_prompt, tool_schemas, cancellation),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_agent_turn(
        self,
        turn_id: str,
        history: list[dict[str, Any]],
        system_prompt: str,
        tool_schemas: list[dict[str, Any]],
        cancellation: CancellationToken,
    ) -> None:
        """Run the agent turn in a worker thread."""
        try:
            final_text = self._agent_engine.run_turn(
                history=history,
                system_prompt=system_prompt,
                tool_schemas=tool_schemas,
                on_text_token=lambda delta: self._enqueue_event(
                    AssistantDelta(turn_id=turn_id, delta=delta)
                ),
                on_tool_call_started=lambda tc_id, tc_name, tc_args: (
                    self._enqueue_event(ToolCallStarted(
                        turn_id=turn_id,
                        tool_call_id=tc_id,
                        tool_name=tc_name,
                        arguments=tc_args,
                    ))
                ),
                on_tool_call_finished=lambda tc_id, tc_name, success: (
                    self._enqueue_event(ToolCallFinished(
                        turn_id=turn_id,
                        tool_call_id=tc_id,
                        tool_name=tc_name,
                        success=success,
                    ))
                ),
                on_tool_output=lambda tc_id, tc_name, output_type, content: (
                    self._enqueue_event(ToolOutputProduced(
                        turn_id=turn_id,
                        tool_call_id=tc_id,
                        tool_name=tc_name,
                        output_type=output_type,
                        content=content,
                    ))
                ),
                on_tool_error=lambda tc_id, tc_name, error: (
                    self._enqueue_event(ToolError(
                        turn_id=turn_id,
                        tool_call_id=tc_id,
                        tool_name=tc_name,
                        error=error,
                    ))
                ),
                execute_tools=lambda tcs, _tid, canc: self._execute_tools_in_turn(
                    tcs, turn_id, canc
                ),
                cancellation=cancellation,
            )

            # Enqueue final message
            message_id = f"msg_final_{turn_id}"
            self._enqueue_event(AssistantFinal(
                turn_id=turn_id,
                message_id=message_id,
                content=final_text,
            ))

        except Exception as exc:
            self._enqueue_event(UICommandFailed(
                command_type="AgentTurn",
                error=f"Agent turn failed: {exc}",
            ))
        finally:
            self._enqueue_event(StatusUpdated(field="turn", value="idle"))
            self._end_turn()

    def _execute_tools_in_turn(
        self,
        tool_calls: list[ToolCall],
        turn_id: str,
        cancellation: CancellationToken,
    ) -> list[tuple[ToolCall, str]]:
        """Execute tool calls during a turn (called from worker thread).

        Handles permission checking, diff/command previews, and execution.
        """
        results: list[tuple[ToolCall, str]] = []

        for tc in tool_calls:
            if cancellation.is_cancelled:
                results.append((tc, "Error: cancelled"))
                continue

            # Check permission level
            is_read_only = self._tool_registry.is_read_only(tc.name)
            if self._permission_manager:
                level = self._permission_manager.check(tc.name, is_read_only=is_read_only)
            elif is_read_only:
                level = "allow"
            else:
                level = "ask"

            if level == "deny":
                self._enqueue_event(ToolRejected(
                    turn_id=turn_id,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                ))
                results.append((tc, f"Permission denied for tool: {tc.name}"))
                continue

            # Determine scope
            scope = self._scope_for_tool(tc.name)
            is_memory_write = self._is_memory_write_tool_call(tc.name, tc.args)

            # Handle approval
            needs_approval = (
                level == "ask"
                and not is_memory_write
                and not self._session_auto_approve.get(scope, False)
            )
            if needs_approval:
                # Emit previews before permission
                self._emit_tool_previews(tc, turn_id)

                # Request permission (blocks until decision)
                request_id = f"perm_{tc.id}"
                decision = self._request_permission_blocking(
                    request_id=request_id,
                    turn_id=turn_id,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    scope=scope,
                    risk_summary=f"Execute {tc.name}",
                    cancellation=cancellation,
                )

                if decision.choice == "no":
                    self._enqueue_event(ToolRejected(
                        turn_id=turn_id,
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                    ))
                    results.append((tc, f"User denied tool: {tc.name}"))
                    continue

                if decision.choice == "yes_all" and scope:
                    self._session_auto_approve[scope] = True

            # Execute the tool
            task_old_state = self._task_old_state_for_call(tc)
            try:
                result_str = self._tool_registry.execute(tc.name, tc.args)
            except Exception as exc:
                result_str = f"Error: {exc}"
            else:
                self._emit_task_state_event(tc, result_str, task_old_state)

            results.append((tc, result_str))

        return results

    def _is_memory_write_tool_call(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Return whether a write/edit targets managed memory files."""
        if self._memory_manager is None or tool_name not in {"write_file", "edit_file"}:
            return False
        path = args.get("path")
        if not isinstance(path, str):
            return False
        return self._memory_manager.is_memory_write_target(path)

    def _scope_for_tool(self, tool_name: str) -> str | None:
        """Determine the permission scope for a tool."""
        if tool_name in {"edit_file", "write_file"}:
            return "write"
        if tool_name == "run_shell":
            return "shell"
        return tool_name

    def _emit_tool_previews(self, tc: ToolCall, turn_id: str) -> None:
        """Emit preview events before permission request."""
        if tc.name in {"edit_file", "write_file"}:
            file_path = str(tc.args.get("path", ""))
            if file_path and tc.name == "write_file":
                new_text = str(tc.args.get("content", ""))
                old_text = ""
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        old_text = f.read()
                except (FileNotFoundError, OSError):
                    pass
                self._enqueue_event(DiffPreviewAvailable(
                    turn_id=turn_id,
                    tool_call_id=tc.id,
                    file_path=file_path,
                    diff_content=self._make_diff(old_text, new_text, file_path),
                ))
            elif file_path and tc.name == "edit_file":
                old_string = str(tc.args.get("old_string", ""))
                new_string = str(tc.args.get("new_string", ""))
                old_text = ""
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        old_text = f.read()
                except (FileNotFoundError, OSError):
                    pass
                new_text = old_text.replace(old_string, new_string)
                self._enqueue_event(DiffPreviewAvailable(
                    turn_id=turn_id,
                    tool_call_id=tc.id,
                    file_path=file_path,
                    diff_content=self._make_diff(old_text, new_text, file_path),
                ))

        elif tc.name == "run_shell":
            cmd = str(tc.args.get("command", ""))
            if cmd:
                self._enqueue_event(CommandPreviewAvailable(
                    turn_id=turn_id,
                    tool_call_id=tc.id,
                    command=cmd,
                ))

    def _make_diff(self, old_text: str, new_text: str, file_path: str) -> str:
        """Build a compact unified diff for preview."""
        return "\n".join(difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=file_path,
            tofile=file_path,
            lineterm="",
        ))

    def _request_permission_blocking(
        self,
        request_id: str,
        turn_id: str,
        tool_call_id: str,
        tool_name: str,
        scope: str,
        risk_summary: str,
        cancellation: CancellationToken,
    ) -> PermissionDecision:
        """Request permission and block until decision (called from worker thread)."""
        request = PermissionRequest(
            request_id=request_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            scope=scope,
            risk_summary=risk_summary,
        )

        wait_event = threading.Event()
        with self._permission_lock:
            self._pending_permission_requests[request_id] = request
            self._permission_wait_events[request_id] = wait_event

        # Emit event for UI
        self._enqueue_event(PermissionRequestEvent(
            request_id=request_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            scope=scope,
            risk_summary=risk_summary,
        ))

        # Block until decision or cancellation
        while not wait_event.wait(timeout=0.1):
            if self._closed:
                return PermissionDecision(choice="no", scope=scope)
            if cancellation.is_cancelled:
                self._record_permission_decision(request_id, PermissionDecision(choice="no", scope=scope))
                break

        with self._permission_lock:
            decision = self._permission_decisions.pop(
                request_id,
                PermissionDecision(choice="no", scope=scope),
            )
            self._pending_permission_requests.pop(request_id, None)
            self._permission_wait_events.pop(request_id, None)

        return decision

    # Slash commands

    def _handle_run_slash_command(self, command: RunSlashCommandCommand) -> None:
        """Handle run slash command."""
        if self._is_compacting:
            self._enqueue_event(UICommandFailed(
                command_type="RunSlashCommandCommand",
                error="Cannot run slash command while compacting context",
            ))
            return

        raw = command.raw.strip()
        parts = raw.split()
        head = parts[0].lower() if parts else ""

        if head == "/help":
            self._enqueue_system_notice(
                "slash_help",
                "\n".join([
                    "/help - Show commands",
                    "/context - Show context budget",
                    "/tasks - Show task list",
                    "/compact - Compact current conversation",
                    "/resume - Show resumable sessions",
                    "/env - Show editable environment settings",
                    "/memory - Show memory status",
                    "/plan - Plan mode controls",
                    "/exit - Exit chat",
                ]),
            )
            return

        if head == "/context":
            cfg = self._config_store.load()
            self._enqueue_system_notice(
                "slash_context",
                "\n".join([
                    f"messages: {len(self._history)}",
                    f"max_tokens: {cfg.max_tokens}",
                    f"render_mode: {cfg.response_render_mode}",
                    f"auto_memory: {'on' if cfg.auto_memory else 'off'}",
                ]),
            )
            return

        if head == "/tasks":
            self._enqueue_system_notice("slash_tasks", self._format_task_list())
            return

        if head == "/compact":
            self._handle_compact(CompactCommand())
            return

        if head == "/resume":
            self._clear_runtime_surfaces()
            sessions = []
            if self._session_store is not None:
                sessions = [
                    self._session_info_to_dict(session)
                    for session in self._session_store.list_sessions()
                ]
            self._enqueue_event(ResumeListLoaded(sessions=sessions))
            return

        if head == "/env":
            cfg = self._config_store.load()
            self._enqueue_system_notice(
                "slash_env",
                "\n".join([
                    "read-only environment display",
                    f"provider: {cfg.provider}",
                    f"base_url: {self._redact_config_value('base_url', cfg.base_url)}",
                    f"model: {cfg.model or '(unset)'}",
                    f"api_key: {self._redact_config_value('api_key', cfg.api_key)}",
                    f"max_tokens: {cfg.max_tokens}",
                    f"max_summary_chars: {cfg.max_summary_chars}",
                ]),
            )
            return

        if head == "/memory":
            self._enqueue_system_notice("slash_memory", self._format_memory_status())
            return

        if head == "/plan":
            action = parts[1].lower() if len(parts) > 1 else ""
            if action in {"approve", "reject"}:
                self._handle_plan_decision(PlanDecisionCommand(
                    decision="approve" if action == "approve" else "reject"
                ))
                return
            if action == "enter":
                if self._plan_mode is not None:
                    self._plan_mode.enter()
                self._enqueue_event(PlanUpdated(plan_content="Planning mode entered."))
                return
            if action == "show":
                self._enqueue_event(PlanUpdated(plan_content=self._format_plan_status()))
                return
            self._enqueue_system_notice(
                "slash_plan",
                "/plan enter | /plan approve | /plan reject",
            )
            return

        if head == "/exit":
            self._handle_exit(ExitCommand())
            return

        self._enqueue_event(UICommandFailed(
            command_type="RunSlashCommandCommand",
            error=f"Unknown slash command: {raw}",
        ))

    def _handle_permission_decision(self, command: PermissionDecisionCommand) -> None:
        """Handle permission decision."""
        with self._permission_lock:
            request = self._pending_permission_requests.pop(command.request_id, None)
        if request is None:
            self._enqueue_event(UICommandFailed(
                command_type="PermissionDecisionCommand",
                error=f"No pending request for id: {command.request_id}",
            ))
            return

        decision = PermissionDecision(
            choice=command.choice,
            scope=request.scope,
        )

        if self._permission_provider:
            if hasattr(self._permission_provider, 'submit_decision'):
                self._permission_provider.submit_decision(command.request_id, decision)

        with self._permission_lock:
            self._permission_decisions[command.request_id] = decision
            wait_event = self._permission_wait_events.get(command.request_id)
            if wait_event:
                wait_event.set()

        self._enqueue_event(PermissionClearedEvent(
            request_id=command.request_id,
            tool_call_id=command.tool_call_id,
        ))

    def _handle_cancel_turn(self, command: CancelTurnCommand) -> None:
        """Handle cancel turn."""
        if self._current_cancellation:
            self._current_cancellation.cancel()

        if self._current_turn_id:
            self._enqueue_event(TurnCancelled(
                turn_id=self._current_turn_id,
                reason=command.reason,
            ))

        # Clear turn surfaces
        self._fail_pending_permissions()
        self._end_turn()

    def _handle_resume_session(self, command: ResumeSessionCommand) -> None:
        """Handle resume session using SessionResumeBuilder for checkpoint-aware restoration."""
        self._clear_runtime_surfaces()
        if self._session_store is None:
            self._enqueue_event(UICommandFailed(
                command_type="ResumeSessionCommand",
                error="No session store available",
            ))
            return

        # Check if session actually exists and capture session info
        sessions = self._session_store.list_sessions()
        selected_session = None
        for s in sessions:
            if s.session_id == command.session_id:
                selected_session = s
                break
        if selected_session is None:
            self._enqueue_event(UICommandFailed(
                command_type="ResumeSessionCommand",
                error=f"Session not found: {command.session_id}",
            ))
            return

        # Use SessionResumeBuilder for checkpoint-aware history restoration
        # with token budget trimming — same logic as legacy /resume.
        # Falls back to raw load_history when no context_manager (e.g. headless tests).
        restored_from_checkpoint = False
        estimated_tokens = 0
        if self._context_manager is not None:
            transcript_path = self._session_store.transcript_path(command.session_id)
            token_budget = int(self._context_manager.max_tokens * 0.6)
            builder = SessionResumeBuilder(self._context_manager, token_budget)
            result = builder.build(transcript_path)
            if not result.history:
                self._enqueue_event(UICommandFailed(
                    command_type="ResumeSessionCommand",
                    error=f"Failed to load session history: {command.session_id}",
                ))
                return
            self._history[:] = result.history
            message_count = result.message_count
            restored_from_checkpoint = result.restored_from_checkpoint
            estimated_tokens = result.estimated_tokens
        else:
            history = self._session_store.load_history(command.session_id)
            if not history:
                self._enqueue_event(UICommandFailed(
                    command_type="ResumeSessionCommand",
                    error=f"Failed to load session history: {command.session_id}",
                ))
                return
            self._history[:] = history
            message_count = len(self._history)

        self._session_id = command.session_id
        self._enqueue_event(ResumeCompleted(
            session_id=command.session_id,
            restored_from_checkpoint=restored_from_checkpoint,
            message_count=message_count,
            estimated_tokens=estimated_tokens,
            last_user_input=selected_session.last_user_input,
        ))
        self._enqueue_event(StatusUpdated(field="resume", value=command.session_id))

    def _handle_compact(self, command: CompactCommand) -> None:
        """Handle compact command."""
        if self.has_active_turn or self._pending_permission_requests:
            self._enqueue_event(UICommandFailed(
                command_type="CompactCommand",
                error="/compact cannot run while a turn or permission request is active",
            ))
            return
        self._is_compacting = True
        self._enqueue_event(CompactionStarted())
        if self._context_manager is None:
            self._is_compacting = False
            self._enqueue_event(CompactionSkipped())
            return

        before_messages = len(self._history)
        previous_summary = self._find_previous_summary(self._history)
        try:
            result = self._context_manager.compress(
                self._history,
                self._llm,
                previous_summary,
            )
        except Exception as exc:
            self._is_compacting = False
            self._enqueue_event(CompactionFailed(error=str(exc)))
            return

        if not result.checkpoint_message:
            self._is_compacting = False
            self._enqueue_event(CompactionSkipped())
            return

        self._history[:] = result.messages
        if self._session_store is not None and self._session_id:
            self._session_store.append_message(self._session_id, result.checkpoint_message)
            self._session_store.append_event(self._session_id, {
                "type": "compaction_checkpoint",
                "summary": result.summary,
                "summary_format": "xcode.v1",
                "source_message_count": before_messages,
            })
        self._is_compacting = False
        self._enqueue_event(CompactionCompleted(
            summary=result.summary,
            source_message_count=before_messages,
        ))

    def _handle_save_env(self, command: SaveEnvCommand) -> None:
        """Handle save env command."""
        for key, value in command.changes.items():
            self._enqueue_event(ConfigUpdated(
                key=key,
                value=self._redact_config_value(key, value),
            ))

    def _handle_plan_decision(self, command: PlanDecisionCommand) -> None:
        """Handle plan decision."""
        if self._plan_mode is not None:
            if command.decision == "approve":
                self._plan_mode.approve()
                self._enqueue_event(PlanUpdated(plan_content="Plan approved."))
            else:
                self._plan_mode.reject()
                self._enqueue_event(PlanUpdated(plan_content="Plan rejected."))
        self._enqueue_event(StatusUpdated(field="plan_decision", value=command.decision))

    def _handle_exit(self, command: ExitCommand) -> None:
        """Handle exit command."""
        self.close()

    def _handle_viewport_state_changed(self, command: ViewportStateChangedCommand) -> None:
        """Handle viewport state changed."""
        self._enqueue_event(StatusUpdated(field="viewport", value=command.is_at_bottom))

    # Permission helpers

    def request_permission(self, request: PermissionRequest) -> PermissionDecision:
        """Request permission for a tool call (deprecated - use _request_permission_blocking).

        This is kept for backward compatibility with Batch 1 tests.
        """
        if self._closed:
            return PermissionDecision(choice="no", scope=request.scope)

        current_turn_id = self.current_turn_id
        if current_turn_id is None:
            if not self._start_turn(request.turn_id):
                raise RuntimeError("Cannot request permission during another active turn")
        elif current_turn_id != request.turn_id:
            raise RuntimeError("Cannot request permission during another active turn")

        wait_event = threading.Event()
        with self._permission_lock:
            self._pending_permission_requests[request.request_id] = request
            self._permission_wait_events[request.request_id] = wait_event

        self._enqueue_event(PermissionRequestEvent(
            request_id=request.request_id,
            turn_id=request.turn_id,
            tool_call_id=request.tool_call_id,
            tool_name=request.tool_name,
            scope=request.scope,
            risk_summary=request.risk_summary,
        ))

        while not wait_event.wait(timeout=0.1):
            if self._closed:
                self._record_permission_decision(
                    request.request_id,
                    PermissionDecision(choice="no", scope=request.scope),
                )
                break
            cancellation = self._current_cancellation
            if cancellation and cancellation.token.is_cancelled:
                self._record_permission_decision(
                    request.request_id,
                    PermissionDecision(choice="no", scope=request.scope),
                )
                break

        with self._permission_lock:
            decision = self._permission_decisions.pop(
                request.request_id,
                PermissionDecision(choice="no", scope=request.scope),
            )
            self._pending_permission_requests.pop(request.request_id, None)
            self._permission_wait_events.pop(request.request_id, None)

        return decision

    def _record_permission_decision(
        self,
        request_id: str,
        decision: PermissionDecision,
    ) -> None:
        """Record and wake a pending permission decision."""
        with self._permission_lock:
            self._permission_decisions[request_id] = decision
            wait_event = self._permission_wait_events.get(request_id)
            if wait_event:
                wait_event.set()

    def _fail_pending_permissions(self) -> None:
        """Fail all pending permission requests closed."""
        with self._permission_lock:
            pending = list(self._pending_permission_requests.items())
            self._pending_permission_requests.clear()

            for request_id, request in pending:
                self._permission_decisions[request_id] = PermissionDecision(
                    choice="no",
                    scope=request.scope,
                )
                wait_event = self._permission_wait_events.get(request_id)
                if wait_event:
                    wait_event.set()

    def _enqueue_system_notice(self, message_id: str, content: str) -> None:
        """Emit a local system notice for Textual command output."""
        self._enqueue_event(SystemNoticeAdded(message_id=message_id, content=content))

    def _clear_runtime_surfaces(self) -> None:
        """Fail pending permission state and ask UI to clear transient surfaces."""
        self._fail_pending_permissions()
        self._enqueue_event(StatusUpdated(field="surfaces", value="clear"))

    def _redact_config_value(self, key: str, value: Any) -> Any:
        """Redact sensitive config values before they reach UI events."""
        if key.lower() in {"api_key", "token", "password", "secret"}:
            return "***" if value else ""
        return value

    def _format_task_list(self) -> str:
        """Format current task tracker state for a local /tasks notice."""
        if self._task_tracker is None:
            return "No tasks."
        tasks = [task for task in self._task_tracker.list_all() if task.status != "deleted"]
        if not tasks:
            return "No tasks."
        return "\n".join(
            f"- {task.subject} [{task.status}]"
            for task in tasks
        )

    def _format_memory_status(self) -> str:
        """Format memory state without touching legacy console rendering."""
        cfg = self._config_store.load()
        lines = [f"auto_memory: {'on' if cfg.auto_memory else 'off'}"]
        if self._memory_manager is not None:
            lines.extend([
                f"project_memory: {self._memory_manager.project_memory_path()}",
                f"user_memory: {self._memory_manager.user_memory_path()}",
            ])
        return "\n".join(lines)

    def _format_plan_status(self) -> str:
        """Format plan state for Textual local display."""
        if self._plan_mode is None:
            return "Plan mode is unavailable."
        if self._plan_mode.pending_approval:
            return f"Plan pending approval: {self._plan_mode.plan_summary or '(no summary)'}"
        if self._plan_mode.is_active:
            return "Planning mode is active."
        return "Planning mode is inactive."

    @staticmethod
    def _find_previous_summary(history: list[dict[str, Any]]) -> str:
        """Find the latest conversation summary checkpoint."""
        for message in reversed(history):
            if message.get("role") == "system":
                content = str(message.get("content", ""))
                marker = "Conversation summary checkpoint:\n"
                if marker in content:
                    return content.split(marker, 1)[-1].strip()
        return ""

    @staticmethod
    def _session_info_to_dict(session: SessionInfo) -> dict[str, Any]:
        """Convert SessionInfo to UI-safe dict payload."""
        return {
            "session_id": session.session_id,
            "updated_at": session.updated_at,
            "last_user_input": session.last_user_input,
            "message_count": session.message_count,
            "has_checkpoint": session.has_checkpoint,
        }

    def _task_old_state_for_call(self, tc: ToolCall) -> str:
        """Capture task state before a mutating task tool runs."""
        if tc.name == "task_create":
            return "none"
        if tc.name != "task_update" or self._task_tracker is None:
            return "unknown"
        task_id = str(tc.args.get("task_id", ""))
        for task in self._task_tracker.list_all():
            if task.id == task_id:
                return task.status
        return "unknown"

    def _emit_task_state_event(self, tc: ToolCall, result_str: str, old_state: str) -> None:
        """Emit UI task state events for task tools."""
        if tc.name == "task_create":
            try:
                payload = json.loads(result_str)
            except json.JSONDecodeError:
                return
            if not isinstance(payload, dict):
                return
            self._enqueue_event(TaskStateChanged(
                task_id=str(payload.get("id", "")),
                old_state=old_state,
                new_state=str(payload.get("status", "pending")),
                description=str(payload.get("subject", "")),
            ))
            return

        if tc.name == "task_update":
            task_id = str(tc.args.get("task_id", ""))
            try:
                payload = json.loads(result_str)
            except json.JSONDecodeError:
                return
            if not isinstance(payload, dict):
                return
            self._enqueue_event(TaskStateChanged(
                task_id=str(payload.get("id", task_id)),
                old_state=old_state,
                new_state=str(payload.get("status", "")),
                description=str(payload.get("subject", "")),
            ))
