# Textual Claude-style UI Design

## 1. Goal and Non-goals

目标是把 `xcode chat` 从当前 legacy `prompt_toolkit + Rich + ANSI` 拼装式 UI，迁移到 Textual 单一终端 UI runtime。最终形态：

```text
xcode chat           -> Textual ChatApp
xcode chat --legacy  -> 当前 AgentRuntime.run_chat()
```

这不是给现有 UI 换皮，也不是做一个 `--textual` demo。Textual 应成为唯一终端渲染器，消息、输入、streaming、工具调用、审批、diff、task、status 和后续 pet 插槽都在同一棵 UI 树中管理。

非目标：

- 第一阶段不实现具体 pet 视觉、动画、多 pet 选择或用户 pet 管理。
- 第一版不改变现有 session transcript 存储格式。
- 不新增 `ui_mode` 配置。迁移期可以保留隐藏开发入口 `xcode chat --textual`，但默认切换必须等强验收通过。
- 不把 Textual 做成固定 IDE 面板。主体验必须是 Claude-like 自然消息流。

## 2. Current Architecture

当前 `xcode chat` 主入口是 `src/xcode_cli/core/agent.py` 的 `AgentRuntime.run_chat()`。它使用：

- `prompt_toolkit.PromptSession` 读取输入和 bottom toolbar。
- Rich `console.print` / Rich Live 展示 assistant 输出、thinking、compaction progress。
- ANSI 局部刷新实现审批菜单、`/resume`、`/env` 等交互。
- `ToolCallExecutor` 在工具执行期间直接输出 diff preview、command preview、approval hint 和工具摘要。

这套架构已经可用，但长期问题是多写者竞争终端：

```text
prompt_toolkit
Rich Live
console.print
ANSI menu
subprocess/logging output
```

Claude-style UI 需要一个统一 terminal runtime，而不是继续在多个输出机制之间做协调。

## 3. Target Architecture

目标架构采用双向但解耦的数据流：

```text
User Input / Widget Action
  -> UICommand
  -> Runtime Controller
  -> Agent / Tool / Session
  -> UIEvent
  -> UIStore
  -> Presenter / ViewModel
  -> Textual Widget
```

职责边界：

- Widget 不直接调用 LLM、工具、session 写入或文件 mutation。
- Widget 可以发 `UICommand`，例如 submit input、approve/deny tool、cancel turn、run slash command、select resume session。
- Runtime Controller 消费 `UICommand`，驱动 agent/tool/session，并把结果转成 `UIEvent`。
- UIStore 只保存 UI 可渲染状态，不承载业务执行逻辑。
- Presenter/ViewModel 把 UIStore 转成 widget 所需结构。
- Textual Widget 只负责渲染和采集交互。

终端输出边界：

```text
所有 stdout / stderr / logging / subprocess output
  -> RuntimeLog / EventSink
  -> UIEvent
  -> Textual 统一展示或折叠
```

工具进程输出不得直写终端。legacy 中的 `console.print`、Rich Live、ANSI 菜单、prompt toolbar 都需要在 Textual 路径中被替换成事件。`run_shell` 的 stdout/stderr capture 是默认切换 blocker；只要 shell 输出还能绕过 Textual 直写终端，就不能认为 Textual 是唯一 terminal renderer。

敏感信息边界：

```text
RuntimeLogSink / ToolOutputSink
  -> apply redaction
  -> UIEvent
```

`/env`、shell output、tool logs、command args 都可能包含 secret。敏感 command args 默认不持久化到 UI history；需要展示时必须先 redaction。

## 4. UICommand / UIEvent Data Flow

建议的 UICommand：

```text
SubmitUserInputCommand(text)
RunSlashCommandCommand(raw)
ApprovePermissionCommand(choice)
CancelTurnCommand
ResumeSessionCommand(session_id)
CompactCommand
SaveEnvCommand(changes)
PlanDecisionCommand(decision)
ExitCommand
```

建议的 UIEvent：

