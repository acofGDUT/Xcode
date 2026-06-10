# MCP Integration Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Phase 1 stdio tools 安全接入基础上，补齐 MCP 管理面与动态工具刷新：本机 state store、server/tool enable-disable、`tools/list_changed` 安全刷新、reconnect/events 可观测性和 per-tool output limit。

**Architecture:** 保持 `xcode_cli.mcp` 为 MCP 子系统。新增本机 `MCPStateStore` 和 tool catalog/status 层；`MCPConnectionManager` 负责连接、refresh、pending event 和 reconnect，但不直接改 `ToolRegistry`。`AgentRuntime` 在 safe point drain MCP events 并重建 MCP ToolDefs。`/mcp` command 继续是 side-effect command，不进入 LLM。

**Tech Stack:** Python 3.10+、pytest、现有 Typer/Rich/prompt_toolkit、标准库 `asyncio`/`threading`/`json`/`pathlib`。沿用官方 MCP Python SDK；Phase 2 不新增 HTTP/OAuth 依赖，不全局 async 化 AgentRuntime。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/xcode_cli/mcp/state.py` | 新建 | 本机 project-scoped MCP state store |
| `src/xcode_cli/mcp/catalog.py` | 新建 | discovered/registered/disabled/invalid tool catalog |
| `src/xcode_cli/mcp/events.py` | 新建 | lifecycle event ring buffer 和 pending refresh event |
| `src/xcode_cli/mcp/status.py` | 修改 | 扩展 server/tool 状态字段 |
| `src/xcode_cli/mcp/connection.py` | 修改 | refresh、reconnect、list_changed notification 接入 |
| `src/xcode_cli/mcp/tools.py` | 修改 | 根据 config + state + catalog 生成 ToolDef |
| `src/xcode_cli/core/tool_registry.py` | 修改 | 增加公开 unregister/remove helpers，避免直接操作 `_tools` |
| `src/xcode_cli/core/agent.py` | 修改 | 初始化 state store、drain events、重建 MCP tools、扩展 `/mcp` handler |
| `src/xcode_cli/core/commands/slash.py` | 修改 | `/mcp` 子命令补全 |
| `tests/test_mcp_state.py` | 新建 | state store 安全和覆盖规则 |
| `tests/test_mcp_catalog.py` | 新建 | tool catalog、filter、状态分类 |
| `tests/test_mcp_dynamic_refresh.py` | 新建 | list_changed/pending refresh 和 registry rebuild |
| `tests/test_mcp_management_command.py` | 新建 | enable/disable/tools/reconnect/events/output-limit 命令 |
| `tests/test_mcp_agent_integration.py` | 修改 | AgentRuntime safe point、权限和 schema 集成 |
| `tests/test_mcp_connection.py` | 修改 | refresh/reconnect/list_changed manager 行为 |
| `docs/current/ARCHITECTURE.md` | 修改 | 实现完成后同步 Phase 2 当前架构 |
| `docs/current/ROADMAP.md` | 修改 | 记录 Phase 2 设计状态和后续 Phase 候选 |
| `docs/current/DEVNOTES.md` | 修改 | 记录 MCP state、dynamic refresh 和 safe point 边界 |
| `docs/current/PROGRESS.md` | 修改 | 记录设计、实现过程和验证证据 |

## Task 文件

- [Task 1: MCP 本机 state store](2026-06-09-mcp-phase2/task-01-mcp-state-store.md)
- [Task 2: Tool catalog 与注册过滤](2026-06-09-mcp-phase2/task-02-tool-catalog-registration.md)
- [Task 3: `/mcp` 管理命令](2026-06-09-mcp-phase2/task-03-mcp-management-commands.md)
- [Task 4: `tools/list_changed` 动态刷新](2026-06-09-mcp-phase2/task-04-dynamic-tool-refresh.md)
- [Task 5: reconnect 与 lifecycle events](2026-06-09-mcp-phase2/task-05-reconnect-events.md)
- [Task 6: per-tool output limit 与暴露面 guardrails](2026-06-09-mcp-phase2/task-06-output-limits-guardrails.md)
- [Task 7: 安全回归与 Windows 验收](2026-06-09-mcp-phase2/task-07-security-windows-verification.md)
- [Task 8: 文档和最终验证](2026-06-09-mcp-phase2/task-08-docs-final-verification.md)

## 执行约束

- 每个 task 单独执行；每完成一个 task 必须停下做 Codex review。
- 代码 task 必须先写失败测试，再写最小实现，再运行聚焦测试。
- Phase 2 只做 stdio tools 的管理面和动态刷新；不做 HTTP、SSE、OAuth、resources、prompts、MCP Apps、marketplace、registry。
- 本机 state store 必须写入 `~/.xcode/projects/<project-key>/mcp_state.json` 或等价本机 project-scoped 路径，不得写入项目仓库。
- `.xcode/mcp.json` 的 `enabled=false`、`tool_allowlist`、`tool_blocklist` 是硬边界；本机 state 不能越权启用。
- server trust 仍先于启动；enable/reconnect 不得绕过 trust gate。
- ToolRegistry mutation 只能在 AgentRuntime safe point 发生，不能从 MCP background thread 直接修改。
- disabled/removed/invalid/conflicting tools 不得进入 LLM tool schema。
- explicit `deny` 仍优先于 read-only 和 enabled state。
- lifecycle events/status 不得泄露 env values、Authorization header、token 或完整 secret。
- 新增管理命令先用普通表格/文本，不做全屏 TUI，降低 Windows prompt_toolkit 风险。

## 推荐最终验证

```powershell
python -m py_compile src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\events.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py
pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_management_command.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

手工验收必须记录：

- PowerShell/cmd.exe 中 `/mcp enable|disable <server>` 会启停 server，且不改 `.xcode/mcp.json`。
- `/mcp tool disable` 后对应 tool 不再出现在 `/mcp tools` registered 状态和 LLM schema。
- fake stdio server 工具列表变化后，`/mcp refresh` 或 list_changed event 能刷新工具集合。
- `/mcp reconnect` 后旧子进程退出，新连接状态正确。
- `/mcp events` 不显示 secret。
- 禁用再启用 MCP tool 后仍走现有审批 UI。
