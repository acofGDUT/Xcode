# Textual UI Rendering Pipeline Redesign Plan

> 本计划用于安排 UI Agent 与 Coding Agent 协作。先由 UI Agent 产出交互/组件设计，再由 Coding Agent 按设计和现有 Textual 框架实现。Codex 负责 review 与同步项目文档。

## 背景

当前 Textual UI 已经能消费 `UIEvent` 并渲染 transcript、streaming、审批、diff、resume selector、基础 task/status/pet slots。但整体仍偏“事件来了就追加一个 block”：

- thinking/reasoning 还没有结构化 UI。
- tool call 只有 `ToolSummaryBlock` / `ToolResultBlock` 等浅层块，缺少同一 `tool_call_id` 的 view state 聚合。
- read/grep/glob 这类高频工具没有 grouped/collapsed 视图。
- shell 输出没有 tail/progress/elapsed/byte count 的动态视图。
- task UI 只有极简 `Tasks: N active`，还不是可扫描的 checklist。
- 当前 turn 的动态过程和长期 transcript 边界还不够明确。

Claude Code 的启发不是“好看地打印日志”，而是：

```text
raw events/messages
  -> normalize
  -> reorder by tool_use_id
  -> group related tool calls
  -> collapse by display density
  -> view model
  -> widget render
```

Xcode 应继承这个管线思想，但实现要贴合当前 Python/Textual 架构。

## 目标

- 建立 Textual UI 的 normalize / reorder / group / collapse / expand 管线。
- 保持 transcript 干净：model-visible history 和 UI-only state 分离。
- 当前 turn 动态过程用 view state 表达，而不是把每个 delta/progress 都追加为长期消息。
- 支持显示密度：
  - `compact`：高度合并摘要。
  - `normal`：每个工具一行或短块。
  - `expanded`：参数、输出、stderr、耗时、完整结果。
- thinking 默认折叠为一行，可展开。
- read/grep/glob 默认合并摘要，可展开。
- edit/write 在当前 turn 显示 diff/approval，完成后只保留简短结果摘要。
- shell 显示 command preview、tail output、elapsed、line/byte count，最终可展开完整输出。
- task 显示为可扫描 checklist，而不是只显示 `Tasks: N active`。

## 非目标

- 不改变 LLM/tool protocol。
- 不改变 transcript JSONL 格式。
- 不把 UI-only state 写入 transcript。
- 不引入 asyncio。
- 不一次性实现完整主题系统。
- 不做默认入口切换。
- 不要求 UI Agent 写 Python 实现代码。

## 当前代码入口

UI Agent 和 Coding Agent 应优先阅读：

- `src/xcode_cli/core/ui/events.py`
- `src/xcode_cli/core/ui/state.py`
- `src/xcode_cli/core/ui/presenters.py`
- `src/xcode_cli/core/ui/textual/app.py`
- `src/xcode_cli/core/ui/textual/widgets.py`
- `src/xcode_cli/core/ui/textual/renderers.py`
- `src/xcode_cli/core/runtime/controller.py`
- `tests/test_textual_chat_app.py`
- `tests/test_task_status_pet_slots.py`

Claude Code 参考材料：

- `D:/Claude-Code/src/components/Messages.tsx`
- `D:/Claude-Code/src/utils/messages.ts`
- `D:/Claude-Code/src/utils/groupToolUses.ts`
- `D:/Claude-Code/src/components/messages/AssistantThinkingMessage.tsx`
- `D:/Claude-Code/src/components/messages/AssistantToolUseMessage.tsx`
- `D:/Claude-Code/src/components/messages/UserToolResultMessage/UserToolResultMessage.tsx`
- `D:/Claude-Code/src/components/shell/ShellProgressMessage.tsx`

## Xcode 推荐架构

### 1. RawTurnStore

新增或扩展 UI-only store，用于保存当前 turn 的原始 UI events 和派生状态。

建议模型：

```python
@dataclass
class ToolCallViewState:
    tool_call_id: str
    tool_name: str
    status: str  # queued | running | waiting_permission | succeeded | rejected | failed | canceled
    arguments: dict[str, Any]
    input_summary: str = ""
    progress_summary: str = ""
    result_summary: str = ""
    output_tail: list[str] = field(default_factory=list)
    output_line_count: int = 0
    output_byte_count: int = 0
    elapsed_ms: int = 0
    expanded: bool = False

@dataclass
class ThinkingViewState:
    turn_id: str
    status: str  # streaming | complete | hidden
    summary: str = "Thinking"
    content: str = ""
    elapsed_ms: int = 0
    expanded: bool = False
```

长期 transcript 仍只保存最终用户/assistant/system/tool 证据块；当前 turn 的动态状态放在 current-turn surfaces / view state。

### 2. Normalize

把 `UIEvent` 转成稳定的 UI state mutation：

