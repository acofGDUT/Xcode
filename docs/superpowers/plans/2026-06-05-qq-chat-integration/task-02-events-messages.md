# Task 2: 消息事件、去重和被动回复

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P0/P1。事件归一化和去重影响回复正确性；被动回复 payload 错误会导致 QQ 侧失败或重复回复。

**Files:**
- Create: `src/xcode_cli/qqchat/events.py`
- Create: `src/xcode_cli/qqchat/dedupe.py`
- Create: `src/xcode_cli/qqchat/message_client.py`
- Test: `tests/test_qqchat_events.py`
- Test: `tests/test_qqchat_message_client.py`

## Goal

把 QQ WebSocket dispatch payload 转换成 Xcode 内部 `QQIncomingMessage`，为 C2C 和群聊 @ 事件构造稳定 conversation key 和 reply target。实现内存去重与 `msg_seq` 分配，并生成 QQ 被动回复 HTTP payload。

## Step 1: 写失败测试 `tests/test_qqchat_events.py`

创建测试文件：

```python
from xcode_cli.qqchat.dedupe import QQMessageDedupe
from xcode_cli.qqchat.events import QQEventNormalizer


def test_normalize_c2c_message_create():
    payload = {
        "op": 0,
        "s": 42,
        "t": "C2C_MESSAGE_CREATE",
        "id": "event-1",
        "d": {
            "id": "msg-1",
            "content": "你好 Xcode",
            "timestamp": "2026-06-05T12:00:00+08:00",
            "author": {"user_openid": "user-openid"},
        },
    }

    result = QQEventNormalizer().normalize(payload)

    assert result is not None
    assert result.event_id == "event-1"
    assert result.event_type == "C2C_MESSAGE_CREATE"
    assert result.message_id == "msg-1"
    assert result.content == "你好 Xcode"
    assert result.conversation_key == "qq:c2c:user-openid"
    assert result.reply_target.kind == "c2c"
    assert result.reply_target.openid == "user-openid"


def test_normalize_group_at_message_create():
    payload = {
        "op": 0,
        "s": 43,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "id": "event-2",
        "d": {
            "id": "msg-2",
            "content": "@机器人 看一下 README",
            "group_openid": "group-openid",
            "author": {"member_openid": "member-openid"},
        },
    }

    result = QQEventNormalizer().normalize(payload)

    assert result is not None
    assert result.event_type == "GROUP_AT_MESSAGE_CREATE"
    assert result.group_openid == "group-openid"
    assert result.member_openid == "member-openid"
    assert result.conversation_key == "qq:group:group-openid:member:member-openid"
    assert result.reply_target.kind == "group"
    assert result.reply_target.group_openid == "group-openid"


def test_unknown_event_is_ignored():
    payload = {"op": 0, "t": "READY", "d": {}}

    assert QQEventNormalizer().normalize(payload) is None


def test_message_dedupe_allows_first_message_only_and_allocates_seq():
    dedupe = QQMessageDedupe()

    assert dedupe.reserve("msg-1") == 1
    assert dedupe.reserve("msg-1") is None
    assert dedupe.reserve("msg-2") == 1
```

## Step 2: 写失败测试 `tests/test_qqchat_message_client.py`

创建测试文件：

```python
from xcode_cli.qqchat.events import QQReplyTarget
from xcode_cli.qqchat.message_client import QQMessageClient


class FakeTransport:
    def __init__(self):
        self.calls = []

    def post_json(self, url, payload, headers=None, timeout=10):
        self.calls.append((url, payload, headers or {}, timeout))
        return 200, {"id": "sent-message"}


def test_send_c2c_reply_uses_v2_user_endpoint():
    transport = FakeTransport()
    client = QQMessageClient(access_token_getter=lambda: "token", transport=transport)

    client.send_text_reply(
        QQReplyTarget(kind="c2c", openid="user-openid"),
        content="收到",
        msg_id="msg-1",
        msg_seq=1,
    )

    url, payload, headers, _timeout = transport.calls[0]
    assert url == "https://api.sgroup.qq.com/v2/users/user-openid/messages"
    assert headers["Authorization"] == "QQBot token"
    assert payload == {"content": "收到", "msg_type": 0, "msg_id": "msg-1", "msg_seq": 1}


def test_send_group_reply_uses_v2_group_endpoint():
    transport = FakeTransport()
    client = QQMessageClient(access_token_getter=lambda: "token", transport=transport)

    client.send_text_reply(
        QQReplyTarget(kind="group", group_openid="group-openid"),
        content="收到",
        msg_id="msg-2",
        msg_seq=2,
    )

    url, payload, headers, _timeout = transport.calls[0]
    assert url == "https://api.sgroup.qq.com/v2/groups/group-openid/messages"
    assert headers["Authorization"] == "QQBot token"
    assert payload["msg_seq"] == 2


def test_send_error_masks_token():
    class ErrorTransport(FakeTransport):
        def post_json(self, url, payload, headers=None, timeout=10):
            return 401, {"message": "bad token"}

    client = QQMessageClient(access_token_getter=lambda: "secret-token", transport=ErrorTransport())

    try:
        client.send_text_reply(
            QQReplyTarget(kind="c2c", openid="user-openid"),
            content="收到",
            msg_id="msg-1",
            msg_seq=1,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "secret-token" not in message
    assert "401" in message
```

