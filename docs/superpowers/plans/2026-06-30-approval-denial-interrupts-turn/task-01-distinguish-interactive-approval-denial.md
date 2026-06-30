# Task 01: Distinguish Interactive Approval Denial

**Risk layer:** P0

## Goal

把“用户在本地审批菜单选择 No”从普通工具错误中区分出来，使执行层能通知 runtime 当前 turn 必须中断。

## Suggested Files

- Modify: `src/xcode_cli/core/tooling/execution.py`
- Test: `tests/test_agent_tool_loop.py`

## Constraints

- 只有 `ToolApprovalController.prompt()` 返回 `"no"` 的本地交互审批路径触发中断。
- `PermissionManager.check() == "deny"` 不触发中断。
- `tool_scope.remote_approval=False` 不触发中断。
- 被拒绝工具和同 batch 后续 sibling tools 都不能执行。
- assistant/tool message 必须保持 OpenAI-compatible 配对。

## Steps

- [ ] 写失败测试：旧 `test_llm_loop_continues_after_user_denies_tool` 改成拒绝后第二次 LLM 不应被调用。
- [ ] 写失败测试：assistant response 同时包含两个 ask tool calls 时，第一个被用户拒绝后第二个不执行。
- [ ] 写失败测试：显式 `deny` 仍进入下一轮 LLM，证明没有扩大中断范围。
- [ ] 扩展 `ToolExecutionResult`，增加 `interrupted_by_user` 和可选 `interruption_message` 字段。
- [ ] 在 approval `"no"` 分支设置中断状态，写入拒绝 tool result，并停止处理 sibling tool calls。
- [ ] 确保拒绝 tool result 文本包含 `User denied tool: <tool>`，并可作为失败显示。
- [ ] 运行聚焦验证。

## Acceptance

```powershell
pytest tests/test_agent_tool_loop.py::test_llm_loop_interrupts_after_user_denies_tool -q
pytest tests/test_agent_tool_loop.py::test_user_denial_skips_later_sibling_tool_calls -q
pytest tests/test_agent_tool_loop.py::test_explicit_permission_deny_still_allows_model_followup -q
```

Expected:

- 用户审批 No 后 fake LLM 只被调用一次。
- 被拒绝工具没有执行，后续 sibling tool 也没有执行。
- 显式配置 deny 仍作为 tool result 进入下一轮模型。

## Documentation

- 本 task 不更新 `docs/current/ARCHITECTURE.md` 或 `PROGRESS.md`。
- 如果实现发现 spec 对消息结构不适配，先记录差异并请求 Codex review。
