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

- [ ] **Step 1: 写失败测试 `tests/test_mcp_dynamic_refresh.py`**

覆盖：

- manager 收到 list_changed 后只记录 pending refresh，不直接注册/删除工具。
- AgentRuntime safe point drain pending refresh 后调用 `tools/list`。
- 新增 tool 会注册并进入 schema。
- 删除 tool 会从 ToolRegistry 移除。
- refresh 失败时状态变为 failed 或保留旧工具，必须按实现策略有明确测试。
- 模型调用已删除 tool 时返回 unknown tool，不崩。
- refresh 期间 schema warning / name conflict 仍可见。

- [ ] **Step 2: 实现 MCP event 模型**

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

- [ ] **Step 3: 扩展 MCPConnectionManager**

建议接口：

```python
def pending_refresh_servers(self) -> set[str]: ...
def mark_tools_changed(self, server_name: str) -> None: ...
def refresh_tools_sync(self, server_name: str) -> None: ...
def drain_events(self) -> list[MCPEvent]: ...
```

如果 SDK 支持 notification handler，则注册 `notifications/tools/list_changed`；如果 SDK 暂不方便接入，先通过 fake session + manager hook 验证内部事件路径，并在 implementation notes 记录 SDK follow-up。

- [ ] **Step 4: AgentRuntime safe point**

只在这些位置 drain MCP events 并 rebuild tools：

- 构建 LLM schema 前。
- `/mcp status` / `/mcp tools` 前。
- `/mcp refresh` / `/mcp reconnect` 后。

不要从 background event loop 直接改 `self.tools`。

- [ ] **Step 5: 处理并发和失败策略**

明确实现选择：

- refresh 成功：更新 manager record tools，AgentRuntime 重建该 server ToolDefs。
- refresh 失败：记录 event；建议该 server 状态变 failed，并移除对应 ToolDefs，避免暴露不可调用工具。
- 正在执行 tool call 时收到 list_changed：延迟到下一 safe point。

- [ ] **Step 6: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_dynamic_refresh.py tests/test_mcp_connection.py tests/test_mcp_agent_integration.py -q
```

Expected: PASS。

- [ ] **Step 7: Codex review 检查点**

Review 重点：

- ToolRegistry 是否只在 AgentRuntime 主线程修改。
- list_changed 是否不会打断当前 tool call。
- refresh failure 是否不会留下不可调用旧工具。
- event 是否不包含 secret。