## Step 3: 运行测试确认失败

Run:

```powershell
pytest tests/test_qqchat_events.py tests/test_qqchat_message_client.py -q
```

Expected: FAIL，提示 `xcode_cli.qqchat.events`、`dedupe` 或 `message_client` 不存在。

## Step 4: 实现事件数据结构

创建 `src/xcode_cli/qqchat/events.py`，至少包含：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class QQReplyTarget:
    kind: Literal["c2c", "group"]
    openid: str | None = None
    group_openid: str | None = None


@dataclass(frozen=True)
class QQIncomingMessage:
    event_id: str | None
    event_type: str
    message_id: str
    content: str
    timestamp: str | None
    conversation_key: str
    reply_target: QQReplyTarget
    author_openid: str | None
    group_openid: str | None
    member_openid: str | None
    raw_payload: dict[str, Any]
```

`QQEventNormalizer.normalize(payload)` 要求：

- 只处理 `t == "C2C_MESSAGE_CREATE"` 和 `t == "GROUP_AT_MESSAGE_CREATE"`。
- C2C 必须存在 `d.id` 和 `d.author.user_openid`。
- Group 必须存在 `d.id`、`d.group_openid` 和 `d.author.member_openid`。
- 关键字段缺失时返回 `None`，不要抛异常打断 gateway loop。

## Step 5: 实现去重

创建 `src/xcode_cli/qqchat/dedupe.py`：

```python
from __future__ import annotations


class QQMessageDedupe:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._seq: dict[str, int] = {}

    def reserve(self, message_id: str) -> int | None:
        if message_id in self._seen:
            return None
        self._seen.add(message_id)
        self._seq[message_id] = 1
        return 1
```

第一版只需要“同一投递不重复回复”。同一消息多段回复的 `msg_seq` 分配可在后续 `split replies` 中扩展，但不能让重复事件再次触发 runner。

## Step 6: 实现消息发送客户端

创建 `src/xcode_cli/qqchat/message_client.py`。

接口要求：

```python
class QQMessageClient:
    def __init__(self, access_token_getter, *, transport=None) -> None: ...
    def send_text_reply(self, target: QQReplyTarget, *, content: str, msg_id: str, msg_seq: int) -> dict[str, object]: ...
```

实现细节：

- OpenAPI base URL 固定为 `https://api.sgroup.qq.com`。
- C2C endpoint：`/v2/users/{openid}/messages`。
- Group endpoint：`/v2/groups/{group_openid}/messages`。
- payload 固定包含 `content`、`msg_type=0`、`msg_id`、`msg_seq`。
- 默认 HTTP transport 使用标准库 `urllib.request`。
- 发送失败的错误消息不能包含 AccessToken。

## Step 7: 运行聚焦测试

Run:

```powershell
pytest tests/test_qqchat_events.py tests/test_qqchat_message_client.py -q
```

Expected: PASS。

## Step 8: Review 检查点

Codex review 时重点检查：

- group conversation key 是否默认按 member 隔离。
- 未知事件和缺字段事件是否不会抛异常。
- duplicate `msg_id` 是否不会触发第二次回复。
- HTTP payload 是否符合 QQ 被动回复字段要求。
- 错误输出是否不泄露 token。

## Step 9: 提交建议

```powershell
git add src/xcode_cli/qqchat/events.py src/xcode_cli/qqchat/dedupe.py src/xcode_cli/qqchat/message_client.py tests/test_qqchat_events.py tests/test_qqchat_message_client.py
git commit -m "feat: normalize qq messages and send replies"
```

