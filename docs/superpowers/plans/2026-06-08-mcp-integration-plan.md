# MCP Integration Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 安全接入 Phase 1 MCP stdio tools，让 trusted MCP servers 的工具可以注册到 Xcode `ToolRegistry`，同时保留 server trust、tool permission、输出截断、失败可恢复和可观测 `/mcp status`。

**Architecture:** 新增 `xcode_cli.mcp` 包作为 MCP 子系统，包含 config、trust、naming、schema、result、connection、tool adapter 和 status model。`MCPConnectionManager` 内部使用 async event loop/thread 管理 stdio client session；`AgentRuntime` Phase 1 仍保持同步外观，通过 sync wrapper 启动 trusted servers、注册 MCP tools、调用 MCP tool 和 shutdown。

**Tech Stack:** Python 3.10+、pytest、现有 Typer/Rich/prompt_toolkit、标准库 `asyncio`/`threading`/`hashlib`/`json`/`pathlib`、官方 MCP Python SDK（仅在 MCP 子系统内部使用）。Phase 1 不引入 HTTP/SSE/OAuth，不全局 async 化 AgentRuntime。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `pyproject.toml` | 修改 | 增加 MCP SDK 依赖 |
| `src/xcode_cli/mcp/__init__.py` | 新建 | MCP 包入口 |
| `src/xcode_cli/mcp/config.py` | 新建 | `.xcode/mcp.json` 读取、校验、变量展开、`max_mcp_output_chars` |
| `src/xcode_cli/mcp/trust.py` | 新建 | trust fingerprint 与 `~/.xcode/mcp_trust.json` |
| `src/xcode_cli/mcp/naming.py` | 新建 | `mcp__server__tool` sanitize 和冲突检测 |
| `src/xcode_cli/mcp/schema.py` | 新建 | MCP `inputSchema` 到 Xcode/OpenAI schema 的防御式转换 |
| `src/xcode_cli/mcp/result.py` | 新建 | MCP `tools/call` result 文本化与截断 |
| `src/xcode_cli/mcp/status.py` | 新建 | server/tool 状态模型，供 `/mcp status` 展示 |
| `src/xcode_cli/mcp/connection.py` | 新建 | 内部 async 的 stdio connection manager |
| `src/xcode_cli/mcp/tools.py` | 新建 | MCP tool adapter，生成 `ToolDef` |
| `src/xcode_cli/core/commands/dispatcher.py` | 修改 | 接入 `/mcp` side-effect handler |
| `src/xcode_cli/core/commands/slash.py` | 修改 | 增加 `/mcp` help/completion |
| `src/xcode_cli/core/agent.py` | 修改 | 初始化 MCP manager、注册 tools、shutdown、handler glue |
| `tests/test_mcp_config.py` | 新建 | config parsing、变量展开、非法配置 |
| `tests/test_mcp_trust.py` | 新建 | trust hash、hash 变化 untrusted、trust store path |
| `tests/test_mcp_naming_schema.py` | 新建 | 名称 sanitize、冲突、schema 防御转换 |
| `tests/test_mcp_result.py` | 新建 | result 文本化、二进制省略、截断 |
| `tests/test_mcp_connection.py` | 新建 | fake async connection lifecycle、failed/untrusted 状态 |
| `tests/test_mcp_tools.py` | 新建 | `ToolDef` 注册、默认非只读、call_tool 错误捕获 |
| `tests/test_mcp_command.py` | 新建 | `/mcp status|trust|untrust|reload` 行为 |
| `tests/test_mcp_agent_integration.py` | 新建 | AgentRuntime 初始化/shutdown 和 PermissionManager 集成 |
| `docs/current/ROADMAP.md` | 修改 | 增加 MCP Phase 5.1 设计状态 |
| `docs/current/DEVNOTES.md` | 修改 | 记录 MCP trust/async/权限边界 |
| `docs/current/PROGRESS.md` | 修改 | 记录本次 MCP 设计和计划文档 |
| `docs/current/ARCHITECTURE.md` | 修改 | 仅在实现完成后同步当前架构，不在本 plan 前置修改 |

## Task 文件

- [Task 1: MCP 配置与 trust store](2026-06-08-mcp-integration/task-01-config-trust.md)
- [Task 2: 命名、schema 和 result 适配](2026-06-08-mcp-integration/task-02-naming-schema-result.md)
- [Task 3: MCPConnectionManager 内部 async 生命周期](2026-06-08-mcp-integration/task-03-connection-manager.md)
- [Task 4: MCP ToolDef adapter 与 ToolRegistry 注册](2026-06-08-mcp-integration/task-04-tool-adapter-registry.md)
- [Task 5: `/mcp` slash command 和状态展示](2026-06-08-mcp-integration/task-05-mcp-command-status.md)
- [Task 6: AgentRuntime 集成、权限和 shutdown](2026-06-08-mcp-integration/task-06-agent-runtime-integration.md)
- [Task 7: 安全回归、Windows 验收和故障恢复](2026-06-08-mcp-integration/task-07-security-windows-verification.md)
- [Task 8: 文档和最终验证](2026-06-08-mcp-integration/task-08-docs-final-verification.md)

## 执行约束

- 每个 task 单独执行；每完成一个 task 必须停下做 Codex review。
- 代码 task 必须先写失败测试，再写最小实现，再运行聚焦测试。
- Phase 1 只做 stdio tools；不做 resources、prompts、HTTP、SSE、OAuth、`list_changed`。
- 未信任 server 不得启动进程；trust gate 必须先于 `npx`、Docker 或 Python subprocess。
- trust store 写入 `~/.xcode/mcp_trust.json`，不得写入项目仓库。
- MCP tool 默认 `is_read_only=False`；只有配置中显式 `read_only_tools` 才能改为 true。
- server trust 不等于 tool allow；MCP tool 调用必须继续走 `PermissionManager` 和审批 UI。
- MCP `inputSchema` 不兼容时跳过 tool 并记录 warning，不能打崩 Agent。
- MCP tool result 必须在进入 `_history` 前按 `max_mcp_output_chars` 截断。
- `MCPConnectionManager` 可以内部 async，但 `AgentRuntime` Phase 1 仍使用同步 wrapper。
- 某个 server 启动失败不能导致 Xcode 启动失败，只能进入 `/mcp status failed`。
- 不自动下载或安装 MCP server；如果用户配置 `npx -y`，只能在 trust prompt 中明确展示并提示风险。

## 推荐最终验证

```powershell
python -m py_compile src\xcode_cli\mcp\config.py src\xcode_cli\mcp\trust.py src\xcode_cli\mcp\naming.py src\xcode_cli\mcp\schema.py src\xcode_cli\mcp\result.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\dispatcher.py src\xcode_cli\core\commands\slash.py
pytest tests\test_mcp_config.py tests\test_mcp_trust.py tests\test_mcp_naming_schema.py tests\test_mcp_result.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_command.py tests\test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

手工验收必须记录：

- PowerShell/cmd.exe 中未信任 server 不启动。
- `/mcp trust <server>` 展示 command/args/cwd/env keys/hash 和 npx/dlx/docker 风险提示。
- trust 后 `/mcp reload` 能连接 fake 或本地已安装 stdio server。
- MCP tool 调用触发现有审批 UI。
- `/exit` 后 stdio server 子进程退出。
