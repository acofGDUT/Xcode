# Approval Denial Interrupts Turn Design

状态：已写设计，代码未实现；自动化回归未执行；PowerShell/cmd.exe 原生 PTY 交互验收未执行。
日期：2026-06-30

## Background

当前 Xcode 的本地 REPL 工具审批拒绝被当成普通 tool result 交给模型。`ToolCallExecutor.execute()` 在用户选择 `No` 后写入 `User denied tool: <name>` 的 tool message，然后 `_run_llm_loop()` 继续下一轮 LLM 请求。这样模型会在同一个 user turn 中继续主动思考、寻找替代方案或继续解释。

用户期望改成 Claude Code 风格的无反馈拒绝语义：用户拒绝本轮工具审批后，当前 turn 立即中断，Xcode 回到输入提示符，等待用户下一次明确输入。下一次输入仍在同一个 session 上下文中继续，不新开空白对话；模型应能看到上一轮的工具请求、拒绝结果和中断标记。

Xcode 现有架构与 Claude Code 不完全相同：Xcode 使用 OpenAI-compatible `assistant.tool_calls` + `role=tool` 配对，session transcript 通过 `SessionStore.append_message()` 持久化，主循环由同步 `AgentRuntime._run_llm_loop()` 编排。因此本设计只借鉴 Claude Code 的行为，不照搬其 React hook / user `tool_result` 数据结构。

## Goals

- 本地 REPL 中用户对交互式工具审批选择 `No`、`n`、Esc、EOF/KeyboardInterrupt fallback 为 `no` 时，当前 user turn 立即停止。
- 停止前仍写入 OpenAI-compatible 的 assistant/tool 配对，保留“模型请求了哪个工具、用户拒绝了哪个工具”的上下文证据。
- 停止后不再发起本 turn 的下一次 LLM 请求，不生成额外 assistant final text，不运行 after-turn success hooks。
- 下一次用户输入继续使用同一个 `_history` 和 session transcript，模型能看到拒绝记录和中断标记。
- 保持 diff preview、shell command preview 和审批菜单的现有可见性；拒绝后给出简短中文提示并回到输入。
- 保持显式配置 `deny`、entry `ToolScope` 拒绝、blocked tool、unknown tool 和工具执行异常的既有“作为工具错误交给模型继续处理”语义，避免扩大行为变更半径。

## Non-goals

- 不新增审批反馈文本框；当前所有本地审批 `No` 都按“无反馈拒绝”处理并中断。
- 不改变 `PermissionManager.check() == "deny"` 的语义；配置级 deny 不是本轮交互式审批拒绝。
- 不改变 QQchat/external/headless 入口的工具 scope 拒绝语义；远程用户不能触发本地等待输入。
- 不改变 OpenAI-compatible message schema，不把 Xcode 的 tool result 改成 Claude Code 的 user `tool_result` block。
- 不实现全局取消、LLM streaming 中断、工具执行期间 Ctrl+C 中断的新语义。
- 不引入 `asyncio`、后台审批队列或新的权限配置格式。

## Current Constraints

- `_run_user_turn()` 当前无条件把 `_run_llm_loop()` 的返回字符串当作 assistant final text 写入 transcript 和 `_history`。本功能不能简单返回 `"Interrupted."`，否则会产生一条并非模型输出的 assistant 回复。
- `_run_llm_loop()` 被测试和 `_run_external_llm_loop()` 直接当作 `str` 使用。实现应采用兼容迁移，例如新增内部结构化结果方法，同时保留旧 `_run_llm_loop()` 返回字符串的测试入口。
- `ToolCallExecutor.execute()` 当前把所有拒绝、blocked scope、permission deny、tool error 都统一成 tool message。实现必须额外区分“本地用户审批 no”这一类交互式拒绝。
- `SessionStore.list_sessions()` 会把最后一条 `role=user` message 当作 session 预览。中断标记不应伪造成 user message，避免污染 `/resume` 列表。
- `SessionResumeBuilder`、compact pair-safe tail 和 `sanitize_model_messages()` 都依赖 assistant/tool 配对合法性。中断路径必须保证没有 orphan tool message，也没有未回应的 assistant tool call。
- 本项目关键交互需要在原生 PowerShell/cmd.exe 验收，不能只靠 Git Bash 或普通单元测试声称完成。

