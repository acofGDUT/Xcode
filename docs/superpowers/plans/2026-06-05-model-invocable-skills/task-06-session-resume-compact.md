# Task 6: session/resume/compact 验收

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Modify: `src/xcode_cli/core/session.py`
- Modify: `src/xcode_cli/core/tooling/execution.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_model_invocable_skill_flow.py`
- Test: `tests/test_resume.py`
- Test: `tests/test_compaction.py`

- [ ] **Step 1: 写 session metadata 测试**

在 `tests/test_model_invocable_skill_flow.py` 增加：

```python
import json


def read_session_events(runtime):
    path = runtime.sessions.transcript_path(runtime._session_id)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_skill_tool_writes_invocation_metadata_without_user_visible_prompt(tmp_path, monkeypatch):
    runtime = make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=["read"])
    runtime._session_id = runtime.sessions.new_session_id()
    runtime.llm.complete = fake_skill_then_final_response()

    runtime._run_user_turn("please review src/foo.py")

    events = read_session_events(runtime)
    user_event = next(e for e in events if e.get("role") == "user")
    skill_events = [e for e in events if e.get("type") == "skill_invocation"]
    assert user_event["content"] == "please review src/foo.py"
    assert "Review $ARGUMENTS" not in user_event["content"]
    assert skill_events
    assert skill_events[0]["skill"] == "review"
    assert skill_events[0]["source"] == "model"
    assert skill_events[0]["skill_source_hash"].startswith("sha256:")
    assert "model_content" not in skill_events[0]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_model_invocable_skill_flow.py::test_skill_tool_writes_invocation_metadata_without_user_visible_prompt -q
```

Expected: FAIL，因为还没有写 `skill_invocation` event。

- [ ] **Step 3: 写 skill_invocation event**

在 `AgentRuntime._run_llm_loop()` 中，处理 `tool_result.skill_invocations`：

```python
for invocation in tool_result.skill_invocations:
    if self._session_id:
        self.sessions.append_event(self._session_id, {"type": "skill_invocation", **invocation})
```

事件不要写完整 `model_content`，只写审计字段：

```python
{
    "type": "skill_invocation",
    "kind": "skill_invocation",
    "source": "model",
    "skill": "review",
    "args": "src/foo.py",
    "source_path": ".../SKILL.md",
    "skill_source_hash": "sha256:..."
}
```

完整 prompt 已在 tool message 中用于模型恢复，不在额外 event 重复保存。

- [ ] **Step 4: 写 resume 测试**

在 `tests/test_resume.py` 增加：

```python
def test_resume_preserves_skill_tool_message_for_model_history(tmp_path):
    from xcode_cli.core.session_resume import build_model_history_from_events

    events = [
        {"type": "message", "role": "user", "content": "please review src/foo.py"},
        {
            "type": "message",
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "skill", "arguments": "{\"skill\":\"review\"}"},
                }
            ],
        },
        {
            "type": "message",
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "<xcode_loaded_skill name=\"review\" source=\"model\">\nReview src/foo.py\n</xcode_loaded_skill>",
        },
    ]

    history = build_model_history_from_events(events)

    assert any("<xcode_loaded_skill name=\"review\"" in str(message) for message in history)
```

如果当前 `session_resume.py` 中没有公开的 `build_model_history_from_events()`，先把现有 resume history 构建逻辑抽成这个函数，再用该测试锁住行为。

- [ ] **Step 5: 写 compact 测试**

在 `tests/test_compaction.py` 增加：

```python
def test_compaction_keeps_loaded_skill_marker_in_source_history(tmp_path):
    from unittest.mock import MagicMock

    from xcode_cli.core.conversation.compaction import ConversationCompactor

    captured = {}

    class FakeContext:
        def estimate_tokens(self, history):
            return len(str(history))

        def compress(self, history, llm, previous_summary):
            captured["history"] = history
            return MagicMock(
                messages=history,
                summary="summary",
                checkpoint_message={"role": "system", "content": "Conversation summary checkpoint:\nsummary"},
            )

    history = [
        {"role": "user", "content": "please review src/foo.py"},
        {"role": "tool", "tool_call_id": "call_1", "content": "<xcode_loaded_skill name=\"review\">Review src/foo.py</xcode_loaded_skill>"},
    ]
    compactor = ConversationCompactor(FakeContext(), MagicMock(), MagicMock(), MagicMock())

    compactor.compact_history(history)

    assert any("<xcode_loaded_skill name=\"review\"" in str(message) for message in captured["history"])
```

这个测试证明 Phase 2 不需要单独为 compact 重放 skill；只要 tool message 在 `_history` 中即可。

- [ ] **Step 6: 运行测试确认通过**

Run:

```powershell
pytest tests/test_model_invocable_skill_flow.py tests/test_resume.py tests/test_compaction.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add src/xcode_cli/core/session.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/agent.py tests/test_model_invocable_skill_flow.py tests/test_resume.py tests/test_compaction.py
git commit -m "feat: persist model skill invocations"
```
