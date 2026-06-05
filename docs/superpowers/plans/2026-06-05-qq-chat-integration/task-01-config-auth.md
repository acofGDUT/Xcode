# Task 1: 配置和鉴权

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P1。配置加载和鉴权失败会影响 `/QQchat start` 用户可见行为；secret 脱敏属于 P0 安全边界。

**Files:**
- Modify: `pyproject.toml`
- Create: `src/xcode_cli/qqchat/__init__.py`
- Create: `src/xcode_cli/qqchat/config.py`
- Create: `src/xcode_cli/qqchat/auth.py`
- Test: `tests/test_qqchat_config.py`
- Test: `tests/test_qqchat_auth.py`

## Goal

建立 QQ 接入的配置和 AccessToken 鉴权基础。配置必须支持环境变量、用户级私密配置、项目级非敏感配置；项目级配置不能覆盖 `client_secret`。鉴权客户端必须可测试，不在单元测试里访问真实 QQ 网络。

## Step 1: 写失败测试 `tests/test_qqchat_config.py`

创建测试文件：

```python
import json

from xcode_cli.qqchat.config import QQChatConfig, load_qqchat_config


def test_env_loads_app_id_and_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("QQ_BOT_APP_ID", "app-from-env")
    monkeypatch.setenv("QQ_BOT_CLIENT_SECRET", "secret-from-env")

    cfg = load_qqchat_config(project_root=tmp_path, user_config_path=tmp_path / "missing.json")

    assert cfg.app_id == "app-from-env"
    assert cfg.client_secret == "secret-from-env"


def test_project_config_cannot_override_client_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("QQ_BOT_APP_ID", "app-from-env")
    monkeypatch.setenv("QQ_BOT_CLIENT_SECRET", "secret-from-env")
    project_config = tmp_path / ".xcode" / "config.json"
    project_config.parent.mkdir()
    project_config.write_text(
        json.dumps(
            {
                "qqchat": {
                    "client_secret": "project-secret-must-not-win",
                    "enable_group_at": False,
                    "group_allowlist": ["group-a"],
                    "max_reply_chars": 1200,
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_qqchat_config(project_root=tmp_path, user_config_path=tmp_path / "missing.json")

    assert cfg.client_secret == "secret-from-env"
    assert cfg.enable_group_at is False
    assert cfg.group_allowlist == ["group-a"]
    assert cfg.max_reply_chars == 1200


def test_user_config_can_supply_secret_when_env_is_missing(tmp_path):
    user_config = tmp_path / "qqchat.json"
    user_config.write_text(
        json.dumps({"app_id": "app-from-user", "client_secret": "secret-from-user"}),
        encoding="utf-8",
    )

    cfg = load_qqchat_config(project_root=tmp_path, user_config_path=user_config, env={})

    assert cfg.app_id == "app-from-user"
    assert cfg.client_secret == "secret-from-user"


def test_default_tool_scope_is_read_only():
    cfg = QQChatConfig(app_id="app", client_secret="secret")

    assert cfg.tool_scope == {
        "visible_tools": ["read_file", "grep", "glob", "task_list"],
        "execution_allowlist": ["read_file", "grep", "glob", "task_list"],
        "remote_approval": False,
    }


def test_safe_summary_masks_secret():
    cfg = QQChatConfig(app_id="app", client_secret="super-secret")

    summary = cfg.safe_summary()

    assert "super-secret" not in summary
    assert summary["client_secret"] == "<set>"
```

## Step 2: 写失败测试 `tests/test_qqchat_auth.py`

创建测试文件：

```python
import json

from xcode_cli.qqchat.auth import QQAuthClient


class FakeClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.responses = []

    def push(self, payload, status=200):
        self.responses.append((status, payload))

    def post_json(self, url, payload, headers=None, timeout=10):
        self.calls.append((url, payload, headers or {}, timeout))
        status, body = self.responses.pop(0)
        return status, body


def test_get_token_posts_app_credentials():
    transport = FakeTransport()
    transport.push({"access_token": "token-1", "expires_in": 7200})
    clock = FakeClock()
    client = QQAuthClient("app-id", "secret", transport=transport, now=clock)

    token = client.get_access_token()

    assert token == "token-1"
    assert transport.calls[0][0] == "https://bots.qq.com/app/getAppAccessToken"
    assert transport.calls[0][1] == {"appId": "app-id", "clientSecret": "secret"}


def test_get_token_reuses_cache_until_near_expiry():
    transport = FakeTransport()
    transport.push({"access_token": "token-1", "expires_in": 7200})
    clock = FakeClock()
    client = QQAuthClient("app-id", "secret", transport=transport, now=clock)

    assert client.get_access_token() == "token-1"
    clock.value += 100
    assert client.get_access_token() == "token-1"

    assert len(transport.calls) == 1


def test_get_token_refreshes_when_less_than_60_seconds_left():
    transport = FakeTransport()
    transport.push({"access_token": "token-1", "expires_in": 120})
    transport.push({"access_token": "token-2", "expires_in": 7200})
    clock = FakeClock()
    client = QQAuthClient("app-id", "secret", transport=transport, now=clock)

    assert client.get_access_token() == "token-1"
    clock.value += 80
    assert client.get_access_token() == "token-2"

    assert len(transport.calls) == 2


def test_auth_error_does_not_leak_secret():
    transport = FakeTransport()
    transport.push({"error": "bad secret"}, status=401)
    client = QQAuthClient("app-id", "super-secret", transport=transport, now=FakeClock())

    try:
        client.get_access_token()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "super-secret" not in message
    assert "401" in message
```