## User-visible Behavior

### 本地 REPL 审批 No

当模型请求需要审批的工具，例如 `run_shell`、`write_file`、`edit_file` 或显式设为 `ask` 的 `dispatch_agent`：

1. Xcode 继续先展示工具摘要、diff preview 或 command preview。
2. 审批菜单出现后，用户选择 `No`、按 `n`、Esc，或非 TTY fallback 输入拒绝。
3. Xcode 显示类似：

```text
  已拒绝工具调用，已中断本轮，等待下一次输入。
```

4. 当前 assistant turn 结束，提示符回到 `you ▸`，Xcode 不再自动请求模型补一句“我会继续不用这个工具”。

### 下一次用户输入

用户再输入新内容时，请求上下文不是空白重来。模型历史中应保留：

```text
user: 上一次用户请求
assistant: tool_use(...)
tool: Error/User denied tool: <tool>
system: [Request interrupted by user for tool use]
user: 新的用户输入
```

这里使用 `system` 中断标记而不是 `user` 标记，是为了符合 Xcode 当前 transcript/session preview 语义；真实用户输入仍只来自用户本人。

### 非交互拒绝保持不变

- `.xcode/settings.json` 或 session rule 中的显式 `deny` 仍作为 tool error 返回给模型，允许模型在同一 turn 中选择无需该工具的替代方案。
- QQchat/external 入口因为 `remote_approval=False` 拒绝本地审批工具时，仍作为 tool error 返回给 headless loop；不进入“等待本地用户下一次输入”状态。
- blocked skill、entry allowlist 拒绝、unknown tool、工具执行异常仍按当前工具错误链路处理。

## Design

### 1. 交互式拒绝成为独立状态

在 `src/xcode_cli/core/tooling/execution.py` 扩展 `ToolExecutionResult`：

```python
@dataclass
class ToolExecutionResult:
    ...
    interrupted_by_user: bool = False
    interruption_message: dict[str, Any] | None = None
```

只有 `level == "ask"` 且 `ToolApprovalController.prompt()` 返回 `"no"` 的路径设置 `interrupted_by_user=True`。其他拒绝路径不设置该字段。

拒绝当前 tool call 后：

- 添加该 tool call 的 assistant/tool 配对，tool message 内容必须包含 `User denied tool: <tool_name>`，建议以 `Error:` 或 `Tool error:` 前缀标记为失败。
- 不执行该工具。
- 不继续执行同一 assistant response 中后续 sibling tool calls。
- 不增加 `executed_count`，不记录 successful tool name，不更新 work state。

### 2. Runtime 追加拒绝证据后停止 LLM loop

在 `AgentRuntime` 中引入结构化 loop 结果，例如：

```python
@dataclass(frozen=True)
class LLMLoopResult:
    text: str
    append_assistant: bool = True
    interrupted_by_user: bool = False
```

推荐新增 `_run_llm_loop_result(...) -> LLMLoopResult` 承载真实逻辑，并保留 `_run_llm_loop(...) -> str` 作为兼容 wrapper，降低测试和 external runner 的迁移成本。

`_run_llm_loop_result()` 在 tool execution 后仍先完成现有写入：

- `history.append(tool_result.assistant_message)`
- `history.extend(tool_result.tool_messages)`
- transcript 写入 assistant/tool messages
- skill invocation audit event 仍只在真实产生时写入

如果 `tool_result.interrupted_by_user` 为真，则再追加中断标记：

```python
{"role": "system", "content": "[Request interrupted by user for tool use]"}
```

该标记写入 runtime `_history` 和 session transcript，随后立即返回：

```python
LLMLoopResult(
    text="[Request interrupted by user for tool use]",
    append_assistant=False,
    interrupted_by_user=True,
)
```

`_run_user_turn()` 使用结构化结果时，若 `append_assistant=False`：

- 不追加 assistant final text。
- 不把中断文本当 assistant message 写入 transcript。
- 不运行 `after_turn_hooks.run_after_turn_success()`，因此不触发 auto memory extraction。
- 仍在 `finally` 中把 runtime status 从 busy 置回 idle。

### 3. Session 和 resume 兼容

新 transcript 事件仍使用现有 `type=message`：

