# Task 8: 文档和最终验证

> Parent plan: [2026-06-09-mcp-phase2-plan.md](../2026-06-09-mcp-phase2-plan.md)
> Spec: [2026-06-09-mcp-phase2-design.md](../../specs/2026-06-09-mcp-phase2-design.md)

**Risk layer:** P1/P0。文档必须准确区分“设计完成”“自动化通过”“Windows 验收完成”，避免后续进入 HTTP/OAuth/resources 前误判 Phase 2 状态。

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/current/PROGRESS.md`
- Possibly modify: `README.md` compatibility entry if needed

## Goal

实现完成后同步当前文档，记录验证证据和未完成边界。仅 Phase 2 实现完成后才把 `ARCHITECTURE.md` 写成当前架构。

## Steps

- [x] **Step 1: 更新 `ARCHITECTURE.md`**

记录：

- `MCPStateStore`
- `MCPToolCatalog`
- dynamic refresh safe point
- `/mcp` 管理命令
- lifecycle events
- per-tool output limit

- [x] **Step 2: 更新 `ROADMAP.md`**

记录：

- MCP Phase 2 状态。
- 后续 Phase 候选：HTTP/Streamable HTTP、OAuth、resources/prompts、MCP Apps、tool search、enterprise policy。
- 明确 Phase 2 不等于完整生态扩展。

- [x] **Step 3: 更新 `DEVNOTES.md`**

记录边界：

- state store 不写项目目录。
- ToolRegistry mutation 只在 safe point。
- list_changed 不直接修改 schema。
- enable/reconnect 不绕过 trust。
- events/status 不泄露 secret。

- [x] **Step 4: 更新 `PROGRESS.md`**

记录：

- task-by-task 实现摘要。
- 自动化命令和通过数量。
- PowerShell/cmd.exe 手工验收记录。
- 若手工验收未完成，必须明确写“未完成”或“待补记录”。

- [x] **Step 5: 运行最终验证**

Run:

```powershell
python -m py_compile src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\events.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py
pytest tests/test_mcp_state.py tests/test_mcp_catalog.py tests/test_mcp_dynamic_refresh.py tests/test_mcp_management_command.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

- [x] **Step 6: Codex review 检查点**

Review 重点：

- 文档是否没有把未做的 HTTP/OAuth/resources/prompts 写成已实现。
- Windows 验收证据是否先于结论。
- ROADMAP 是否仍保持后续生态扩展逐项设计、逐项验收。
- Task 文件 checkbox 是否和真实状态一致。

执行记录（2026-06-10）：

- Step 1 通过：`docs/current/ARCHITECTURE.md` 已记录 `MCPStateStore`、`MCPToolCatalog`、dynamic refresh safe point、`/mcp` 管理命令、lifecycle events 和 per-tool output limit；并明确当前只支持 stdio tools，不支持 HTTP/SSE/OAuth/resources/prompts/MCP Apps。
- Step 2 通过：`docs/current/ROADMAP.md` 已记录 MCP Phase 2 为代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 验收通过；HTTP/Streamable HTTP、OAuth、resources/prompts、MCP Apps、tool search、enterprise policy 仍是后续候选。
- Step 3 通过：`docs/current/DEVNOTES.md` 已记录 state store 本机路径、ToolRegistry mutation safe point、list_changed 只置 pending、enable/reconnect 不绕过 trust、events/status 不泄露 secret 等边界。
- Step 4 通过：`docs/current/PROGRESS.md` 已记录 Task 1-8 实现摘要、自动化命令和通过数量，并补充 PowerShell/cmd.exe 原生 PTY 验收证据。
- Step 5 验证：
  - `python -m py_compile src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\events.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py`：通过。
  - `pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_management_command.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py -q`：77 passed。
  - `pytest -q`：504 passed。
  - `git diff --check`：退出码 0，仅有 Windows LF/CRLF 行尾提示。
- Step 6 review 结论：文档没有把 HTTP/OAuth/resources/prompts 写成已实现；Windows 验收结论有 PowerShell/cmd.exe 原生 PTY 证据支撑；ROADMAP 仍保留后续生态扩展逐项设计；Task 7 的 PowerShell/cmd.exe 验收 checkbox 已勾选，符合真实状态。
