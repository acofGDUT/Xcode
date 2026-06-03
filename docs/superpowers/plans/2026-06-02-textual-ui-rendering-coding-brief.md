# Textual UI Rendering Pipeline Coding Brief

> 本 brief 交给 Coding Agent 执行。实现前先阅读 UI Agent 设计稿：`docs/superpowers/specs/2026-06-02-textual-ui-rendering-design.md`，以及总计划：`docs/superpowers/plans/2026-06-02-textual-ui-rendering-pipeline-redesign.md`。

## 背景目标

当前 Textual UI 已有基础 transcript、streaming、tool result、approval、diff、resume、task/status/pet slot，但仍偏“事件直接追加 block”。本次目标是建立 Claude Code-style 的 UI rendering pipeline：

```text
UIEvent
  -> current turn view state
  -> normalize
  -> reorder by tool_call_id
  -> group related tools
  -> collapse by density
  -> render widgets / transcript blocks
```

第一轮不要追求一次完成全部 UI。先做可测试、可 review 的基础管线，再分批增强。

## 总体约束

- 不改变 LLM/tool protocol。
- 不改变 transcript JSONL 格式。
- 不把 thinking delta、shell chunk、progress tick 写入长期 transcript。
- 不引入 asyncio。
- 不把 UI Agent 设计里的 Unicode/emoji 当作默认实现；默认使用 ASCII/fallback 文案。
- 不让 diff preview 和 approval 被工具折叠隐藏。
- 不破坏现有 `/resume` selector、approval key handling、compaction blocking。
- 不直接修改 `docs/current/*`，除非 Codex plan 明确授权；实现完成后交给 Codex review 再同步。

## 优先文件

优先查看和修改：

- `src/xcode_cli/core/ui/state.py`
- `src/xcode_cli/core/ui/events.py`
- `src/xcode_cli/core/ui/presenters.py`
- `src/xcode_cli/core/ui/textual/app.py`
- `src/xcode_cli/core/ui/textual/renderers.py`
- `src/xcode_cli/core/ui/textual/widgets.py`
- `tests/test_textual_chat_app.py`
- `tests/test_task_status_pet_slots.py`

视情况修改：

- `src/xcode_cli/core/runtime/controller.py`
- `src/xcode_cli/core/runtime/agent_engine.py`

## Batch A：View State 管线

### 目标

建立 current-turn view state，把 tool events 聚合到 `tool_call_id`，但尽量保持现有 UI 行为。

### 建议实现

在 `state.py` 增加 UI-only view state：

```python
@dataclass
class ToolCallViewState:
    tool_call_id: str
    tool_name: str
    status: str
    arguments: dict[str, Any] = field(default_factory=dict)
    input_summary: str = ""
    progress_summary: str = ""
    result_summary: str = ""
    output_tail: list[str] = field(default_factory=list)
    output_line_count: int = 0
    output_byte_count: int = 0
    expanded: bool = False
```

在 `UIStore` 中增加：

```python
tool_calls: dict[str, ToolCallViewState]
tool_order: list[str]
```

在 `ChatApp` 或新的 helper 中实现 event normalization：

- `ToolCallStarted` 创建 state，status=`running`。
- `PermissionRequestEvent` 更新 status=`waiting_permission`。
- `ToolOutputProduced` 更新 output buffer / result summary。
- `ToolCallFinished` 更新 status=`succeeded` 或 `failed`。
- `ToolRejected` 更新 status=`rejected`，并保留现有长期 evidence block。
- `ToolError` 更新 status=`failed`，并保留现有长期 evidence block。
- `PermissionClearedEvent` 不删除 tool state，只清除 approval surface。

### 测试

新增或扩展测试：

- `ToolCallStarted` 后 `UIStore.tool_calls[tool_call_id]` 存在。
- 同一 `tool_call_id` 的 preview/result/status 更新同一个 state。
- 多个 tool call 按 first-seen order 保存在 `tool_order`。
- `ToolRejected` / `ToolError` 仍进入长期 message_blocks。
- `AssistantDelta` 仍只进入 streaming widget，不追加长期 message block。

