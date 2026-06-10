# MCP Integration Phase 2 Design

> 状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 交互验收已完成。
> 日期：2026-06-09
> 风险层级：P0/P1。Phase 2 仍然处理外部 MCP server 暴露给模型的工具集合，涉及工具可见性、权限预期、动态 schema 更新、server 进程生命周期和真实 Windows 交互验收。

## 当前 MCP 阶段

Xcode 当前处在 **MCP Phase 1 已实现、Phase 2 可进入设计** 的状态。

Phase 1 已完成：

- `.xcode/mcp.json` 中的 stdio server 配置读取。
- trust gate 先于本地进程启动；trust store 写入 `~/.xcode/mcp_trust.json`。
- trusted server 的 `tools/list` 接入 `ToolRegistry`，工具命名为 `mcp__<server>__<tool>`。
- MCP tool 默认 `is_read_only=False`，继续走 `PermissionManager` 和审批 UI。
- schema 防御式转换、result 文本化、`max_mcp_output_chars` 截断。
- `/mcp status|trust|untrust|reload`。
- `MCPConnectionManager` 内部 async，`AgentRuntime` 同步 wrapper。
- 连接/初始化 timeout cancellation cleanup 已补回归。

Phase 1 当前证据：

- MCP 聚焦自动化矩阵：`57 passed`。
- 全量测试：`432 passed`。
- 原生 PowerShell/cmd.exe fake stdio server 验收：2026-06-10 用户确认通过。

因此 Phase 2 可以设计，但不能把 Phase 1 的“工具安全接入”直接扩大成完整生态扩展。

## 主流 Agent MCP 集成观察

Phase 2 参考主流客户端和 MCP 规范，但只选择和当前 Xcode 架构相匹配的下一步。

