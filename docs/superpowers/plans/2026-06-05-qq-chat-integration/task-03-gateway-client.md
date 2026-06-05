# Task 3: WebSocket Gateway Client

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P0。Gateway 状态机、heartbeat 和 reconnect 失败会导致外部入口不可用；异常必须被捕获并转为状态，不得打崩 Agent 主循环。

**Files:**
- Create: `src/xcode_cli/qqchat/gateway.py`
- Test: `tests/test_qqchat_gateway.py`

## Goal

实现 QQ WebSocket Gateway 的同步客户端基础：获取 gateway URL、构造 Identify/Heartbeat/Resume payload、保存 session/seq，并把 dispatch event 放入回调。第一版单元测试只验证 payload 和状态机，不连接真实 QQ。

## Step 1: 写失败测试

创建 `tests/test_qqchat_gateway.py`：

```python
from xcode_cli.qqchat.gateway import (
    GROUP_AND_C2C_INTENTS,
    QQGatewayClient,
    build_heartbeat_payload,
    build_identify_payload,
    build_resume_payload,
)


class FakeGatewayTransport:
    def __init__(self):
        self.calls = []

    def get_json(self, url, headers=None, timeout=10):
        self.calls.append((url, headers or {}, timeout))
        return 200, {"url": "wss://api.sgroup.qq.com/websocket/"}


def test_group_and_c2c_intents_bitmask():
    assert GROUP_AND_C2C_INTENTS == 1 << 25


def test_fetch_gateway_url_calls_openapi_gateway():
    transport = FakeGatewayTransport()
    client = QQGatewayClient(access_token_getter=lambda: "token", transport=transport)

    assert client.fetch_gateway_url() == "wss://api.sgroup.qq.com/websocket/"

    url, headers, _timeout = transport.calls[0]
    assert url == "https://api.sgroup.qq.com/gateway"
    assert headers["Authorization"] == "QQBot token"


def test_identify_payload_uses_qqbot_token_and_intents():
    payload = build_identify_payload("token")

    assert payload["op"] == 2
    assert payload["d"]["token"] == "QQBot token"
    assert payload["d"]["intents"] == 1 << 25
    assert payload["d"]["shard"] == [0, 1]
    assert payload["d"]["properties"]["os"] == "windows"


def test_heartbeat_payload_uses_latest_seq_or_null():
    assert build_heartbeat_payload(None) == {"op": 1, "d": None}
    assert build_heartbeat_payload(42) == {"op": 1, "d": 42}


def test_resume_payload_uses_session_id_and_seq():
    payload = build_resume_payload("token", session_id="session-1", seq=99)

    assert payload == {
        "op": 6,
        "d": {"token": "QQBot token", "session_id": "session-1", "seq": 99},
    }


def test_handle_ready_saves_session_and_seq():
    client = QQGatewayClient(access_token_getter=lambda: "token", transport=FakeGatewayTransport())

    client.handle_payload({"op": 0, "s": 7, "t": "READY", "d": {"session_id": "session-1"}})

    assert client.session_id == "session-1"
    assert client.seq == 7


def test_dispatch_event_is_forwarded_to_callback():
    seen = []
    client = QQGatewayClient(
        access_token_getter=lambda: "token",
        transport=FakeGatewayTransport(),
        on_event=seen.append,
    )
    payload = {"op": 0, "s": 8, "t": "C2C_MESSAGE_CREATE", "d": {"id": "msg-1"}}

    client.handle_payload(payload)

    assert client.seq == 8
    assert seen == [payload]
```

## Step 2: 运行测试确认失败

Run:

```powershell
pytest tests/test_qqchat_gateway.py -q
```

Expected: FAIL，提示 `xcode_cli.qqchat.gateway` 不存在。

## Step 3: 实现 payload builders

创建 `src/xcode_cli/qqchat/gateway.py`，先实现常量和纯函数：

```python
from __future__ import annotations

import platform
from typing import Any, Callable


GROUP_AND_C2C_INTENTS = 1 << 25


def build_identify_payload(access_token: str, *, intents: int = GROUP_AND_C2C_INTENTS) -> dict[str, Any]:
    return {
        "op": 2,
        "d": {
            "token": f"QQBot {access_token}",
            "intents": intents,
            "shard": [0, 1],
            "properties": {
                "os": "windows",
                "browser": "xcode",
                "device": "xcode",
            },
        },
    }


def build_heartbeat_payload(seq: int | None) -> dict[str, Any]:
    return {"op": 1, "d": seq}


def build_resume_payload(access_token: str, *, session_id: str, seq: int | None) -> dict[str, Any]:
    return {
        "op": 6,
        "d": {"token": f"QQBot {access_token}", "session_id": session_id, "seq": seq},
    }
```

`properties.os` 固定为 `"windows"` 即可，因为当前项目主验收环境是 Windows。不要从平台字符串里暴露用户机器细节。

## Step 4: 实现 Gateway client 状态

`QQGatewayClient` 接口要求：

```python
class QQGatewayClient:
    def __init__(self, access_token_getter, *, transport=None, on_event=None, on_status=None) -> None: ...
    @property
    def seq(self) -> int | None: ...
    @property
    def session_id(self) -> str | None: ...
    def fetch_gateway_url(self) -> str: ...
    def handle_payload(self, payload: dict[str, Any]) -> None: ...
```

实现细节：

- `fetch_gateway_url()` 调用 `https://api.sgroup.qq.com/gateway`。
- Authorization header 是 `QQBot {access_token}`。
- HTTP status 非 2xx 时抛出脱敏 `RuntimeError`。
- `handle_payload()` 如果存在 int 类型 `s`，更新 `self._seq`。
- `t == "READY"` 时保存 `d.session_id`。
- `op == 0` 且 `t` 是消息事件时调用 `on_event(payload)`。
- `on_event` 异常要捕获并通过 `on_status` 记录，不要向外抛出。

## Step 5: 实现同步 runner 骨架

在同一文件中提供 `start()` / `stop()` 但单元测试可以先不覆盖真实 socket：

- `start()` 创建后台 thread，调用 `websocket.WebSocketApp.run_forever()`。
- `stop()` 设置 stop event 并关闭 websocket。
- on_open 发送 identify 或 resume payload。
- on_message parse JSON 后调用 `handle_payload()`。
- on_error/on_close 更新状态，不抛到主线程。
- heartbeat thread 根据 hello 的 `heartbeat_interval` 定期发送 `op=1`。

约束：

- websocket import 放在 `start()` 内部，避免单元测试和无依赖环境 import 即失败。
- 不使用 `asyncio`。
- 后台线程必须 daemon=True，防止 CLI 退出被卡住。

## Step 6: 运行聚焦测试

Run:

```powershell
pytest tests/test_qqchat_gateway.py -q
```

Expected: PASS。

## Step 7: Review 检查点

Codex review 时重点检查：

- intents 是否是 `1 << 25`。
- Identify/Resume token 是否有 `QQBot ` 前缀。
- AccessToken 是否不进入 status/error 输出。
- websocket import 是否不会让普通测试环境失败。
- on_event 异常是否被捕获。
- 是否没有引入 `asyncio`。

## Step 8: 提交建议

```powershell
git add src/xcode_cli/qqchat/gateway.py tests/test_qqchat_gateway.py
git commit -m "feat: add qq gateway client"
```

