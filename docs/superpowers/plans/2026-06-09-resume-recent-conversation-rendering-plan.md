# Plan: `/resume` 恢复后渲染最近对话

> Parent spec: [2026-06-09-resume-recent-conversation-rendering-design.md](../specs/2026-06-09-resume-recent-conversation-rendering-design.md)

**Risk layer:** P1。该能力是用户可见的 resume 体验增强；由于 session resume 属于核心状态路径，数据选择和 hidden prompt 不泄露按 P0 检查。

**Goal:** `/resume` 成功恢复后，额外渲染最新 checkpoint 之后的所有 user/assistant 对话，让用户能直接看到当前 session 最近上下文。

## 涉及文件

优先修改：

- `src/xcode_cli/core/session_resume.py`
- `src/xcode_cli/core/conversation/resume.py`

优先补测试：

- `tests/test_session_resume.py`
- `tests/test_resume.py`
- `tests/test_agent_resume_command.py`

文档收口：

- `docs/current/ARCHITECTURE.md`
- `docs/current/DEVNOTES.md`
- `docs/current/PROGRESS.md`
- 如 roadmap 状态变化，再更新 `docs/current/ROADMAP.md`

## 约束

- 不引入 `asyncio`。
- 不改变 `SessionResumeBuilder.build()` 当前恢复模型 history 的语义。
- replay 使用 transcript display content，不使用 `metadata.model_content`。
- 不展示 tool result、system summary、audit event。
- 不把 replay 内容写回 transcript。
- Rich 渲染必须避免 markup 注入。

## Step 1: 写失败测试

在 `tests/test_session_resume.py` 中新增 replay helper 测试：

```python
def test_resume_replay_uses_messages_after_latest_checkpoint(tmp_path):
    from xcode_cli.core.session_resume import build_resume_replay_messages

    transcript = tmp_path / "s.jsonl"
    _write_events(transcript, [
        {"type": "message", "role": "user", "content": "old user"},
        {"type": "message", "role": "assistant", "content": "old assistant"},
        {"type": "compaction_checkpoint", "summary": "summary 1"},
        {"type": "message", "role": "user", "content": "new user"},
        {"type": "message", "role": "assistant", "content": "new assistant"},
    ])

    replay = build_resume_replay_messages(transcript)

    assert [(m.role, m.content) for m in replay] == [
        ("user", "new user"),
        ("assistant", "new assistant"),
    ]
```

```python
def test_resume_replay_skips_tool_and_assistant_tool_call_only_messages(tmp_path):
    from xcode_cli.core.session_resume import build_resume_replay_messages

    transcript = tmp_path / "s.jsonl"
    _write_events(transcript, [
        {"type": "message", "role": "user", "content": "read file"},
        {
            "type": "message",
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
        },
        {"type": "message", "role": "tool", "tool_call_id": "c1", "content": "secret tool output"},
        {"type": "message", "role": "assistant", "content": "final answer"},
    ])

    replay = build_resume_replay_messages(transcript)

    assert [(m.role, m.content) for m in replay] == [
        ("user", "read file"),
        ("assistant", "final answer"),
    ]
    assert "secret tool output" not in str(replay)
```

```python
def test_resume_replay_uses_display_content_for_skill_invocation(tmp_path):
    from xcode_cli.core.session_resume import build_resume_replay_messages

    transcript = tmp_path / "s.jsonl"
    _write_events(transcript, [
        {
            "type": "message",
            "role": "user",
            "content": "/review src/foo.py",
            "metadata": {"model_content": "FULL HIDDEN SKILL PROMPT"},
        },
        {"type": "message", "role": "assistant", "content": "review done"},
    ])

    replay = build_resume_replay_messages(transcript)

    assert replay[0].content == "/review src/foo.py"
    assert "FULL HIDDEN" not in str(replay)
```

在 `tests/test_resume.py` 或 `tests/test_agent_resume_command.py` 中新增服务层测试：

```python
def test_resume_success_renders_recent_conversation(monkeypatch):
    service = _make_resume_service_with_one_session(...)
    rendered = []
    monkeypatch.setattr(service, "_render_recent_conversation", lambda messages: rendered.append(messages))

    result = service.run()

    assert result is not None
    assert rendered
```