```json
{"type":"message","role":"assistant","content":null,"tool_calls":[...]}
{"type":"message","role":"tool","tool_call_id":"...","content":"Error: User denied tool: run_shell"}
{"type":"message","role":"system","content":"[Request interrupted by user for tool use]"}
```

无需迁移旧 transcript。`/resume` 读取到 system 中断标记时会把它作为普通 history system message 恢复；该标记不影响 `SessionStore.list_sessions()` 的 `last_user_input`。

Compact 仍按现有 pair-safe tail 处理 assistant/tool 配对；system 中断标记可以像 restored context 一样作为普通 system history message 参与摘要或 tail 裁剪。

## Security and Reliability

- 拒绝后绝不能执行被拒绝工具，也不能执行同一 batch 中后续工具调用。
- 拒绝后的 tool message 不能包含完整工具参数、shell 输出、diff 内容或 secret；它只说明用户拒绝了工具名。
- 中断标记是固定字符串，不包含用户输入或模型输出，避免 prompt injection。
- `ToolApprovalController.prompt()` 的 EOF/KeyboardInterrupt fallback 仍返回 `"no"`，因此也走中断路径；这比把半失败审批继续交给模型更安全。
- `PermissionManager` 显式 deny 继续优先于 memory auto-allow、session auto-approve 和 read-only auto-allow。
- Xcode 主循环必须捕获异常并恢复 idle 状态，不能因中断结果新增分支导致 REPL 卡在 busy。

## Compatibility and Migration

- 旧 session transcript 不需要迁移。
- `_run_llm_loop()` 的旧字符串返回接口可暂时保留，降低测试迁移成本；新行为的断言应优先覆盖结构化 `_run_llm_loop_result()` 或 `_run_user_turn()`。
- 现有测试 `test_llm_loop_continues_after_user_denies_tool` 代表旧语义，必须改写为“拒绝后不再调用第二次 LLM”。
- 外部入口仍拿到字符串结果，不需要在本轮引入 `ExternalTurnResult` 的中断字段。

## Alternatives

- **把拒绝当普通 tool error 继续交给模型**：这是当前行为，能让模型自行找替代方案，但违背用户明确想“停下来等我下一句”的交互意图。
- **把中断标记写成 `role=user`**：更接近 Claude Code transcript，但会污染 Xcode 的 session `last_user_input` 和用户输入历史语义，因此不采用。
- **不写中断标记，只保留 tool denial**：实现更小，但下一轮模型只能从 tool result 推断上一轮已中断；固定 system 标记更清楚，也方便测试和 resume。
- **让所有 deny 都中断**：过度扩大行为变更。配置级 deny、entry scope 拒绝和 blocked tool 更像策略错误，模型可以在同一 turn 中调整。

## Acceptance Criteria

- 自动化回归：本地审批 `No` 后 `_run_llm_loop_result()` 不发起第二次 LLM 请求。
- 自动化回归：拒绝路径写入合法 assistant/tool 配对，并追加固定 system 中断标记。
- 自动化回归：`_run_user_turn()` 在中断后不追加 assistant final text，不运行 after-turn success hooks。
- 自动化回归：同一 assistant response 中第一个 ask tool 被用户拒绝后，后续 sibling tool calls 不执行。
- 自动化回归：显式 `PermissionManager` deny、entry `ToolScope.remote_approval=False`、blocked tool 和工具异常仍可作为 tool error 进入下一轮模型，不被误判为用户中断。
- 自动化回归：下一次用户输入的 LLM 请求包含上一轮 tool denial、中断标记和新的 user message。
- 手工验收：PowerShell 和 cmd.exe 原生 PTY 中，拒绝 `run_shell` 后立即回到输入提示符，不出现模型继续回答；下一句输入能在同一 session 继续。
- 手工验收：`write_file` / `edit_file` 的 diff preview 在拒绝前仍可见；拒绝后文件不被修改，并立即回到输入。
- 文档收口：实现完成后再更新 `ARCHITECTURE.md` / `PROGRESS.md` / `ROADMAP.md` / `DEVNOTES.md`，且结论必须跟随真实验证证据。

## Open Questions

- 将来如果审批 UI 增加“带理由拒绝”，是否允许带理由拒绝像 Claude Code 一样继续交给模型？本轮不设计。
- 中断标记最终是否需要独立 event type 便于 UI replay 隐藏？本轮先复用 `message(system)`，实现成本最低。
