# QQ Chat Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `/QQchat start|stop|status`，让 Xcode 通过 QQ 机器人 API v2 的 WebSocket 接收单聊和群聊 @ 消息，并以安全的只读外部 user turn 被动回复 QQ。

**Architecture:** 新增 `xcode_cli.qqchat` 包承载 QQ 平台适配层，新增 headless `ExternalTurnRunner` 为每个 QQ conversation key 维护独立 session/history。`/QQchat` 是 side-effect slash command，只启动、停止和展示 QQ service 状态，不作为 prompt command；QQ turn 默认通过入口级 `ToolScope` 只暴露和执行只读工具，并且不允许远程 QQ 用户审批危险操作。

**Tech Stack:** Python 3.10+、pytest、现有 Typer/Rich/prompt_toolkit、标准库 `threading`/`queue`/`urllib`、新增同步 WebSocket 依赖 `websocket-client`。不引入 `asyncio`。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `pyproject.toml` | 修改 | 增加 `websocket-client>=1.8.0` |
| `src/xcode_cli/qqchat/__init__.py` | 新建 | QQ chat 包入口 |
| `src/xcode_cli/qqchat/config.py` | 新建 | QQChatConfig、项目级非敏感配置、用户级私密配置和环境变量合并 |
| `src/xcode_cli/qqchat/auth.py` | 新建 | AccessToken 获取、缓存、刷新和脱敏错误 |
| `src/xcode_cli/qqchat/message_client.py` | 新建 | C2C/group 被动回复 payload 与 HTTP transport |
| `src/xcode_cli/qqchat/events.py` | 新建 | Payload/event normalization、conversation key、reply target |
| `src/xcode_cli/qqchat/dedupe.py` | 新建 | `msg_id` 去重和 `msg_seq` 分配 |
| `src/xcode_cli/qqchat/gateway.py` | 新建 | WebSocket identify、heartbeat、resume、reconnect 状态机 |
| `src/xcode_cli/qqchat/service.py` | 新建 | QQChatService 生命周期、队列 worker、runner/reply 编排 |
| `src/xcode_cli/core/external_turn.py` | 新建 | Headless external turn runner，隔离 QQ session/history |
| `src/xcode_cli/core/commands/dispatcher.py` | 修改 | 注册 `/qqchat` side-effect handler |
| `src/xcode_cli/core/commands/slash.py` | 修改 | 增加 `/QQchat` help/completion |
| `src/xcode_cli/core/agent.py` | 修改 | 构造 QQChatService，接入 handler 和 ExternalTurnRunner |
| `src/xcode_cli/core/tooling/execution.py` | 修改 | 验证并补强入口级 `ToolScope` 执行层拒绝路径，防止 QQ turn 调用危险工具 |
| `tests/test_qqchat_config.py` | 新建 | 配置和 secret 脱敏测试 |
| `tests/test_qqchat_auth.py` | 新建 | token 缓存/刷新测试 |
| `tests/test_qqchat_events.py` | 新建 | C2C/group event normalization 测试 |
| `tests/test_qqchat_message_client.py` | 新建 | 发送 payload 和脱敏错误测试 |
| `tests/test_qqchat_gateway.py` | 新建 | identify/heartbeat/resume payload 测试 |
| `tests/test_qqchat_service.py` | 新建 | service 生命周期、去重和 reply 编排测试 |
| `tests/test_external_turn.py` | 新建 | session 隔离、`ToolScope`、metadata 测试 |
| `tests/test_slash_dispatcher.py` | 修改 | `/QQchat` 分发测试 |
| `docs/current/ARCHITECTURE.md` | 修改 | 实现后记录 QQ 外部入口数据流 |
| `docs/current/ROADMAP.md` | 修改 | 实现后更新 Phase 6 状态 |
| `docs/current/DEVNOTES.md` | 修改 | 记录 QQ 接入安全边界和 review 注意事项 |
| `docs/current/PROGRESS.md` | 修改 | 记录实现验收证据 |
| `docs/reference/qq-bot-integration-guide.md` | 修改 | 将目标教程更新为实际可用教程 |

## Task 文件

- [Task 1: 配置和鉴权](2026-06-05-qq-chat-integration/task-01-config-auth.md)
- [Task 2: 消息事件、去重和被动回复](2026-06-05-qq-chat-integration/task-02-events-messages.md)
- [Task 3: WebSocket Gateway Client](2026-06-05-qq-chat-integration/task-03-gateway-client.md)
- [Task 4: ExternalTurnRunner](2026-06-05-qq-chat-integration/task-04-external-turn-runner.md)
- [Task 5: QQChatService 和 `/QQchat`](2026-06-05-qq-chat-integration/task-05-service-slash-command.md)
- [Task 6: 权限、审计和 Windows 回归](2026-06-05-qq-chat-integration/task-06-security-audit-windows.md)
- [Task 7: 文档和最终验证](2026-06-05-qq-chat-integration/task-07-docs-final-verification.md)

## 执行约束

- 每个 task 单独执行；每完成一个 task 必须停下做 Codex review。
- 每个代码 task 必须先写失败测试，再写最小实现，再运行聚焦测试。
- 不引入 `asyncio`。
- 不使用会把主调用链拖入异步架构的 QQ SDK。
- 不实现 Webhook、主动推送、富媒体、频道消息、公域频道或 QQ 远程审批。
- 不允许 QQ turn 的 `ToolScope` 暴露 `write_file`、`edit_file`、`run_shell`、git 或安装依赖能力。
- QQchat 不复用 skill frontmatter 的 `allowed-tools`；skill `allowed-tools` 只保留为 skill metadata，QQ 外部入口必须使用 `ToolScope` / `entry_tool_scope`。
- 不把 QQ service 线程直接接入当前 REPL `_history`。
- AppSecret、AccessToken、完整 Authorization header 不得写入项目配置、session transcript、audit event、错误输出或测试快照。
- 真实 QQ 验收没有完成前，文档和总结不得声称 `/QQchat` 已完成真实接入。
