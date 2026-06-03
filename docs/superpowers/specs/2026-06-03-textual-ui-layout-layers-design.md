# Textual UI 布局层重构规格说明

> 本规格用于定义 Textual UI 下一轮优化的目标态。它基于现有 `2026-06-02-textual-ui-rendering-design.md`，但本轮重点不是继续扩展 renderer pipeline，而是先把布局层、状态域和 transient interaction 的职责收口清楚。

## 背景

当前 Textual UI 已经具备 transcript、streaming、approval、diff preview、resume selector、task/status/pet 插槽等基础能力，但布局仍偏“组件顺序堆叠”：

```text
TranscriptArea
StreamingWidget
ActiveToolIndicator
ApprovalCard
ResumeSelector
BottomArea
PetSurface
```

这会让 `current_turn`、工具执行、审批、resume selector 等不同生命周期的内容混在同一条布局流里。用户贴出的设计建议是：保留 `current_turn`，但把它从“布局层”降级为“无占位状态域”。这与 Claude Code 的槽位思想一致：当前 turn 可以有状态，但 UI 上不应固定开一个 `CurrentTurn` 面板。

## 目标

本轮目标是把 Textual UI 收口为更清晰的五层结构：

```text
ChatApp
  ChatScreen
    ScrollLayer
      TranscriptViewport
        TranscriptRenderer
          MessageRows
          ThinkingRows
          StreamingThinkingTail
          StreamingAssistantTail
          ToolUseRows
          ToolProgressRows
          ToolResultRows
          InlineTransientRows
          SpinnerRow

    OverlayLayer
      PermissionOverlay
      SandboxPermissionOverlay
      AskUserPromptOverlay

    ModalLayer
      ResumeScreen
      EnvScreen
      PlanScreen
      MemoryScreen

    BottomLayer
      CommandSuggestionsOverlay
      StickyPermissionFooter
      QueuedCommands
      InputBox
      StatusBar

    FloatLayer
      NewMessagesPill
      StickyPromptHeader
      PetSurface
```

实际实现不要求一次性创建全部类名；但职责边界必须按这套结构调整。

## 组件职责调整

| 现有组件 | 新职责 |
|---|---|
| `TranscriptArea` | 作为 `TranscriptViewport`，只承载长期 transcript 和 transcript tail |
| `RichLogHistory` | 继续作为第一版 `TranscriptRenderer`，只渲染 finalized rows |
| `StreamingWidget` | 改为 `StreamingTail`，属于 transcript 尾部，不是独立中层面板 |
| `ActiveToolIndicator` | 不再作为固定布局层，转为工具动态行或 spinner 的渲染来源 |
| `ApprovalCard` | 语义改为 `PermissionOverlay`，生命周期归属 `pending_interaction` |
| `ResumeSelector` | 进入 `ModalLayer`，作为 screen-like transient surface |
| `CommandSuggestions` | 作为 input 上方 overlay，不进入 transcript |
| `InputBox` | 固定在 `BottomLayer` |
| `StatusBar` | 固定在 `BottomLayer`，保持稳定一行 |
| `PetSurface` | 进入 `FloatLayer`，默认 invisible 且不占位 |
| `current_turn_surfaces` | 收口为 `current_turn` 状态域，不直接对应布局节点 |

## TranscriptRenderer 与 thinking

`thinking` 和 streaming answer 一样，属于 assistant turn 的 transcript 动态渲染，不属于 approval、modal 或固定 `current_turn` 区域。

推荐结构：

```text
ScrollLayer
  TranscriptViewport
    TranscriptRenderer
      UserMessageRow
      AssistantMessageRow
      AssistantThinkingRow
      StreamingThinkingTail
      StreamingAssistantTail
      AssistantToolUseRow
      ToolProgressRow
      ToolResultRow
      SpinnerRow
```

Claude Code 的思路是：thinking 是 assistant content block 的一种。最终 thinking 进入 message renderer；streaming thinking 作为 live 状态传给 transcript renderer；默认折叠，verbose/transcript 模式下才展开，旧 thinking 可以隐藏或只保留最近一段。

Xcode 对应规则：

```text
ThinkingDelta
  -> UIStore.thinking.active_buffer
  -> StreamingThinkingTail 更新

ThinkingFinal
  -> AssistantThinkingBlock / ThinkingRow
  -> active_buffer 清空或短暂保留
```

默认显示：

```text
∴ Thinking...
```

展开或 verbose 模式：

```text
显示完整 thinking markdown
```

历史 thinking：

- 默认折叠或隐藏。
- 只保留最近一段可见，避免旧 thinking 长期占据 transcript。
- 不进入 `current_turn` 固定层，不与 approval/diff 混合。

## UIStore 目标结构

