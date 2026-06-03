# Textual Session Transcript Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Textual runtime 像 legacy REPL 一样完整保持多轮模型上下文，并把普通对话、工具调用、工具结果写入现有 session transcript，确保 Textual 创建的新会话可以被 `/resume` 恢复。

**Architecture:** 本次只迁移 transcript 持久化语义，不改变现有 transcript JSONL 格式，不把 diff preview、permission UI、status/task/pet 等 ephemeral UI 内容写入 transcript。`RuntimeController` 继续作为 Textual runtime 的业务主控，负责 turn 生命周期和 session 写入；`AgentEngine` 保持 UI-free，但必须保证 assistant final 进入 runtime history，并让 controller 能按新增 message 顺序写入 transcript。

**Tech Stack:** Python 3.10+、现有 `SessionStore` JSONL、`RuntimeController`、`AgentEngine`、pytest。项目默认 SDD，不要求 TDD 先写 failing test，但本计划要求每个关键行为补回归测试。

---

## 当前问题

Textual 现在有三层 history，其中只有一部分完成：

- UI 显示 history：当前运行中的 `ChatApp` 会把消息 block 放进 UIStore / RichLog，能看到本次进程内的消息流。
- 模型上下文 history：`RuntimeController._history` 会跨 turn 保留 user message；tool-call 分支里 `AgentEngine` 会追加 assistant tool-call message 和 tool result。但普通 assistant final 目前没有稳定追加到 `_history`，下一轮可能缺少上一轮 assistant 回复。
- 磁盘 session transcript：`SessionStore.append_message()` 已存在，`/resume` 和 `/compact` 已能读写部分 transcript；但 Textual 普通 turn 没有完整按 legacy 语义持续写入 user / assistant / tool messages。

目标数据流：

```text
SubmitUserInputCommand
  -> append user to runtime history
  -> append user to SessionStore transcript
  -> AgentEngine.run_turn(history=...)
  -> append assistant final / assistant tool_calls / tool results to runtime history
  -> RuntimeController appends new model-visible messages to transcript
  -> /resume can restore Textual-created session
```

## 非目标

- 不改变 transcript 文件格式。
- 不把 diff preview、command preview、permission prompt、approval decision、status bar、task panel、pet surface 写进 transcript。
- 不做默认入口切换。
- 不重构 UI 样式。
- 不把 `SessionStore` 改成异步。
- 不引入 asyncio。

## 文件职责

- `src/xcode_cli/core/runtime/agent_engine.py`
  - 保持 UI-free agent turn loop。
  - 补齐 assistant final 进入 `history` 的语义。
  - 避免 tool-call 分支和 final 分支重复追加。

- `src/xcode_cli/core/runtime/controller.py`
  - 负责 Textual turn 的 session transcript 写入。
  - user message、assistant message、assistant tool_calls、tool result 的持久化顺序必须和 `_history` 一致。
  - 处理 cancel / error / permission reject 时的 transcript 边界。

- `src/xcode_cli/core/session.py`
  - 原则上不改格式；如需要，只新增很小的 helper，例如 `append_messages(session_id, messages)`，内部仍调用现有 `append_message()`。

- `tests/test_agent_engine.py`
  - 覆盖普通 assistant final 进入 history。
  - 覆盖 tool-call turn 的最终 assistant 回复也进入 history。
  - 覆盖不重复追加 assistant final。

- `tests/test_runtime_controller.py`
  - 覆盖 Textual controller 普通 turn 写入 transcript。
  - 覆盖 tool-call turn 写入 assistant tool_calls、tool result、final assistant。
  - 覆盖 session_id 为空或 session_store 缺失时不崩溃。

- `tests/test_textual_slash_commands.py` 或 `tests/test_textual_chat_app.py`
  - 覆盖 Textual 创建的新 session 能通过 `/resume` 加载。
  - 覆盖 resume 后 `_history` 和 transcript message count 对齐。

- `docs/current/PROGRESS.md` / `docs/current/ARCHITECTURE.md` / `docs/current/DEVNOTES.md`
  - Coding agent 不默认修改。实现完成并经 Codex review 后由 Codex 更新。
  - `DEVNOTES.md` 需要记录 transcript 只保存 model-visible message 的长期边界，避免后续把 diff preview、permission UI、status/task/pet 等 UI-only event 写入 transcript。

---

## Task 1: 明确 AgentEngine 的 history contract

**Files:**
- Modify: `src/xcode_cli/core/runtime/agent_engine.py`
- Test: `tests/test_agent_engine.py`

- [ ] **Step 1: 固定普通 assistant final 会追加到 history**

在 `tests/test_agent_engine.py` 增加测试，沿用现有 fake LLM helper。如果 helper 名称不同，可以按现有测试风格调整，但断言语义不能删除：

