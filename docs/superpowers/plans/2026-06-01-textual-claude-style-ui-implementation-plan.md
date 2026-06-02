# Textual Claude-style UI Implementation Plan

## 0. Context

设计来源：

- `docs/superpowers/specs/2026-06-01-textual-claude-style-ui-design.md`
- `claude-code-ui-in-textual.md`

目标是把 `xcode chat` 迁移到 Textual 单一终端 UI runtime，最终形态：

```text
xcode chat           -> Textual ChatApp
xcode chat --legacy  -> 当前 AgentRuntime.run_chat()
```

但默认入口切换必须等强验收通过。迁移期允许保留隐藏开发入口：

```text
xcode chat --textual
```

本计划不是让 Coding Agent 一次性重写 UI。必须按 batch 推进，每批独立 review、独立测试、独立文档更新。

## 1. Hard Rules

这些规则不可放宽：

- Textual App 是唯一终端渲染器。
- Textual path 中禁止 `print()`、`console.print()`、Rich Live、ANSI 局部刷新、prompt_toolkit toolbar。
- Widget 不直接调用 LLM、工具、session 写入或文件 mutation。
- Widget 只能发 `UICommand`。
- Worker/thread 不直接 mutate UIStore。
- Worker 只能把 `UIEvent` 放入 thread-safe event queue。
- Textual app loop 消费 event queue 并更新 UIStore。
- 工具 stdout/stderr/logging 必须进入 `RuntimeLogSink` / `ToolOutputSink`，并在生成 UIEvent 前 redaction。
- `run_shell` stdout/stderr capture 是默认切换 blocker。
- 第一版不改变现有 session transcript 存储。
- 第一阶段不实现具体 pet UI，只保留 `PetSurface` / `PetState` / `PetViewModel` 插槽。
- 不做固定框 IDE UI；Transcript 是无边框自然消息流。
- legacy REPL 必须保留为 `xcode chat --legacy`。

## 2. Target Data Flow

```text
User Input / Widget Action
  -> UICommand
  -> RuntimeController
  -> Agent / Tool / Session services
  -> UIEvent
  -> thread-safe event queue
  -> Textual app loop
  -> UIStore
  -> Presenter / ViewModel
  -> Textual Widget
```

Request-response approval:

```text
Tool needs permission
  -> PermissionRequestEvent
  -> UIStore.pending_permission
  -> transient permission UI
  -> PermissionDecisionCommand
  -> RuntimeController resumes worker
  -> ToolResult / ToolRejected / ToolError event
```

Current turn temporary UI:

```text
UIStore.current_turn_surfaces: dict[tool_call_id, list[TurnSurface]]
```

Surfaces are UI-only, not long-term message history:

```text
DiffPreviewSurface
CommandPreviewSurface
PermissionPromptSurface
ActiveToolSurface
```

## 3. Batch Overview

| Batch | Goal | Default entry change? |
|------|------|------------------------|
| Batch 0 | Interface and service boundary prep | No |
| Batch 1 | Textual chat shell with fake/local events | No, hidden `--textual` only |
| Batch 2 | Agent turn + streaming + tool summary | No |
| Batch 3 | Permission + diff/current-turn surfaces | No |
| Batch 4 | Required slash commands | No |
| Batch 5 | Task/status/pet slots | No |
| Batch 6 | Default entry switch candidate | Yes, only after full acceptance |

## 4. Batch 0 Detailed Task: Interfaces and Boundaries

Batch 0 is the first task for Coding Agent. It should not build the full Textual UI. It prepares the architecture so later batches do not copy legacy UI logic.

### 4.1 Goals

- Define `UICommand` types.
- Define `UIEvent` types.
- Define UI state models but keep them UI-only.
- Define `SlashCommandResult`.
- Define `PermissionProvider`.
- Define `ToolOutputSink`.
- Define `RuntimeLogSink`.
- Define `CancellationToken` or equivalent cancellation boundary.
- Add a `RuntimeController` skeleton that can be tested without Textual.
- Start extracting UI-free service boundaries from legacy code without changing legacy behavior.

### 4.2 Non-goals

- Do not add Textual dependency in Batch 0 unless already present for another reason.
- Do not change `xcode chat` default behavior.
- Do not add `xcode chat --textual` yet unless needed for compile wiring.
- Do not rewrite `AgentRuntime.run_chat()`.
- Do not change session transcript format.
- Do not implement pet visuals.
- Do not remove Rich/prompt_toolkit legacy UI.