- MCP 官方 tools 规范要求客户端清楚展示暴露给模型的工具、在调用时给用户可见确认，并定义 `notifications/tools/list_changed` 让 server 动态通知 tool list 更新：[MCP Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。
- Claude Code 支持远程 HTTP、stdio、`list_changed` 动态刷新、OAuth scopes、resources、tool search 等能力；其中 `list_changed` 和 tool search 说明大规模 MCP 场景需要动态和按需管理，而不是把所有能力静态塞进上下文：[Claude Code MCP](https://code.claude.com/docs/en/mcp)。
- OpenAI Agents SDK 把 MCP 分成 hosted MCP、Streamable HTTP 和 stdio，并明确 SSE 已被 MCP 项目弃用，新集成优先 Streamable HTTP 或 stdio：[OpenAI Agents SDK MCP](https://openai.github.io/openai-agents-js/guides/mcp/)。
- VS Code 提供 MCP server 管理入口、启停、日志、清 cached tools、trust；server enable/disable 状态单独存储，不改共享 `mcp.json`：[VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers)。
- Cursor 在 MCP 体验上强调 tool toggle、默认审批、可展开查看参数和响应；disabled tools 不加载进上下文也不可被 Agent 使用：[Cursor MCP](https://docs.cursor.com/context/model-context-protocol)。
- Windsurf/Cascade 支持 stdio、Streamable HTTP、SSE、OAuth、工具级 toggle、总工具数上限和团队管控；这说明工具管理面和可见性预算是成熟 MCP 客户端的核心能力：[Cascade MCP](https://docs.devin.ai/desktop/cascade/mcp)。

结论：Xcode Phase 2 应优先补齐 **管理面、工具可见性控制、动态刷新和可观测性**。HTTP/OAuth/resources/prompts/MCP Apps 虽然是主流能力，但它们会引入新的传输、安全和 UI 表达面，应作为后续 Phase 单独设计。

## Phase 2 目标

Phase 2 的目标是把 Phase 1 的“trusted stdio tools 能安全注册”升级为“用户能稳定管理 MCP server 和工具集合，server 动态变化能安全刷新，Agent 暴露给模型的 MCP schema 可审计、可控、可恢复”。

具体目标：

- 增加本机 MCP state store，保存用户对 server/tool 的 enable/disable、per-tool 输出上限和最近工具目录，不写项目仓库。
- 增加 `/mcp` 管理命令：查看工具、启停 server、启停单个 tool、手动 refresh/reconnect、查看事件。
- 支持 `notifications/tools/list_changed` 或等价 manager event，安全刷新 connected server 的 tool list。
- 刷新后重新构建 MCP ToolDefs，删除已消失或被禁用的 MCP tools，避免旧 schema 继续暴露给模型。
- 增加 MCP lifecycle event ring buffer，让 `/mcp status --verbose` 和 `/mcp events` 可解释失败、刷新和跳过原因。
- 保持 Phase 1 的 trust、permission、schema/result 防御和 shutdown 约束。

## Phase 2 非目标

Phase 2 明确不做：

- HTTP / Streamable HTTP transport。
- SSE transport。
- OAuth / browser auth / token refresh。
- MCP resources、prompts、MCP Apps。
- MCP prompt 转 slash command。
- marketplace、registry、一键安装或自动下载 server。
- 企业集中 policy / organization whitelist。
- 子 Agent 独立 MCP scope。
- 模型主动 tool search / lazy schema loading。
- 全局 async 化 `AgentRuntime`、`LLMClient.complete()`、`ToolCallExecutor` 或 REPL。
- 自动执行 MCP hooks。

这些能力继续保留为后续候选，必须逐项写 spec、逐项验收。

## 用户状态模型

Phase 2 新增本机 state store：

```text
~/.xcode/projects/<project-key>/mcp_state.json
```

它不是项目共享配置，也不是 trust store。它只记录当前用户在当前项目中对 MCP 管理面的选择。

建议结构：

```json
{
  "version": 1,
  "servers": {
    "github": {
      "enabled": true,
      "tools": {
        "create_issue": {
          "enabled": false,
          "max_output_chars": 12000
        },
        "list_issues": {
          "enabled": true
        }
      }
    }
  }
}
```

约束：

- state store 路径使用现有 `SessionStore.project_key()` 规则，避免写入项目目录。
- 损坏 JSON、权限错误、未知字段必须可恢复；不能影响 REPL 启动。
- `.xcode/mcp.json` 仍是 server 配置来源；`enabled=false` 的 config 是硬禁用，本地 state 不能覆盖它。
- 本地 state 可以额外禁用 server 或 tool，但不能越过 config 中 `tool_allowlist` / `tool_blocklist`。
- trust 仍独立；启用 server 不等于 trust，也不等于允许 tool 调用。

## Tool Catalog 和注册规则

Phase 2 需要把“server 发现的工具”和“注册给模型的工具”分开建模。

建议新增 `MCPToolCatalog` 或扩展现有 status model：

```text
discovered tool
  -> config allow/block filter
  -> local state enable/disable filter
  -> schema conversion
  -> naming collision detection
  -> ToolRegistry registration
```

工具状态至少区分：

- `discovered`：server 当前 `tools/list` 返回。
- `registered`：已经进入 `ToolRegistry`，会暴露给模型。
- `disabled_by_config`：被 `tool_allowlist` / `tool_blocklist` 或 server `enabled=false` 排除。
- `disabled_by_state`：用户本地禁用。
- `invalid_schema`：schema 不兼容，被跳过。
- `name_conflict`：注册名冲突，被跳过。

`/mcp tools <server>` 应展示原始 tool name、注册名、enabled/registered/read-only、schema warning 和 output limit。

## `/mcp` 管理命令

Phase 2 仍保持 `/mcp` 为 side-effect command，不进入 LLM。

建议新增：

```text
/mcp status [--verbose]
/mcp tools [server]
/mcp enable <server>
/mcp disable <server>
/mcp tool enable <server> <tool>
/mcp tool disable <server> <tool>
/mcp refresh [server]
/mcp reconnect [server]
/mcp events [server]
/mcp output-limit <server> <tool> <chars|default>
```

行为约束：

- `enable <server>` 只改本机 state，不写 `.xcode/mcp.json`，不写 trust。
- `disable <server>` 应停止正在运行的 server，并从 `ToolRegistry` 移除该 server 的 MCP tools。
- `tool disable` 应从 ToolRegistry 移除对应 tool；后续 LLM schema 不能再看到它。
- `tool enable` 只对当前 server 已发现且未被 config block 的 tool 生效；不能启用 invalid schema 或 name conflict tool。
- `refresh` 对已连接 server 重新 `tools/list`，不重启进程。
- `reconnect` 关闭并重启 trusted + enabled server，适合 failed server 或配置外部状态改变。
- `events` 展示最近生命周期事件，不泄露 env values 或 secrets。
- 所有输出关闭 Rich markup 解析，避免 server name/tool name 注入。

## Dynamic Tool Refresh

MCP tools capability 可以声明 `listChanged`。Phase 2 应支持动态刷新，但不能让 background async thread 直接改 `ToolRegistry`。

推荐架构：

```text
MCPConnectionManager background loop
  -> receives notifications/tools/list_changed
  -> records pending refresh event for server

AgentRuntime safe point
  -> before building LLM tool schemas
  -> before /mcp status/tools
  -> after /mcp refresh/reconnect
  -> drains pending MCP events
  -> asks manager to refresh tools/list
  -> rebuilds MCP ToolDefs on main thread
```

原则：

- ToolRegistry mutation 只在 AgentRuntime 主线程发生。
- 正在执行 tool call 时不替换当前 tool；刷新延迟到 safe point。
- 如果刷新失败，保留上一次已注册工具或按 server 状态降级为 failed，需要在 spec implementation task 中明确选择并测试。
- 删除的 tool 必须从 schema 中消失；如果模型随后调用旧 tool，`ToolRegistry.execute()` 返回 unknown tool，不崩溃。
- `tools/list` pagination 如 SDK 暴露，应完整遍历；如果 Phase 2 实现暂不支持 pagination，必须记录 warning 并测试不崩。

## Reconnect 和生命周期事件

Phase 2 不做自动重连风暴。只做显式 reconnect 和有限失败恢复：

- `/mcp reconnect`：重连所有 trusted + enabled servers。
- `/mcp reconnect <server>`：只重连一个 server。
- failed server 不自动无限重试；可记录 `retry_after` 或 `last_failed_at`，但不后台轮询。
- reconnect 期间先关闭旧 session，再重新建立连接；失败时状态为 `failed`，旧 ToolDefs 应移除，避免暴露不可调用工具。
- shutdown、timeout、CancelledError、tools/list failure、schema skip、name conflict、state disabled 都写入 lifecycle event ring buffer。

事件不进入 LLM `_history`，只供用户和 review 使用。

## 输出上限

Phase 1 只有全局 `max_mcp_output_chars`。Phase 2 增加本机 per-tool override：

```text
/mcp output-limit <server> <tool> 50000
/mcp output-limit <server> <tool> default
```

规则：

- override 写入本机 state store，不写项目 config。
- 最终限制优先级：per-tool state override > global `.xcode/mcp.json` `max_mcp_output_chars` > default 20000。
- 非正整数、过大值应拒绝或 clamp；建议最大 200000。
- 截断仍必须发生在 ToolOutput 进入 `_history` 前。

## 权限和安全边界

Phase 2 不降低 Phase 1 权限：

- server trust、server enabled、tool enabled、tool permission 是四个独立层。
- 禁用 tool/server 只是减少暴露面，不代表允许其他 tool。
- `read_only_tools` 仍只能来自 `.xcode/mcp.json`，本机 state 不应把任意 tool 标为 read-only。
- explicit `deny` 仍高于 read-only auto allow。
- state store 损坏不能导致默认全启危险工具；安全 fallback 应是忽略损坏 state，然后回到 config + trust + permission 模型，并显示 warning。
- lifecycle events、status、tests 不能打印 env values、Authorization header 或 token。

## 测试策略

风险分层：

- P0：state store 安全、disabled tool 不进入 schema、dynamic refresh 不污染 ToolRegistry、reconnect/shutdown 不泄露进程、permission 不被绕过。
- P1：`/mcp` 管理命令、status/tools/events 输出、output-limit override。
- P2：文案、表格展示、简单 docs。

必须自动化覆盖：

- state store 不写项目目录，损坏 JSON 不崩。
- config disabled server 不能被 state enable。
- state disabled server 不启动。
- state disabled tool 不注册、不进 LLM schema。
- tool enable 不能越过 config blocklist。
- `/mcp tools` 能展示 discovered/registered/disabled/invalid 状态。
- `notifications/tools/list_changed` 或 fake manager event 会在 safe point 触发 refresh。
- refresh 后删除的 tool 从 `ToolRegistry` 消失。
- refresh 新增的 tool 注册并遵守 permission 默认 ask。
- reconnect failed 不导致 AgentRuntime 崩溃，旧工具不会继续暴露。
- per-tool output limit 在 ToolOutput 进入 history 前生效。
- event log 不包含 env values。

手工验收：

- 原生 PowerShell/cmd.exe 中启停 server 和 tool，确认补全/状态/审批 UI 不混乱。
- fake stdio server 触发 list_changed 或通过 `/mcp refresh` 模拟工具变化，确认 status/tools 和 LLM schema 变化一致。
- `/mcp reconnect` 后旧子进程退出，新 server connected。
- 禁用 tool 后模型无法再调用该 tool；再次启用后恢复审批流程。

## 主要风险

- **状态污染**：background notification 直接修改 registry，导致 LLM schema 和执行路径不同步。缓解：只在 AgentRuntime safe point mutation。
- **误启危险 server**：enable 命令绕过 trust 或 config disabled。缓解：enable 只改 local state，trust gate 仍先于启动。
- **旧工具残留**：refresh 后 ToolRegistry 仍保留已删除工具。缓解：server-scoped unregister + regression test。
- **工具过多**：MCP server 暴露大量 tools，影响上下文和模型选择。缓解：Phase 2 先提供 tool-level disable 和 tools listing；model tool search 留到后续。
- **日志泄密**：events/status 打印 env values。缓解：只记录 env keys、server/tool name、error summary。
- **Windows TTY 风险**：新命令输出和审批 UI 交错。缓解：Phase 2 管理命令先用普通表格，不做全屏 TUI。

## 后续 Phase 候选

- Phase 3：Streamable HTTP transport + static headers，仍不做 OAuth。
- Phase 4：OAuth / auth refresh / dynamic headers。
- Phase 5：MCP resources/prompts 和 `@server:uri` 引用。
- Phase 6：MCP Apps / UI rendering。
- Phase 7：model-driven MCP tool search / lazy schema exposure。
- Phase 8：enterprise policy / registry / marketplace。
