# Task 4: MCP ToolDef adapter 与 ToolRegistry 注册

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P0。该 task 把外部 MCP tools 暴露给模型；默认权限、schema 过滤、名称冲突和结果截断必须正确。

**Files:**
- Create: `src/xcode_cli/mcp/tools.py`
- Modify: `src/xcode_cli/core/tool_registry.py`（仅在需要增强 register 冲突行为时）
- Test: `tests/test_mcp_tools.py`

## Goal

把 connected MCP tools 转成 Xcode `ToolDef`，注册到 `ToolRegistry`。MCP tool 默认非只读，执行时通过 connection manager 调用 `tools/call`。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_tools.py`**

覆盖：

- `tools/list` 中 `read_file` 注册为 `mcp__filesystem__read_file`。
- 默认 `ToolDef.is_read_only is False`。
- server config `read_only_tools=["read_file"]` 时才为 true。
- allowlist/blocklist 按 MCP tool 原名过滤。
- schema invalid 的 tool 被 skip + warning。
- connection manager `call_tool_sync()` 返回 error 时 `ToolRegistry.execute()` 得到 `Tool error: ...`，主循环不崩。
- 超长 result 经 `max_mcp_output_chars` 截断。

- [x] **Step 2: 实现 `tools.py`**

建议接口：

```python
def create_mcp_tool_defs(
    *,
    connection_manager: MCPConnectionManager,
    config: MCPConfig,
) -> tuple[list[ToolDef], list[str]]:
    ...
```

每个 `ToolDef.execute` 捕获 server/tool 名，调用：

```python
raw_result = connection_manager.call_tool_sync(server_name, original_tool_name, kwargs)
return ToolOutput(content=render_mcp_tool_result(raw_result, max_chars=config.max_mcp_output_chars))
```

- [x] **Step 3: 注册冲突策略**

如果 `ToolRegistry.register()` 当前会静默覆盖，MCP adapter 层必须先检查 `registry.list_names()` 或由 AgentRuntime 过滤，避免覆盖内置工具。Phase 1 不允许 MCP 覆盖内置工具。

- [x] **Step 4: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_tools.py -q
```

Expected: PASS。

