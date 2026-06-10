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

- [ ] **Step 1: 自动化安全矩阵**

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

- [ ] **Step 2: fake stdio server 增强**

如有需要，扩展 `examples/fake_mcp_server.py` 支持：

- 切换 tool list。
- 返回长输出。
- 记录 start/stop/reconnect。
- 可触发或模拟 list_changed。

不得依赖 `npx` 或真实网络。

- [ ] **Step 3: 跑聚焦和全量测试**

Run:

```powershell
pytest tests/test_mcp_state.py tests/test_mcp_catalog.py tests/test_mcp_dynamic_refresh.py tests/test_mcp_management_command.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

Expected: PASS。

- [ ] **Step 4: 原生 PowerShell 手工验收**

记录：

- `/mcp enable|disable <server>` 不改 `.xcode/mcp.json`。
- `/mcp tool disable` 后 tool 从 `/mcp tools` registered 状态消失。
- `/mcp refresh` 或 list_changed 模拟能更新工具集合。
- `/mcp reconnect` 后旧 fake server 进程退出，新连接成功。
- 禁用再启用 tool 后仍触发现有审批 UI。
- `/mcp events` 不显示 secret。

- [ ] **Step 5: 原生 cmd.exe 手工验收**

同 PowerShell，重点看：

- 中文/宽字符输出。
- 普通表格与 prompt_toolkit 共存。
- 审批菜单不被 `/mcp` 输出污染。
- `/exit` 后子进程退出。

- [ ] **Step 6: Codex review 检查点**

未完成原生 Windows 记录时，文档和总结不得声称 Phase 2 真实终端验收完成。
