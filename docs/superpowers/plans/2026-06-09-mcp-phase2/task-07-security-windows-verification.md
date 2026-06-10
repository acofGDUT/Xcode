# Task 7: 安全回归与 Windows 验收

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P0。Phase 2 会动态改变工具集合并启停本地子进程，必须补安全矩阵和原生 Windows 交互验收。

**Files:**
- Modify/Create: `tests/test_mcp_*.py`
- Modify: `examples/fake_mcp_server.py` if needed
- Modify: `docs/current/PROGRESS.md` after implementation

## Goal

补齐 Phase 2 安全回归矩阵和真实终端验收，确认 enable/disable、refresh、reconnect、events 和 output limit 不破坏 Phase 1 安全边界。

## Steps

- [x] **Step 1: 自动化安全矩阵**

确认覆盖：

- state disabled server 不启动。
- state disabled tool 不注册、不进 schema。
- config disabled/blocklist 不能被 state enable 覆盖。
- untrusted server 不能被 enable/reconnect 启动。
- list_changed refresh 不由 background thread 直接改 ToolRegistry。
- refresh 删除 tool 后旧 tool 不再进入 schema。
- reconnect failure 移除旧工具或按已定义策略处理。
- per-tool output limit 截断发生在进入 history 前。
- events/status 不泄露 env values。
- explicit deny 仍阻止 enabled MCP tool。

- [x] **Step 2: fake stdio server 增强**

如有需要，扩展 `examples/fake_mcp_server.py` 支持：

- 切换 tool list。
- 返回长输出。
- 记录 start/stop/reconnect。
- 可触发或模拟 list_changed。

不得依赖 `npx` 或真实网络。

- [x] **Step 3: 跑聚焦和全量测试**

Run:

```powershell
pytest tests/test_mcp_state.py tests/test_mcp_catalog.py tests/test_mcp_dynamic_refresh.py tests/test_mcp_management_command.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

Expected: PASS。

- [x] **Step 4: 原生 PowerShell 手工验收**

记录：

- `/mcp enable|disable <server>` 不改 `.xcode/mcp.json`。
- `/mcp tool disable` 后 tool 从 `/mcp tools` registered 状态消失。
- `/mcp refresh` 或 list_changed 模拟能更新工具集合。
- `/mcp reconnect` 后旧 fake server 进程退出，新连接成功。
- 禁用再启用 tool 后仍触发现有审批 UI。
- `/mcp events` 不显示 secret。

- [x] **Step 5: 原生 cmd.exe 手工验收**

同 PowerShell，重点看：

- 中文/宽字符输出。
- 普通表格与 prompt_toolkit 共存。
- 审批菜单不被 `/mcp` 输出污染。
- `/exit` 后子进程退出。

- [x] **Step 6: Codex review 检查点**

原生 Windows 记录必须先于文档和总结结论；不能把未覆盖的 HTTP/OAuth/resources/prompts 误写成 Phase 2 已实现能力。

执行记录（2026-06-10）：

- Step 1 自动化安全矩阵已覆盖：state disabled server effective config 不启动、state disabled tool 不进 schema、config disabled/blocklist 不能被 state enable 覆盖、untrusted reconnect 不启动、list_changed 只置 pending 且 safe point 刷新、删除 tool 后旧 schema 消失、reconnect failure 移除旧 tools、per-tool output limit 在 `ToolOutput` 前截断、events/status 脱敏、explicit deny 阻止 enabled MCP tool。
- Step 2 未修改 `examples/fake_mcp_server.py`。现有 fake server 已支持长输出；动态 tool list、list_changed、reconnect/failure 使用 fake session/manager 自动化覆盖，未引入 `npx` 或网络依赖。
- Step 3 验证：PowerShell `pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_management_command.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py -q`：77 passed。
- Step 3 验证：`pytest -q`：504 passed。
- Step 3 验证：`git diff --check`：退出码 0，仅 Windows LF/CRLF 行尾提示。
- 额外 shell 验证：`cmd /c pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_management_command.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py -q`：77 passed。
- Step 4 原生 PowerShell 验收：使用 `winpty.PtyProcess` 分配 PowerShell 原生控制台缓冲区，临时项目设置 `XCODE_PROJECT_ROOT`，临时 home 放置 `rg.exe`，运行 `python -m xcode_cli.main` 并输入 `/mcp status`、`/mcp trust fake`、`/mcp tools fake`、`/mcp tool disable|enable fake echo`、`/mcp output-limit fake long_output 123`、`/mcp refresh fake`、`/mcp reconnect fake`、`/mcp events fake`、`/mcp disable|enable fake`、`/exit`。结果：`config_hash_unchanged=True`、`process_exitstatus=0`、`secret_absent_from_transcript=True`、`connected_seen=True`、`tool_disable_seen=True`、`tool_enable_seen=True`、`output_limit_seen=True`、`refresh_extra_seen=True`、`reconnect_seen=True`、`events_seen=True`、`exit_seen=True`；fake server log 显示 `start=3`、`stop=3`，reconnect 旧进程退出后新进程启动。
- Step 4 审批 UI 验收：在 PowerShell PTY 中直接调用 `ToolApprovalController.prompt("mcp__fake__echo", "mcp__fake__echo")`，真实菜单渲染 `Apply mcp__fake__echo for mcp__fake__echo?`，输入 `y` 后 `approval_result=yes`。
- Step 5 原生 cmd.exe 验收：使用 `winpty.PtyProcess` 分配 cmd.exe 原生控制台缓冲区，运行同一临时项目和同一组 `/mcp` 命令。结果：`config_hash_unchanged=True`、`process_exitstatus=0`、`secret_absent_from_transcript=True`、`connected_seen=True`、`tool_disable_seen=True`、`tool_enable_seen=True`、`output_limit_seen=True`、`refresh_extra_seen=True`、`reconnect_seen=True`、`events_seen=True`、`exit_seen=True`；fake server log 显示 `start=3`、`stop=3`。
- Step 5 审批 UI 验收：在 cmd.exe PTY 中直接调用 `ToolApprovalController.prompt("mcp__fake__echo", "mcp__fake__echo")`，真实菜单渲染并输入 `y` 后 `approval_result=yes`。
- Review 结论：通过。自动化安全矩阵、PowerShell 原生 PTY、cmd.exe 原生 PTY 和 MCP 工具名审批 UI 冒烟均通过；文档仍必须保留 Phase 2 只覆盖 stdio tools 管理面，不包含 HTTP/OAuth/resources/prompts/MCP Apps。
