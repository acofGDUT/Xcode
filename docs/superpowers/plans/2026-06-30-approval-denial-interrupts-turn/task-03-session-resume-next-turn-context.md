# Task 03: Session, Resume, and Next-turn Context

**Risk layer:** P0

## Goal

确保拒绝中断记录能在同一个 session 的下一次输入和 `/resume` 恢复后保持合法、可用、不过度污染用户历史。

## Suggested Files

- Modify/Test: `tests/test_agent_tool_loop.py`
- Modify/Test: `tests/test_session_resume.py`
- Modify if needed: `src/xcode_cli/core/session_resume.py`
- Modify if needed: `src/xcode_cli/core/message_history.py`

## Constraints

- 不把中断标记写成 `role=user`。
- 不破坏 assistant/tool pair。
- 不让 `/resume` session preview 的 last user input 变成中断标记。
- 不把中断 marker 当作新的 compaction checkpoint 或 restored context。

## Steps

- [ ] 写失败测试：拒绝中断后，下一次 user turn 的 LLM request 能看到 tool denial、system interruption marker 和新 user message。
- [ ] 写失败测试：`SessionStore.list_sessions()` 的 `last_user_input` 仍是用户真实输入，不是中断 marker。
- [ ] 写失败测试：`SessionResumeBuilder` 恢复 interrupted transcript 后，不产生 orphan tool message 或缺 result 的 assistant tool call。
- [ ] 如果现有 `SessionResumeBuilder` 已天然通过，只保留测试证明；不要为了形式改实现。
- [ ] 如果 `sanitize_model_messages()` 会裁掉中断 marker 或配对，按最小范围修复。
- [ ] 运行聚焦验证。

## Acceptance

```powershell
pytest tests/test_agent_tool_loop.py::test_next_user_turn_sees_prior_tool_denial_and_interruption_marker -q
pytest tests/test_session_resume.py::test_resume_preserves_tool_denial_interruption_pair -q
pytest tests/test_session.py::test_interruption_marker_does_not_replace_last_user_input -q
```

Expected:

- 下一次模型请求包含上一轮拒绝证据。
- `/resume` 恢复出的 history 能通过 OpenAI-compatible message 清洗，不丢合法配对。
- session 列表仍显示真实用户输入。

## Documentation

- 若本 task 发现需要改变 marker role 或 event type，必须同步更新 parent spec 后再继续实现。