### 4.3 Suggested Files

New files:

```text
src/xcode_cli/core/ui/events.py
src/xcode_cli/core/ui/commands.py
src/xcode_cli/core/ui/state.py
src/xcode_cli/core/ui/presenters.py
src/xcode_cli/core/runtime/controller.py
src/xcode_cli/core/runtime/permissions.py
src/xcode_cli/core/runtime/output.py
src/xcode_cli/core/runtime/cancellation.py
src/xcode_cli/core/commands/result.py
tests/test_ui_events_commands.py
tests/test_runtime_controller.py
tests/test_slash_command_result.py
```

Existing files to inspect:

```text
src/xcode_cli/core/agent.py
src/xcode_cli/core/tooling/execution.py
src/xcode_cli/core/tooling/approval.py
src/xcode_cli/core/conversation/compaction.py
src/xcode_cli/core/conversation/resume.py
src/xcode_cli/core/ui/env_dashboard.py
src/xcode_cli/core/commands/slash.py
src/xcode_cli/core/task_tracker.py
src/xcode_cli/core/session.py
src/xcode_cli/core/session_resume.py
src/xcode_cli/core/config.py
```

File names can be adjusted to fit existing project style, but responsibilities should remain separated.

### 4.4 UICommand Types

Implement as dataclasses or simple typed classes.

Required commands:

```text
SubmitUserInputCommand(text: str)
RunSlashCommandCommand(raw: str)
PermissionDecisionCommand(request_id: str, tool_call_id: str, choice: "yes" | "no" | "yes_all")
CancelTurnCommand(reason: str = "user")
ResumeSessionCommand(session_id: str)
CompactCommand()
SaveEnvCommand(changes: dict[str, object])
PlanDecisionCommand(decision: "approve" | "reject")
ExitCommand()
ViewportStateChangedCommand(is_at_bottom: bool)
```

Rules:

- Commands are user/UI intentions, not rendered content.
- Commands must not contain raw secrets unless unavoidable.
- Sensitive fields must support redaction before logging or UI display.

### 4.5 UIEvent Types

Required events:

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
UICommandFailed
TurnCancelled
```

Rules:

- Events describe facts that occurred.
- Events must be safe for UIStore to consume.
- Events should carry stable ids where needed: `turn_id`, `message_id`, `tool_call_id`, `request_id`.
- Tool errors that should be visible to the model must remain distinguishable from UI command errors.

### 4.6 MessageBlock and TurnSurface Models

Long-term UI history:

```text
MessageBlock
  id: str
  kind: str
  created_at: float
  model_visible: bool
  persist_ui: bool
  content / payload
```

Required block kinds:

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

Current-turn UI surface:

```text
TurnSurface
  id: str
  turn_id: str
  tool_call_id: str | None
  kind: str
  payload
```

Required surface kinds:

```text
DiffPreviewSurface
CommandPreviewSurface
PermissionPromptSurface
ActiveToolSurface
```

Surface cleanup triggers:

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

### 4.7 SlashCommandResult

Add a structured command result:

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

Rules:

- `display` decides how result appears to user.
- `model_visible` decides whether result enters model context.
- `persist_ui` decides whether it becomes long-term UI history.
- `should_start_agent_turn` decides whether command triggers an agent turn.
- `next_input` / `submit_next_input` supports prompt-expansion commands.
- Sensitive values must be redacted before becoming UIEvent or MessageBlock.

Batch 0 should not migrate every slash handler. It should define the type and add tests for result semantics.

### 4.8 PermissionProvider

Define an interface independent from prompt_toolkit/Textual:

```text
PermissionProvider.request(request: PermissionRequest) -> PermissionDecision
```

Request should include:

```text
request_id
turn_id
tool_call_id
tool_name
scope
risk_summary
```

Decision should include:

```text
choice: "yes" | "no" | "yes_all"
scope
```

Legacy adapter:

```text
ToolApprovalControllerPermissionProvider
  -> uses existing ToolApprovalController.prompt()
```

Textual adapter will come later:

```text
TextualPermissionProvider
  -> emits PermissionRequestEvent
  -> waits for PermissionDecisionCommand
