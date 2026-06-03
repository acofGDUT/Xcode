"""UI state models for Textual-based terminal UI.

五层布局状态域：
  ScrollLayer  → messages + stream + tool_views + current_turn.inline_surfaces
  OverlayLayer → pending_interaction (permission / sandbox / ask_user)
  ModalLayer   → modal.screen (Resume / Env / Plan / Memory)
  BottomLayer  → bottom (input_enabled / command_suggestions / sticky_permission_footer)
  FloatLayer   → viewport (is_at_bottom / unseen_count / sticky_prompt) + pet

状态域之间通过 UIStore 统一管理，布局层只消费不反向写入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Screen enum for ModalLayer ──

class ModalScreen(Enum):
    """ModalLayer 当前展示的 screen 类型."""
    RESUME = "resume"
    ENV = "env"
    PLAN = "plan"
    MEMORY = "memory"


# ── Pet mode enum for FloatLayer ──

class PetMode(Enum):
    """Pet 显示模式."""
    IDLE = "idle"
    TOOL = "tool"
    TASK = "task"
    ERROR = "error"


# ── MessageBlock types - long-term UI history (ScrollLayer) ──

@dataclass
class MessageBlock:
    """Base class for message blocks in UI history."""
    id: str
    kind: str
    created_at: float = 0.0
    model_visible: bool = False
    persist_ui: bool = True


@dataclass
class UserMessageBlock(MessageBlock):
    """User message block."""
    content: str = ""
    kind: str = "user_message"


@dataclass
class AssistantMessageBlock(MessageBlock):
    """Assistant message block."""
    content: str = ""
    kind: str = "assistant_message"


@dataclass
class AssistantThinkingBlock(MessageBlock):
    """Finalized assistant thinking block rendered by TranscriptRenderer."""
    content: str = ""
    display_mode: str = "collapsed"  # collapsed / expanded / hidden
    elapsed: float | None = None
    kind: str = "assistant_thinking"


@dataclass
class ToolSummaryBlock(MessageBlock):
    """Tool call summary block."""
    tool_name: str = ""
    tool_call_id: str = ""
    summary: str = ""
    kind: str = "tool_summary"


@dataclass
class ToolResultBlock(MessageBlock):
    """Tool result block."""
    tool_name: str = ""
    tool_call_id: str = ""
    result: str = ""
    kind: str = "tool_result"


@dataclass
class ToolRejectedBlock(MessageBlock):
    """Tool rejected block."""
    tool_name: str = ""
    tool_call_id: str = ""
    kind: str = "tool_rejected"


@dataclass
class TaskSnapshotBlock(MessageBlock):
    """Task snapshot block."""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "task_snapshot"


@dataclass
class SystemNoticeBlock(MessageBlock):
    """System notice block."""
    content: str = ""
    kind: str = "system_notice"


@dataclass
class ToolErrorBlock(MessageBlock):
    """Tool error block."""
    tool_name: str = ""
    tool_call_id: str = ""
    error: str = ""
    kind: str = "tool_error"


@dataclass
class ContextSummaryBlock(MessageBlock):
    """Context summary block (after compaction)."""
    summary: str = ""
    kind: str = "context_summary"


@dataclass
class TaskListBlock(MessageBlock):
    """Task list block."""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "task_list"


@dataclass
class MemoryStatusBlock(MessageBlock):
    """Memory status block."""
    status: str = ""
    kind: str = "memory_status"


# TurnSurface types - current-turn UI surface

@dataclass
class TurnSurface:
    """Base class for current-turn UI surfaces."""
    id: str
    turn_id: str
    tool_call_id: str | None = None
    kind: str = ""


@dataclass
class DiffPreviewSurface(TurnSurface):
    """Diff preview surface."""
    file_path: str = ""
    diff_content: str = ""
    kind: str = "diff_preview"


@dataclass
class CommandPreviewSurface(TurnSurface):
    """Command preview surface."""
    command: str = ""
    kind: str = "command_preview"


@dataclass
class PermissionPromptSurface(TurnSurface):
    """Permission prompt surface."""
    request_id: str = ""
    tool_name: str = ""
    scope: str = ""
    risk_summary: str = ""
    kind: str = "permission_prompt"


@dataclass
class ActiveToolSurface(TurnSurface):
    """Active tool execution surface."""
    tool_name: str = ""
    status: str = ""
    kind: str = "active_tool"


# ── Stream domain (ScrollLayer: streaming tail) ──

@dataclass
class ToolUseDraft:
    """Streaming 中的工具调用草稿."""
    tool_call_id: str
    tool_name: str
    arguments_json: str = ""


@dataclass
class StreamView:
    """ScrollLayer 中 streaming tail 的状态."""
    assistant_text: str = ""
    thinking_text: str | None = None
    streaming_tool_uses: dict[str, ToolUseDraft] = field(default_factory=dict)


# ── Thinking domain (ScrollLayer: transcript renderer/tail) ──

@dataclass
class ThinkingState:
    """Assistant thinking state — transcript renderer/tail, not current_turn."""
    active_buffer: str | None = None
    active_started_at: float | None = None
    active_ended_at: float | None = None
    finalized_blocks: dict[str, AssistantThinkingBlock] = field(default_factory=dict)
    display_mode: str = "collapsed"  # collapsed / expanded / hidden


# ── Tool views domain (ScrollLayer: dynamic tool rows) ──

@dataclass
class ToolCallView:
    """单个工具调用的 UI 视图状态."""
    tool_call_id: str
    tool_name: str
    status: str = "queued"  # queued / running / waiting_permission / resolved / error
    summary: str = ""
    args_preview: str = ""


@dataclass
class ProgressView:
    """工具执行进度视图状态."""
    tool_call_id: str
    tail_stdout: str = ""
    tail_stderr: str = ""
    elapsed: float = 0.0
    line_count: int = 0
    byte_count: int = 0


@dataclass
class ToolViewsState:
    """ScrollLayer 中工具行聚合状态."""
    tool_calls: dict[str, ToolCallView] = field(default_factory=dict)
    progress: dict[str, ProgressView] = field(default_factory=dict)
    expanded: set[str] = field(default_factory=set)


# ── Current turn domain (不直接对应布局节点) ──

@dataclass
class SpinnerView:
    """当前 turn 的 spinner 状态."""
    active: bool = False
    label: str = ""


@dataclass
class InlineSurface:
    """当前 turn 的内联临时 surface（不固定占位）."""
    id: str
    kind: str = ""
    content: str = ""


@dataclass
class CurrentTurnState:
    """当前 turn 状态域 — 只保存状态，不直接对应布局节点."""
    turn_id: str | None = None
    spinner: SpinnerView | None = None
    inline_surfaces: list[InlineSurface] = field(default_factory=list)


# ── Pending interaction domain (OverlayLayer) ──

@dataclass
class DiffPreviewView:
    """Diff 预览视图（挂到 permission）."""
    file_path: str = ""
    diff_content: str = ""


@dataclass
class CommandPreviewView:
    """命令预览视图（挂到 permission）."""
    command: str = ""


@dataclass
class PermissionRequestView:
    """权限请求视图 — 属于 pending_interaction，不进入长期 transcript."""
    request_id: str = ""
    turn_id: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    scope: str = ""
    risk_summary: str = ""
    preview: DiffPreviewView | CommandPreviewView | None = None


@dataclass
class SandboxRequestView:
    """沙箱权限请求视图."""
    request_id: str = ""
    command: str = ""


@dataclass
class PromptRequestView:
    """ask_user prompt 请求视图."""
    request_id: str = ""
    question: str = ""


@dataclass
class PendingInteractionState:
    """OverlayLayer 状态域 — 审批 / 沙箱 / 用户询问."""
    permission: PermissionRequestView | None = None
    sandbox: SandboxRequestView | None = None
    ask_user: PromptRequestView | None = None


# ── Bottom domain (BottomLayer) ──

@dataclass
class CommandSuggestion:
    """斜杠命令建议."""
    text: str
    description: str = ""


@dataclass
class FooterView:
    """sticky 权限底部提示."""
    shortcuts: str = ""
    selected_option: str = ""


@dataclass
class BottomState:
    """BottomLayer 状态域."""
    input_enabled: bool = True
    command_suggestions: list[CommandSuggestion] = field(default_factory=list)
    sticky_permission_footer: FooterView | None = None


# ── Viewport domain (FloatLayer 部分) ──

@dataclass
class StickyPrompt:
    """顶部 sticky prompt 提示."""
    text: str = ""
    visible: bool = False


@dataclass
class ViewportState:
    """Viewport 状态域（滚动和浮层相关）."""
    is_at_bottom: bool = True
    unseen_count: int = 0
    sticky_prompt: StickyPrompt | None = None


# ── Pet domain (FloatLayer) ──

@dataclass
class PetState:
    """Pet 状态域 — 默认不占位."""
    visible: bool = False
    mode: PetMode = PetMode.IDLE


# ── UIStore - central UI state ──

@dataclass(init=False)
class UIStore:
    """Central UI state store — 五层状态域统一管理.

    ScrollLayer:
      messages / stream / tool_views / current_turn.inline_surfaces
    OverlayLayer:
      pending_interaction
    ModalLayer:
      modal
    BottomLayer:
      bottom
    FloatLayer:
      viewport / pet
    """

    # ── ScrollLayer: 长期 UI 历史 ──
    message_blocks: list[MessageBlock] = field(default_factory=list)
    messages: list[MessageBlock] = field(default_factory=list)  # alias, 推荐使用

    # ── ScrollLayer: streaming tail ──
    stream: StreamView = field(default_factory=StreamView)

    # ── ScrollLayer: assistant thinking rows/tail ──
    thinking: ThinkingState = field(default_factory=ThinkingState)

    # ── ScrollLayer: 工具调用动态行 ──
    tool_views: ToolViewsState = field(default_factory=ToolViewsState)

    # ── ScrollLayer: 当前 turn 状态域（不直接对应布局节点） ──
    current_turn: CurrentTurnState = field(default_factory=CurrentTurnState)

    # ── OverlayLayer: pending interaction ──
    pending_interaction: PendingInteractionState = field(
        default_factory=PendingInteractionState
    )

    # ── ModalLayer: screen-like transient surface ──
    modal: ModalScreen | None = None

    # ── BottomLayer: input / suggestions / sticky footer ──
    bottom: BottomState = field(default_factory=BottomState)

    # ── FloatLayer: viewport 和 pet ──
    viewport: ViewportState = field(default_factory=ViewportState)
    pet: PetState = field(default_factory=PetState)

    # ── 兼容旧字段 ──
    # current_turn_surfaces: 保留为桥接属性
    # pending_permission: 保留为桥接属性
    # current_turn_id: 保留为桥接属性
    # is_at_bottom: 保留为桥接属性

    # ── 兼容属性 ──

    def __init__(
        self,
        message_blocks: list[MessageBlock] | None = None,
        messages: list[MessageBlock] | None = None,
        stream: StreamView | None = None,
        thinking: ThinkingState | None = None,
        tool_views: ToolViewsState | None = None,
        current_turn: CurrentTurnState | None = None,
        pending_interaction: PendingInteractionState | None = None,
        modal: ModalScreen | None = None,
        bottom: BottomState | None = None,
        viewport: ViewportState | None = None,
        pet: PetState | None = None,
        current_turn_surfaces: dict[str, list[TurnSurface]] | None = None,
        pending_permission: PermissionPromptSurface | None = None,
        current_turn_id: str | None = None,
        is_at_bottom: bool | None = None,
    ) -> None:
        """Create a UIStore while preserving old constructor keywords.

        Older code and tests instantiate UIStore(current_turn_id=..., is_at_bottom=...).
        Keep those entry points alive while new code uses the nested state domains.
        """
        self.message_blocks = list(message_blocks or [])
        self.messages = list(messages) if messages is not None else list(self.message_blocks)
        self.stream = stream or StreamView()
        self.thinking = thinking or ThinkingState()
        self.tool_views = tool_views or ToolViewsState()
        self.current_turn = current_turn or CurrentTurnState()
        self.pending_interaction = pending_interaction or PendingInteractionState()
        self.modal = modal
        self.bottom = bottom or BottomState()
        self.viewport = viewport or ViewportState()
        self.pet = pet or PetState()

        if current_turn_id is not None:
            self.current_turn.turn_id = current_turn_id
        if is_at_bottom is not None:
            self.viewport.is_at_bottom = is_at_bottom
        if pending_permission is not None:
            self.pending_permission = pending_permission
        if current_turn_surfaces:
            for surfaces in current_turn_surfaces.values():
                for surface in surfaces:
                    self.add_turn_surface(surface)

    @property
    def current_turn_surfaces(self) -> dict[str, list[TurnSurface]]:
        """兼容旧代码：将 current_turn.inline_surfaces 映射回旧格式.

        新代码应直接使用 current_turn.inline_surfaces。
        """
        result: dict[str, list[TurnSurface]] = {}
        for surface in self.current_turn.inline_surfaces:
            # 尝试将 InlineSurface 映射到合适的 TurnSurface 子类
            ts = ActiveToolSurface(
                id=surface.id,
                turn_id=self.current_turn.turn_id or "",
                kind=surface.kind or "active_tool",
            )
            key = surface.kind or "default"
            if key not in result:
                result[key] = []
            result[key].append(ts)
        return result

    @current_turn_surfaces.setter
    def current_turn_surfaces(self, value: dict[str, list[TurnSurface]]) -> None:
        """兼容旧代码写入."""
        pass  # 新架构中不再直接操作此字段

    @property
    def pending_permission(self) -> PermissionPromptSurface | None:
        """兼容旧代码：映射 pending_interaction.permission 到旧 PermissionPromptSurface."""
        perm = self.pending_interaction.permission
        if perm is None:
            return None
        return PermissionPromptSurface(
            id=perm.request_id,
            turn_id=perm.turn_id,
            tool_call_id=perm.tool_call_id,
            request_id=perm.request_id,
            tool_name=perm.tool_name,
            scope=perm.scope,
            risk_summary=perm.risk_summary,
        )

    @pending_permission.setter
    def pending_permission(self, value: PermissionPromptSurface | None) -> None:
        """兼容旧代码写入：同步到 pending_interaction.permission."""
        if value is None:
            self.pending_interaction.permission = None
        else:
            self.pending_interaction.permission = PermissionRequestView(
                request_id=value.request_id,
                turn_id=value.turn_id,
                tool_call_id=value.tool_call_id,
                tool_name=value.tool_name,
                scope=value.scope,
                risk_summary=value.risk_summary,
            )

    @property
    def current_turn_id(self) -> str | None:
        """兼容旧代码：映射到 current_turn.turn_id."""
        return self.current_turn.turn_id

    @current_turn_id.setter
    def current_turn_id(self, value: str | None) -> None:
        """兼容旧代码写入."""
        self.current_turn.turn_id = value

    @property
    def is_at_bottom(self) -> bool:
        """兼容旧代码：映射到 viewport.is_at_bottom."""
        return self.viewport.is_at_bottom

    @is_at_bottom.setter
    def is_at_bottom(self, value: bool) -> None:
        """兼容旧代码写入."""
        self.viewport.is_at_bottom = value

    # ── 核心方法 ──

    def add_message_block(self, block: MessageBlock) -> None:
        """Add a message block to history. 同步写入 message_blocks 和 messages."""
        self.message_blocks.append(block)
        self.messages.append(block)

    def add_turn_surface(self, surface: TurnSurface) -> None:
        """兼容旧代码：将 TurnSurface 转为 InlineSurface 存入 current_turn.

        新代码应直接写入 current_turn.inline_surfaces。
        """
        inline = InlineSurface(
            id=surface.id,
            kind=surface.kind,
            content=surface.tool_name if hasattr(surface, "tool_name") else "",
        )
        self.current_turn.inline_surfaces.append(inline)

    def clear_turn_surfaces(self, tool_call_id: str | None = None) -> None:
        """兼容旧代码：清除 current_turn 状态."""
        if tool_call_id is None:
            self.current_turn.inline_surfaces.clear()
        else:
            self.current_turn.inline_surfaces = [
                s for s in self.current_turn.inline_surfaces
                if s.kind != tool_call_id
            ]

    def clear_all_turn_surfaces(self) -> None:
        """清除所有当前 turn 状态（兼容旧代码和新架构）."""
        self.current_turn.inline_surfaces.clear()
        self.current_turn.spinner = None
        self.pending_interaction.permission = None
        self.pending_interaction.sandbox = None
        self.pending_interaction.ask_user = None

    def set_pending_permission(self, surface: PermissionPromptSurface | None) -> None:
        """Set or clear pending permission. 同步新旧字段."""
        if surface is None:
            self.pending_interaction.permission = None
        else:
            self.pending_interaction.permission = PermissionRequestView(
                request_id=surface.request_id,
                turn_id=surface.turn_id,
                tool_call_id=surface.tool_call_id,
                tool_name=surface.tool_name,
                scope=surface.scope,
                risk_summary=surface.risk_summary,
            )

    def get_pending_permission(self) -> PermissionPromptSurface | None:
        """Get pending permission. 兼容旧代码."""
        return self.pending_permission  # 使用兼容属性
