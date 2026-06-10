# MCP Integration Phase 1 Design

> 状态：Phase 1 已实现并通过自动化回归；真实 Windows 手工验收待补具体记录。
> 日期：2026-06-08
> 风险层级：P0。MCP 会把本地外部进程贡献的工具暴露给模型，涉及本地命令启动、权限、工具执行、输出进入 `_history`、Windows 进程生命周期和主循环稳定性。

## 背景

Xcode 当前已经有稳定的 `ToolDef` / `ToolRegistry`、`PermissionManager`、`ToolCallExecutor`、slash command dispatcher、session transcript 和工具异常兜底。QQchat 第一版还新增了外部入口 `ToolScope`，证明 Xcode 可以在 schema 层和 execution 层同时限制某类入口能看到和能执行哪些工具。

MCP 与 QQchat 不同：QQchat 是不可信远程用户入口，默认只读；MCP 是本机 owner 主动配置的外部 tool provider，但 stdio server 本质上仍是本地命令，例如 `npx -y ...`、`python server.py` 或 `docker run ...`。因此 Phase 1 的重点不是功能炫，而是把外部 provider 安全、可审计、可失败恢复地转成 Xcode 的 ToolRegistry 工具来源。

用户已确认：允许设计 MCP 接入，并允许 `MCPConnectionManager` 内部使用 `async`；`AgentRuntime` 后续可以逐步 async 化。本设计采用“内部 async、外部同步外观”的过渡形态，避免一次性把 REPL、LLM loop 和工具执行全部改成 async。

## 外部资料依据

