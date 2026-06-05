# Task 4: ExternalTurnRunner

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P0。外部入口如果复用当前 REPL `_history` 会造成 session 污染；入口级 `ToolScope` 若失效会让 QQ 用户触发危险工具。

**Files:**
- Create: `src/xcode_cli/core/external_turn.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_external_turn.py`
- Modify: `tests/test_agent_user_turn.py`
- Modify: `tests/test_agent_tool_loop.py`

## Goal

新增 headless external turn runner，让 QQ 外部消息在独立 session/history 中复用 Xcode LLM/tool loop，并返回 assistant final text。现有 REPL `_run_user_turn()` 的用户可见行为必须保持不变。

## Step 1: 写失败测试

创建 `tests/test_external_turn.py`：

```python
from xcode_cli.core.external_turn import ExternalTurnRunner, ToolScope
from xcode_cli.core.turn import UserTurnInput


READ_ONLY_SCOPE = ToolScope(
    source="qqchat",
    visible_tools=("read_file", "grep", "glob", "task_list"),
    execution_allowlist=("read_file", "grep", "glob", "task_list"),
    remote_approval=False,
)


class FakeSessionStore:
    def __init__(self):
        self.next_id = 0
        self.messages = {}
        self.user_history = []

    def new_session_id(self):
        self.next_id += 1
        return f"session-{self.next_id}"

    def append_message(self, session_id, message):
        self.messages.setdefault(session_id, []).append(message)

    def append_user_history(self, session_id, display):
        self.user_history.append((session_id, display))


class FakeLoop:
    def __init__(self):
        self.calls = []

    def __call__(self, *, history, system_prompt, tool_scope):
        self.calls.append((list(history), system_prompt, tool_scope))
        return "assistant reply"


def test_different_conversation_keys_get_different_sessions():
    sessions = FakeSessionStore()
    loop = FakeLoop()
    runner = ExternalTurnRunner(session_store=sessions, run_llm_loop=loop, build_system_prompt=lambda: "system")

    first = runner.run("qq:c2c:user-a", UserTurnInput("QQ user-a: hi", "hi"), tool_scope=READ_ONLY_SCOPE)
    second = runner.run("qq:c2c:user-b", UserTurnInput("QQ user-b: hi", "hi"), tool_scope=READ_ONLY_SCOPE)

    assert first.session_id == "session-1"
    assert second.session_id == "session-2"


def test_same_conversation_key_reuses_history():
    sessions = FakeSessionStore()
    loop = FakeLoop()
    runner = ExternalTurnRunner(session_store=sessions, run_llm_loop=loop, build_system_prompt=lambda: "system")

    runner.run("qq:c2c:user-a", UserTurnInput("QQ: first", "first"), tool_scope=READ_ONLY_SCOPE)
    runner.run("qq:c2c:user-a", UserTurnInput("QQ: second", "second"), tool_scope=READ_ONLY_SCOPE)

    second_history = loop.calls[1][0]
    assert [m["content"] for m in second_history if m["role"] == "user"] == ["first", "second"]
    assert "assistant reply" in [m["content"] for m in second_history if m["role"] == "assistant"]


def test_tool_scope_is_passed_to_loop_and_dangerous_tools_absent():
    sessions = FakeSessionStore()
    loop = FakeLoop()
    runner = ExternalTurnRunner(session_store=sessions, run_llm_loop=loop, build_system_prompt=lambda: "system")

    runner.run(
        "qq:c2c:user-a",
        UserTurnInput(
            display_content="QQ: inspect",
            model_content="inspect",
            metadata={"external_source": "qq"},
        ),
        tool_scope=READ_ONLY_SCOPE,
    )

    tool_scope = loop.calls[0][2]
    assert tool_scope.visible_tools == ("read_file", "grep", "glob", "task_list")
    assert tool_scope.execution_allowlist == ("read_file", "grep", "glob", "task_list")
    assert tool_scope.remote_approval is False
    assert "write_file" not in tool_scope.visible_tools
    assert "edit_file" not in tool_scope.execution_allowlist
    assert "run_shell" not in tool_scope.execution_allowlist


def test_metadata_is_written_without_secret():
    sessions = FakeSessionStore()
    runner = ExternalTurnRunner(
        session_store=sessions,
        run_llm_loop=lambda **kwargs: "assistant reply",
        build_system_prompt=lambda: "system",
    )

    result = runner.run(
        "qq:c2c:user-a",
        UserTurnInput(
            display_content="QQ: hi",
            model_content="hi",
            metadata={"external_source": "qq", "access_token": "must-not-save"},
        ),
        tool_scope=READ_ONLY_SCOPE,
    )

    user_message = sessions.messages[result.session_id][0]
    assert user_message["metadata"]["external_source"] == "qq"
    assert "access_token" not in user_message["metadata"]
```