```python
def test_final_assistant_message_is_appended_to_history():
    llm = FakeLLM([
        LLMResponse(content="hello back", tool_calls=[]),
    ])
    engine = AgentEngine(llm_client=llm)
    history = [{"role": "user", "content": "hello"}]

    final_text = engine.run_turn(
        history=history,
        system_prompt="",
        tool_schemas=[],
        on_text_token=lambda delta: None,
    )

    assert final_text == "hello back"
    assert history[-1] == {"role": "assistant", "content": "hello back"}
```

- [ ] **Step 2: 固定 tool-call 后最终 assistant 回复也会追加**

模拟两次 LLM response：第一次要求 tool call，第二次返回 final content。

```python
def test_tool_turn_appends_tool_messages_and_final_assistant_message():
    tool_call = ToolCall(id="call_1", name="read_file", args={"path": "README.md"})
    llm = FakeLLM([
        LLMResponse(content=None, tool_calls=[tool_call]),
        LLMResponse(content="I read it.", tool_calls=[]),
    ])
    engine = AgentEngine(llm_client=llm)
    history = [{"role": "user", "content": "read README"}]

    final_text = engine.run_turn(
        history=history,
        system_prompt="",
        tool_schemas=[],
        on_text_token=lambda delta: None,
        execute_tools=lambda tool_calls, turn_id, cancellation: [(tool_call, "file content")],
    )

    assert final_text == "I read it."
    assert history[1]["role"] == "assistant"
    assert history[1]["tool_calls"][0]["id"] == "call_1"
    assert history[2] == {"role": "tool", "tool_call_id": "call_1", "content": "file content"}
    assert history[3] == {"role": "assistant", "content": "I read it."}
```

- [ ] **Step 3: 修改 `AgentEngine.run_turn()` 的 no-tool 分支**

在 `if not response.tool_calls:` 分支里追加 assistant final message。不要把 `[v0]` error response 当作普通 assistant message，保持现有错误返回语义。

推荐实现：

```python
if not response.tool_calls:
    final_content = response.content or ""
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": final_content}
    if response.reasoning_content:
        assistant_msg["reasoning_content"] = response.reasoning_content
    history.append(assistant_msg)
    return final_content
```

- [ ] **Step 4: 跑 AgentEngine 测试**

Run:

```powershell
pytest tests/test_agent_engine.py -q
```

Expected: all tests pass.

---

## Task 2: 给 RuntimeController 增加 transcript append 边界

**Files:**
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Optional Modify: `src/xcode_cli/core/session.py`
- Test: `tests/test_runtime_controller.py`

- [ ] **Step 1: 固定普通 Textual turn 写 transcript**

增加非 headless controller 测试，使用 fake LLM 立即返回 final content。测试应该等待 worker 结束，然后读取 `SessionStore.load_history(session_id)`。

```python
def wait_for_controller_idle(controller: RuntimeController, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not controller.has_active_turn:
            return
        time.sleep(0.01)
    raise AssertionError("controller did not become idle")


def test_submit_user_input_persists_user_and_assistant_messages(tmp_path):
    store = SessionStore(cwd=str(tmp_path / "project"))
    session_id = store.new_session_id()
    llm = FakeLLM([LLMResponse(content="answer", tool_calls=[])])
    controller = RuntimeController(
        llm_client=llm,
        tool_registry=ToolRegistry(),
        session_store=store,
        session_id=session_id,
    )

    controller.dispatch(SubmitUserInputCommand(text="question"))
    wait_for_controller_idle(controller)

    history = store.load_history(session_id)
    assert history == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
```

- [ ] **Step 2: 在 controller 里新增持久化 helper**

```python
def _append_transcript_message(self, message: dict[str, Any]) -> None:
    """Append a model-visible message to the session transcript when available."""
    if self._session_store is None or not self._session_id:
        return
    self._session_store.append_message(self._session_id, dict(message))


def _append_transcript_messages(self, messages: list[dict[str, Any]]) -> None:
    for message in messages:
        self._append_transcript_message(message)
```

- [ ] **Step 3: user message 进入 `_history` 时同步写 transcript**

在 `_handle_submit_user_input()` 中，把 user message 先建成变量：

```python
user_message = {"role": "user", "content": command.text}
self._history.append(user_message)
self._append_transcript_message(user_message)
```

注意：headless 分支现在会提前 return。第一版不改变 headless 语义；需要 transcript 的测试使用 `headless=False`。

- [ ] **Step 4: assistant/tool messages 在 worker 完成后同步写 transcript**

在 `_run_agent_turn()` 调用前记录长度：

```python
history_start_index = len(history)
final_text = self._agent_engine.run_turn(...)
new_messages = history[history_start_index:]
self._append_transcript_messages(new_messages)
```

约束：