先运行：

```powershell
pytest tests\test_session_resume.py tests\test_resume.py tests\test_agent_resume_command.py -q
```

预期：失败，提示 replay helper 或 render hook 尚未实现。

## Step 2: 实现 replay 数据 helper

在 `src/xcode_cli/core/session_resume.py` 中新增：

```python
@dataclass(frozen=True)
class ResumeReplayMessage:
    role: str
    content: str
```

新增函数：

```python
def build_resume_replay_messages(transcript_path: Path) -> list[ResumeReplayMessage]:
    ...
```

实现规则：

- 文件不存在返回空列表。
- 逐行读取 JSONL，损坏行跳过。
- 遇到 `compaction_checkpoint` 时清空当前 replay 缓冲，只保留之后的消息。
- `message.role == "user"` 且 `content` 是字符串时加入 replay。
- `message.role == "assistant"` 且 `content` 是非空字符串时加入 replay。
- 其他事件跳过。

不要复用 `_message_for_model_history()`，因为该函数会把 user content 替换为 `metadata.model_content`，这正是 UI replay 需要避免的行为。

## Step 3: 接入 ResumeCommandService

在 `src/xcode_cli/core/conversation/resume.py` 中：

- 导入 `ResumeReplayMessage` 和 `build_resume_replay_messages`。
- 在 TTY 与非 TTY 两条恢复成功路径中，选中 session 并 build history 成功后调用：

```python
replay_messages = build_resume_replay_messages(selected_session.path)
self._render_recent_conversation(replay_messages)
```

为避免 TTY/非 TTY 重复代码，建议抽出：

```python
def _restore_selected_session(self, selected_session) -> ResumeResult | None:
    ...
```

但如果当前文件改动更小时，也可以先在两处各加一行，后续再重构。

新增渲染函数：

```python
def _render_recent_conversation(self, messages: list[ResumeReplayMessage]) -> None:
    ...
```

渲染要求：

- 空列表时打印 `No user/assistant messages after the latest checkpoint.`。
- 非空时先打印标题 `Recent conversation since checkpoint:`。
- 每条消息打印 role 和 content。
- 使用 `markup=False` / `highlight=False` 或 Rich `Text`，不能解析用户内容 markup。

## Step 4: 保持 resume 语义不变

重点检查：

- `ResumeResult.history` 内容不变。
- `_history[:] = result.history` 的赋值路径不变。
- `update_session_id()` 仍在恢复成功后调用。
- `Latest user input` 可以保留，也可以被最近对话 replay 替代；如移除，需同步测试和文档。推荐第一版保留，降低行为变化。

## Step 5: 验证

运行：

```powershell
python -m py_compile src\xcode_cli\core\conversation\resume.py src\xcode_cli\core\session_resume.py
pytest tests\test_session_resume.py tests\test_resume.py tests\test_agent_resume_command.py -q
git diff --check
```

手工验收记录：

```text
PowerShell:
  1. 准备有 checkpoint 且 checkpoint 后有两轮 user/assistant 的 session。
  2. /resume 选择该 session。
  3. 确认恢复摘要后显示两轮最近对话。
  4. 确认 tool result 不显示。

cmd.exe:
  重复 PowerShell 的恢复与 replay 展示。
```

未做手工验收时，结论只能写自动化和本地逻辑通过。

## Review 检查点

- replay 是否只读 transcript，不写 transcript。
- user skill invocation 是否没有泄露 `metadata.model_content`。
- assistant tool_call-only 中间消息是否跳过。
- tool result 是否跳过。
- checkpoint 边界是否使用最新 checkpoint。
- resume 的模型 history 是否没有被 replay helper 改变。
- Rich 渲染是否禁用了用户内容 markup。

## 建议提交信息

```powershell
git add src/xcode_cli/core/session_resume.py src/xcode_cli/core/conversation/resume.py tests/test_session_resume.py tests/test_resume.py tests/test_agent_resume_command.py docs/current/ARCHITECTURE.md docs/current/DEVNOTES.md docs/current/PROGRESS.md
git commit -m "feat: show recent conversation after resume"
```
