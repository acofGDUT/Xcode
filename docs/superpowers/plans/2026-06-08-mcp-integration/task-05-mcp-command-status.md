# Task 5: `/mcp` slash command 和状态展示

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P1/P0。`/mcp status` 是可观测性入口；`/mcp trust` 是 P0 trust gate 的用户确认路径。

**Files:**
- Modify: `src/xcode_cli/core/commands/slash.py`
- Modify: `src/xcode_cli/core/commands/dispatcher.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_mcp_command.py`
- Test: `tests/test_slash_dispatcher.py`

## Goal

实现 `/mcp status|trust|untrust|reload` side-effect command，不进入 LLM。状态展示必须让用户知道哪些 server connected/failed/untrusted/disabled。

## Steps

- [x] **Step 1: 写失败测试**

覆盖：

- `/mcp` 和 `/mcp status` 调用 mcp handler。
- `/mcp trust filesystem` 调用 trust flow。
- `/mcp untrust filesystem` 删除 trust 并停止 server。
- `/mcp reload` 重新加载配置并重建工具注册。
- unknown subcommand 给出 usage。
- `/mcp trust` 不带 server 时给出 usage。

- [x] **Step 2: 更新 slash command 列表和补全**

在 `COMMANDS` 增加：

```python
"/mcp": "Manage MCP servers (status/trust/untrust/reload)"
```

补全：

```text
/mcp status
/mcp trust 
/mcp untrust 
/mcp reload
```

- [x] **Step 3: 更新 dispatcher**

`SlashCommandDispatcher` 增加 `mcp_handler`，`/mcp` 作为 side-effect command。

- [x] **Step 4: 实现 AgentRuntime mcp handler glue**

`_handle_mcp_command(parts)`：

- 无参数或 `status`：渲染 table。
- `trust <server>`：显示 command/args/cwd/env keys/hash 和风险提示，调用审批/确认后 trust。
- `untrust <server>`：删除 trust，停止 server。
- `reload`：shutdown 当前 MCP manager，重新加载配置/trust，启动 trusted server 并注册工具。

确认交互可复用现有 approval 控制器，也可以先用简单 `input()`/TTY fallback，但必须能在非 TTY 测试中注入确认函数。

- [x] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_command.py tests/test_slash_dispatcher.py -q
```

Expected: PASS。