验收命令：

```powershell
pytest tests/test_textual_chat_app.py tests/test_task_status_pet_slots.py -q
```

## Batch B：Tool grouping / collapse

### 目标

把 read/search 和 shell 输出从“逐块追加”升级为可折叠 view model。

### 建议实现

在 `presenters.py` 增加工具 presenter，例如：

```python
class ToolCallPresenter:
    def build_groups(self, store: UIStore) -> list[dict[str, Any]]:
        ...
```

分组策略：

- 连续 `read_file` / `grep` / `glob` 合并为 `read_search_group`。
- `write_file` / `edit_file` 独立显示，保留 diff/approval。
- `run_shell` 独立显示 shell progress。
- `task_create` / `task_update` 不进入普通工具组，交给 task UI。

Shell 输出策略：

- `ToolOutputProduced` 只更新 buffer。
- 默认显示 tail 3-5 行。
- 记录 line count 和 byte count。
- expanded 时显示更完整内容。

### 测试

- 连续 read/grep/glob 被合并为一个 group。
- edit/write 不被合并进 read/search group。
- shell 长输出只显示 tail 和计数。
- expanded 状态能显示参数和更多输出。
- error/rejection 不被 collapse 吞掉。

验收命令：

```powershell
pytest tests/test_textual_chat_app.py tests/test_tool_display.py -q
```

## Batch C：Thinking + Task UI

### 目标

补 thinking 折叠视图和 task checklist，让 UI 不再只有 `Tasks: N active`。

### Thinking

如果当前 runtime 已能提供 reasoning token：

- 新增 `AssistantThinkingDelta` / `AssistantThinkingFinal` 或复用已有 reasoning callback 后发 UI event。
- 当前 turn 中显示 `Thinking... (Ns)`。
- 完成后显示 `Thought for Ns`。
- expanded 时显示完整 Markdown。

如果 runtime 尚未稳定提供 reasoning event：

- 先实现 `ThinkingViewState` 和 renderer 测试。
- 不强行改 LLM 协议。

### Task UI

把 task snapshot 渲染为 checklist：

```text
Tasks
[x] Setup project
[-] Build task UI
[ ] Write tests
```

状态映射：

- `pending` -> `[ ]`
- `in_progress` -> `[-]`
- `completed` -> `[x]`
- `failed` -> `[!]`
- `canceled` -> `[~]`

Status/active-turn：

- 显示 current task 和 next task。
- 不要占用太多行；窄窗口下截断。

### 测试

- `TaskStateChanged` 后 checklist 包含任务标题和状态。
- in-progress task 显示在 active-turn/status 信息中。
- completed/failed/canceled 状态有稳定 ASCII fallback。
- thinking delta 不污染长期 transcript。

验收命令：

```powershell
pytest tests/test_task_status_pet_slots.py tests/test_textual_chat_app.py -q
```

## Windows 与交互验收

实现后需要补手工验收记录：

- PowerShell 和 cmd.exe。
- 80 列和 60 列左右窄窗口。
- approval 期间 y/n/a 仍可用。
- resume selector 上下键仍可用。
- shell 长输出不刷爆 transcript。
- task checklist 不和输入框/状态栏重叠。

## 全量验证

至少运行：

```powershell
python -m py_compile src/xcode_cli/core/ui/state.py src/xcode_cli/core/ui/presenters.py src/xcode_cli/core/ui/textual/app.py src/xcode_cli/core/ui/textual/renderers.py src/xcode_cli/core/ui/textual/widgets.py
pytest tests/test_textual_chat_app.py tests/test_task_status_pet_slots.py tests/test_textual_slash_commands.py -q
pytest -q
git diff --check
```

## 交付摘要要求

Coding Agent 完成后，请提供：

- 完成了 Batch A/B/C 中哪些批次。
- 修改文件列表。
- UI 行为变化摘要。
- 未完成项和风险。
- 测试命令和结果。
- 是否做了 PowerShell/cmd.exe 手工验收。