- `AssistantDelta`：进入 streaming buffer，不逐条追加历史。
- future `AssistantThinkingDelta`：进入 `ThinkingViewState.content`。
- `ToolCallStarted`：创建或更新 `ToolCallViewState(status=running)`。
- `PermissionRequestEvent`：同一个 tool call 转为 `waiting_permission`，并显示 approval surface。
- `DiffPreviewAvailable` / `CommandPreviewAvailable`：挂到对应 tool call。
- `ToolOutputProduced`：追加到 tool output buffer，但 UI 只显示 tail。
- `ToolCallFinished`：转为 succeeded/failed。
- `ToolRejected` / `ToolError`：进入长期 transcript 作为证据。

### 3. Reorder

展示时以 `tool_call_id` 聚合：

```text
tool call
  command/diff preview
  permission
  progress
  result/error/rejection
```

不要按 event 到达顺序傻排，避免 preview/result 和 tool call 分离。

### 4. Group

工具分组策略：

- `read_file` / `grep` / `glob`：可按连续只读工具合并为 read/search group。
- `write_file` / `edit_file`：不和只读工具混组，保留 diff/approval 优先级。
- `run_shell`：独立 shell progress group。
- `dispatch_agent`：独立 agent/subtask group。
- `task_create` / `task_update`：进入 task checklist view。

### 5. Collapse / Expand

显示密度：

```text
compact:
  Read 5 files, searched 3 patterns
  Shell running: pytest ... (+120 lines, 18s)

normal:
  read_file README.md
  grep "MemoryManager" src/
  shell pytest tests/... (+42 lines, 7s)

expanded:
  tool id, arguments, preview, stdout/stderr tail/full output, timing, result
```

展开 key 使用 `tool_call_id` 或 group id。展开后 tool_use 和 tool_result 必须一起展开。

## UI Agent 任务

UI Agent 不写 Python 实现代码。请输出一份设计稿，建议文件名：

```text
docs/superpowers/specs/2026-06-02-textual-ui-rendering-design.md
```

设计稿必须包含：

1. **信息架构**
   - Transcript 区域显示什么。
   - Current turn 区域显示什么。
   - Bottom area / status bar 显示什么。
   - 哪些内容是 transient，哪些进入长期 transcript。

2. **显示密度规范**
   - compact / normal / expanded 的规则。
   - 默认密度建议。
   - 展开/折叠交互建议，含键位候选。

3. **Thinking UI**
   - streaming 时显示什么。
   - 完成后显示 `thought for Ns` 还是隐藏。
   - verbose/expanded 时如何显示完整 Markdown。

4. **Tool UI**
   - read/search group 样式。
   - edit/write diff + approval 样式。
   - shell progress 样式：tail lines、elapsed、line count、byte count。
   - error/rejection 样式。
   - agent/subtask 样式。

5. **Task UI**
   - checklist 样式。
   - pending / in_progress / completed / failed / canceled 图标或文本。
   - current task 和 next task 如何显示在 active-turn/status 区域。

6. **示例**
   - 一轮包含 read + grep + edit 的 turn。
   - 一轮 shell 长输出 turn。
   - 一轮 task_create/task_update turn。
   - 一轮 thinking + final answer turn。

7. **Windows 约束**
   - cmd.exe / PowerShell 窄窗口下不溢出。
   - 不依赖复杂鼠标交互。
   - 文本不要被按钮/边框挤爆。

UI Agent 产物完成后交给 Codex review，再交给 Coding Agent 实现。

当前 UI Agent 设计稿已整理为：

```text
docs/superpowers/specs/2026-06-02-textual-ui-rendering-design.md
```

Coding Agent brief 已整理为：

```text
docs/superpowers/plans/2026-06-02-textual-ui-rendering-coding-brief.md
```

## Coding Agent 后续实现批次

UI Agent 设计通过后，建议分三批实现。

### Batch A：View State 管线

- 新增 current-turn view state。
- 将 tool events normalize 到 `ToolCallViewState`。
- 实现按 `tool_call_id` reorder。
- 保持现有 UI 行为不大幅改变。
- 测试 event -> view state。

### Batch B：工具 grouping / collapse

- 实现 read/search group。
- 实现 shell output tail/progress。
- 实现 expanded 状态。
- 测试 collapse/expand、长输出截断、错误/拒绝证据保留。

### Batch C：Thinking + Task UI

- 增加 thinking view state 和 collapsed thinking line。
- 把 task snapshot 从 `Tasks: N active` 升级为 checklist。
- 接入 active-turn/status 简要任务信息。
- 测试 task 状态变化和 thinking 折叠。

## 验收标准

- 普通对话 transcript 不被 thinking delta / shell chunk / progress tick 污染。
- read/grep/glob 连续工具默认能合并摘要。
- edit/write diff 和 approval 不会被折叠隐藏。
- shell 长输出只显示 tail 和计数，最终可展开。
- task UI 可见任务标题和状态，而不是只有数量。
- 错误和拒绝作为证据进入长期消息流。
- 窄窗口下不出现明显重叠或文本爆框。
- `pytest -q`、相关 Textual tests、`git diff --check` 通过。