```

### 4.9 ToolOutputSink and RuntimeLogSink

Define:

```text
ToolOutputSink.emit(event: ToolOutputEvent) -> None
RuntimeLogSink.emit(event: RuntimeLogEvent) -> None
```

Tool output event examples:

```text
ToolSummaryProduced
ToolStdoutProduced
ToolStderrProduced
DiffPreviewProduced
CommandPreviewProduced
ToolResultProduced
ToolErrorProduced
```

Rules:

- Apply redaction before UIEvent.
- `run_shell` stdout/stderr must be captured.
- No subprocess should inherit terminal stdout/stderr in Textual path.
- Legacy adapter can still render through console for now.

### 4.10 RuntimeController Skeleton

Batch 0 controller can be minimal.

Responsibilities:

```text
- accept UICommand
- prevent concurrent active turns
- expose event queue
- own pending permission state skeleton
- clear turn surfaces on cancellation/resume/compact boundaries
```

It does not need to call real LLM in Batch 0.

Suggested minimal API:

```text
RuntimeController.dispatch(command: UICommand) -> None
RuntimeController.drain_events() -> list[UIEvent]
RuntimeController.close() -> None
```

Threading rule:

```text
worker never mutates UIStore directly
worker -> thread-safe event queue
Textual app loop -> consume event -> mutate UIStore
```

### 4.11 Batch 0 Tests

Required:

```powershell
pytest tests/test_ui_events_commands.py tests/test_runtime_controller.py tests/test_slash_command_result.py -q
python -m py_compile src/xcode_cli/core/ui/events.py src/xcode_cli/core/ui/commands.py src/xcode_cli/core/runtime/controller.py
```

Suggested assertions:

- UICommand dataclasses carry expected fields.
- UIEvent ids are stable where needed.
- `SlashCommandResult` can represent:
  - local display-only command
  - prompt expansion without immediate submit
  - prompt expansion with immediate submit
  - sensitive result with redaction metadata
- RuntimeController rejects second active turn.
- RuntimeController queues events instead of mutating UIStore.
- Pending surface cleanup works for cancel/resume/compact triggers.
- ToolError vs UICommandFailed are distinct.

## 5. Batch 1 Plan: Textual Chat Shell

Do only after Batch 0 is reviewed.

Goals:

- Add Textual dependency if not already present.
- Add hidden `xcode chat --textual`.
- Build shell UI with fake/local events, not full agent turn.

Components:

```text
ChatApp
ChatScreen
TranscriptArea
RichLogHistory
StreamingWidget
NewMessagesPill
InputBox
CommandSuggestions
StatusBar
PetSurface hidden slot
```

Hard UX rules:

- Transcript is the main experience.
- No bordered fixed output panel.
- Input is lightweight.
- User can scroll history freely.
- New messages do not force scroll if user is reading history.
- NewMessagesPill appears when user is away from bottom.

Tests:

- Textual pilot starts ChatApp.
- Type input and see user message.
- Fake AssistantDelta updates StreamingWidget.
- AssistantFinal appends finalized message.
- Scrolling away from bottom shows NewMessagesPill on new event.
- PetSurface exists but is hidden and takes no height.

## 6. Batch 2 Plan: Agent Turn + Streaming + Tool Summary

Goals:

- Introduce AgentEngine or UI-free turn loop.
- Connect RuntimeController to AgentEngine.
- Support assistant streaming through StreamingWidget.
- Support finalized assistant messages and tool summaries.

Do not implement high-risk permission yet unless the boundaries are already clean.

Tests:

- fake LLM streams deltas then final.
- fake read-only tool call emits ToolSummaryBlock and ToolResultBlock.
- tool error emits ToolErrorBlock and model-visible tool result.
- no console output occurs in Textual path.

## 7. Batch 3 Plan: Permission + Diff Surfaces

Goals:

- Implement PermissionRequestEvent.
- Implement transient PermissionPromptSurface.
- Implement DiffPreviewSurface and CommandPreviewSurface.
- Implement PermissionDecisionCommand.

Rules:

- Diff preview is first-class UI content but not long-term MessageBlock.
- Approval UI is interaction, not history.
- Yes leaves no approval record.
- No emits ToolRejectedBlock.
- Yes all updates session permission state without dedicated history row.
- Input disabled while permission is pending.
- User can still scroll transcript.

Tests:

- approve y.
- reject n.
- yes_all a.
- cancel during permission.
- diff surface disappears after decision.
- command preview surface disappears after decision.
- tool rejection is visible in UI and model-visible as tool result.

## 8. Batch 4 Plan: Slash Commands

Migrate required commands:

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

Command kind mapping:

```text
/help      local
/context   local
/tasks     local
/compact   runtime
/resume    screen
/env       screen
/memory    local first
/plan      screen/runtime
/exit      runtime
```

Special rule for `/compact`:

- Atomic session mutation.
- No new turn during compact.
- Pending permission must resolve or cancel first.
- Failure must not corrupt transcript or runtime history.
- Success must align UI system notice with session checkpoint.

Tests:

- each command returns correct SlashCommandResult.
- `/compact` blocks concurrent turn.
- `/resume` clears ephemeral surfaces.
- `/env` changes are redacted where needed.
- `/plan` decision does not use legacy console.

## 9. Batch 5 Plan: Task / Status / Pet Slot

Goals:

- TaskPresenter.
- StatusPresenter.
- PetPresenter.
- ActiveTurnWidget.
- TaskSnapshotBlock policy.

Task policy:

```text
running:
  ActiveTurn shows current/next task

