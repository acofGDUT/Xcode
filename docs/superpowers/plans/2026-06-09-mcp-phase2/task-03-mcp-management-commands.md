# Task 3: `/mcp` 管理命令

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P1/P0。命令本身是 UX，但启停 server/tool 会改变模型可见工具集合，必须和 trust/config/permission 边界一致。

**Files:**
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `src/xcode_cli/core/commands/slash.py`
- Test: `tests/test_mcp_management_command.py`
- Modify: `tests/test_mcp_command.py`

## Goal

扩展 `/mcp` side-effect command，提供 server/tool 管理入口，不进入 LLM，不写项目配置。

## Commands

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

## Steps

- [x] **Step 1: 写失败测试**

覆盖：

- `/mcp tools` 展示 server/tool catalog。
- `/mcp disable <server>` 写本机 state，触发 reload/rebuild，不写 `.xcode/mcp.json`。
- `/mcp enable <server>` 不绕过 untrusted 状态；未 trust 时仍不启动。
- `/mcp tool disable` 后 tool 不再注册。
- `/mcp tool enable` 不能启用 config-blocked 或 invalid schema tool。
- `/mcp output-limit` 校验数字和 `default`。
- unknown server/tool 输出 usage 或可读错误，不崩。
- 输出关闭 Rich markup 解析。

- [x] **Step 2: 更新 slash command 列表和补全**

补全至少覆盖：

- `/mcp status`
- `/mcp tools`
- `/mcp enable `
- `/mcp disable `
- `/mcp tool enable `
- `/mcp tool disable `
- `/mcp refresh`
- `/mcp reconnect`
- `/mcp events`
- `/mcp output-limit `

- [x] **Step 3: 实现命令 handler**

建议拆小 helper：

```python
_handle_mcp_tools_command(parts)
_handle_mcp_enable_command(parts)
_handle_mcp_tool_command(parts)
_handle_mcp_refresh_command(parts)
_handle_mcp_reconnect_command(parts)
_handle_mcp_output_limit_command(parts)
```

不要让 `_handle_mcp_command()` 继续无限膨胀。

- [x] **Step 4: 接入 state store 和 registry rebuild**

命令写 state 后应调用统一的 MCP rebuild 方法：

```python
_rebuild_mcp_tool_registry()
```

server enable/disable 需要 reload 或 reconnect，具体策略在实现中保持可审查。

- [x] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_management_command.py tests/test_mcp_command.py tests/test_slash_dispatcher.py -q
```

Expected: PASS。

- [x] **Step 6: Codex review 检查点**

Review 重点：

- enable 是否没有绕过 trust。
- disable 是否从 ToolRegistry 和 schema 中移除工具。
- 命令是否写本机 state 而非项目 config。
- 输出是否不泄露 env values。

Review 记录（2026-06-10）：

- 实现文件：`src/xcode_cli/core/agent.py`、`src/xcode_cli/core/commands/slash.py`。
- 验证：`pytest tests\test_mcp_management_command.py tests\test_mcp_command.py tests\test_slash_dispatcher.py -q`：38 passed。
- 验证：`pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_tools.py tests\test_mcp_management_command.py tests\test_mcp_command.py tests\test_mcp_agent_integration.py -q`：58 passed。
- 验证：`python -m py_compile src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py`：通过。
- Review 结论：通过。`/mcp enable` 只写 local state，不写 trust；effective config 保证 local disable 阻止 server 启动且 local enable 不能覆盖 config `enabled=false`；tool disable 通过 `_rebuild_mcp_tool_registry()` 从 `ToolRegistry` 和 OpenAI schema 移除；命令写 `mcp_state.json`，不写项目 `.xcode/mcp.json`；tools/status 表格使用 `Text` cell，测试覆盖 Rich markup 不被解析且 env value 不输出。
- 说明：`/mcp refresh` 当前先做安全 registry rebuild；`/mcp reconnect` 当前走 reload，真实 tools/list refresh 与 lifecycle event 细化留给 Task 4/5。