- MCP 官方 transport 文档说明 stdio 是 client 启动的本地子进程，通过标准流传输 newline-delimited JSON-RPC，MCP 消息要求 UTF-8 编码：[Transports](https://modelcontextprotocol.io/specification/draft/basic/transports)。
- MCP 官方 tools 文档定义了 `tools/list`、`tools/call`、`inputSchema` 和 tool result，并强调 tool 调用应有人类可拒绝的交互模型：[Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。
- OpenAI Agents SDK 的 Python 文档把 stdio MCP server 作为本地 subprocess 管理，context manager 退出时关闭进程，并提供 server manager 的 connected/failed 子集管理：[OpenAI Agents SDK MCP](https://openai.github.io/openai-agents-python/mcp/)。
- Claude Agent SDK / Claude Code MCP 文档使用 `mcp__<server>__<tool>` 命名模式，强调 MCP tools 需要显式 permission；stdio 用于命令形式的本地 server：[Claude MCP](https://code.claude.com/docs/en/agent-sdk/mcp)。
- Claude Code 安全文档明确新 MCP servers 需要 trust verification，并提醒用户只配置可信 MCP server：[Claude Code Security](https://code.claude.com/docs/en/security)。
- VS Code MCP 文档在安装 Playwright MCP server 时要求用户确认 trust 后才启动，并提示 local MCP server 可运行任意本机代码：[VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers)。
- Windsurf/Cascade MCP 文档体现主流 Agent 会提供 MCP server 配置、工具启用/禁用和管理入口；但 Xcode Phase 1 不做 marketplace 或 registry：[Cascade MCP](https://docs.devin.ai/desktop/cascade/mcp)。

## Phase 1 范围

Phase 1 只支持：

- 项目级配置文件：`<project>/.xcode/mcp.json`。
- stdio server：`command`、`args`、`cwd`、`env`。
- server trust gate：未信任或配置 hash 变化时，不启动 server。
- tools capability：连接 trusted server 后调用 `tools/list`，把工具注册成 `mcp__<server>__<tool>`。
- `tools/call`：模型调用 MCP 工具时，经 Xcode 的 PermissionManager 和审批 UI 后，由 MCP client 调用远端 tool。
- `/mcp status|trust|untrust|reload`：查看状态、信任/撤销信任、重新加载配置。
- output truncation：MCP tool result 超过 `max_mcp_output_chars` 必须截断。
- failed server 不影响主 Agent 启动。
- `MCPConnectionManager` 内部使用 async event loop/thread，向当前同步 `AgentRuntime` 暴露同步方法。

Phase 1 明确不做：

- resources、prompts、roots、sampling、elicitation、MCP Apps。
- HTTP、SSE、OAuth。
- `notifications/tools/list_changed` 动态热更新。
- MCP prompt 转 slash command。
- tool search / lazy tool schema loading。
- marketplace、registry、自动安装 server。
- 自动执行 hooks 或把 MCP server 变成 skill。
- 子 Agent 独立 MCP server scope。
- 全局 async 化 `AgentRuntime`、`LLMClient.complete()` 或 `_run_llm_loop()`。

## 用户可见配置

项目级配置使用 `.xcode/mcp.json`，只描述“这个项目建议连接哪些 MCP server”。它不是 trust store。

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "${workspace}"],
      "cwd": "${workspace}",
      "env": {
        "EXAMPLE_TOKEN": "${EXAMPLE_TOKEN}"
      },
      "enabled": true,
      "tool_allowlist": [],
      "tool_blocklist": [],
      "read_only_tools": []
    }
  },
  "max_mcp_output_chars": 20000
}
```

字段说明：

| 字段 | 语义 |
|------|------|
| `mcpServers` | server name 到 server config 的映射。 |
| `type` | Phase 1 只接受 `stdio`；缺失时默认 `stdio`。 |
| `command` | 要启动的本地命令。必须是非空字符串。 |
| `args` | 参数列表。必须是字符串数组。 |
| `cwd` | server 工作目录。支持 `${workspace}`；缺失时为项目根。 |
| `env` | server 环境变量。支持 `${VAR}` 从当前环境读取；trust prompt 只显示 key，不显示值。 |
| `enabled` | false 时不启动、不注册工具。 |
| `tool_allowlist` | 可选，server 内 tool 原名 allowlist；Phase 1 用于 schema 注册过滤。 |
| `tool_blocklist` | 可选，server 内 tool 原名 blocklist；allowlist 后再移除。 |
| `read_only_tools` | 可选，声明某些 MCP tool 可作为 read-only；默认所有 MCP tool 都 `is_read_only=False`。 |
| `max_mcp_output_chars` | 进入 `_history` 前的 MCP 输出字符上限；缺失默认 20000。 |

## Trust 模型

MCP trust 是用户本机状态，不能写进项目仓库。trust store 放在：

```text
~/.xcode/mcp_trust.json
```

trust record 绑定 server 的配置指纹：

```text
project_key + server_name + type + command + args + resolved cwd + sorted env keys -> sha256
```

只把 env key 纳入 hash，不把 env value 纳入 hash，原因是 env value 可能是 secret。代价是 env value 改变不会触发重新信任；文档和 `/mcp status` 需要明确这一点。

trust gate 必须先于进程启动：

```text
load .xcode/mcp.json
  -> validate config
  -> compute fingerprint
  -> trust store match?
       yes: allow startup
       no: mark untrusted, do not spawn process
```

第一次发现 server、配置 hash 改变、trust record 缺失、server 被 `untrust` 后，状态都应为 `untrusted`。未信任 server 不会启动，因此不会触发 `npx -y`、Docker、Python 脚本或其他潜在下载/执行行为。

`/mcp trust <server>` 必须展示：

- server name。
- command。
- args。
- resolved cwd。
- env keys。
- config fingerprint。
- 如果 command/args 看起来包含 `npx -y`、`npm exec`、`pnpm dlx`、`uvx`、`docker run` 等，需要提示“此命令可能下载或执行外部代码，请确认来源可信”。

用户确认后才写 trust store，并启动该 server 或提示下次 `/mcp reload`/重启后生效。实现可以选择 trust 后立即启动，但启动失败只能进入 `failed`，不能打断 REPL。

## 权限模型

MCP 有两层独立权限：

```text
server trust：是否允许启动本地 MCP server 进程
tool permission：是否允许调用 mcp__server__tool
```

信任 server 不等于允许所有 tool 调用。MCP tool 注册成 `ToolDef` 时默认：

```python
is_read_only = False
```

因此现有 `PermissionManager` 默认会对未知工具返回 `ask`。用户仍可在 session/project/global settings 中显式 `allow`、`ask`、`deny`：

```json
{
  "permissions": {
    "mcp__filesystem__read_file": "allow",
    "mcp__github__create_issue": "ask",
    "mcp__danger__shell": "deny"
  }
}
```

如果项目 `.xcode/mcp.json` 对某个 server 声明 `read_only_tools`，仅这些工具可注册为 `is_read_only=True`。MCP server 自带 annotations（例如 `readOnlyHint`）只能作为 warning 或 metadata，Phase 1 不把它当作真实权限依据；客户端必须把 server annotations 视为不可信。

## 工具命名与冲突

MCP 工具名转成：

```text
mcp__<server>__<tool>
```

server 和 tool 名都要 sanitize：

- 只允许 `[a-zA-Z0-9_]`。
- 非法字符转 `_`。
- 多个 `_` 可折叠为一个。
- 空名报错。
- 不能与内置工具重名。
- sanitized 后若同一 server 内 tool 冲突，Phase 1 跳过冲突 tool 并在 `/mcp status` warning 中显示；不要静默覆盖。
- sanitized server name 冲突时，整个 server config 进入 `failed_config`，不启动。

## Schema 适配

MCP `inputSchema` 是 JSON Schema，但不一定与 OpenAI-compatible tool schema 完全兼容。Phase 1 采用防御式最小兼容：

- `inputSchema` 必须是 dict。
- `type` 缺失时可补为 `"object"`。
- `properties` 缺失时补 `{}`。
- `required` 必须是字符串数组，否则清空并 warning。
- 不支持或无法序列化的 schema 跳过该 tool。
- 不因为一个 tool schema 错误导致 server 断开或 Agent 启动失败。
- 原始 schema 可以保存在 metadata 里供 `/mcp status --verbose` 后续展示，但不要塞进模型不可用 schema。

## Tool result 转换与截断

MCP `tools/call` result 可能包含 text、image、resource、structuredContent 等内容。Phase 1 转成单一文本结果：

- text content：拼接文本。
- structuredContent：JSON 序列化后追加。
- image/audio/resource：Phase 1 不注入二进制内容，只写占位摘要，例如 `[mcp image omitted: image/png]`。
- `isError=true` 或 server 返回 tool error：转成模型可见 `Tool error: ...` 字符串。
- 所有结果进入 `_history` 前按 `max_mcp_output_chars` 截断，并追加截断提示：

```text

[MCP output truncated: 54821 -> 20000 chars]
```

截断是 P0 验收项，不能只在 UI 层摘要。

## 进程生命周期

Phase 1 lifecycle：

```text
AgentRuntime 初始化
  -> 创建 MCPConnectionManager
  -> 加载配置和 trust store
  -> trusted + enabled server 启动
  -> tools/list 注册工具

/mcp reload
  -> 停止当前 MCP servers
  -> 重新加载配置与 trust
  -> trusted + enabled server 再启动

/exit 或 AgentRuntime finally
  -> shutdown MCPConnectionManager
  -> 关闭连接和子进程
```

连接失败、启动失败、`tools/list` 失败、schema 转换失败都不能让 `AgentRuntime` 初始化失败。失败 server 状态为 `failed`，记录 `error_summary`。

Phase 1 不做复杂自动重连。后续可以在 Phase 2 增加 `/mcp reconnect` 或 failed-only reconnect。

## 内部 async 边界

`MCPConnectionManager` 可以内部使用 async event loop 和 background thread：

```text
sync AgentRuntime
  -> MCPConnectionManager.start_trusted_servers()
       -> run_coroutine_threadsafe(...)
          -> async MCP client session
  -> ToolDef.execute(...)
       -> MCPConnectionManager.call_tool_sync(...)
          -> run_coroutine_threadsafe(...)
```

设计原则：

- async 只在 MCP subsystem 内部。
- `AgentRuntime._run_llm_loop()`、`ToolCallExecutor.execute()`、`LLMClient.complete()` Phase 1 不改 async。
- 所有 sync wrapper 都必须有 timeout。
- shutdown 必须能从同步 `finally` 调用。
- async 任务异常必须转成 server/tool 状态，不向外泄漏打断主循环。

这为后续逐步 async 化留下入口：先让 `MCPConnectionManager` async，再考虑 LLM streaming、tool execution、external turn 和 REPL orchestration 的 async 边界。

## `/mcp` 命令

Phase 1 `/mcp` 是 side-effect slash command，不进入 LLM。

```text
/mcp
/mcp status
/mcp trust <server>
/mcp untrust <server>
/mcp reload
```

`/mcp status` 至少显示：

| 字段 | 示例 |
|------|------|
| server | `filesystem` |
| status | `connected` / `failed` / `untrusted` / `disabled` |
| tool count | `4` |
| config hash | `sha256:...` 短 hash |
| error summary | `tools/list timed out` |
| warnings | `skipped 1 invalid schema` |

`/mcp trust <server>` 用于显式信任当前配置 hash。`/mcp untrust <server>` 删除对应 trust record，并停止已运行 server。`/mcp reload` 重新加载配置、trust 和工具注册。

## 文件结构

建议新增：

```text
src/xcode_cli/mcp/
  __init__.py
  config.py
  trust.py
  naming.py
  schema.py
  result.py
  connection.py
  tools.py
  status.py

tests/
  test_mcp_config.py
  test_mcp_trust.py
  test_mcp_naming_schema.py
  test_mcp_connection.py
  test_mcp_tools.py
  test_mcp_command.py
  test_mcp_agent_integration.py
```

建议修改：

```text
pyproject.toml
src/xcode_cli/core/agent.py
src/xcode_cli/core/tool_registry.py
src/xcode_cli/core/tooling/execution.py
src/xcode_cli/core/commands/dispatcher.py
src/xcode_cli/core/commands/slash.py
docs/current/ROADMAP.md
docs/current/DEVNOTES.md
docs/current/PROGRESS.md
```

`ARCHITECTURE.md` 只描述当前已实现系统。MCP 代码未实现前，不把 MCP 当作当前架构写入 `ARCHITECTURE.md`；实现完成后的最后 task 再同步。

## 验收标准

自动化最少覆盖：

- 未信任 server 不启动。
- 配置 hash 变化后重新变成 untrusted。
- trust store 写在 `~/.xcode/mcp_trust.json`，不写项目文件。
- `tools/list` 注册 `mcp__server__tool`。
- MCP tool 默认 `is_read_only=False`，需要审批。
- 显式 `deny` 拒绝 MCP tool。
- `read_only_tools` 中声明的工具才可自动 read-only allow。
- `tools/call` 错误被捕获，主 loop 不崩。
- 超长 output 被截断后再进入 tool message。
- invalid schema 被 warning + skip，不打崩 server 或 Agent。
- server 启动失败仅 `/mcp status failed`。
- `/mcp status` 显示 connected/failed/untrusted/disabled、tool count、error summary。
- schema 层和执行层都能禁用/拒绝不允许的 MCP 工具。
- `/exit` 或 runtime shutdown 调用 MCP manager shutdown。
- `MCPConnectionManager` 内部 async wrapper timeout 不会无限卡住同步 tool call。

手工验收：

- 原生 PowerShell 中配置一个假的 stdio MCP server，首次 `/mcp status` 显示 untrusted，不启动。
- `/mcp trust <server>` 显示 command/args/cwd/env keys 和 npx/dlx/docker 风险提示。
- trust 后 `/mcp reload` 能连接并注册工具。
- 调用 MCP tool 时仍出现 Xcode 现有审批 UI。
- `/exit` 后 server 子进程退出。

## 主要风险

- **后门风险**：`.xcode/mcp.json` 可以被仓库作者写入恶意命令。缓解：trust gate 先于启动，trust 绑定配置 hash。
- **权限误解**：信任 server 被误当成允许所有 tool。缓解：默认 `is_read_only=False`，走 PermissionManager。
- **schema 崩溃**：MCP server 返回复杂/不兼容 JSON Schema。缓解：跳过问题 tool，status warning。
- **输出污染**：MCP result 太大或包含二进制/资源。缓解：文本化 + 截断。
- **async 侵入**：MCP SDK async 传染主 loop。缓解：connection manager 内部 async，外部 sync wrapper。
- **进程泄漏**：stdio server 未关闭。缓解：runtime finally shutdown，测试 fake subprocess lifecycle。
- **供应链下载**：`npx -y` / `uvx` / Docker 可能下载执行代码。缓解：trust prompt 明确展示并警告，文档建议优先使用已安装命令。

## 后续 Phase 2 候选

- HTTP / Streamable HTTP。
- OAuth。
- tools/list_changed。
- tool search / 按需 schema 暴露。
- server-level tool enable/disable TUI。
- per-subagent MCP scope。
- MCP resources/prompts。
- MCP Apps。
- managed MCP policy / organization whitelist。
- 逐步 async 化 `AgentRuntime`。
