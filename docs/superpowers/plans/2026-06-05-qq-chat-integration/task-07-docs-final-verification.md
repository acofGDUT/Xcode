# Task 7: 文档和最终验证

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P0/P1/P2。最终验证必须覆盖代码编译、聚焦测试、全量测试、真实 PowerShell/cmd.exe 交互和 QQ 平台被动回复。没有真实 QQ 验收时不能声称完整完成。

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/reference/qq-bot-integration-guide.md`

## Goal

实现完成后同步权威文档，并用证据收口。该 task 是 merge/提交前闸门，不实现新功能。

## Step 1: 更新 ARCHITECTURE

在 `docs/current/ARCHITECTURE.md` 增加 QQ 外部入口章节，记录：

```text
QQChatService
  -> QQGatewayClient
  -> QQEventNormalizer
  -> QQMessageDedupe
  -> ExternalTurnRunner
  -> QQMessageClient
```

必须明确：

- `/QQchat` 是 side-effect command。
- QQ turn 不复用 REPL `_history`。
- 每个 conversation key 独立 session/history。
- 默认 `ToolScope.visible_tools` 和 `ToolScope.execution_allowlist` 是只读列表。
- QQchat 不复用 skill frontmatter 的 `allowed-tools`；skill `allowed-tools` 只作为 skill metadata 保留。
- WebSocket 后台线程只投递事件，不直接写终端 UI。

## Step 2: 更新 ROADMAP

将 Phase 6 QQ 接入状态从“已调研/待实现”更新为实际状态。

如果真实 QQ 单聊和群聊验收都通过，写：

```text
QQ `/QQchat` 第一版完成：支持 WebSocket、C2C_MESSAGE_CREATE、GROUP_AT_MESSAGE_CREATE、被动文本回复、只读工具白名单和审计。
QQ `/QQchat` 第一版完成：支持 WebSocket、C2C_MESSAGE_CREATE、GROUP_AT_MESSAGE_CREATE、被动文本回复、入口级只读 ToolScope 和审计。
```

如果只完成自动化测试但未跑真实 QQ，写：

```text
QQ `/QQchat` 代码已实现并通过自动化测试；真实 QQ 平台验收未执行，不能标记为完整完成。
```

## Step 3: 更新 PROGRESS

新增验收记录，包含：

- `python -m py_compile ...` 结果。
- 聚焦 `pytest` 结果。
- 全量 `pytest -q` 结果。
- `git diff --check` 结果。
- PowerShell/cmd.exe 手工验收记录。
- QQ 单聊被动回复结果。
- QQ 群聊 @ 被动回复结果。
- 危险工具请求结果。

必须把证据写在结论之前。

## Step 4: 更新 DEVNOTES

补充或更新 QQ 边界：

- 不引入 `asyncio`。
- 不允许 QQ 远程用户审批危险工具。
- 不保存 AppSecret、AccessToken、Authorization header。
- group 默认按 member 隔离。
- 被动回复受 `msg_id`、`msg_seq` 和时间窗口限制。
- 后续如果做 Webhook，需要单独设计签名校验、公网回调和端口限制。

## Step 5: 更新教程

把 `docs/reference/qq-bot-integration-guide.md` 从目标教程改为实际使用教程：

- 保留环境变量配置步骤。
- 增加 `/QQchat status/start/stop` 实际输出说明。
- 增加常见错误：
  - missing app id
  - missing client secret
  - gateway fetch failed
  - websocket disconnected
  - reply window expired
- 填写 Windows 手工验收记录；未执行时写“未执行”，不要写“通过”。

## Step 6: 编译检查

Run:

```powershell
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/external_turn.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/slash.py src/xcode_cli/qqchat/config.py src/xcode_cli/qqchat/auth.py src/xcode_cli/qqchat/message_client.py src/xcode_cli/qqchat/events.py src/xcode_cli/qqchat/dedupe.py src/xcode_cli/qqchat/gateway.py src/xcode_cli/qqchat/service.py
```

Expected: exit code 0。

## Step 7: 聚焦测试

Run:

```powershell
pytest tests/test_qqchat_config.py tests/test_qqchat_auth.py tests/test_qqchat_events.py tests/test_qqchat_message_client.py tests/test_qqchat_gateway.py tests/test_qqchat_service.py tests/test_external_turn.py tests/test_slash_dispatcher.py tests/test_agent_tool_loop.py -q
```

Expected: PASS。

## Step 8: 全量测试

Run:

```powershell
pytest -q
```

Expected: PASS。

## Step 9: diff 检查

Run:

```powershell
git diff --check
```

Expected: no whitespace errors。Windows LF/CRLF warning 不算失败。

## Step 10: PowerShell/cmd.exe 手工验收

在原生 PowerShell 或 cmd.exe 中运行：

```powershell
xcode chat
/QQchat status
/QQchat start
/QQchat status
/QQchat stop
```

记录：

- 是否能启动 REPL。
- `/QQchat status` 是否可读。
- 缺配置时是否提示明确错误。
- 有配置时是否完成 auth、gateway、identify。
- WebSocket 后台线程是否破坏 prompt_toolkit 输入。

## Step 11: 真实 QQ 平台验收

使用测试机器人：

1. 单聊机器人发送短消息。
2. 确认收到 Xcode 被动文本回复。
3. 群里 @ 机器人发送短消息。
4. 确认收到 Xcode 被动文本回复。
5. 发送“执行 shell”或“改文件”类请求。
6. 确认危险工具不可用，或只能由本机 owner 审批。

如果没有测试机器人或平台权限，本 step 标记为未执行，并在 PROGRESS 中写明缺口。

## Step 12: Review 检查点

Codex review 时重点检查：

- current docs 是否和真实实现一致。
- 是否有任何文档把未执行的真实 QQ 验收写成已通过。
- 是否保留官方平台限制和安全边界。
- 是否有足够 P0/P1 自动化测试。
- 是否有 PowerShell/cmd.exe 手工验收记录。

## Step 13: 提交建议

```powershell
git add docs/current/ARCHITECTURE.md docs/current/ROADMAP.md docs/current/PROGRESS.md docs/current/DEVNOTES.md docs/reference/qq-bot-integration-guide.md
git commit -m "docs: document qq chat integration"
```