- 不要额外手动 append final assistant 到 `_history`，避免和 Task 1 重复。
- transcript 写入顺序必须保持 `history[history_start_index:]` 的顺序。
- `AssistantFinal` UIEvent 仍然只负责 UI 展示，不等于 transcript。

- [ ] **Step 5: turn 异常时不要写半截 assistant final**

如果 `_agent_engine.run_turn()` 抛异常，controller 只发 `UICommandFailed`，不要伪造 assistant message 写入 transcript。已写入的 user message 可以保留。

- [ ] **Step 6: 跑 controller 测试**

Run:

```powershell
pytest tests/test_runtime_controller.py -q
```

Expected: all tests pass.

---

## Task 3: 持久化 tool-call transcript 顺序

**Files:**
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Test: `tests/test_runtime_controller.py`

- [ ] **Step 1: 测试 tool-call turn 写入完整顺序**

使用 read-only fake tool，避免权限阻塞：

```python
registry = ToolRegistry()
registry.register(ToolDef(
    name="fake_read",
    description="Fake read tool",
    parameters={"type": "object", "properties": {}},
    required=[],
    execute=lambda: "fake output",
    is_read_only=True,
))
```

断言 transcript 顺序：

```python
history = store.load_history(session_id)
assert history[0] == {"role": "user", "content": "use tool"}
assert history[1]["role"] == "assistant"
assert history[1]["tool_calls"][0]["function"]["name"] == "fake_read"
assert history[2]["role"] == "tool"
assert history[2]["tool_call_id"] == "call_1"
assert history[2]["content"] == "fake output"
assert history[3] == {"role": "assistant", "content": "done"}
```

- [ ] **Step 2: 确认 `ToolRejected` 仍是模型可见 tool result**

增加权限拒绝测试。断言 transcript 包含 user、assistant tool_calls、tool result containing `User denied tool`。不要把 `PermissionRequestEvent`、`PermissionClearedEvent`、`DiffPreviewAvailable` 写入 transcript。

- [ ] **Step 3: 工具错误也应进入 tool message**

fake tool 抛异常，断言 transcript 中 tool message content 以 `Error:` 或 `Tool error:` 开头，并且 worker 不崩溃。

- [ ] **Step 4: 跑相关测试**

Run:

```powershell
pytest tests/test_runtime_controller.py -q
```

Expected: all tests pass.

---

## Task 4: Textual-created session 可以被 `/resume` 恢复

**Files:**
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Test: `tests/test_textual_slash_commands.py` or `tests/test_textual_chat_app.py`

- [ ] **Step 1: 写 controller 级 resume parity 测试**

流程：

1. 创建 `SessionStore` 和固定 `session_id`。
2. 用 Textual controller 跑一轮普通对话。
3. 创建第二个 controller，传同一个 `SessionStore`。
4. dispatch `ResumeSessionCommand(session_id=session_id)`。
5. 断言第二个 controller 的 `_history` 包含第一轮 user 和 assistant。

```python
assert resumed_controller._history == [
    {"role": "user", "content": "question"},
    {"role": "assistant", "content": "answer"},
]
```

- [ ] **Step 2: 写 `/resume` 列表显示测试**

断言 Textual-created session 会出现在 `ResumeListLoaded.sessions`，并且 `last_user_input` 是刚才提交的用户输入。

```python
loaded = next(e for e in events if isinstance(e, ResumeListLoaded))
assert loaded.sessions[0]["session_id"] == session_id
assert loaded.sessions[0]["last_user_input"] == "question"
assert loaded.sessions[0]["message_count"] == 2
```

- [ ] **Step 3: 跑 slash/resume 相关测试**

Run:

```powershell
pytest tests/test_textual_slash_commands.py tests/test_runtime_controller.py -q
```

Expected: all tests pass.

---

## Task 5: 避免重复写入和 session 边界污染

**Files:**
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Test: `tests/test_runtime_controller.py`

- [ ] **Step 1: 测试同一 turn 不重复写 assistant final**

```python
assistant_messages = [
    m for m in history
    if m.get("role") == "assistant" and m.get("content") == "answer"
]
assert len(assistant_messages) == 1
```

- [ ] **Step 2: 测试 `/resume` 后继续对话写入被 resume 的 session**

流程：原 session 已有 user/assistant，controller resume 该 session，继续 submit 新 input，断言新 message 追加到同一个 transcript 文件，而不是新 session。

```python
history = store.load_history(session_id)
assert [m["content"] for m in history if m["role"] in {"user", "assistant"}] == [
    "old question",
    "old answer",
    "new question",
    "new answer",
]
```

- [ ] **Step 3: 测试 `session_store=None` 或 `session_id=""` 不崩溃**

```python
controller = RuntimeController(
    llm_client=FakeLLM([LLMResponse(content="answer", tool_calls=[])]),
    tool_registry=ToolRegistry(),
    session_store=None,
    session_id="",
)
controller.dispatch(SubmitUserInputCommand(text="question"))
wait_for_controller_idle(controller)
assert not controller.has_active_turn
```

