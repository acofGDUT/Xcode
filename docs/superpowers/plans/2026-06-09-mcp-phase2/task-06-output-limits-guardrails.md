# Task 6: per-tool output limit 与暴露面 guardrails

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P1/P0。输出上限影响 `_history` 污染风险；工具数量 guardrails 影响模型上下文和工具选择可靠性。

**Files:**
- Modify: `src/xcode_cli/mcp/state.py`
- Modify: `src/xcode_cli/mcp/tools.py`
- Modify: `src/xcode_cli/mcp/catalog.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_mcp_state.py`
- Test: `tests/test_mcp_tools.py`
- Test: `tests/test_mcp_management_command.py`

## Goal

支持 per-tool output limit override，并为 MCP tool 暴露面提供最小 guardrails：可见工具数过多时 warning，用户可通过 `/mcp tools` 和 tool disable 收敛。

## Steps

- [x] **Step 1: 写失败测试**

覆盖：

- per-tool output limit 优先于 `.xcode/mcp.json` 全局 `max_mcp_output_chars`。
- `default` 会清除 override。
- 非正整数、非数字、超过上限会被拒绝或 clamp，并有可读消息。
- 截断仍发生在 ToolOutput 返回前。
- `/mcp tools` 显示当前 output limit 来源。
- enabled MCP tools 超过阈值时 status warning 可见。

- [x] **Step 2: 实现 output limit 优先级**

优先级：

```text
tool state max_output_chars > MCPConfig.max_mcp_output_chars > DEFAULT_MAX_MCP_OUTPUT_CHARS
```

建议最大值：`200000`。超过时拒绝比静默 clamp 更可审计。

- [x] **Step 3: Adapter 使用 per-tool limit**

`_make_execute()` 需要拿到最终 max chars，而不是只使用 config 全局值。

- [x] **Step 4: 暴露面 warning**

建议默认 warning 阈值：`100` enabled MCP tools。Phase 2 只 warning，不自动禁用、不做 model tool search。

warning 出现在：

- `/mcp status --verbose`
- `/mcp tools`
- `_mcp_tool_warnings`

- [x] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_state.py tests/test_mcp_tools.py tests/test_mcp_management_command.py -q
```

Expected: PASS。

- [x] **Step 6: Codex review 检查点**

Review 重点：

- output limit 是否在进入 `_history` 前生效。
- override 是否只写本机 state。
- 大量 tools warning 是否不会自动放宽权限或隐藏工具。
- 这一步是否没有实现 model-driven tool search。

Review 记录（2026-06-10）：

- 实现文件：`src/xcode_cli/mcp/catalog.py`、`src/xcode_cli/mcp/tools.py`、`src/xcode_cli/core/agent.py`。
- 验证：`pytest tests\test_mcp_state.py tests\test_mcp_tools.py tests\test_mcp_management_command.py -q`：39 passed。
- 验证：`pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_tools.py tests\test_mcp_management_command.py tests\test_mcp_command.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_connection.py tests\test_mcp_agent_integration.py -q`：84 passed。
- 验证：`python -m py_compile src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\agent.py`：通过。
- Review 结论：通过。最终上限优先级为 tool state `max_output_chars` > `MCPConfig.max_mcp_output_chars`；adapter 把最终上限传给 `_make_execute()`，在 `render_mcp_tool_result()` 生成 `ToolOutput` 前截断；`/mcp output-limit` 仍只写本机 state；`/mcp tools` 显示 `value (state|config)`；enabled MCP tools 超过 100 只写 warning，不自动禁用、不隐藏工具、不实现 model-driven tool search。
