# Textual UI 布局层重构开发说明

> 本 brief 交给 Coding Agent 执行。实现前先阅读规格说明：`docs/superpowers/specs/2026-06-03-textual-ui-layout-layers-design.md`。

## 背景目标

当前 Textual UI 已经有基础能力，但布局结构仍像组件顺序堆叠。目标是把 UI 调整为更接近 Claude Code 槽位思想的结构：`current_turn` 保留为状态域，但不再是固定布局层；transcript 承载自然流体验，overlay 承载审批和 diff，modal 承载 resume/env/plan/memory，bottom 承载输入和状态栏，float 承载 pill/pet 等不占位浮层。

## 涉及文件

优先查看和修改：

- `src/xcode_cli/core/ui/state.py`
- `src/xcode_cli/core/ui/events.py`
- `src/xcode_cli/core/ui/textual/app.py`
- `src/xcode_cli/core/ui/textual/widgets.py`
- `src/xcode_cli/core/ui/textual/renderers.py`
- `src/xcode_cli/core/ui/presenters.py`

只在必要时查看：

- `src/xcode_cli/core/runtime/controller.py`
- `src/xcode_cli/core/runtime/agent_engine.py`
- `tests/test_textual_chat_app.py`
- `tests/test_task_status_pet_slots.py`

不要默认修改：

- `docs/current/PROGRESS.md`
- `docs/current/ARCHITECTURE.md`
- `docs/current/DEVNOTES.md`
- `docs/current/ROADMAP.md`
- `AGENTS.md`
- `XCODE.md`

这些权威跟踪文档由 Codex review 后同步。

## 开发任务

### 1. 收口 UIStore 状态域

在 `state.py` 中把 UI 状态语义整理清楚。可以保留旧字段兼容，但新增或明确以下状态域：

- `messages` 或继续兼容 `message_blocks`：长期 UI 历史。
- `thinking`：assistant thinking 的 active buffer、时间戳、finalized blocks 和显示模式。
- `stream`：assistant streaming / streaming tool draft。
- `tool_views`：工具调用、进度、展开状态。
- `current_turn`：只保存 `turn_id`、spinner、inline surfaces，不直接对应布局节点。
- `pending_interaction`：permission、sandbox、ask-user。
- `modal`：resume/env/plan/memory 当前 screen。
- `bottom`：input enabled、command suggestions、sticky permission footer。
- `viewport`：bottom 状态、unseen count、sticky prompt。
- `pet`：visible、mode。

实现建议：

- 不要一次删除 `current_turn_surfaces`，可以保留为兼容属性或桥接方法。
- 新增 dataclass 时保持简单，不要提前抽象复杂基类。
- 状态字符串使用英文枚举值，用户可见文案保持中文或沿用现有英文文案。
- `thinking.display_mode` 使用 `collapsed | expanded | hidden`，默认 `collapsed`。

### 2. 调整 ChatApp 布局语义

在 `app.py` 中把 `compose()` 的布局调整为五类职责。实际类名可以保守处理，但结构和注释要清楚：

```text
ScrollLayer:
  TranscriptArea
  TranscriptRenderer
  StreamingThinkingTail
  StreamingAssistantTail
  Tool rows / inline transient rows

OverlayLayer:
  PermissionOverlay

ModalLayer:
  ResumeSelector

BottomLayer:
  NewMessagesPill
  CommandSuggestions
  InputBox
  StatusBar

FloatLayer:
  PetSurface
```

实现建议：

- 可以先使用 `Vertical` 容器模拟 layer，不必一次写复杂 overlay manager。
- `StreamingWidget` 可以保留类名，但需要区分 assistant streaming tail 和 thinking streaming tail；第一版可以先在同一 widget 内渲染，语义必须写清楚。
- `ActiveToolIndicator` 不应继续被理解为固定 current-turn 面板；可以继续作为一行 transient row，后续再替换为 ToolUseRow。
- `ResumeSelector` 保持纯文本 transient widget，但归入 modal/screen-like 容器。
- `PetSurface` 继续默认 hidden 且不占位。

### 3. 把审批和 diff 归入 pending interaction

调整 `PermissionRequestEvent`、`DiffPreviewAvailable`、`CommandPreviewAvailable` 的消费路径：

- permission request 写入 `store.pending_interaction.permission`。
- diff/command preview 挂到同一个 pending permission view。
- `ApprovalCard` 可以先保留类名，但注释和调用语义应改为 `PermissionOverlay`。
- `PermissionClearedEvent` 只清除 pending interaction，不清掉同一 tool 的历史证据。

约束：

- diff preview 不能成为长期 `MessageBlock`。
- 长 diff 截断后必须保留审批选项。
- input pending permission 时继续阻塞普通提交。
- `y/n/a`、方向键、Enter 继续可用。

