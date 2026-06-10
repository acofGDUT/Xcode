# QQchat init 与 reload 增量设计

> 本文是 `2026-06-05-qq-chat-integration-design.md` 的增量 spec，只覆盖 `/QQchat init` 和热部署命令。当前任务不直接修改功能代码。

## 背景

现有 QQchat 第一版已经支持 `/QQchat start|stop|status`，配置加载来源为：

1. 环境变量：`QQ_BOT_APP_ID`、`QQ_BOT_CLIENT_SECRET`
2. 用户级私密配置：`~/.xcode/qqchat.json`
3. 项目级非敏感配置：`<project>/.xcode/config.json` 的 `qqchat` 字段

目前缺口是首次使用体验较硬：缺少一条命令帮助用户创建配置文件骨架；配置变更后也缺少不重启整个 Xcode REPL 的热部署入口。

用户提到的项目级路径写作 `.xocde/config`，本文按项目既有约定规范为 `<project>/.xcode/config.json`。

## 目标

- 新增 `/QQchat init`：幂等初始化 QQchat 相关配置文件。
- 新增 `/QQchat reload`：热加载 QQchat 配置，并在 service 已运行时用新配置重建连接。
- 两个命令都是 side-effect slash command，不进入 `_run_user_turn()`，不写 LLM history。
- 初始化不覆盖用户已有配置，不写入真实 secret，不泄露 `client_secret`。

## 非目标

- 不在本轮实现真实 QQ 平台验收。
- 不新增 Webhook、主动推送、富媒体或危险工具远程审批。
- 不改变现有配置优先级：环境变量仍优先于用户级配置，用户级 secret 仍优先于项目级非敏感字段。
- 不把项目级配置文件从 `.xcode/config.json` 改名为 `.xcode/config`。

## 命令设计

```text
/QQchat init
/QQchat reload
```

`/QQchat init` 行为：

- 如果 `<project>/.xcode/` 不存在，则创建目录。
- 如果 `<project>/.xcode/config.json` 不存在，则创建带 `qqchat` 默认字段的 JSON 文件。
- 如果 `<project>/.xcode/config.json` 已存在且是合法 JSON object：
  - 如果没有 `qqchat` 字段，则追加默认 `qqchat` object。
  - 如果已有 `qqchat` 字段，则只补缺失字段，不覆盖用户已有值。
- 如果 `~/.xcode/` 不存在，则创建目录。
- 如果 `~/.xcode/qqchat.json` 不存在，则创建用户级 secret 模板。
- 如果 `~/.xcode/qqchat.json` 已存在，则不覆盖。
- 输出应汇总 created / updated / unchanged / failed 文件列表。

`/QQchat reload` 行为：

- 重新调用 `load_qqchat_config(project_root=self.cwd)`。
- 如果配置缺少 `app_id` 或 `client_secret`，更新 `_qqchat_init_error`，把 `qqchat_service` 置为不可启动状态，并打印可读错误。
- 如果当前 service 未运行：
  - 用新配置重建 `QQChatService` 依赖。
  - 不自动启动 gateway。
  - 打印 status。
- 如果当前 service 正在运行：
  - 先停止旧 service。
  - 用新配置重建 `QQChatService` 依赖。
  - 再启动新 service。
  - 如果重启失败，应保持可读错误状态，不能抛出导致主 REPL 崩溃。

## 默认文件模板

项目级 `<project>/.xcode/config.json` 只保存非敏感字段：

```json
{
  "qqchat": {
    "enabled": true,
    "enable_c2c": true,
    "enable_group_at": true,
    "group_allowlist": [],
    "owner_openids": [],
    "tool_scope": {
      "visible_tools": ["read_file", "grep", "glob", "task_list"],
      "execution_allowlist": ["read_file", "grep", "glob", "task_list"],
      "remote_approval": false
    },
    "max_reply_chars": 1800,
    "group_turn_timeout_seconds": 240,
    "c2c_turn_timeout_seconds": 900
  }
}
```

用户级 `~/.xcode/qqchat.json` 可保存 secret，但模板只写占位符：

```json
{
  "app_id": "",
  "client_secret": ""
}
```

允许用户级文件也使用包裹形式，保持当前 loader 兼容：

```json
{
  "qqchat": {
    "app_id": "",
    "client_secret": ""
  }
}
```

第一版 init 推荐生成未包裹的简洁形式，减少用户编辑成本。

## 错误处理

- 项目级 config 已存在但不是合法 JSON：`/QQchat init` 不应覆盖，应提示用户手动修复。
- 项目级 config 根节点不是 object：不覆盖，提示错误。
- 用户级 `qqchat.json` 已存在但损坏：init 不覆盖，reload 报可读错误。
- 文件写入失败必须捕获并展示路径，不让 Agent 主循环崩溃。
- 输出路径和错误不得包含 `client_secret`、AccessToken 或 Authorization header。

## 实现建议

- 新增 `xcode_cli.qqchat.config_init` 或在 `xcode_cli.qqchat.config` 中增加小型 helper，避免把 JSON 文件创建逻辑堆进 `agent.py`。
- 建议接口：

```python
@dataclass(frozen=True)
class QQChatInitResult:
    project_config_path: Path
    user_config_path: Path
    created: tuple[Path, ...]
    updated: tuple[Path, ...]
    unchanged: tuple[Path, ...]
    errors: tuple[str, ...]

def init_qqchat_config(*, project_root: str | Path, user_config_path: str | Path | None = None) -> QQChatInitResult:
    ...
```

- `AgentRuntime._handle_qqchat_command()` 只负责命令分发和打印结果。
- `_create_qqchat_service()` 保持 service 构造单一入口，`reload` 复用它。
- `QQChatService.status()` 如已有 `state` 字段，可用它判断是否运行；若没有稳定 API，先补一个小的 `is_running` property 或 `state` 常量。

## 测试分层

本轮属于 P1 用户可见行为，secret 和热部署错误边界按 P0 检查。

必须补自动化测试：

- `init_qqchat_config()` 创建 `<project>/.xcode/config.json` 和 `~/.xcode/qqchat.json`。
- init 对已有配置幂等，不覆盖已有 `qqchat` 字段和 secret。
- init 能给已有项目 config 补齐缺失的 `qqchat` 字段。
- 损坏 JSON 不被覆盖，返回可读错误。
- `/QQchat init` 是 handled side-effect command，不进入 LLM。
- `/QQchat reload` 在 stopped 状态重建 service 但不自动 start。
- `/QQchat reload` 在 running 状态 stop 旧 service、创建新 service、start 新 service。
- 缺 secret 时 reload 给出可读错误，不影响普通 REPL。

必须补手工验收记录：

- PowerShell 中运行 `xcode chat`，依次输入 `/QQchat init`、`/QQchat status`、`/QQchat reload`。
- `cmd.exe` 中至少验证 `/QQchat init` 不破坏 prompt_toolkit 输入。

## 验收标准

- `python -m py_compile` 覆盖改动模块。
- 聚焦 pytest 通过。
- `git diff --check` 通过。
- 文档结论必须写在验证证据之后；未做真实 QQ 平台测试时，不得声称真实接入完成。
