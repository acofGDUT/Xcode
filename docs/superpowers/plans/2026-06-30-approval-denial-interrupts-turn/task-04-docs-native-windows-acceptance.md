# Task 04: Docs and Native Windows Acceptance

**Risk layer:** P1

## Goal

完成实现后的文档收口、全量验证和原生 Windows 手工验收记录，避免把“自动化通过”写成“交互体验已完成”。

## Suggested Files

- Modify after verification: `docs/current/ARCHITECTURE.md`
- Modify after verification: `docs/current/PROGRESS.md`
- Modify after verification: `docs/current/ROADMAP.md`
- Modify after verification: `docs/current/DEVNOTES.md`
- Modify: this plan/task checklist if implementation proceeds

## Constraints

- 没有真实执行的命令不能写成通过。
- PowerShell/cmd.exe 原生 PTY 未验收时，必须明确保留缺口。
- 修改中文文档使用 `apply_patch`，不要用 PowerShell here-string、`Set-Content`、`Out-File` 或重定向写中文。
- 中文文档更新后必须用 Python UTF-8 读取关键行做磁盘级编码抽样验证。

## Steps

- [x] 运行聚焦自动化回归。
- [x] 运行 `python -m compileall -q src`。
- [x] 运行全量 `pytest -q`。
- [x] 运行 `git diff --check`。
- [x] PowerShell 原生 PTY 验收：拒绝 `run_shell` 后立即回到输入提示符，无模型继续回答。
- [x] cmd.exe 原生 PTY 验收：同上。
- [x] PowerShell 或 cmd.exe 验收：拒绝 `write_file` / `edit_file`，diff preview 可见，文件未修改。
- [x] 更新 `ARCHITECTURE.md` 当前机制。
- [x] 更新 `PROGRESS.md` 实现和验证证据。
- [x] 更新 `ROADMAP.md`，移除或改写待实现项。
- [x] 更新 `DEVNOTES.md`，保留仍有效的 review 边界。
- [x] 用 Python 按 UTF-8 读取 spec/plan/current docs 关键中文行，确认无乱码。

## Acceptance

```powershell
pytest tests/test_agent_tool_loop.py tests/test_agent_user_turn.py tests/test_session_resume.py -q
python -m compileall -q src
pytest -q
git diff --check
```

Expected:

- 聚焦和全量测试通过。
- PowerShell/cmd.exe 中拒绝审批后不会继续主动思考。
- 文档只在证据之后声明完成。
- 编码抽样确认新增中文段落正常。

## Documentation

- `ARCHITECTURE.md`：实现完成后描述本地审批 No 的中断数据流。
- `PROGRESS.md`：记录真实命令、通过数量、手工验收状态。
- `ROADMAP.md`：实现完成后移除待实现项；若手工验收未做，保留验收缺口。
- `DEVNOTES.md`：保留“用户审批 No 与配置 deny 不同”的 review 注意事项。
