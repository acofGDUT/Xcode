# Task 2: Tool catalog 与注册过滤

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P0。catalog 和 registration 决定模型实际看到哪些 MCP tools；disabled、invalid 或已消失的工具不能残留在 schema 中。

**Files:**
- Create: `src/xcode_cli/mcp/catalog.py`
- Modify: `src/xcode_cli/mcp/status.py`
- Modify: `src/xcode_cli/mcp/tools.py`
- Modify: `src/xcode_cli/core/tool_registry.py`
- Test: `tests/test_mcp_catalog.py`
- Modify: `tests/test_mcp_tools.py`

## Goal

把 MCP discovered tools、filtered tools 和 registered ToolDefs 分层建模。注册 MCP tools 时同时考虑 config allow/block、local state enable-disable、schema validity 和 name conflicts。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_catalog.py`**

覆盖：

- discovered tool 默认可注册。
- config `tool_blocklist` 中的 tool 状态为 `disabled_by_config`，不注册。
- config `tool_allowlist` 存在时，未列入 tool 状态为 `disabled_by_config`。
- local state disabled tool 状态为 `disabled_by_state`，不注册。
- local state 不能启用被 config block 的 tool。
- invalid schema 状态为 `invalid_schema`，不注册。
- name conflict 状态为 `name_conflict`，不覆盖内置工具或同 server 工具。
- registered tool 保留 original name、registered name、read_only、output limit。

- [x] **Step 2: 实现 catalog 数据结构**

建议：

```python
ToolCatalogState = Literal[
    "discovered",
    "registered",
    "disabled_by_config",
    "disabled_by_state",
    "invalid_schema",
    "name_conflict",
]

@dataclass(frozen=True)
class MCPCatalogTool:
    server_name: str
    original_name: str
    registered_name: str | None
    state: ToolCatalogState
    read_only: bool
    schema_warnings: tuple[str, ...] = ()
    output_limit: int | None = None
```

- [x] **Step 3: 修改 ToolDef adapter**

`create_mcp_tool_defs()` 应返回：

```python
tuple[list[ToolDef], list[str], list[MCPCatalogTool]]
```

或等价结构。AgentRuntime 后续可用 catalog 展示 `/mcp tools`。

- [x] **Step 4: 增加 ToolRegistry 公开移除接口**

避免继续使用 `self.tools._tools.pop(...)`：

```python
def unregister(self, name: str) -> None: ...
def unregister_prefix(self, prefix: str) -> list[str]: ...
```

- [x] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_catalog.py tests/test_mcp_tools.py -q
```

Expected: PASS。

- [x] **Step 6: Codex review 检查点**

Review 重点：

- disabled/invalid/conflicting tools 是否完全不进入 OpenAI schema。
- state 是否不能越过 config allow/block。
- ToolRegistry mutation 是否通过公开方法。
- read-only 仍只来自 `.xcode/mcp.json`，不是 local state。

Review 记录（2026-06-10）：

- 实现文件：`src/xcode_cli/mcp/catalog.py`、`src/xcode_cli/mcp/tools.py`、`src/xcode_cli/mcp/status.py`、`src/xcode_cli/core/tool_registry.py`、`src/xcode_cli/core/agent.py`。
- 验证：`pytest tests\test_mcp_catalog.py tests\test_mcp_tools.py -q`：18 passed。
- 验证：`pytest tests\test_mcp_agent_integration.py tests\test_mcp_command.py -q`：15 passed。
- 验证：`pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py tests\test_mcp_command.py -q`：44 passed。
- 验证：`python -m py_compile src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py src\xcode_cli\core\agent.py`：通过。
- Review 结论：通过。过滤优先级为 config 硬边界、local state、schema、name conflict、registered；disabled/invalid/conflicting tools 不进入 OpenAI schema；local state enabled 不能覆盖 config blocklist；`_remove_mcp_tools()` 已改用 `ToolRegistry.unregister_prefix()`；read-only 仍只来自 `.xcode/mcp.json`。
