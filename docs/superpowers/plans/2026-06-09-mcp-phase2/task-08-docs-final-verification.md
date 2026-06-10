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

- [ ] **Step 1: 更新 `ARCHITECTURE.md`**

记录：

- `MCPStateStore`
- `MCPToolCatalog`
- dynamic refresh safe point
- `/mcp` 管理命令
- lifecycle events
- per-tool output limit

- [ ] **Step 2: 更新 `ROADMAP.md`**

记录：

- MCP Phase 2 状态。
- 后续 Phase 候选：HTTP/Streamable HTTP、OAuth、resources/prompts、MCP Apps、tool search、enterprise policy。
- 明确 Phase 2 不等于完整生态扩展。

- [ ] **Step 3: 更新 `DEVNOTES.md`**

记录边界：

- state store 不写项目目录。
- ToolRegistry mutation 只在 safe point。
- list_changed 不直接修改 schema。
- enable/reconnect 不绕过 trust。
- events/status 不泄露 secret。

- [ ] **Step 4: 更新 `PROGRESS.md`**

记录：

- task-by-task 实现摘要。
- 自动化命令和通过数量。
- PowerShell/cmd.exe 手工验收记录。
- 若手工验收未完成，必须明确写“未完成”或“待补记录”。

- [ ] **Step 5: 运行最终验证**

Run:

```powershell
python -m py_compile src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\events.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py
pytest tests/test_mcp_state.py tests/test_mcp_catalog.py tests/test_mcp_dynamic_refresh.py tests/test_mcp_management_command.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

- [ ] **Step 6: Codex review 检查点**

Review 重点：

- 文档是否没有把未做的 HTTP/OAuth/resources/prompts 写成已实现。
- Windows 验收证据是否先于结论。
- ROADMAP 是否仍保持后续生态扩展逐项设计、逐项验收。
- Task 文件 checkbox 是否和真实状态一致。
