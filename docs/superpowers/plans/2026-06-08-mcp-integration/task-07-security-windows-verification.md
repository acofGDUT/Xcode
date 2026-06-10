# Task 7: 安全回归、Windows 验收和故障恢复

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P0。MCP 是本地进程 + 外部工具来源，必须用安全路径回归和原生 Windows 手工验收兜底。

**Files:**
- Modify/Create: `tests/test_mcp_*.py`
- Modify: `docs/current/PROGRESS.md`（实现完成后记录验收结果）

## Goal

补齐 Phase 1 MCP 安全验收矩阵，确保失败恢复、权限、输出截断和 Windows 子进程生命周期可信。

## Steps

- [x] **Step 1: 补安全矩阵测试**

确认测试覆盖：

- 未信任 server 不启动。
- hash 变化重新 untrusted。
- trust prompt 前不执行 `npx -y`。
- tool 默认非只读。
- explicit deny 覆盖 read-only 声明。
- schema invalid skip。
- call_tool error 捕获。
- output truncation。
- failed server 不影响 AgentRuntime。
- shutdown 可重复调用。
- 启动/初始化超时取消时等待 coroutine cleanup；`SDKStdioSession.open()` 在 `initialize()` cancellation 路径关闭已进入的 async context。

- [x] **Step 2: 补 fake stdio server 测试工具**

在测试内使用 fake MCP server 或 fake connection，不依赖真实网络/registry。若需要真实 subprocess，只使用本仓库内测试脚本，避免 `npx` 下载。

- [x] **Step 3: 运行 MCP 聚焦测试**

Run:

```powershell
pytest tests/test_mcp_config.py tests/test_mcp_trust.py tests/test_mcp_naming_schema.py tests/test_mcp_result.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_command.py tests/test_mcp_agent_integration.py -q
```

Expected: PASS。

- [ ] **Step 4: 原生 PowerShell 手工验收**

状态：用户反馈已基本完成，待补具体命令、现象和结果记录后勾选。

记录：

- 配置一个 fake local stdio server。
- 启动 Xcode，`/mcp status` 显示 untrusted。
- 确认 fake server 进程没有启动。
- `/mcp trust <server>` 显示 command/args/cwd/env keys/hash。
- `/mcp reload` 后 connected。
- 调用 `mcp__server__tool` 出现审批 UI。
- `/exit` 后 fake server 进程退出。

- [ ] **Step 5: 原生 cmd.exe 手工验收**

状态：用户反馈已基本完成，待补具体命令、现象和结果记录后勾选。

同 PowerShell，重点看路径、中文、审批菜单和进程退出。

- [x] **Step 6: Review 检查点**

未完成原生 Windows 验收时，文档和总结不得声称 MCP Phase 1 真实终端验收完成。