```text
UserMessageAdded
AssistantDelta
AssistantFinal
ToolCallStarted
ToolCallFinished
ToolOutputProduced
ToolRejected
ToolError
DiffPreviewAvailable
CommandPreviewAvailable
PermissionRequestEvent
PermissionClearedEvent
TaskStateChanged
StatusUpdated
CompactionStarted
CompactionCompleted
CompactionSkipped
CompactionFailed
ResumeListLoaded
ResumeCompleted
ConfigUpdated
PlanApprovalRequested
PlanUpdated
SystemNoticeAdded
```

审批是 request-response：

```text
PermissionRequestEvent
  -> UIStore pending permission state
  -> Textual permission widget
  -> PermissionDecisionCommand
  -> Runtime Controller resumes tool execution
  -> ToolResult / ToolRejected event
```

Widget 不得绕过 Runtime Controller 直接继续执行工具。

### 4.1 Batch 4/5 hardening implementation note

截至 2026-06-02，Textual path 的 Batch 4/5 hardening 已实现到以下边界：

- `RunSlashCommandCommand` 已在 `RuntimeController` 内事件化处理 `/help`、`/context`、`/tasks`、`/compact`、`/resume`、`/env`、`/memory`、`/plan`、`/exit`。
- local slash command 通过 `SystemNoticeAdded` 等 UIEvent 展示，不再用 legacy console/status 占位。
- `/compact` 在 active turn 或 pending permission 存在时拒绝执行。
- `/compact` 已接入 `ContextManager.compress()`，用 `CompactionCompleted` / `CompactionSkipped` / `CompactionFailed` 汇报结果，不使用 Rich Live。
- `/resume` 先发 transient surface cleanup，再读取真实 `SessionStore.list_sessions()` 发 `ResumeListLoaded`；`ResumeSessionCommand` 可通过 `load_history()` 恢复指定 session。完整 resume screen 未完成。
- `/plan enter/show/approve/reject` 已接入 `PlanMode` 状态机。
- `/env` 明确是 read-only display；`SaveEnvCommand` 事件已做敏感字段 redaction。完整 env edit screen 未完成。
- `TaskStateChanged` 已从 `task_create` / `task_update` 工具执行路径发出，ChatApp 将当前 task 列表保存为聚合的精简 `TaskSnapshotBlock`，并把 in-progress task 显示到 active-turn 区域。
- Task/Status/ActiveTurn/Pet presenters 已有基础 view model；StatusBar 通过 StatusPresenter 输出单行状态；Pet 默认隐藏且不加载资源。

这仍不是默认入口切换条件。`run_shell` stdout/stderr capture、完整 `/resume` / `/env` screen 和原生 Windows E2E 仍是 Batch 6 前置 blocker。

## 5. Chat Layout and Message Model

主界面采用 Claude-like 混合布局：默认是自然聊天流，复杂交互才进入 Screen。

```text
ChatApp
  ChatScreen
    TranscriptArea
      RichLogHistory
      StreamingWidget
      NewMessagesPill
    BottomArea
      CommandSuggestions
      InputBox
      StatusBar
      PetSurface(hidden slot)
    ScreenStack
      EnvScreen
      ResumeScreen
      PlanScreen
      MemoryScreen
```

第一版消息流用 `RichLogHistory + StreamingWidget`，但必须通过抽象层写入。这里要区分长期消息和当前 turn UI surface：

```text
UIEvent
  -> UIStore.messages: list[MessageBlock]
  -> UIStore.current_turn_surfaces: dict[tool_call_id, list[TurnSurface]]
  -> MessagePresenter
  -> MessageRenderer
      - RichLogRenderer 第一版
      - MessageListRenderer 后续替换
```

第一版可以用 RichLog，但业务逻辑、Runtime Controller、Widget 都不能到处直接 `log.write(...)`。长期内容必须先变成结构化 `MessageBlock`：