### 4. 降级 current_turn 布局职责

清理代码中“current turn surface = 布局节点”的隐含关系：

- `current_turn_id` 可以继续用于状态栏。
- `current_turn.inline_surfaces` 可以保存临时信息，但不要求 UI 固定渲染一个 `CurrentTurnSurface`。
- thinking 不进入 `current_turn.inline_surfaces`，而进入 transcript renderer / thinking 状态域。
- 工具开始、运行、完成应更新 tool view state 或 transient row。
- turn 结束时清理 transient 状态，但长期 evidence block 继续保留。

### 5. 补 thinking 的 transcript 渲染路径

thinking 属于 assistant content / transcript renderer，不属于 approval/current_turn 固定区。

实现目标：

- 新增或明确 `ThinkingState`：
  - `active_buffer: str | None`
  - `active_started_at: float | None`
  - `active_ended_at: float | None`
  - `finalized_blocks: dict[str, ThinkingBlock]`
  - `display_mode: collapsed | expanded | hidden`
- 如 runtime 已有 reasoning/thinking callback，应转换成 UI event：
  - `ThinkingDelta`
  - `ThinkingFinal`
- `ThinkingDelta` 更新 `store.thinking.active_buffer`，并更新 `StreamingThinkingTail`。
- `ThinkingFinal` 生成 `AssistantThinkingBlock` 或 `ThinkingRow`，清空或短暂保留 active buffer。
- 默认显示折叠行，例如 `∴ Thinking...` 或 ASCII fallback `Thinking...`。
- expanded/verbose 模式显示完整 thinking markdown。
- 历史 thinking 默认折叠或隐藏，只保留最近一段可见。

约束：

- 不把 thinking 放进 `current_turn` 固定层。
- 不把每个 thinking delta 追加成长期 `MessageBlock`。
- 不和 approval/diff/pending interaction 混在一起。
- 如果本轮 runtime 还没有稳定 thinking event，可以先补 state、block、renderer 和 app 消费入口，但要明确哪些路径尚未由真实 LLM reasoning callback 驱动。

### 6. 工具行语义轻量整理

本轮不要求完整 grouping/collapse pipeline，但要为后续铺好边界：

- `ToolCallStarted` 更新 tool view state，并可渲染短工具行。
- `ToolOutputProduced` 对 `run_shell` 这类长输出只保留摘要或 tail，不要逐 chunk 污染长期 transcript。
- `ToolRejected` 和 `ToolError` 仍写入长期 transcript。
- `edit_file` / `write_file` 的 diff/approval 不被工具折叠隐藏。
- 工具行、thinking tail、assistant streaming tail 都属于 transcript renderer/tail，不属于 fixed current-turn panel。

### 7. 保持现有交互语义

键盘优先级保持：

```text
resume selection > pending permission > normal input
```

必须保持：

- `/resume` 选择期间普通输入被阻塞。
- permission pending 期间普通输入被阻塞。
- compacting 期间普通输入和 slash command 被阻塞。
- approval 决策后 input 清空并恢复 focus。
- resume 取消仍显示 `Cancelled.`。

## 非目标

不要做这些事：

- 不新增自动化测试任务。
- 不要求跑 `pytest` 作为交付条件。
- 不切默认入口。
- 不改 transcript JSONL。
- 不改 LLM/tool protocol。
- 不引入 `asyncio`。
- 不做完整 rendering pipeline grouping/collapse。
- 不实现完整 `/env` 编辑 screen。
- 不把 thinking 展开交互做成鼠标依赖。
- 不修改 `docs/current/*`。

## 自检建议

本轮用户明确不要求测试。Coding Agent 完成后只需要做轻量自检并报告：

- 修改了哪些文件。
- `current_turn` 是否已经不再作为固定布局面板。
- thinking 是否已经进入 transcript renderer/tail 语义，而不是 current_turn/pending interaction。
- approval/diff 是否归入 pending interaction。
- resume selector 是否仍可作为 modal-like transient surface 工作。
- input/status/pet 是否保持原有边界。
- 哪些地方为了兼容旧测试或旧调用保留了旧类名/字段。

如需做语法级自检，可以运行：

```powershell
python -m py_compile src/xcode_cli/core/ui/state.py src/xcode_cli/core/ui/textual/app.py src/xcode_cli/core/ui/textual/widgets.py src/xcode_cli/core/ui/textual/renderers.py
```

不要把自动化测试作为本轮完成门槛。

## 交付说明格式

Coding Agent 完成后，请给出：

```text
完成内容：
- ...

修改文件：
- ...

保持不变：
- LLM/tool protocol 未变
- transcript JSONL 未变
- Textual 未切默认入口

未完成/后续：
- ...

自检：
- 是否运行 py_compile：是/否
- 是否运行测试：否，本轮按要求不做测试
```
