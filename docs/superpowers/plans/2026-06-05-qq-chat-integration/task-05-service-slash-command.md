# Task 5: QQChatService 和 `/QQchat`

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P1。slash command 和 service 生命周期是用户可见行为；去重和线程异常仍按 P0 检查。

**Files:**
- Create: `src/xcode_cli/qqchat/service.py`
- Modify: `src/xcode_cli/core/commands/dispatcher.py`
- Modify: `src/xcode_cli/core/commands/slash.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_qqchat_service.py`
- Modify: `tests/test_slash_dispatcher.py`

## Goal

实现 `/QQchat start|stop|status` 的 side-effect command，并通过 `QQChatService` 编排 gateway event、normalizer、dedupe、ExternalTurnRunner 和 QQMessageClient。`/QQchat` 不进入普通 user turn，不写入 LLM history。

## Step 1: 写失败测试 `tests/test_qqchat_service.py`

创建测试文件：

```python
from xcode_cli.qqchat.dedupe import QQMessageDedupe
from xcode_cli.qqchat.events import QQEventNormalizer
from xcode_cli.qqchat.service import QQChatService


class FakeGateway:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.on_event = None

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, conversation_key, turn, *, tool_scope=None):
        self.calls.append((conversation_key, turn, tool_scope))
        return type("Result", (), {"text": "assistant reply", "session_id": "session-1", "error": None})()


class FakeReplyClient:
    def __init__(self):
        self.calls = []

    def send_text_reply(self, target, *, content, msg_id, msg_seq):
        self.calls.append((target, content, msg_id, msg_seq))


def _c2c_payload(message_id="msg-1"):
    return {
        "op": 0,
        "t": "C2C_MESSAGE_CREATE",
        "id": "event-1",
        "d": {"id": message_id, "content": "你好", "author": {"user_openid": "user-openid"}},
    }


def test_start_is_idempotent():
    gateway = FakeGateway()
    service = QQChatService(gateway=gateway, runner=FakeRunner(), reply_client=FakeReplyClient())

    service.start()
    service.start()

    assert gateway.started == 1
    assert service.status()["state"] == "running"


def test_stop_closes_gateway():
    gateway = FakeGateway()
    service = QQChatService(gateway=gateway, runner=FakeRunner(), reply_client=FakeReplyClient())

    service.start()
    service.stop()

    assert gateway.stopped == 1
    assert service.status()["state"] == "stopped"


def test_handle_event_runs_external_turn_and_replies():
    runner = FakeRunner()
    replies = FakeReplyClient()
    service = QQChatService(gateway=FakeGateway(), runner=runner, reply_client=replies)

    service.handle_gateway_event(_c2c_payload())

    assert runner.calls[0][0] == "qq:c2c:user-openid"
    assert runner.calls[0][2].visible_tools == ("read_file", "grep", "glob", "task_list")
    assert runner.calls[0][2].execution_allowlist == ("read_file", "grep", "glob", "task_list")
    assert runner.calls[0][2].remote_approval is False
    assert replies.calls[0][1] == "assistant reply"
    assert replies.calls[0][2] == "msg-1"


def test_duplicate_event_does_not_call_runner_twice():
    runner = FakeRunner()
    service = QQChatService(gateway=FakeGateway(), runner=runner, reply_client=FakeReplyClient())

    service.handle_gateway_event(_c2c_payload("msg-1"))
    service.handle_gateway_event(_c2c_payload("msg-1"))

    assert len(runner.calls) == 1
```

## Step 2: 修改 dispatcher 测试

在 `tests/test_slash_dispatcher.py` 增加：

```python
def test_qqchat_dispatch_is_side_effect_command(console):
    calls = []
    dispatcher = SlashCommandDispatcher(
        console=console,
        help_handler=lambda: None,
        context_handler=lambda: None,
        dashboard_handler=lambda: None,
        skill_handler=lambda parts: None,
        env_handler=lambda parts: None,
        plan_handler=lambda parts: None,
        memory_handler=lambda parts: None,
        resume_handler=lambda: None,
        compact_handler=lambda: None,
        qqchat_handler=lambda parts: calls.append(parts),
    )

    result = dispatcher.dispatch("/QQchat status")

    assert result.kind == "handled"
    assert calls == [["/QQchat", "status"]]
```

