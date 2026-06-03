"""Renderers for Textual UI — ScrollLayer 渲染管线.

RichLogRenderer = 第一版 TranscriptRenderer，只渲染 finalized rows。
后续扩展：ToolUseRow / ToolProgressRow / ToolResultRow / InlineTransientRows / SpinnerRow。
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

from xcode_cli.core.ui.state import (
    AssistantMessageBlock,
    AssistantThinkingBlock,
    ContextSummaryBlock,
    MemoryStatusBlock,
    MessageBlock,
    SystemNoticeBlock,
    TaskListBlock,
    TaskSnapshotBlock,
    ToolErrorBlock,
    ToolRejectedBlock,
    ToolResultBlock,
    ToolSummaryBlock,
    UserMessageBlock,
)


class RichLogRenderer:
    """ScrollLayer: TranscriptRenderer（第一版） — 将 MessageBlock 渲染到 RichLog.

    只渲染 finalized rows，streaming/tool 动态行由其他 widget 处理。
    """

    def __init__(self, rich_log: RichLog) -> None:
        self._rich_log = rich_log

    def append(self, block: MessageBlock) -> None:
        """Append a message block to the RichLog."""
        if isinstance(block, UserMessageBlock):
            self._render_user_message(block)
        elif isinstance(block, AssistantMessageBlock):
            self._render_assistant_message(block)
        elif isinstance(block, AssistantThinkingBlock):
            self._render_assistant_thinking(block)
        elif isinstance(block, ToolSummaryBlock):
            self._render_tool_summary(block)
        elif isinstance(block, ToolResultBlock):
            self._render_tool_result(block)
        elif isinstance(block, ToolRejectedBlock):
            self._render_tool_rejected(block)
        elif isinstance(block, ToolErrorBlock):
            self._render_tool_error(block)
        elif isinstance(block, SystemNoticeBlock):
            self._render_system_notice(block)
        elif isinstance(block, ContextSummaryBlock):
            self._render_context_summary(block)
        elif isinstance(block, TaskSnapshotBlock):
            self._render_task_snapshot(block)
        elif isinstance(block, TaskListBlock):
            self._render_task_list(block)
        elif isinstance(block, MemoryStatusBlock):
            self._render_memory_status(block)
        else:
            self._render_unknown_block(block)

    def _render_user_message(self, block: UserMessageBlock) -> None:
        text = Text("You: ", style="bold cyan")
        text.append(str(block.content), style="bold default")
        self._rich_log.write(text)

    def _render_assistant_message(self, block: AssistantMessageBlock) -> None:
        self._rich_log.write(Text(str(block.content)))

    def _render_assistant_thinking(self, block: AssistantThinkingBlock) -> None:
        if block.display_mode == "hidden":
            return
        if block.display_mode == "expanded":
            text = Text("Thinking\n", style="dim italic")
            text.append(str(block.content), style="dim")
        else:
            suffix = ""
            if block.elapsed is not None:
                suffix = f" for {block.elapsed:.1f}s"
            text = Text(f"Thinking{suffix}", style="dim italic")
        self._rich_log.write(text)

    def _render_tool_summary(self, block: ToolSummaryBlock) -> None:
        text = Text(f"Tool: {block.tool_name}", style="bold dim")
        if block.summary and block.summary != block.tool_name:
            args_preview = block.summary[len(block.tool_name):].strip()
            if args_preview:
                text.append(f" {args_preview}", style="italic dim")
        self._rich_log.write(text)

    def _render_tool_result(self, block: ToolResultBlock) -> None:
        result_preview = block.result[:120].replace("\n", " ")
        if len(block.result) > 120:
            result_preview += "..."
        self._rich_log.write(Text(f"Result: {result_preview}", style="dim"))

    def _render_tool_rejected(self, block: ToolRejectedBlock) -> None:
        self._rich_log.write(
            Text(f"Tool rejected: {block.tool_name}", style="bold yellow")
        )

    def _render_tool_error(self, block: ToolErrorBlock) -> None:
        text = Text(f"Error in {block.tool_name}: ", style="bold red")
        text.append(str(block.error), style="dim red")
        self._rich_log.write(text)

    def _render_system_notice(self, block: SystemNoticeBlock) -> None:
        self._rich_log.write(Text(f"Notice: {block.content}", style="dim cyan"))

    def _render_context_summary(self, block: ContextSummaryBlock) -> None:
        self._rich_log.write(Text(f"Context summary: {block.summary}", style="dim"))

    def _render_task_snapshot(self, block: TaskSnapshotBlock) -> None:
        if block.tasks:
            self._rich_log.write(
                Text(f"Tasks: {len(block.tasks)} active", style="dim")
            )

    def _render_task_list(self, block: TaskListBlock) -> None:
        if block.tasks:
            self._rich_log.write(
                Text(f"Task list: {len(block.tasks)} tasks", style="dim")
            )

    def _render_memory_status(self, block: MemoryStatusBlock) -> None:
        self._rich_log.write(Text(f"Memory: {block.status}", style="dim"))

    def _render_unknown_block(self, block: MessageBlock) -> None:
        self._rich_log.write(Text(f"Unknown block: {block.kind}", style="dim"))
