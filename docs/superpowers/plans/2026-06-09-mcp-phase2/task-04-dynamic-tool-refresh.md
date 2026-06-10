# Task 4: `tools/list_changed` 动态刷新

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P0。动态刷新会改变运行中模型可见工具集合；如果刷新和 ToolRegistry mutation 不在安全点执行，可能出现 schema 与执行路径不一致。

**Files:**
- Create: `src/xcode_cli/mcp/events.py`
- Modify: `src/xcode_cli/mcp/connection.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_mcp_dynamic_refresh.py`
- Modify: `tests/test_mcp_connection.py`
- Modify: `tests/test_mcp_agent_integration.py`

## Goal

支持 MCP server 的 tool list 动态变化。Phase 2 可以用真实 `notifications/tools/list_changed` 或 fake manager event 验证，但架构上必须保证 background MCP thread 不直接修改 `ToolRegistry`。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_dynamic_refresh.py`**

覆盖：

- manager 收到 list_changed 后只记录 pending refresh，不直接注册/删除工具。
- AgentRuntime safe point drain pending refresh 后调用 `tools/list`。
- 新增 tool 会注册并进入 schema。
- 删除 tool 会从 ToolRegistry 移除。
- refresh 失败时状态变为 failed 或保留旧工具，必须按实现策略有明确测试。
- 模型调用已删除 tool 时返回 unknown tool，不崩。
- refresh 期间 schema warning / name conflict 仍可见。

- [x] **Step 2: 实现 MCP event 模型**

建议：

```python
@dataclass(frozen=True)
class MCPEvent:
    ts: float
    server_name: str
    kind: Literal["list_changed", "refresh", "reconnect", "failed", "warning"]
    message: str
```

`MCPEventLog` 使用固定长度 ring buffer，默认 100 条。

- [x] **Step 3: 扩展 MCPConnectionManager**

建议接口：

```python
def pending_refresh_servers(self) -> set[str]: ...
def mark_tools_changed(self, server_name: str) -> None: ...
def refresh_tools_sync(self, server_name: str) -> None: ...
def drain_events(self) -> list[MCPEvent]: ...
```

如果 SDK 支持 notification handler，则注册 `notifications/tools/list_changed`；如果 SDK 暂不方便接入，先通过 fake session + manager hook 验证内部事件路径，并在 implementation notes 记录 SDK follow-up。

- [x] **Step 4: AgentRuntime safe point**

只在这些位置 drain MCP events 并 rebuild tools：

- 构建 LLM schema 前。
- `/mcp status` / `/mcp tools` 前。
- `/mcp refresh` / `/mcp reconnect` 后。

不要从 background event loop 直接改 `self.tools`。

- [x] **Step 5: 处理并发和失败策略**

明确实现选择：

- refresh 成功：更新 manager record tools，AgentRuntime 重建该 server ToolDefs。
- refresh 失败：记录 event；建议该 server 状态变 failed，并移除对应 ToolDefs，避免暴露不可调用工具。
- 正在执行 tool call 时收到 list_changed：延迟到下一 safe point。

- [x] **Step 6: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_dynamic_refresh.py tests/test_mcp_connection.py tests/test_mcp_agent_integration.py -q
```

Expected: PASS。

- [x] **Step 7: Codex review 检查点**

Review 重点：

- ToolRegistry 是否只在 AgentRuntime 主线程修改。
- list_changed 是否不会打断当前 tool call。
- refresh failure 是否不会留下不可调用旧工具。
- event 是否不包含 secret。

Review 记录（2026-06-10）：

- 实现文件：`src/xcode_cli/mcp/events.py`、`src/xcode_cli/mcp/connection.py`、`src/xcode_cli/core/agent.py`。
- 验证：`pytest tests\test_mcp_dynamic_refresh.py tests\test_mcp_connection.py tests\test_mcp_agent_integration.py -q`：23 passed。
- 验证：`pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_tools.py tests\test_mcp_management_command.py tests\test_mcp_command.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_connection.py tests\test_mcp_agent_integration.py -q`：73 passed。
- 验证：`python -m py_compile src\xcode_cli\mcp\events.py src\xcode_cli\mcp\connection.py src\xcode_cli\core\agent.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py`：通过。
- Review 结论：通过。`MCPConnectionManager.mark_tools_changed()` 只写 pending refresh + event，不触碰 `ToolRegistry`；pending/event 读写加锁；`AgentRuntime` 只在 status/tools、手动 refresh 和 LLM schema 构建前 drain pending 并重建 registry；refresh 成功更新 manager tool cache，失败标记 server failed、关闭 session、移除旧 tools，避免旧 schema 继续暴露；事件错误摘要对 env value/token/secret-like 文本脱敏。
- Review follow-up（2026-06-10）：真实 SDK notification handler 已接入。`SDKStdioSession.open()` 通过 `ClientSession(..., message_handler=...)` 监听 `notifications/tools/list_changed`，并桥接到 `MCPConnectionManager.mark_tools_changed(server.name)`；background MCP thread 仍只写 pending refresh + event，`ToolRegistry` mutation 仍只在 `AgentRuntime` safe point 发生。
