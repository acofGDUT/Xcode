# Task 1: MCP 本机 state store

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P0。state store 决定哪些 server/tool 会暴露给模型；错误默认值或路径错误可能绕过用户禁用意图，或把本机偏好写进项目仓库。

**Files:**
- Create: `src/xcode_cli/mcp/state.py`
- Test: `tests/test_mcp_state.py`
- Modify if needed: `src/xcode_cli/mcp/config.py`
- Modify if needed: `src/xcode_cli/core/agent.py`

## Goal

新增 project-scoped 本机 MCP state store，用于保存 server/tool enable-disable 和 per-tool output limit。state store 不替代 `.xcode/mcp.json`，不替代 trust store，也不能越过 config 硬边界。

## Steps

- [ ] **Step 1: 写失败测试 `tests/test_mcp_state.py`**

覆盖：

- 默认 state path 位于 `~/.xcode/projects/<project-key>/mcp_state.json` 或等价本机 project-scoped 路径。
- state store 不写 `<project>/.xcode/mcp.json`。
- 缺失 state 文件返回 empty state。
- 损坏 JSON 返回 empty state + warning，不打崩 AgentRuntime。
- `set_server_enabled()` / `set_tool_enabled()` 可保存并重新读取。
- `set_tool_output_limit()` 支持正整数和 `default` 清除。
- env values / secrets 不会写入 state。

- [ ] **Step 2: 实现 `state.py` 数据模型**

建议数据结构：

```python
@dataclass(frozen=True)
class MCPToolState:
    enabled: bool | None = None
    max_output_chars: int | None = None

@dataclass(frozen=True)
class MCPServerState:
    enabled: bool | None = None
    tools: dict[str, MCPToolState] = field(default_factory=dict)

@dataclass(frozen=True)
class MCPProjectState:
    servers: dict[str, MCPServerState] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
```

建议接口：

```python
class MCPStateStore:
    def __init__(self, project_key: str, path: Path | None = None) -> None: ...
    def load(self) -> MCPProjectState: ...
    def set_server_enabled(self, server_name: str, enabled: bool | None) -> None: ...
    def set_tool_enabled(self, server_name: str, tool_name: str, enabled: bool | None) -> None: ...
    def set_tool_output_limit(self, server_name: str, tool_name: str, value: int | None) -> None: ...
```

- [ ] **Step 3: 定义安全默认值**

规则：

- 缺失 state 不改变 Phase 1 行为。
- 损坏 state 不应导致默认信任或默认启用 config-disabled server。
- state 中 unknown server/tool 不报错，但在 `/mcp status --verbose` 或 task 后续 catalog 中可显示 warning。
- output limit 最大值建议 clamp 或拒绝超过 `200000`。

- [ ] **Step 4: AgentRuntime 初始化接入**

只初始化 store，不改变现有 MCP 注册行为。后续 Task 2 再把 state 应用于 tool registration。

- [ ] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_state.py -q
```

Expected: PASS。

- [ ] **Step 6: Codex review 检查点**

Review 重点：

- state store 是否完全不写项目目录。
- 损坏 state 是否不会放大权限。
- config disabled / blocklist 是否还没有被 state 覆盖。
- secret 是否不会进入 state 或 warning。
