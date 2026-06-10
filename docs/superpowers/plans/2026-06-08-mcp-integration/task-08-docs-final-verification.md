# Task 8: 文档和最终验证

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P1/P0。文档必须准确区分“设计完成”“自动化通过”“真实 MCP/Windows 验收完成”，避免把未执行验收写成已完成能力。

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/current/PROGRESS.md`

## Goal

实现完成后同步当前架构、路线图、开发笔记和进度记录，并跑最终验证。

## Steps

- [x] **Step 1: 更新 `ARCHITECTURE.md`**

只有 MCP 代码实现完成后再写入当前架构。需要记录：

- `.xcode/mcp.json` 配置。
- `MCPConnectionManager` 内部 async / 外部 sync 边界。
- trust store 和 startup gate。
- ToolRegistry 注册路径。
- `/mcp` command。
- result truncation。
- failure status。

- [x] **Step 2: 更新 `ROADMAP.md`**

把 MCP Phase 1 状态从“已写 spec/plan，未实现”更新为真实状态。若只完成自动化未完成 Windows/MCP 真实验收，必须保留未完成项。

- [x] **Step 3: 更新 `DEVNOTES.md`**

记录 MCP 关键边界：

- trust gate before spawn。
- server trust vs tool permission。
- MCP tool 默认非只读。
- schema/result 防御。
- 内部 async 例外和后续 AgentRuntime async 化路线。

- [x] **Step 4: 更新 `PROGRESS.md`**

记录实现内容和验证证据。证据必须包含实际命令输出摘要；真实 Windows 验收未做时要明确写“未执行”。

- [x] **Step 5: 运行最终验证**

Run:

```powershell
python -m py_compile src\xcode_cli\mcp\config.py src\xcode_cli\mcp\trust.py src\xcode_cli\mcp\naming.py src\xcode_cli\mcp\schema.py src\xcode_cli\mcp\result.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\dispatcher.py src\xcode_cli\core\commands\slash.py
pytest tests\test_mcp_config.py tests\test_mcp_trust.py tests\test_mcp_naming_schema.py tests\test_mcp_result.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_command.py tests\test_mcp_agent_integration.py -q
pytest -q
git diff --check
```

Expected: PASS，或明确记录失败原因和未完成项。

- [x] **Step 6: Codex review**

Review 重点：

- 是否误把 MCP prompts/resources/HTTP/SSE/OAuth 写进 Phase 1。
- 是否有任何路径让 untrusted server 启动。
- 是否把 trust 写进项目文件。
- 是否把 MCP annotations 当作 read-only 权限依据。
- 是否所有输出进入 `_history` 前截断。
- 是否有 Windows 手工验收记录。