## Step 2: 运行测试确认失败

Run:

```powershell
pytest tests/test_external_turn.py -q
```

Expected: FAIL，提示 `xcode_cli.core.external_turn` 不存在。

## Step 3: 设计 ExternalTurnRunner 接口

创建 `src/xcode_cli/core/external_turn.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any, Literal

from xcode_cli.core.turn import UserTurnInput, coerce_user_turn_input


@dataclass(frozen=True)
class ExternalTurnResult:
    text: str
    session_id: str
    error: str | None = None


@dataclass(frozen=True)
class ToolScope:
    source: Literal["qqchat"]
    visible_tools: tuple[str, ...]
    execution_allowlist: tuple[str, ...]
    remote_approval: bool = False


@dataclass
class _ExternalConversationState:
    session_id: str
    history: list[dict[str, Any]] = field(default_factory=list)
```

`ExternalTurnRunner.__init__()` 推荐参数：

```python
def __init__(
    self,
    *,
    session_store,
    run_llm_loop: Callable[..., str],
    build_system_prompt: Callable[[], str],
    default_tool_scope: ToolScope | None = None,
) -> None:
    ...
```

这样测试可以注入 fake loop，`AgentRuntime` 可以注入当前 `_run_llm_loop` adapter。

## Step 4: 实现 run 流程

`run(conversation_key, turn)` 要求：

1. 获取或创建 `_ExternalConversationState`。
2. 清洗 metadata，删除这些 key：
   - `access_token`
   - `client_secret`
   - `authorization`
   - `Authorization`
3. 写 user message 到 `SessionStore.append_message()`。
4. 写轻量 user history 到 `append_user_history()`。
5. 将 `{"role": "user", "content": turn.model_content}` 加入该 conversation 独立 history。
6. 计算 `effective_tool_scope = sanitize_tool_scope(tool_scope or default_tool_scope)`，并在 metadata 中记录不含 secret 的 `entry_tool_scope` 摘要。
7. 调用 `run_llm_loop(history=state.history, system_prompt=..., tool_scope=effective_tool_scope)`。
8. 将 assistant message 写入 transcript 和 state.history。
9. 返回 `ExternalTurnResult(text=final_text, session_id=state.session_id)`。

如果 LLM 返回缺 API key 或 request failed，返回 `ExternalTurnResult(error=..., text=...)`，调用方再决定是否回复 QQ。

## Step 5: 接入 AgentRuntime

修改 `src/xcode_cli/core/agent.py` 时保持小步：

- 不要直接把 QQ 逻辑放进 `_run_user_turn()`。
- 为 `_run_llm_loop()` 增加可选 `tool_scope` 参数，或提供 adapter 在调用前设置当前入口 `ToolScope`，并在 tool schema 过滤和 execution 拒绝层同时使用。
- 保持现有 `tests/test_agent_user_turn.py` 通过。
- 不改变普通 REPL 中 user bubble、assistant bubble、session transcript 行为。

## Step 6: 运行聚焦测试

Run:

```powershell
pytest tests/test_external_turn.py tests/test_agent_user_turn.py tests/test_agent_tool_loop.py -q
```

Expected: PASS。

## Step 7: Review 检查点

Codex review 时重点检查：

- 不同 QQ conversation key 是否真正隔离 history。
- ExternalTurnRunner 是否不使用当前 REPL `_history`。
- `ToolScope` 是否传到 LLM schema 过滤和 execution 校验路径。
- 是否没有把 skill `allowed-tools` 与 QQ `entry_tool_scope` 合并或混用。
- metadata 清洗是否移除 token/secret。
- 普通 `/init`、project skill prompt command 和普通输入行为是否未回归。

## Step 8: 提交建议

```powershell
git add src/xcode_cli/core/external_turn.py src/xcode_cli/core/agent.py tests/test_external_turn.py tests/test_agent_user_turn.py tests/test_agent_tool_loop.py
git commit -m "feat: add external turn runner"
```