```text
UserMessageBlock
AssistantMessageBlock
ToolSummaryBlock
ToolResultBlock
ToolRejectedBlock
TaskSnapshotBlock
SystemNoticeBlock
ToolErrorBlock
ContextSummaryBlock
TaskListBlock
MemoryStatusBlock
```

当前 turn 的临时 UI 内容进入 `current_turn_surfaces`，不进入长期消息历史：

```text
DiffPreviewSurface
CommandPreviewSurface
PermissionPromptSurface
ActiveToolSurface
```

每个 surface 必须带 `turn_id` 和 `tool_call_id`；即使第一版只串行执行高风险工具，也不能把状态建模成“全局唯一 surface”。diff preview / command preview 是一等 UI 内容，但不是 session 对话记录。它们可以显示在 transcript 视觉区域中，位置上像消息流的一部分，但生命周期跟随当前 permission/tool interaction。

surface 清理规则：

```text
ToolCallFinished(tool_call_id)
ToolRejected(tool_call_id)
ToolError(tool_call_id)
PermissionDecisionCommand resolved
CancelTurnCommand
CompactCommand starts
ResumeSessionCommand starts
App unmount/shutdown
```

这些事件必须清理对应 `tool_call_id` 的 turn surface，避免出现审批 UI 已结束但 diff/command preview 仍挂在界面上的幽灵状态。

错误块可见性：

```text
ToolErrorBlock
  visible in UI
  maps to model-visible tool_result is_error

UICommandError / SystemNoticeBlock
  visible in UI
  not model-visible by default
```

工具失败必须回给模型，确保 agent 能继续推理和恢复；UI 命令错误默认只是本地 UI 反馈，不污染模型上下文。

## 6. Streaming Strategy

streaming 不靠 RichLog 原地更新。RichLog 是追加式 API，不适合 update last，也不应该 clear 重写历史。

第一版结构：

```text
TranscriptArea
  RichLogHistory     # 只追加 finalized blocks
  StreamingWidget    # 当前 assistant delta，独立可更新
```

RichLogRenderer 必须防重复 append。每个 `MessageBlock` 必须有稳定 id；renderer 维护 `last_rendered_message_id` 或 `last_rendered_index`，只追加未渲染的新 block。Presenter 重算、窗口 resize、refresh、resume 后都不能全量重写 RichLog，也不能重复刷历史。

数据流：

```text
AssistantDelta
  -> UIStore.active_stream_buffer
  -> StreamingWidget.update(buffer)

AssistantFinal
  -> append AssistantMessageBlock to RichLogHistory
  -> clear StreamingWidget
```

滚动规则：

- 用户在底部时，assistant streaming 显示在 transcript 末尾，并自动跟随。
- 用户滚到历史位置时，不强制拉回底部。
- 有新内容或 streaming 时显示 `NewMessagesPill`。
- pill 可点击，跳回底部。
- 快捷键如 `Ctrl+End` 也跳回底部。
- `is_at_bottom` 是 UI viewport local state，不属于业务事件。

## 7. Permission and Diff Flow

审批是交互，不是内容。pending approval UI 可以临时嵌在 transcript 底部交互位置，但完成后消失，不留下“用户点击 Yes”之类的记录。

规则：

```text
Yes:
  pending approval UI disappears
  tool stdout/result enters message flow

No:
  pending approval UI disappears
  ToolRejectedBlock enters message flow

Yes all:
  pending approval UI disappears
  permission session state updates
  tool result enters message flow
```

审批 UI 出现时：

- 强制滚到底一次。
- 输入框暂时禁用。
- 用户仍可自由滚动消息流查看上方 diff/context。
- 支持 y/n/a，也可支持方向键 + Enter。

diff preview 是一等 UI 内容，但不属于长期消息历史，也不改变现有 session transcript。它应该作为 permission UI / current turn surface 的一部分出现，通常在 permission prompt 之前或附近展示。审批 prompt 显示工具名、风险摘要、快捷键；diff preview 可以在同一 UI surface 中作为可滚动/可折叠内容存在。

