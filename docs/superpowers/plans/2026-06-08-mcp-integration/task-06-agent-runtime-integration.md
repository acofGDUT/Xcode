# Task 6: AgentRuntime 集成、权限和 shutdown

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P0。集成点在 `AgentRuntime` 初始化、tool schema 暴露、PermissionManager、tool loop 和 `/exit` shutdown。

**Files:**
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `src/xcode_cli/core/tooling/execution.py`（如需增强 MCP 展示/metadata）
- Test: `tests/test_mcp_agent_integration.py`
- Test: `tests/test_agent_tool_loop.py`
- Test: `tests/test_task_permissions.py`

## Goal

把 MCP manager 接进 AgentRuntime：初始化时启动 trusted servers，注册 MCP tools；tool 调用走现有 PermissionManager；退出时关闭 MCP 子系统。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_agent_integration.py`**

覆盖：

- AgentRuntime 初始化时会创建 MCP manager，但 untrusted server 不启动。
- trusted server 的 tool 注册到 `runtime.tools`。
- MCP tool 默认 `is_read_only=False`，`PermissionManager.check(..., False)` 默认 ask。
- settings 中显式 deny MCP tool 时 execution 拒绝。
- `read_only_tools` 声明后 `is_read_only=True` 才默认 allow。
- runtime `finally` 调用 manager shutdown。
- MCP server failed 不影响 AgentRuntime 构造。

- [x] **Step 2: AgentRuntime 初始化接入**

建议顺序：

```text
resolve cwd
load config/trust
create MCPConnectionManager
start trusted servers
create ToolRegistry and register built-ins
register MCP ToolDefs
create ToolCallExecutor
create SlashCommandDispatcher with mcp handler
```

如果启动失败，保留 status，不抛到构造外。

- [x] **Step 3: LLM tool schema 暴露**

现有 `self.tools.get_openai_schemas(blocked_tools=...)` 会自然包含 MCP ToolDefs。确认 blocked-tools 和 future visible_tools 不被破坏。

- [x] **Step 4: PermissionManager 集成**

不新增 MCP 专用权限层。MCP tool 名称是完整工具名，例如 `mcp__filesystem__read_file`，现有 session/project/global settings 直接生效。

- [x] **Step 5: shutdown 集成**

在 `AgentRuntime.run_chat()` 的 `finally` 中先/后调用 MCP manager shutdown。shutdown 异常必须捕获并打印短 warning，不影响 runtime status delete。

- [x] **Step 6: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_agent_integration.py tests/test_agent_tool_loop.py tests/test_task_permissions.py -q
```

Expected: PASS。