`UIStore` 应逐步从当前的 `message_blocks + current_turn_surfaces + pending_permission` 扩展为以下状态域：

```text
UIStore
  messages: list[MessageBlock]

  thinking:
    active_buffer: str | None
    active_started_at: float | None
    active_ended_at: float | None
    finalized_blocks: dict[message_id, ThinkingBlock]
    display_mode: collapsed | expanded | hidden

  stream:
    assistant_text: str
    streaming_tool_uses: dict[tool_id, ToolUseDraft]

  tool_views:
    tool_calls: dict[tool_id, ToolCallView]
    progress: dict[tool_id, ProgressView]
    expanded: set[tool_id]

  current_turn:
    turn_id: str | None
    spinner: SpinnerView | None
    inline_surfaces: list[InlineSurface]

  pending_interaction:
    permission: PermissionRequestView | None
    sandbox: SandboxRequestView | None
    ask_user: PromptRequestView | None

  modal:
    screen: Resume | Env | Plan | Memory | None

  bottom:
    input_enabled: bool
    command_suggestions: list[CommandSuggestion]
    sticky_permission_footer: FooterView | None

  viewport:
    is_at_bottom: bool
    unseen_count: int
    sticky_prompt: StickyPrompt | None

  pet:
    visible: bool
    mode: idle | tool | task | error
```

第一版实现可以保留旧字段做兼容，但新逻辑应以这些状态域为准。

## Diff 与审批

diff 不应成为长期 `MessageBlock`，也不应混入普通 transcript。推荐形态：

```text
pending_interaction.permission
  tool_name
  risk_summary
  preview:
    DiffPreviewView | CommandPreviewView | None
  options:
    yes
    no
    yes_all
  sticky_footer:
    shortcuts / selected option
```

视觉上：

```text
TranscriptViewport 底部
  PermissionOverlay
    DiffPreview
    Question
    Options

BottomLayer
  StickyPermissionFooter?
  InputBox disabled
```

长 diff 时必须保证审批选项仍可见。第一版可以继续复用现有 `ApprovalCard` 的截断机制，但职责命名和状态归属应改为 pending interaction。

## 工具调用显示

工具调用不再进入固定 `current_turn` 面板。工具执行应进入 transcript renderer 的动态行，和 thinking/streaming assistant tail 共享 transcript 动态渲染层：

```text
AssistantToolUseRow
  name
  input summary
  status: queued/running/waiting_permission/resolved/error

ToolProgressRow
  tail stdout/stderr
  elapsed
  line count
  expandable

ToolResultRow
  summary
  error/rejected/success
```

原则：

- `read_file` / `grep` / `glob` 可以合并为只读工具摘要。
- `edit_file` / `write_file` 不与只读工具混组，diff 和 approval 不可隐藏。
- `run_shell` 显示 tail、elapsed、line count、byte count。
- `ToolRejected` / `ToolError` 仍作为长期证据进入 transcript。
- 普通 tool progress chunk 不逐条进入长期 `MessageBlock`。
- `ThinkingDelta` / `ThinkingFinal` 走 `thinking` 状态域和 `AssistantThinkingRow`，不进入 fixed current-turn surface。

## 非目标

本轮不做：

- 不切换 Textual 为默认入口。
- 不改变 LLM/tool protocol。
- 不改变 transcript JSONL schema。
- 不引入 `asyncio`。
- 不做完整主题系统。
- 不实现完整 mouse interaction。
- 不要求新增自动化测试。
- 不要求 Coding Agent 修改 `docs/current/*`。

## 验收标准

本轮以代码审查和手工观察为主，不要求新增测试。

完成后应满足：

- `current_turn` 只作为状态域存在，不再表现为固定占位布局节点。
- `ChatApp.compose()` 或等价布局能够清楚区分 scroll、overlay、modal、bottom、float 五类职责。
- streaming 内容表现为 transcript tail。
- thinking 内容表现为 `StreamingThinkingTail` 或 `AssistantThinkingRow`，不进入 fixed current-turn surface。
- approval/diff 属于 pending interaction，不污染长期 transcript。
- resume selector 属于 modal/screen-like transient surface。
- input 和 status bar 稳定固定在 bottom area。
- pet 默认不占位。
- 现有 approval 快捷键、resume selector 快捷键和 input 阻塞语义不被破坏。

## 风险

- Textual overlay/modal 能力和当前 widget 堆叠方式可能需要折中，第一版可用容器和显示状态模拟五层结构。
- 如果直接重命名大量 widget，容易造成测试和引用大面积破裂；建议保留兼容别名或先做语义迁移。
- approval、resume、input 都消费键盘事件，必须保持优先级：resume selection > pending permission > normal input。
- 长 diff 和窄窗口仍是主要体验风险，不能因为布局重构让审批选项被挤出可视区域。