长 diff 第一版可以截断并提供 “show more” 占位；后续 `MessageListRenderer` 再做折叠展开。审批完成后，diff preview 默认消失；通过审批后的证据是工具结果/摘要，拒绝后的证据是 `ToolRejectedBlock`。

## 8. Slash Command Migration

命令不应继续作为 `agent.py` 内的 if/else 扩展。需要命令注册层：

```text
SlashCommand
  name
  description
  kind
  handler
```

命令 handler 返回结构化结果，而不是直接 print 或直接启动 agent：

```text
SlashCommandResult
  display: "skip" | "system" | "user"
  model_visible: bool
  persist_ui: bool
  should_start_agent_turn: bool
  next_input: str | None
  submit_next_input: bool
  redactions: list[Redaction] | None
```

语义：

- `display` 决定是否以及如何显示给用户。
- `model_visible` 决定结果是否进入模型上下文。
- `persist_ui` 决定是否写入长期 UI history。
- `should_start_agent_turn` 决定命令是否触发 agent turn。
- `next_input` / `submit_next_input` 支持 `/review` 这类 prompt-expansion 命令。
- 敏感参数必须先 redaction，再进入 UIEvent 或 MessageBlock。

命令类型：

```text
prompt
  展开成 prompt，送入普通 agent turn

local
  本地执行，结果进入消息流

screen
  打开 Textual Screen

runtime
  驱动 Runtime Controller
```

第一阶段必须迁移：

```text
/help      local    -> SystemNoticeBlock
/context   local    -> ContextSummaryBlock
/tasks     local    -> TaskListBlock
/resume    screen   -> ResumeScreen
/compact   runtime  -> Runtime Controller
/env       screen   -> EnvScreen
/memory    local    -> MemoryStatusBlock
/plan      screen/runtime -> PlanScreen + Runtime Controller
/exit      runtime  -> shutdown
```

命令补全：

- 输入 `/` 时显示 `CommandSuggestions`。
- suggestions 是 BottomArea 的自然高度内容，不是独立终端写者。
- 上下键可选择，Enter 接受。
- Esc 关闭 suggestions。
- 第一版前缀匹配即可，后续再支持 fuzzy match。

## 9. Task / Status / Pet Slots

Task 采用 Claude-like 混合策略：

```text
运行中：
  ActiveTurn 区显示 current task / next task / task stats

turn 结束：
  可留一次克制 TaskSnapshotBlock

完整列表：
  /tasks 查看
```

Task 不应每次 `task_create/update` 都刷一大段历史。工具调用本身可以有一行 tool summary，但 task list 作为状态 UI 要克制。

StatusBar 是稳定的一行：

```text
model | tokens≈3k/128k | tools:5 | session 4m12s | ready
```

StatusBar 不显示长文本，不显示完整 task list，不显示 pet 动画。

Pet 第一阶段只做架构插槽：

```text
PetState
  enabled: bool
  pet_name: str | None
  mode: "idle" | "task" | "tool" | "error"
  asset_ref: str | None

PetViewModel
  visible: bool
  mode
  frame_ref
  description
```

第一阶段行为：

- `enabled = false`
- `visible = false`
- `PetSurface` 存在于布局树
- 不占行高
- 不加载外部资源
- 不执行 pet 代码

pet 后续资源只能是资源，不是插件代码。pet 不开线程，不直接写终端，不调用工具。

## 10. RuntimeController and Service Boundaries

RuntimeController 是 UI 和业务之间的唯一桥。

职责：

```text
- 接收 UICommand
- 管理当前 turn lifecycle
- 管理 cancellation
- 管理 pending permission future/state
- 调用 AgentEngine
- 把业务结果转成 UIEvent
- 保证同一时间只有一个 active turn
```

AgentEngine 是从 legacy `AgentRuntime` 中提取出来的 UI 无关 turn loop。

职责：

```text
- 构造 system prompt
- 管理 LLM request/stream
- 处理 assistant delta/final/tool_calls
- 请求 tool permission
- 执行工具
- 更新 session transcript
- 更新 context history
- 发 UIEvent
```