如果现有 fixture 不叫 `console`，沿用该文件已有创建方式。

## Step 3: 运行测试确认失败

Run:

```powershell
pytest tests/test_qqchat_service.py tests/test_slash_dispatcher.py -q
```

Expected: FAIL，提示 `QQChatService` 不存在或 dispatcher 不支持 `qqchat_handler`。

## Step 4: 实现 QQChatService

创建 `src/xcode_cli/qqchat/service.py`。

接口要求：

```python
class QQChatService:
    def __init__(self, *, gateway, runner, reply_client, normalizer=None, dedupe=None, default_tool_scope=None) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def status(self) -> dict[str, object]: ...
    def handle_gateway_event(self, payload: dict[str, object]) -> None: ...
```

`handle_gateway_event()` 要求：

- 调用 `QQEventNormalizer.normalize()`。
- `None` 事件直接忽略。
- `dedupe.reserve(message_id)` 返回 `None` 时忽略。
- 构造 `UserTurnInput`：
  - `display_content`: `QQ(C2C user-openid): 你好` 或 `QQ(group group-openid/member member-openid): 你好`
  - `model_content`: 包含外部不可信输入提示和原始 content。
  - `metadata`: 包含 `external_source=qq`、event type、message id、conversation key、`entry_tool_scope` 摘要。
  - `tool_scope`: 默认 `ToolScope(source="qqchat", visible_tools=("read_file", "grep", "glob", "task_list"), execution_allowlist=("read_file", "grep", "glob", "task_list"), remote_approval=False)`。
- 调用 `runner.run(conversation_key, turn, tool_scope=tool_scope)`。
- 如果 `result.text` 非空，调用 `reply_client.send_text_reply(...)`。
- runner 或 reply 失败要记录 status error，不向 gateway 线程抛出。

## Step 5: 注册 `/QQchat`

修改 `src/xcode_cli/core/commands/dispatcher.py`：

- `__init__()` 增加 `qqchat_handler: Callable[[list[str]], None] | None = None`。
- `_handlers` 增加 `"/qqchat": lambda parts: qqchat_handler(parts) if qqchat_handler else console.print("QQchat is not available.")`。
- command head 已 lower-case，`/QQchat status` 会路由到 `/qqchat`。

修改 `src/xcode_cli/core/commands/slash.py`：

- `COMMANDS` 增加 `"/QQchat": "Start, stop, or inspect QQ chat bridge"`。
- completion 支持 `/QQchat start`、`/QQchat stop`、`/QQchat status`。

## Step 6: 接入 AgentRuntime

修改 `src/xcode_cli/core/agent.py`：

- 在 `__init__()` 中创建 QQ service 依赖，但不要启动连接。
- 新增 `_handle_qqchat_command(parts)`：
  - 无参数或 `status`：打印 status table。
  - `start`：调用 service.start()，打印连接状态或配置错误。
  - `stop`：调用 service.stop()。
  - 其他：打印 `Usage: /QQchat start|stop|status`。
- 将 handler 注入 `SlashCommandDispatcher`。

注意：

- 缺少 QQ 配置时普通 `xcode chat` 启动不能失败。
- `/QQchat start` 的错误要可读，并且不泄露 secret。
- service 的后台输出不要直接和 prompt_toolkit 抢屏；状态摘要由命令输出即可。

## Step 7: 运行聚焦测试

Run:

```powershell
pytest tests/test_qqchat_service.py tests/test_slash_dispatcher.py tests/test_agent_user_turn.py -q
```

Expected: PASS。

## Step 8: Review 检查点

Codex review 时重点检查：

- `/QQchat` 是否 side-effect handled，不进入 LLM。
- 重复 start 是否不会创建多个 gateway worker。
- duplicate message 是否不会调用 runner 第二次。
- 缺配置时普通 REPL 是否不受影响。
- 后台线程异常是否不抛出到主循环。

## Step 9: 提交建议

```powershell
git add src/xcode_cli/qqchat/service.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/slash.py src/xcode_cli/core/agent.py tests/test_qqchat_service.py tests/test_slash_dispatcher.py tests/test_agent_user_turn.py
git commit -m "feat: add qq chat service command"
```
