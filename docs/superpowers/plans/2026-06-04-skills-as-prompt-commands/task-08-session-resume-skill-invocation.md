# Task 8: Session/resume 记录 skill invocation

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Modify: `src/xcode_cli/core/session.py`
- Modify: `src/xcode_cli/core/session_resume.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_skill_prompt_command_flow.py`
- Test: `tests/test_resume.py`

- [ ] **Step 1: 写 transcript 记录测试**

在 `tests/test_skill_prompt_command_flow.py` 增加：

```python
def test_skill_turn_writes_display_content_and_metadata_to_session(tmp_path, monkeypatch):
    import json

    from xcode_cli.core.agent import AgentRuntime
    from xcode_cli.core.turn import UserTurnInput

    runtime = AgentRuntime()
    runtime.cwd = str(tmp_path)
    runtime._session_id = runtime.sessions.new_session_id()
    monkeypatch.setattr(runtime, "_run_llm_loop", lambda history, system_prompt: "ok")

    turn_input = UserTurnInput(
        display_content="/review src/foo.py",
        model_content="Review this: src/foo.py",
        metadata={
            "kind": "skill_invocation",
            "skill": "review",
            "args": "src/foo.py",
            "skill_source_hash": "sha256:test",
        },
    )

    runtime._run_user_turn(turn_input)
    session_path = runtime.sessions.transcript_path(runtime._session_id)
    events = [
        json.loads(line)
        for line in session_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    user_event = next(e for e in events if e["type"] == "message" and e["role"] == "user")
    assert user_event["content"] == "/review src/foo.py"
    assert user_event["metadata"]["kind"] == "skill_invocation"
    assert user_event["metadata"]["skill"] == "review"
    assert user_event["metadata"]["model_content"] == "Review this: src/foo.py"
    assert user_event["metadata"]["skill_source_hash"] == "sha256:test"
```

- [ ] **Step 2: 确认 session append 保留 metadata**

`SessionStore.append_message()` 当前如果只写 role/content，需要允许额外字段透传。不要破坏旧 transcript。

- [ ] **Step 3: resume 恢复策略**

Phase 1 简化策略：

- transcript 中 user event 保留 display content 和 metadata。
- metadata 必须保存 `model_content` 和 `skill_source_hash`。
- `_history` 恢复时优先使用 `metadata.model_content`，没有时才退回 display content。
- 后续如果担心 transcript 过大，再设计 snapshot 压缩或 source hash 重放。

将这个取舍写入测试或注释，避免 Coding Agent 误以为可以只用 `/review args` 恢复模型上下文。

- [ ] **Step 4: 运行测试**

Run:

```powershell
pytest tests/test_skill_prompt_command_flow.py tests/test_resume.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/xcode_cli/core/session.py src/xcode_cli/core/session_resume.py src/xcode_cli/core/agent.py tests/test_skill_prompt_command_flow.py tests/test_resume.py
git commit -m "feat: record skill invocations in sessions"
```