turn end:
  optionally add concise TaskSnapshotBlock

/tasks:
  full task list
```

Pet policy:

- PetSurface exists.
- PetState exists.
- PetViewModel exists.
- visible false by default.
- no resources loaded.
- no pet code executed.

Tests:

- task_create/update updates state.
- snapshot is concise.
- StatusBar remains one line.
- PetSurface hidden.

## 10. Batch 6 Plan: Default Entry Switch Candidate

Only after all blockers and required items pass.

Change:

```text
xcode chat           -> Textual ChatApp
xcode chat --legacy  -> AgentRuntime.run_chat()
```

Keep hidden/debug entry only if useful:

```text
xcode chat --textual
```

Required verification:

```powershell
pytest -q
python -m py_compile <new modules>
git diff --check
```

Manual:

- PowerShell full workflow.
- cmd.exe full workflow.
- legacy fallback.

## 11. Acceptance Matrix

Blocker:

```text
ordinary chat
input
assistant streaming
tool call
permission request-response
/resume
/compact
run_shell stdout/stderr capture
PowerShell/cmd.exe manual acceptance
```

Required before default:

```text
diff preview surfaces
history scrollback
/help /context /tasks
/env /memory /plan
Python logging / third-party output capture
legacy fallback
```

Architecture slot:

```text
task/status display
PetSurface / PetState / pet asset interface
theme CSS foundation
```

## 12. Review Checklist for Coding Agent Output

Architecture:

- Are widgets free of LLM/tool/session calls?
- Does worker avoid direct UIStore mutation?
- Are events queued thread-safely?
- Are surfaces keyed by turn/tool id?
- Are surfaces cleaned on all lifecycle boundaries?

Terminal safety:

- Any `print()` in Textual path?
- Any `console.print()` in Textual path?
- Any Rich Live in Textual path?
- Any subprocess inheriting terminal stdout/stderr?
- Any logging handler bypassing RuntimeLogSink?

Security:

- Are secrets redacted before UIEvent?
- Are `/env` values protected?
- Are command args persisted only when safe?

Model correctness:

- Tool errors reach model-visible tool result.
- UI command errors do not enter model context by default.
- ToolRejected is visible to UI and model as needed.

UX:

- Transcript is not boxed into an IDE panel.
- User can scroll freely.
- Streaming does not yank user from history.
- Approval is interaction, not history.
- Diff preview is current-turn UI surface, not transcript.

Tests:

- Unit tests cover UICommand/UIEvent.
- RuntimeController tests cover concurrency and permission.
- Event replay tests cover streaming, permission, cancel, error, compact, resume.
- Textual pilot tests cover basic UI behavior.

## 13. Documentation Updates Required Per Batch

Each batch must update relevant docs:

```text
docs/current/PROGRESS.md
docs/current/ARCHITECTURE.md
docs/current/DEVNOTES.md
docs/superpowers/specs/2026-06-01-textual-claude-style-ui-design.md
```

Do not mark Textual as default-ready until Batch 6 acceptance passes.
