# Task 3: MCPConnectionManager 内部 async 生命周期

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P0。连接管理会启动本地 stdio 子进程；失败、超时、shutdown 和 async 异常都必须可恢复，不能污染主 Agent。

**Files:**
- Create: `src/xcode_cli/mcp/status.py`
- Create: `src/xcode_cli/mcp/connection.py`
- Test: `tests/test_mcp_connection.py`

## Goal

实现内部 async 的 MCP stdio connection manager，向同步 `AgentRuntime` 暴露同步方法。只启动 trusted + enabled servers。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_connection.py`**

使用 fake async client/session，不启动真实 MCP server。覆盖：

- untrusted server 不调用 spawn/connect。
- trusted server 启动成功后状态为 connected。
- 启动失败后状态为 failed，错误摘要可见。
- `tools/list` 失败后 server failed，不影响其他 server。
- `shutdown()` 关闭已连接 server。
- `call_tool_sync()` 对 async timeout 返回可读 `Tool error:`。

- [x] **Step 2: 实现 `status.py`**

建议模型：

```python
@dataclass
class MCPToolStatus:
    original_name: str
    registered_name: str
    read_only: bool

@dataclass
class MCPServerStatus:
    name: str
    status: Literal["connected", "failed", "untrusted", "disabled"]
    fingerprint: str
    tool_count: int = 0
    error_summary: str = ""
    warnings: list[str] = field(default_factory=list)
```

- [x] **Step 3: 实现 `connection.py` 内部 event loop**

建议结构：

```python
class MCPConnectionManager:
    def __init__(..., timeout_seconds: float = 15.0) -> None: ...
    def start_trusted_servers(self) -> None: ...
    def list_connected_tools(self) -> list[MCPDiscoveredTool]: ...
    def call_tool_sync(self, server_name: str, tool_name: str, arguments: dict) -> object: ...
    def shutdown(self) -> None: ...
    def statuses(self) -> list[MCPServerStatus]: ...
```

内部使用 `asyncio.new_event_loop()` + background thread，所有 public sync 方法通过 `asyncio.run_coroutine_threadsafe()` 调用并带 timeout。

- [x] **Step 4: 接入官方 MCP SDK**

stdio client session 建议由 connection manager 内部创建。SDK import 只出现在 `xcode_cli.mcp` 包内，避免 async 依赖扩散到 `core/agent.py`。

- [x] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_connection.py -q
```

Expected: PASS。

- [x] **Step 6: Review 检查点**

Codex review 重点：

- async 异常是否都落到 status/error summary。
- shutdown 是否可重复调用。
- 未信任 server 是否完全不启动。
- public sync wrapper 是否都有 timeout。

