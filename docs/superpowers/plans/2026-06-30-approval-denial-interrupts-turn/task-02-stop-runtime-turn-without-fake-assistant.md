# Task 02: Stop AgentRuntime Turn Without Fake Assistant

**Risk layer:** P0

## Goal

让 `AgentRuntime` 在收到执行层的用户中断状态后停止当前 `_run_llm_loop`，并避免 `_run_user_turn()` 把中断文本写成 assistant final reply。

## Suggested Files

- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_agent_tool_loop.py`
- Test: `tests/test_agent_user_turn.py` or an existing user-turn test module

## Constraints

- 保持 `_run_llm_loop(...) -> str` 兼容，除非一次性更新全部调用点和测试。
- 结构化结果不得传染到 QQchat/external runner 公共接口。
- 中断后必须恢复 runtime status `idle`。
- 中断后不得运行 after-turn success hooks 和 auto memory extraction。
- 中断标记不能作为 assistant final text 追加。

## Steps

- [ ] 写失败测试：`_run_user_turn()` 遇到审批 No 后，session transcript 没有额外 assistant final text。
- [ ] 写失败测试：中断 turn 不调用 after-turn success hooks。
- [ ] 引入 `LLMLoopResult` 或等价结构，表达 `text`、`append_assistant`、`interrupted_by_user`。
- [ ] 推荐新增 `_run_llm_loop_result(...) -> LLMLoopResult` 承载真实逻辑，让旧 `_run_llm_loop(...) -> str` 调用它并返回 `.text`。
- [ ] 在 tool execution 后，先 append assistant/tool messages，再检测 `interrupted_by_user`。
- [ ] 追加固定 system marker：`[Request interrupted by user for tool use]`。
- [ ] 返回 `append_assistant=False` 的 loop result，停止 while，不再请求 LLM。
- [ ] 修改 `_run_user_turn()` 使用结构化结果；`append_assistant=False` 时直接结束本 turn。
- [ ] 运行聚焦验证。

## Acceptance

```powershell
pytest tests/test_agent_tool_loop.py::test_llm_loop_interrupts_after_user_denies_tool -q
pytest tests/test_agent_user_turn.py::test_user_turn_does_not_append_fake_assistant_after_tool_denial -q
pytest tests/test_agent_user_turn.py::test_user_turn_does_not_run_after_turn_hooks_after_tool_denial -q
```

Expected:

- 中断路径没有第二次 LLM 调用。
- transcript 中有 user、assistant tool_calls、tool denial、system interruption marker；没有 assistant final interruption reply。
- after-turn hook 未触发。

## Documentation

- 本 task 完成后仍不更新 `ARCHITECTURE.md`，等 Task 04 汇总验证后统一收口。
