"""Textual ChatApp for terminal UI."""
from __future__ import annotations

import time
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
    ReasoningDelta,
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
    AssistantThinkingBlock,
    CommandPreviewView,
    DiffPreviewView,
    ModalScreen,
    PermissionPromptSurface,
    ProgressView,
    SystemNoticeBlock,
    TaskSnapshotBlock,
    ToolCallView,
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

    # ── 工具分类（工具行语义） ──

    # 只读工具：output 不逐条进 transcript，finish 时合并一条摘要
    READ_ONLY_TOOLS: tuple[str, ...] = (
        "read_file", "grep", "glob", "search_file",
        "search_content", "list_files", "ls", "find",
    )

    # Shell 工具：output 只保留 tail 到 ProgressView，finish 时写最终摘要
    SHELL_TOOLS: tuple[str, ...] = ("run_shell", "bash")

    # 编辑工具：diff/approval 不可被折叠隐藏
    EDIT_TOOLS: tuple[str, ...] = ("edit_file", "write_file")

    @classmethod
    def _tool_category(cls, tool_name: str) -> str:
        """返回工具类别: 'read_only' | 'shell' | 'edit' | 'other'."""
        if tool_name in cls.READ_ONLY_TOOLS:
            return "read_only"
        if tool_name in cls.SHELL_TOOLS:
            return "shell"
        if tool_name in cls.EDIT_TOOLS:
            return "edit"
        return "other"

    # ── 五层布局 CSS ──
    # ScrollLayer: transcript viewport owns renderer + thinking/assistant tail + tool rows
    # OverlayLayer: permission/sandbox/ask-user overlays (pending interaction)
    # ModalLayer: resume/env/plan/memory screens (screen-like transient)
    # BottomLayer: new-messages pill + command suggestions + input + status
    # FloatLayer: pet (默认不占位)
    CSS = """
    Screen {
        background: transparent;
    }

    #main-container {
        height: 100%;
        margin: 0 1;
    }

    /* ══ ScrollLayer ══ */
    #transcript {
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #streaming {
        /* streaming tail — 属于 transcript 尾部，不是独立中层面板 */
        height: auto;
        max-height: 50%;
        color: $text;
    }

    /* ══ OverlayLayer (pending interaction) ══ */
    #approval-card {
        /* 语义: PermissionOverlay — 属于 pending_interaction，不进入长期 transcript */
        height: auto;
        max-height: 24;
    }

    /* ══ ModalLayer ══ */
    #resume-selector {
        /* screen-like transient surface */
        height: auto;
        max-height: 12;
    }

    /* ══ BottomLayer ══ */
    #bottom-area {
        height: auto;
        dock: bottom;
        background: transparent;
        padding-top: 1;
    }

    #new-messages {
        height: auto;
    }

    #suggestions {
        height: auto;
        max-height: 10;
    }

    #input-box {
        height: auto;
    }

    #status-bar {
        height: 1;
    }

    /* ══ FloatLayer ══ */
    #pet {
        display: none;
        height: 0;
        width: 0;
    }

    #active-tool {
        /* transient tool row — lives inside TranscriptArea, not fixed current-turn */
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
        self._is_at_bottom = True  # 映射到 store.viewport.is_at_bottom
        self._renderer: RichLogRenderer | None = None
        self._pending_permission: bool = False  # 映射到 store.pending_interaction.permission
        self._pending_previews: dict[str, DiffPreviewView | CommandPreviewView] = {}
        self._tasks_by_id: dict[str, dict[str, str]] = {}
        self._is_resume_selecting: bool = False  # 对应 modal=RESUME 状态
        self._is_compacting: bool = False

    def compose(self) -> ComposeResult:
        """Compose the app — 五层布局结构.

        ScrollLayer:   TranscriptArea owns TranscriptRenderer + StreamingTail + tool transient rows
        OverlayLayer:  ApprovalCard (语义 PermissionOverlay)
        ModalLayer:    ResumeSelector (语义 screen-like transient)
        BottomLayer:   NewMessagesPill + CommandSuggestions + InputBox + StatusBar
        FloatLayer:    PetSurface (默认不占位)
        """
        with Vertical(id="main-container"):
            # ══ ScrollLayer: transcript viewport owns renderer + streaming/thinking tail + tool rows ══
            yield TranscriptArea(id="transcript")

            # ══ OverlayLayer: pending interaction (permission/sandbox/ask-user) ══
            yield ApprovalCard(id="approval-card")  # 语义: PermissionOverlay

            # ══ ModalLayer: screen-like transient surface ══
            yield ResumeSelector(id="resume-selector")

            # ══ BottomLayer: pill + suggestions + input + status ══
            with Vertical(id="bottom-area"):
                yield NewMessagesPill(id="new-messages")
                yield CommandSuggestions(id="suggestions")
                yield InputBox(id="input-box")
                yield StatusBar(id="status-bar")

            # ══ FloatLayer: pet（默认不占位） ══
            yield PetSurface(id="pet")

    def on_mount(self) -> None:
        """Initialize the app — 连接 ScrollLayer renderer 并初始化状态."""
        # 初始化 renderer（ScrollLayer 核心）
        history = self.query_one("#history", RichLogHistory)
        self._renderer = RichLogRenderer(history)
        self.update_status_bar()
        self.set_interval(0.1, self.poll_events)

        # 初始 focus 在输入框（BottomLayer）
        self.query_one("#input").focus()

    def poll_events(self) -> None:
        """Poll events from the controller."""
        events = self.controller.drain_events()
        for event in events:
            self.handle_event(event)

    def handle_event(self, event: UIEvent) -> None:
        """Handle a UI event — 按状态域路由到五层布局.

        ScrollLayer:  UserMessage / Assistant / Tool / System / Task
        OverlayLayer: Permission / Diff / Command preview
        ModalLayer:   Resume / Plan
        BottomLayer:  Status / Config
        FloatLayer:   (pet 后续)
        """
        if isinstance(event, UserMessageAdded):
            self._handle_user_message_added(event)
        elif isinstance(event, AssistantDelta):
            self._handle_assistant_delta(event)
        elif isinstance(event, ReasoningDelta):
            self._handle_reasoning_delta(event)
        elif isinstance(event, AssistantFinal):
            self._handle_assistant_final(event)
        elif isinstance(event, StatusUpdated):
            self._handle_status_updated(event)
        elif isinstance(event, SystemNoticeAdded):
            self._handle_system_notice(event)
        elif isinstance(event, UICommandFailed):
            self._handle_command_failed(event)
        # ScrollLayer: Tool events → transcript dynamic rows
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
        # Turn lifecycle
        elif isinstance(event, TurnCancelled):
            self._handle_turn_cancelled(event)
        # OverlayLayer: Permission and previews (pending interaction)
        elif isinstance(event, PermissionRequestEvent):
            self._handle_permission_request(event)
        elif isinstance(event, PermissionClearedEvent):
            self._handle_permission_cleared(event)
        elif isinstance(event, DiffPreviewAvailable):
            self._handle_diff_preview(event)
        elif isinstance(event, CommandPreviewAvailable):
            self._handle_command_preview(event)
        # Compaction
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
        """流式文本 — 更新 StreamingWidget + store.stream 状态域."""
        streaming = self.query_one("#streaming", StreamingWidget)
        new_text = streaming.text + event.delta
        streaming.update_text(new_text)
        # 同步写入 store.stream（ScrollLayer streaming tail 状态域）
        self.store.stream.assistant_text = new_text

    def _handle_reasoning_delta(self, event: ReasoningDelta) -> None:
        """Reasoning/thinking delta — 进入 ScrollLayer transcript tail.

        thinking 作为 streaming tail 一部分渲染（dim 样式），
        不进入 current_turn 固定面板。
        """
        now = time.monotonic()
        if self.store.thinking.active_started_at is None:
            self.store.thinking.active_started_at = now

        # 更新独立 thinking 状态域，stream.thinking_text 仅作为 widget 兼容镜像。
        current = self.store.thinking.active_buffer or ""
        new_text = current + event.delta
        self.store.thinking.active_buffer = new_text
        self.store.stream.thinking_text = new_text

        # 渲染到 StreamingWidget transcript tail（dim 前缀）
        streaming = self.query_one("#streaming", StreamingWidget)
        streaming.update_thinking(new_text)

    def _handle_assistant_final(self, event: AssistantFinal) -> None:
        """Assistant 完成 — 清理 streaming（含 thinking）+ 写入长期 transcript."""
        streaming = self.query_one("#streaming", StreamingWidget)
        streaming.clear_text()  # 同时清 text 和 thinking_text

        thinking_block = self._finalize_active_thinking(event.message_id)
        if thinking_block is not None:
            self.store.add_message_block(thinking_block)
            if self._renderer:
                self._renderer.append(thinking_block)

        # 清理 store.stream 状态域
        self.store.stream.assistant_text = ""
        self.store.stream.thinking_text = None

        block = AssistantMessageBlock(
            id=event.message_id,
            kind="assistant_message",
            content=event.content,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

        # 用户不在底部时更新 unseen_count 并显示 pill
        if not self._is_at_bottom:
            self.store.viewport.unseen_count += 1
            pill = self.query_one("#new-messages", NewMessagesPill)
            pill.show_pill(self.store.viewport.unseen_count)
        else:
            self.store.viewport.unseen_count = 0

    def _finalize_active_thinking(self, message_id: str) -> AssistantThinkingBlock | None:
        """Move active thinking from transcript tail into a finalized transcript row."""
        content = self.store.thinking.active_buffer
        if not content:
            return None

        ended_at = time.monotonic()
        started_at = self.store.thinking.active_started_at
        elapsed = ended_at - started_at if started_at is not None else None
        self.store.thinking.active_ended_at = ended_at

        block = AssistantThinkingBlock(
            id=f"thinking_{message_id}",
            content=content,
            display_mode=self.store.thinking.display_mode,
            elapsed=elapsed,
            model_visible=False,
            persist_ui=True,
        )
        self.store.thinking.finalized_blocks[message_id] = block
        self.store.thinking.active_buffer = None
        self.store.thinking.active_started_at = None
        return block

    # ── ScrollLayer: 工具事件 → transcript renderer 动态行 ──

    def _handle_tool_call_started(self, event: ToolCallStarted) -> None:
        """工具开始 — 按类别区分行为.

        read_only: 极简行（不逐条污染 transcript）
        shell:     初始化 ProgressView，写入简短摘要 block
        edit:      写入摘要 block（diff/approval 不可被折叠隐藏）
        other:     默认行为
        """
        category = self._tool_category(event.tool_name)

        # 更新 tool_views 状态域（ScrollLayer）
        self.store.tool_views.tool_calls[event.tool_call_id] = ToolCallView(
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_name,
            status="running",
        )

        # 安全截断参数
        safe_args: dict[str, object] = {}
        if event.arguments:
            safe_args = {
                k: v for k, v in event.arguments.items()
                if k not in ("api_key", "password", "token", "secret")
            }

        if category == "read_only":
            # 只读工具：显示轻量 transient row，不写长期 transcript block
            indicator = self.query_one("#active-tool", ActiveToolIndicator)
            indicator.show_tool(event.tool_call_id, event.tool_name)
            # 初始化 ProgressView 用于后续合并
            self.store.tool_views.progress[event.tool_call_id] = ProgressView(
                tool_call_id=event.tool_call_id,
            )

        elif category == "shell":
            # Shell 工具：初始化 ProgressView，写简短摘要 block
            indicator = self.query_one("#active-tool", ActiveToolIndicator)
            indicator.show_tool(event.tool_call_id, event.tool_name)
            self.store.tool_views.progress[event.tool_call_id] = ProgressView(
                tool_call_id=event.tool_call_id,
            )
            cmd_preview = safe_args.get("command", "") if safe_args else ""
            summary_text = f"{event.tool_name}"
            if cmd_preview:
                summary_text += f" {str(cmd_preview)[:80]}"
            block = ToolSummaryBlock(
                id=f"tool_sum_{event.tool_call_id}",
                tool_name=event.tool_name,
                tool_call_id=event.tool_call_id,
                summary=summary_text,
            )
            self.store.add_message_block(block)
            if self._renderer:
                self._renderer.append(block)

        elif category == "edit":
            # 编辑工具：写摘要 block（不可被折叠隐藏）
            indicator = self.query_one("#active-tool", ActiveToolIndicator)
            indicator.show_tool(event.tool_call_id, event.tool_name)
            file_path = safe_args.get("file_path", "") if safe_args else ""
            summary_text = f"{event.tool_name} {str(file_path)[:80]}"
            block = ToolSummaryBlock(
                id=f"tool_sum_{event.tool_call_id}",
                tool_name=event.tool_name,
                tool_call_id=event.tool_call_id,
                summary=summary_text.strip(),
            )
            self.store.add_message_block(block)
            if self._renderer:
                self._renderer.append(block)

        else:
            # other: 默认行为
            indicator = self.query_one("#active-tool", ActiveToolIndicator)
            indicator.show_tool(event.tool_call_id, event.tool_name)
            summary_text = f"{event.tool_name}"
            if safe_args:
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
        """工具完成 — 按类别写最终摘要到 transcript.

        read_only: 合并摘要（一行，含文件数/行数/字节数）
        shell:     最终摘要（elapsed, line_count, byte_count, tail）
        edit:      正常摘要
        other:     默认行为
        """
        # 更新 tool_views 状态
        if event.tool_call_id in self.store.tool_views.tool_calls:
            self.store.tool_views.tool_calls[event.tool_call_id].status = (
                "resolved" if event.success else "error"
            )

        category = self._tool_category(event.tool_name)
        prog = self.store.tool_views.progress.get(event.tool_call_id)

        if category == "read_only":
            # 只读工具可能是 finish 先于 result。已有 stdout/stderr chunk 时才在这里落 transcript；
            # 普通 result 由 _handle_tool_output 消费，避免 finish 抢先 pop 掉 progress。
            if prog and (prog.line_count or prog.byte_count or prog.tail_stdout or prog.tail_stderr):
                parts = [event.tool_name]
                if prog.line_count:
                    parts.append(f"{prog.line_count} lines")
                if prog.byte_count:
                    if prog.byte_count >= 1024:
                        parts.append(f"{prog.byte_count / 1024:.1f}KB")
                    else:
                        parts.append(f"{prog.byte_count}B")
                parts.append("done" if event.success else "error")
                block = ToolResultBlock(
                    id=f"tool_res_{event.tool_call_id}",
                    tool_name=event.tool_name,
                    tool_call_id=event.tool_call_id,
                    result=" ".join(parts),
                )
                self.store.add_message_block(block)
                if self._renderer:
                    self._renderer.append(block)
                self.store.tool_views.progress.pop(event.tool_call_id, None)

        elif category == "shell":
            # Shell result 在当前真实路径中会晚于 finish 到达；只有已有 progress chunk 时才落 transcript。
            if prog and (prog.line_count or prog.byte_count or prog.tail_stdout or prog.tail_stderr):
                summary_parts: list[str] = []
                if prog.line_count:
                    summary_parts.append(f"{prog.line_count} lines")
                if prog.byte_count:
                    if prog.byte_count >= 1024:
                        summary_parts.append(f"{prog.byte_count / 1024:.1f}KB")
                    else:
                        summary_parts.append(f"{prog.byte_count}B")
                tail_text = prog.tail_stdout or prog.tail_stderr
                if tail_text:
                    truncated = tail_text[-200:]
                    if len(tail_text) > 200:
                        truncated = f"...\n{truncated}"
                    summary_parts.append(truncated)
                status = "done" if event.success else "error"
                block = ToolResultBlock(
                    id=f"tool_res_{event.tool_call_id}",
                    tool_name=event.tool_name,
                    tool_call_id=event.tool_call_id,
                    result=f"{event.tool_name} {status}: {' | '.join(summary_parts) if summary_parts else status}",
                )
                self.store.add_message_block(block)
                if self._renderer:
                    self._renderer.append(block)
                self.store.tool_views.progress.pop(event.tool_call_id, None)

        elif category == "edit":
            # 编辑工具完成：diff 已通过 OverlayLayer 处理，此处只写确认行
            status = "applied" if event.success else "failed"
            block = ToolResultBlock(
                id=f"tool_res_{event.tool_call_id}",
                tool_name=event.tool_name,
                tool_call_id=event.tool_call_id,
                result=f"{event.tool_name} {status}",
            )
            self.store.add_message_block(block)
            if self._renderer:
                self._renderer.append(block)

        # else: other 工具不在此额外写入（output handler 已处理）

        # 隐藏 ActiveToolIndicator
        indicator = self.query_one("#active-tool", ActiveToolIndicator)
        indicator.hide_tool()

    def _handle_tool_output(self, event: ToolOutputProduced) -> None:
        """工具输出 — 按类别区分，避免逐 chunk 污染长期 transcript.

        read_only: 累积到 ProgressView，不写 MessageBlock（finish 时合并摘要）
        shell:     更新 ProgressView tail/line_count/byte_count，不写 MessageBlock
        edit:      正常走 diff/approval 路径，不在此处隐去
        other:     默认行为（写入 ToolResultBlock）
        """
        if event.output_type == "rejected":
            return  # Handled by ToolRejected event

        category = self._tool_category(event.tool_name)

        if category == "read_only":
            # 只读工具 output 不逐条进 transcript — 更新 ProgressView 累积
            prog = self.store.tool_views.progress.get(event.tool_call_id)
            if prog is None:
                prog = ProgressView(tool_call_id=event.tool_call_id)
                self.store.tool_views.progress[event.tool_call_id] = prog
            # 追加到 tail_stdout（只保留最后 300 字符）
            content = event.content
            if event.output_type in ("stdout", "stderr", "result", "summary"):
                combined = f"{prog.tail_stdout}\n{content}" if prog.tail_stdout else content
                prog.tail_stdout = combined[-300:]
                lines = content.splitlines()
                prog.line_count += len(lines) if lines else 1
                prog.byte_count += len(content.encode("utf-8", errors="replace"))
                if event.output_type in ("result", "summary"):
                    parts = [event.tool_name]
                    if prog.line_count:
                        parts.append(f"{prog.line_count} lines")
                    if prog.byte_count:
                        if prog.byte_count >= 1024:
                            parts.append(f"{prog.byte_count / 1024:.1f}KB")
                        else:
                            parts.append(f"{prog.byte_count}B")
                    block = ToolResultBlock(
                        id=f"tool_res_{event.tool_call_id}",
                        tool_name=event.tool_name,
                        tool_call_id=event.tool_call_id,
                        result=" ".join(parts),
                    )
                    self.store.add_message_block(block)
                    if self._renderer:
                        self._renderer.append(block)
                    self.store.tool_views.progress.pop(event.tool_call_id, None)

        elif category == "shell":
            # Shell 输出：更新 ProgressView tail + line_count + byte_count
            prog = self.store.tool_views.progress.get(event.tool_call_id)
            if prog is None:
                prog = ProgressView(tool_call_id=event.tool_call_id)
                self.store.tool_views.progress[event.tool_call_id] = prog
            content = event.content
            if event.output_type == "stderr":
                combined = f"{prog.tail_stderr}\n{content}" if prog.tail_stderr else content
                prog.tail_stderr = combined[-500:]
            else:
                combined = f"{prog.tail_stdout}\n{content}" if prog.tail_stdout else content
                prog.tail_stdout = combined[-500:]
            lines = content.splitlines()
            prog.line_count += len(lines) if lines else 1
            prog.byte_count += len(content.encode("utf-8", errors="replace"))
            if event.output_type in ("result", "summary"):
                summary_parts: list[str] = []
                if prog.line_count:
                    summary_parts.append(f"{prog.line_count} lines")
                if prog.byte_count:
                    if prog.byte_count >= 1024:
                        summary_parts.append(f"{prog.byte_count / 1024:.1f}KB")
                    else:
                        summary_parts.append(f"{prog.byte_count}B")
                tail_text = prog.tail_stdout or prog.tail_stderr
                if tail_text:
                    truncated = tail_text[-200:]
                    if len(tail_text) > 200:
                        truncated = f"...\n{truncated}"
                    summary_parts.append(truncated)
                block = ToolResultBlock(
                    id=f"tool_res_{event.tool_call_id}",
                    tool_name=event.tool_name,
                    tool_call_id=event.tool_call_id,
                    result=f"{event.tool_name} done: {' | '.join(summary_parts) if summary_parts else content[:200]}",
                )
                self.store.add_message_block(block)
                if self._renderer:
                    self._renderer.append(block)
                self.store.tool_views.progress.pop(event.tool_call_id, None)

        elif category == "edit":
            # 编辑工具 diff output：不写入 ToolResultBlock
            # diff 通过 DiffPreviewAvailable 走 OverlayLayer approval 路径
            if event.output_type in ("diff", "result", "summary"):
                # 仅当非 diff 通道时写入简短摘要
                if event.output_type != "diff":
                    block = ToolResultBlock(
                        id=f"tool_res_{event.tool_call_id}",
                        tool_name=event.tool_name,
                        tool_call_id=event.tool_call_id,
                        result=event.content[:200],
                    )
                    self.store.add_message_block(block)
                    if self._renderer:
                        self._renderer.append(block)

        else:
            # other: 默认行为，截断到 500 字符
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
        """工具拒绝 — 作为长期证据进入 transcript."""
        block = ToolRejectedBlock(
            id=f"tool_rej_{event.tool_call_id}",
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
        )
        self.store.add_message_block(block)
        if self._renderer:
            self._renderer.append(block)

    def _handle_tool_error(self, event: ToolError) -> None:
        """工具错误 — 作为长期证据进入 transcript."""
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
        """Turn 取消 — 清理所有层 transient 状态，保留长期 evidence block."""
        # ScrollLayer: 清理 streaming tail（含 thinking）
        streaming = self.query_one("#streaming", StreamingWidget)
        streaming.clear_text()
        self.store.stream.assistant_text = ""
        self.store.stream.thinking_text = None
        self.store.thinking.active_buffer = None
        self.store.thinking.active_started_at = None
        self.store.thinking.active_ended_at = None

        # ScrollLayer: 清理 active tool indicator
        indicator = self.query_one("#active-tool", ActiveToolIndicator)
        indicator.hide_tool()

        # OverlayLayer: 清理 pending permission
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.hide_card()

        self._pending_permission = False
        self.store.clear_all_turn_surfaces()
        # 清理工具视图状态（ScrollLayer transient rows）
        self.store.tool_views.tool_calls.clear()
        self.store.tool_views.progress.clear()
        self.update_status_bar()

    # ── OverlayLayer: Permission (pending interaction) ──

    def _handle_permission_request(self, event: PermissionRequestEvent) -> None:
        """Show permission prompt — 写入 pending_interaction (OverlayLayer).

        permission 属于 pending interaction，不污染长期 transcript。
        """
        self._pending_permission = True
        # 同步写入新旧状态域
        self.store.set_pending_permission(PermissionPromptSurface(
            id=f"permission_{event.request_id}",
            turn_id=event.turn_id,
            tool_call_id=event.tool_call_id,
            request_id=event.request_id,
            tool_name=event.tool_name,
            scope=event.scope,
            risk_summary=event.risk_summary,
        ))
        self._attach_pending_preview(event.tool_call_id)
        # ApprovalCard 语义为 PermissionOverlay — OverlayLayer
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
        """Clear permission prompt — 只清除 pending interaction，不清历史证据."""
        self._pending_permission = False
        self.store.set_pending_permission(None)
        self._pending_previews.pop(event.tool_call_id, None)
        # 不清掉同一 tool 的历史证据（ToolRejected/ToolError 继续保留在 transcript）
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.hide_card()
        self._clear_input_value()
        self.update_status_bar()

        # 恢复 input focus（BottomLayer）
        self.query_one("#input").focus()

    def on_approval_card_decision(self, event: ApprovalCard.Decision) -> None:
        """Handle permission decision from approval card."""
        self.controller.dispatch(PermissionDecisionCommand(
            request_id=event.request_id,
            tool_call_id=event.tool_call_id,
            choice=event.choice,  # type: ignore[arg-type]
        ))

    def on_key(self, event: "textual.events.Key") -> None:  # type: ignore[name-defined]
        """Global key handler — 键盘优先级.

        优先级: resume selection > pending permission > normal input
        """
        # 最高优先: ModalLayer resume selection
        if self._is_resume_selecting:
            if self._handle_resume_key(event.key.lower()):
                event.stop()
            return

        # 中等优先: OverlayLayer pending permission
        if not self._pending_permission:
            return

        if self.handle_permission_key(event.key.lower()):
            event.stop()

    # ── OverlayLayer: Diff/command preview (pending interaction) ──

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
                self.store.modal = None
                self.controller.dispatch(ResumeSessionCommand(session_id=session_id))

    def _cancel_resume_selection(self) -> None:
        """Cancel resume selection — 退出 ModalLayer."""
        selector = self.query_one("#resume-selector", ResumeSelector)
        selector.hide_selector()
        self._is_resume_selecting = False
        self.store.modal = None
        self.add_system_notice("resume_cancelled", "Cancelled.")

    def _clear_input_value(self) -> None:
        """Clear the text input if it is mounted."""
        input_box = self.query_one("#input")
        if hasattr(input_box, "value"):
            input_box.value = ""

    def _handle_diff_preview(self, event: DiffPreviewAvailable) -> None:
        """Diff 预览 — 挂到 pending interaction (OverlayLayer).

        diff preview 不成为长期 MessageBlock。
        """
        preview = DiffPreviewView(
            file_path=event.file_path,
            diff_content=event.diff_content,
        )
        self._pending_previews[event.tool_call_id] = preview
        self._attach_pending_preview(event.tool_call_id)
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.show_diff(event.file_path, event.diff_content)

    def _handle_command_preview(self, event: CommandPreviewAvailable) -> None:
        """命令预览 — 挂到 pending interaction (OverlayLayer)."""
        preview = CommandPreviewView(command=event.command)
        self._pending_previews[event.tool_call_id] = preview
        self._attach_pending_preview(event.tool_call_id)
        approval_card = self.query_one("#approval-card", ApprovalCard)
        approval_card.show_command(event.command)

    def _attach_pending_preview(self, tool_call_id: str) -> None:
        """Attach a preview to the active permission, even if preview arrived first."""
        permission = self.store.pending_interaction.permission
        if permission is None or permission.tool_call_id != tool_call_id:
            return
        preview = self._pending_previews.get(tool_call_id)
        if preview is not None:
            permission.preview = preview

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
        """进入 ModalLayer resume selection 状态."""
        if not event.sessions:
            self.add_system_notice("resume_empty", "No recent sessions found for this project.")
            return

        selector = self.query_one("#resume-selector", ResumeSelector)
        selector.show_sessions(event.sessions)
        selector.scroll_visible()
        self._is_resume_selecting = True
        self.store.modal = ModalScreen.RESUME

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
            # 清理 ScrollLayer transient 状态
            self.store.stream.assistant_text = ""
            self.store.stream.thinking_text = None
            self.store.thinking.active_buffer = None
            self.store.thinking.active_started_at = None
            self.store.thinking.active_ended_at = None
            self.store.tool_views.tool_calls.clear()
            self.store.tool_views.progress.clear()
            try:
                self.query_one("#active-tool", ActiveToolIndicator).hide_tool()
                self.query_one("#approval-card", ApprovalCard).hide_card()
                streaming = self.query_one("#streaming", StreamingWidget)
                streaming.clear_text()
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
        """Handle input submission — BottomLayer 输入阻塞语义.

        阻塞优先级: resume selection > pending permission > compacting > normal input
        """
        # Block input while permission is pending (OverlayLayer)
        if self._pending_permission:
            self.add_system_notice(
                f"blocked_{id(event)}",
                "Please respond to the permission prompt first (y/n/a).",
            )
            return

        # Block input while resume selection is active (ModalLayer)
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
        """Handle scroll events — 同步 store.viewport."""
        # 同步新旧 viewport 状态
        self.store.viewport.is_at_bottom = self._is_at_bottom
        self.controller.dispatch(ViewportStateChangedCommand(is_at_bottom=self._is_at_bottom))

        # 回到底部时清除 unseen_count 和 pill
        if self._is_at_bottom:
            self.store.viewport.unseen_count = 0
            pill = self.query_one("#new-messages", NewMessagesPill)
            pill.hide_pill()