需要抽接口：

```text
PermissionProvider
ToolOutputSink
RuntimeLogSink
CancellationToken
```

需要拆或适配：

```text
ToolCallExecutor
  拆成 execution core + output sink + permission provider

ConversationCompactor
  拆出 compact core，Textual 用 UIEvent 显示进度

ResumeCommandService
  拆成 session listing/resume service + Textual ResumeScreen

EnvDashboard
  拆成 config edit service + Textual EnvScreen

AgentRuntime
  保留为 legacy orchestration
  新 AgentEngine 只提取业务 loop，不继承 prompt/session UI
```

并发模型：

```text
Textual App event loop
  -> RuntimeController starts worker/thread for turn
  -> worker calls AgentEngine
  -> worker enqueues UIEvent into thread-safe event queue
  -> Textual app loop consumes event queue
  -> Textual app loop mutates UIStore
```

硬约束：worker never mutates UIStore directly。所有 UIStore mutation 必须发生在 Textual app loop。streaming、permission、cancel 同时发生时，也只能通过 thread-safe event queue 排序进入 UIStore。

审批 request-response：

```text
worker waits on permission decision
UI remains responsive
user can scroll transcript
input disabled while permission pending
decision command wakes worker
```

`/compact` 是原子 session mutation，不是普通 local command：

- compact 期间禁止新 turn。
- 如果存在 pending permission，必须先 resolve 或 cancel。
- compact 失败不能破坏原 transcript，也不能替换 runtime history。
- compact 成功后，UI history 的系统提示和 session transcript checkpoint 边界必须一致。
- compact start 必须清理当前 turn surfaces，避免旧 preview 和新上下文边界混在一起。

## 11. Migration Batches

Batch 0：架构准备与接口拆分

```text
UICommand / UIEvent 类型定义
UIStore / ViewModel 初版
RuntimeController skeleton
PermissionProvider 接口
ToolOutputSink 接口
Tool execution core 拆分
Compaction core 拆分
Resume service 拆分
Env config service 拆分
```

Batch 1：Textual Chat Shell

```text
ChatApp / ChatScreen
TranscriptArea
RichLogHistory
StreamingWidget
NewMessagesPill
InputBox
StatusBar
PetSurface hidden slot
CommandSuggestions
```

Batch 2：Agent Turn + Streaming + Tool Summary

```text
SubmitUserInputCommand
AgentEngine turn loop
AssistantDelta / AssistantFinal
ToolCallStarted / ToolCallFinished
ToolSummaryBlock
ToolOutputSink -> MessageBlock
```

Batch 3：审批 + diff preview

```text
PermissionRequestEvent
pending approval UI 临时交互
PermissionDecisionCommand
DiffPreviewSurface
CommandPreviewSurface
ToolRejectedBlock
```

Batch 4：关键 Slash 命令

```text
/help
/context
/tasks
/compact
/resume
/env
/memory
/plan
/exit
```

Batch 5：Task / Status / Pet Slot

```text
TaskState
TaskPresenter
ActiveTurnWidget
TaskSnapshotBlock
StatusPresenter
PetState / PetViewModel / PetSurface hidden
```

Batch 6：默认入口切换候选

```text
xcode chat -> Textual ChatApp
xcode chat --legacy -> AgentRuntime.run_chat()
Textual 启动失败提示 fallback
文档更新
```

默认入口切换只能在强验收通过后合入。

## 12. Test and Acceptance Plan

自动测试分四层：

1. 纯业务层测试
   - AgentEngine 普通 turn
   - AssistantDelta / AssistantFinal 事件顺序
   - 多轮 tool call
   - 工具异常
   - permission request-response
   - context compaction
   - resume history restore

2. RuntimeController 测试
   - SubmitUserInputCommand
   - RunSlashCommandCommand
   - PermissionDecisionCommand
   - CancelTurnCommand
   - ResumeSessionCommand
   - CompactCommand
   - SaveEnvCommand
   - PlanDecisionCommand