## Step 3: 运行测试确认失败

Run:

```powershell
pytest tests/test_qqchat_config.py tests/test_qqchat_auth.py -q
```

Expected: FAIL，提示 `No module named 'xcode_cli.qqchat'`。

## Step 4: 修改 `pyproject.toml`

在 dependencies 中增加：

```toml
"websocket-client>=1.8.0",
```

注意：如果本地环境尚未安装该依赖，后续运行真实 WebSocket 前需要安装包；本 task 的单元测试不应 import `websocket`。

## Step 5: 实现 `QQChatConfig`

创建 `src/xcode_cli/qqchat/__init__.py`，内容保持轻量：

```python
"""QQ bot integration package."""
```

创建 `src/xcode_cli/qqchat/config.py`，实现这些接口：

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


READ_ONLY_TOOLS = ["read_file", "grep", "glob", "task_list"]


def default_tool_scope() -> dict[str, object]:
    return {
        "visible_tools": list(READ_ONLY_TOOLS),
        "execution_allowlist": list(READ_ONLY_TOOLS),
        "remote_approval": False,
    }


@dataclass
class QQChatConfig:
    app_id: str = ""
    client_secret: str = ""
    enabled: bool = True
    enable_c2c: bool = True
    enable_group_at: bool = True
    group_allowlist: list[str] = field(default_factory=list)
    owner_openids: list[str] = field(default_factory=list)
    tool_scope: dict[str, object] = field(default_factory=default_tool_scope)
    max_reply_chars: int = 1800
    group_turn_timeout_seconds: int = 240
    c2c_turn_timeout_seconds: int = 900

    def safe_summary(self) -> dict[str, object]:
        return {
            "app_id": self.app_id or "<missing>",
            "client_secret": "<set>" if self.client_secret else "<missing>",
            "enabled": self.enabled,
            "enable_c2c": self.enable_c2c,
            "enable_group_at": self.enable_group_at,
            "group_allowlist": list(self.group_allowlist),
            "owner_openids": list(self.owner_openids),
            "tool_scope": dict(self.tool_scope),
            "max_reply_chars": self.max_reply_chars,
            "group_turn_timeout_seconds": self.group_turn_timeout_seconds,
            "c2c_turn_timeout_seconds": self.c2c_turn_timeout_seconds,
        }
```

`load_qqchat_config()` 要求：

- 从 user config 读取 `app_id` 和 `client_secret`。
- 从 env 覆盖 `app_id` 和 `client_secret`。
- 从 project `.xcode/config.json` 的 `qqchat` 只读取非敏感字段。
- 项目级 `client_secret`、`access_token`、`authorization` 字段必须忽略。
- 项目级工具配置使用 `tool_scope.visible_tools`、`tool_scope.execution_allowlist` 和 `tool_scope.remote_approval`；不要新增或读取 QQ 专用 `allowed-tools` / `default_allowed_tools` 字段。
- JSON 损坏时返回可读 `RuntimeError`，不要吞掉错误。

## Step 6: 实现 `QQAuthClient`

创建 `src/xcode_cli/qqchat/auth.py`。

接口要求：

```python
class QQAuthClient:
    def __init__(self, app_id: str, client_secret: str, *, transport=None, now=None) -> None: ...
    def get_access_token(self) -> str: ...
    def clear_cache(self) -> None: ...
```

实现细节：

- 默认 transport 使用标准库 `urllib.request`。
- `get_access_token()` 只有在没有 token 或距离过期不足 60 秒时才请求新 token。
- QQ 返回体字段使用 `access_token` 和 `expires_in`。
- 错误消息包含状态码和简短原因，但不得包含 secret 或完整请求体。

## Step 7: 运行聚焦测试

Run:

```powershell
pytest tests/test_qqchat_config.py tests/test_qqchat_auth.py -q
```

Expected: PASS。

## Step 8: Review 检查点

Codex review 时重点检查：

- 项目级 `.xcode/config.json` 是否不能覆盖 secret。
- 错误输出和 `safe_summary()` 是否不泄露 secret。
- 单元测试是否没有访问真实 QQ 网络。
- 新增依赖是否是同步 WebSocket 依赖，不引入 `asyncio`。

## Step 9: 提交建议

```powershell
git add pyproject.toml src/xcode_cli/qqchat/__init__.py src/xcode_cli/qqchat/config.py src/xcode_cli/qqchat/auth.py tests/test_qqchat_config.py tests/test_qqchat_auth.py
git commit -m "feat: add qq chat config and auth"
```
