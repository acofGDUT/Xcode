# Approval Denial Interrupts Turn Implementation Plan

> **给 Coding Agent：** REQUIRED SUB-SKILL: 使用 `superpowers:test-driven-development` 执行每个 P0 行为改动；如遇到现有测试或实现与本文冲突，先停下记录差异，不要把“拒绝后继续”旧语义保留下来。建议按 task 文件逐个实现和 review。

状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 交互验收已完成。
日期：2026-06-30

**Goal:** 用户在本地 REPL 拒绝工具审批后，当前 turn 立即中断并等待下一次用户输入，同时保留拒绝记录供同 session 后续请求使用。

**Architecture:** 在 `ToolCallExecutor` 中区分“本地用户审批 no”和其他工具拒绝；在 `AgentRuntime` 中把 tool denial 写入 history/transcript 后停止 `_run_llm_loop`，并避免 `_run_user_turn` 追加伪 assistant final text。保持同步主循环、OpenAI-compatible assistant/tool 配对和现有 session transcript 格式。

**Tech Stack:** Python 3.10+、pytest、Rich/prompt_toolkit、现有同步 `AgentRuntime`、`ToolCallExecutor`、`ToolApprovalController`、`SessionStore`。不新增依赖，不引入 `asyncio`。

---

## Evidence and References

- Parent spec: [2026-06-30-approval-denial-interrupts-turn-design.md](../specs/2026-06-30-approval-denial-interrupts-turn-design.md).
- 当前审批执行入口：`src/xcode_cli/core/tooling/execution.py`.
- 当前 LLM/tool loop 编排：`src/xcode_cli/core/agent.py`.
- 当前审批 UI：`src/xcode_cli/core/tooling/approval.py`.
- 当前 session transcript：`src/xcode_cli/core/session.py`.
- 旧语义测试：`tests/test_agent_tool_loop.py::test_llm_loop_continues_after_user_denies_tool` 需要改写。
- 当前 roadmap 入口：`docs/current/ROADMAP.md`.

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/xcode_cli/core/tooling/execution.py` | Modify | 给 `ToolExecutionResult` 增加用户中断状态；审批 `no` 后停止 sibling tools |
| `src/xcode_cli/core/agent.py` | Modify | 增加结构化 loop result；中断后不继续 LLM、不追加 assistant final text |
| `tests/test_agent_tool_loop.py` | Modify | 改写拒绝审批旧测试，补 no-second-LLM、sibling tools 不执行、非用户拒绝保持继续 |
| `tests/test_agent_user_turn.py` 或现有邻近测试 | Modify/Create | 覆盖 `_run_user_turn()` 不写伪 assistant、不跑 after-turn hooks |
| `tests/test_session_resume.py` | Modify if needed | 覆盖 interrupted transcript 恢复后不产生 orphan tool message |
| `docs/current/ARCHITECTURE.md` | Update after implementation | 只在代码和验证完成后描述当前机制 |
| `docs/current/PROGRESS.md` | Update after implementation | 记录实现范围、测试证据和手工验收状态 |
| `docs/current/ROADMAP.md` | Update after implementation | 将本项从待实现移除或改为剩余验收缺口 |
| `docs/current/DEVNOTES.md` | Update after implementation | 保留仍有效的 review 边界和风险 |

## Task Files

- [Task 01: Distinguish Interactive Approval Denial](2026-06-30-approval-denial-interrupts-turn/task-01-distinguish-interactive-approval-denial.md)
- [Task 02: Stop AgentRuntime Turn Without Fake Assistant](2026-06-30-approval-denial-interrupts-turn/task-02-stop-runtime-turn-without-fake-assistant.md)
- [Task 03: Session, Resume, and Next-turn Context](2026-06-30-approval-denial-interrupts-turn/task-03-session-resume-next-turn-context.md)
- [Task 04: Docs and Native Windows Acceptance](2026-06-30-approval-denial-interrupts-turn/task-04-docs-native-windows-acceptance.md)

## Execution Constraints

- Execute one task at a time; stop for review after each task.
- Keep `_run_llm_loop()` string wrapper compatible unless the implementation deliberately updates every direct caller and test in one small, reviewable patch.
- Do not change `PermissionManager` default levels.
- Do not let local approval `No` execute the rejected tool or later sibling tool calls.
- Do not treat explicit config `deny`, QQchat/external `remote_approval=False`, blocked tool, unknown tool, or execution exception as user interruption.
- Do not append `[Request interrupted by user for tool use]` as `role=user`; use a fixed system marker or another design that does not pollute session `last_user_input`.
- Do not run auto memory extraction or other after-turn success hooks for interrupted turns.
- Do not update `ARCHITECTURE.md` as current behavior until the code and verification are complete.

## Recommended Final Verification

```powershell
pytest tests/test_agent_tool_loop.py tests/test_agent_user_turn.py tests/test_session_resume.py -q
python -m compileall -q src
pytest -q
git diff --check
```

Manual/E2E acceptance records required:

- PowerShell 原生 PTY：触发 `run_shell` 审批，选择 `No`，确认立即回到输入提示符且没有模型继续回答。
- cmd.exe 原生 PTY：重复同一场景。
- PowerShell 或 cmd.exe：触发 `write_file` / `edit_file` diff preview，选择 `No`，确认文件未修改、diff 可见、turn 立即结束。
- 同一 session 中拒绝后再输入一句新命令，确认模型请求上下文包含上一轮拒绝记录和新 user message。

## Closeout Rules

实现完成前，本 plan 和 task checkbox 不要标记完成。实现完成后必须写真实命令输出数量，例如 `N passed`，不能只写“预期通过”。如果原生 Windows 验收没做，必须明确保留缺口，不能写“完成”。