3. UIStore / Presenter 测试
   - MessageBlock 顺序
   - current turn surfaces 按 `turn_id/tool_call_id` 建模
   - current turn surface 生命周期和清理
   - Streaming buffer
   - NewMessagesPill state
   - TaskPresenter
   - StatusPresenter
   - PetPresenter
   - DiffPresenter
   - Permission pending state

4. Textual pilot / smoke 测试
   - 启动 ChatApp
   - 输入消息
   - 消息显示
   - 滚动历史
   - StreamingWidget 更新
   - NewMessagesPill 点击/快捷键
   - pending approval 出现
   - y/n/a 决策
   - InputBox disabled/enabled
   - ResumeScreen 选择
   - EnvScreen save/cancel

5. Event replay 测试
   - 固定 fake AgentEngine 事件流 replay 到 UIStore/Presenter。
   - 覆盖 streaming finalization。
   - 覆盖 permission approve/reject。
   - 覆盖 cancel during permission。
   - 覆盖 tool error。
   - 覆盖 compact interrupted。
   - 覆盖 resume 后 ephemeral surface 为空。

手工验收必须覆盖 PowerShell 和 cmd.exe。

Blocker：

```text
普通聊天
输入
assistant streaming
tool call
审批 request-response
/resume
/compact
run_shell stdout/stderr capture
PowerShell/cmd.exe 手工验收
```

Required before default：

```text
diff preview
消息滚动/历史回看
/help /context /tasks
/env /memory /plan
Python logging / third-party output 统一收口
legacy fallback 可用
```

Architecture slot：

```text
task/status 展示位
PetSurface / PetState / pet asset interface
主题 CSS 基础
```

## 13. Risks and Guardrails

RichLog 迁移风险：

- 只能通过 MessageRenderer 写 RichLog。
- 业务和 widget 不直接写 log。
- 每个 MessageBlock 必须有稳定 id。
- RichLogRenderer 只追加未渲染 block，不能在 refresh 时重复 append。

AgentEngine 与 AgentRuntime 分叉：

- 先拆 PermissionProvider / ToolOutputSink / command services。
- legacy 与 Textual 尽量共享无 UI 内核。

审批 future 悬挂：

- pending permission 必须支持 cancel/timeout。
- unmount 时 resolve/abort pending requests。
- RuntimeController 统一管理 pending state。

stdout/stderr 泄漏：

- subprocess capture output。
- logging handler 进入 RuntimeLog。
- 禁止 Textual path `console.print`。

secret 泄漏：

- RuntimeLogSink / ToolOutputSink 必须在生成 UIEvent 前 redaction。
- `/env` 值、shell output、tool logs、command args 默认视为可能敏感。
- sensitive command args 默认不持久化到 UI history。

Windows 终端兼容：

- PowerShell/cmd.exe 是 blocker。
- Git Bash 不作为主要验收。
- legacy fallback 保留。

Pet scope 漂移：

- 只定义 PetState / PetViewModel / PetSurface hidden。
- 不做动画。
- 不加载资源。
- 不执行代码。

UI 固定框风险：

- Transcript 是主体验。
- 无边框自然消息流。
- 输入区轻量。
- 复杂命令才进 Screen。

## 14. Open Questions

本轮已确认：

- 允许 `xcode chat --textual` 作为开发期隐藏入口。
- 不做 `ui_mode` 配置。
- 第一版不改变现有 session transcript 存储。

后续实现前仍需在执行计划中细化：

- `MessageRenderer` 接口的具体方法签名。
- `PermissionProvider` 同步等待和 Textual async loop 的桥接方式。
- `ToolOutputSink` 如何覆盖 shell stdout/stderr 和 Python logging。
- `/plan` 的 pending approval UI 是 transcript 临时交互还是 PlanScreen 内交互。
- `SlashCommandResult` 字段到现有 slash handlers 的迁移矩阵。
- redaction 的默认规则和可测试 fixture。
