# Task 5: reconnect 与 lifecycle events

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P0/P1。reconnect 涉及关闭和重启外部 stdio 子进程；events 是可观测性，但不能泄露 secret。

**Files:**
- Modify: `src/xcode_cli/mcp/connection.py`
- Modify: `src/xcode_cli/mcp/events.py`
- Modify: `src/xcode_cli/mcp/status.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_mcp_connection.py`
- Test: `tests/test_mcp_management_command.py`

## Goal

增加显式 reconnect 和 lifecycle event 查看能力，让 failed server 可被用户恢复，同时让失败原因、refresh、shutdown、skip warning 可审计。

## Steps

- [x] **Step 1: 写失败测试**

覆盖：

- `/mcp reconnect <server>` 会关闭旧 session 并重新 connect。
- `/mcp reconnect` 会重连所有 trusted + enabled + state-enabled servers。
- untrusted server reconnect 后仍是 untrusted，不启动。
- reconnect failure 不打崩 AgentRuntime。
- reconnect failure 后对应 server tools 从 registry 移除。
- `/mcp events` 展示最近事件。
- events 不包含 env values。
- repeated shutdown/reconnect 不泄露 session。

- [x] **Step 2: 实现 manager reconnect API**

建议：

```python
def reconnect_sync(self, server_name: str | None = None) -> None: ...
```

规则：

- 先 close 旧 session。
- 再按 trust/config/state 重新启动。
- server 不存在或 disabled 给可读 event。

- [x] **Step 3: 扩展 status**

`MCPServerStatus` 可增加：

- `last_connected_at`
- `last_failed_at`
- `last_refreshed_at`
- `disabled_reason`
- `event_count`

不要让 status 必须依赖 wall-clock 精确断言，测试用存在性和 ordering 即可。

- [x] **Step 4: `/mcp events` 命令**

展示：

| 字段 | 含义 |
|------|------|
| time | 简短本地时间或相对时间 |
| server | server name |
| kind | refresh/reconnect/failed/warning |
| message | 脱敏摘要 |

- [x] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_connection.py tests/test_mcp_management_command.py -q
```

Expected: PASS。

- [x] **Step 6: Codex review 检查点**

Review 重点：

- reconnect 是否仍经过 trust gate。
- 旧 session 是否可靠关闭。
- failed reconnect 是否移除旧工具。
- events/status 是否不泄露 env values/token。

Review 记录（2026-06-10）：

- 实现文件：`src/xcode_cli/mcp/connection.py`、`src/xcode_cli/mcp/events.py`、`src/xcode_cli/mcp/status.py`、`src/xcode_cli/core/agent.py`。
- 验证：`pytest tests\test_mcp_connection.py tests\test_mcp_management_command.py -q`：30 passed。
- 验证：`pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_tools.py tests\test_mcp_management_command.py tests\test_mcp_command.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_connection.py tests\test_mcp_agent_integration.py -q`：80 passed。
- 验证：`python -m py_compile src\xcode_cli\mcp\events.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\status.py src\xcode_cli\core\agent.py`：通过。
- Review 结论：通过。`reconnect_sync()` 对每个 server 先关闭旧 session，再走 config enabled + local state effective config + trust gate；untrusted/disabled server 不启动；reconnect failure 标记 failed、移除旧 record/tools，runtime rebuild 后旧 schema 消失；重复 reconnect/shutdown 覆盖旧 session 关闭；`/mcp events [server]` 展示最近事件表格，测试覆盖 env value/token-like 文本不出现在 status/events。