- [ ] **Step 4: 跑 controller 测试**

Run:

```powershell
pytest tests/test_runtime_controller.py -q
```

Expected: all tests pass.

---

## Task 6: 手工验收路径

**Files:**
- No code changes required unless previous tasks expose a bug.

- [ ] **Step 1: 在 PowerShell 或 cmd.exe 启动 Textual**

Run:

```powershell
xcode chat --textual
```

Expected: Textual UI starts without crashing.

- [ ] **Step 2: 连续对话验证模型上下文**

第一轮输入：

```text
记住这个临时词：蓝色铅笔。下一轮我会问你。
```

第二轮输入：

```text
我刚才让你记住的临时词是什么？
```

Expected: assistant can answer `蓝色铅笔` from current conversation context.

- [ ] **Step 3: 退出后用 `/resume` 恢复**

重新启动：

```powershell
xcode chat --textual
```

输入：

```text
/resume
```

选择刚才的 session。

Expected: resume list contains the Textual-created session, and restored session reports the expected message count and last user input.

- [ ] **Step 4: resume 后继续问上下文**

输入：

```text
恢复后你还记得那个临时词吗？
```

Expected: assistant can answer based on restored transcript.

- [ ] **Step 5: 验证 transcript 文件**

```powershell
Get-ChildItem "$env:USERPROFILE\.xcode\projects" -Recurse -Filter "*.jsonl" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 3 FullName, LastWriteTime
```

Expected: latest transcript contains `type=message` rows for user/assistant/tool messages. It should not contain rows for `DiffPreviewAvailable`, `PermissionRequestEvent`, `PermissionClearedEvent`, `StatusUpdated`, or `TaskStateChanged`.

---

## Task 7: 回归验证

**Files:**
- No code changes.

- [ ] **Step 1: 跑核心测试**

Run:

```powershell
pytest tests/test_agent_engine.py tests/test_runtime_controller.py tests/test_textual_slash_commands.py -q
```

Expected: all tests pass.

- [ ] **Step 2: 跑全量测试**

Run:

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: 跑 py_compile**

Run:

```powershell
python -m py_compile src\xcode_cli\core\runtime\agent_engine.py src\xcode_cli\core\runtime\controller.py src\xcode_cli\core\session.py
```

Expected: no output and exit code 0.

---

## 验收标准

- Textual 普通对话 turn 会写入现有 `SessionStore` transcript。
- Textual tool-call turn 会按模型可见顺序写入 user、assistant tool_calls、tool result、final assistant。
- 普通 assistant final 会进入 `_history`，下一轮模型上下文可见。
- `/resume` 能恢复 Textual 创建的新 session。
- `/resume` 后继续对话会追加到被恢复的 session，而不是新 session。
- diff preview、command preview、permission prompt、approval decision、status/task/pet UI 不写入 transcript。
- session_store 缺失或 session_id 为空时 controller 不崩溃。
- `pytest -q` 通过。
- legacy transcript 格式不变。

## 风险与注意事项

- 不要在 `RuntimeController` 和 `AgentEngine` 两处同时追加 assistant final 到 `_history`，否则会重复。
- 不要把 UIEvent 当 transcript event 写入。Transcript 只保存模型可见 message，以及已有 compaction checkpoint event。
- `ToolRejected` 的长期证据应该是 model-visible tool result，不是 approval action 记录。
- `/compact` 期间仍应阻塞新输入；本计划不改变 compact 原子性。
- PowerShell 显示中文异常不等于文件编码损坏。判断文件编码时用 UTF-8 读取或测试验证，不要只看终端渲染。

## Coding Agent 文档要求

Coding agent 不默认修改 `docs/current/PROGRESS.md`、`docs/current/ARCHITECTURE.md`、`docs/current/DEVNOTES.md`、`docs/current/ROADMAP.md`、`AGENTS.md` 或 `XCODE.md`。

实现完成后，Coding agent 应在交付摘要里提供：

- 修改文件列表。
- 行为变化摘要。
- 测试命令和结果。
- 手工验收结果。
- 是否存在未解决风险。

Codex review 后再同步权威项目跟踪文档。

## Self-Review

- Spec coverage: 覆盖 runtime `_history`、磁盘 transcript、tool-call 顺序、resume parity、非目标和 UI-only 内容排除。
- Placeholder scan: 本计划没有 `TBD` / `TODO` / “以后实现” 占位。
- Type consistency: 使用现有 `RuntimeController`、`AgentEngine`、`SessionStore`、`SubmitUserInputCommand`、`ResumeSessionCommand`、`ToolCall`、`LLMResponse` 名称；测试 helper 可按现有 test fake 类型微调，但行为断言不可删除。
