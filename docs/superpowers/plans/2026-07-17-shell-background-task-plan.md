# Shell 后台任务最小闭环实施计划

状态：代码实现、自动化回归、PowerShell/cmd.exe 原生进程验收和文档收口已完成。
日期：2026-07-17

**目标：** 让 `run_shell` 对长驻服务显式或超时原地转后台，并提供会话内输出查询、列表、停止和退出清理能力。

**架构：** 新增同步外观的 `ShellTaskManager`，每个进程从 spawn 起注册并由 daemon monitor 持续 drain bounded 输出。只有本地 `AgentRuntime` 使用 manager-bound ToolDefs；General sub-agent 保留一次性硬超时 `run_shell`，现有 LLM/tool loop 保持同步，不引入全局 asyncio。

**技术栈：** Python 3.10+、`subprocess.Popen`、`threading`、pytest；Windows 进程树使用 `taskkill /T /F`，不新增第三方依赖。

## 证据和引用

- 父设计：[2026-07-17-shell-background-task-design.md](../specs/2026-07-17-shell-background-task-design.md)
- 当前实现：`src/xcode_cli/core/tools/shell.py`
- 生命周期入口：`src/xcode_cli/core/agent.py::run_chat`
- 当前 backlog：`docs/current/ROADMAP.md`

## 文件结构

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/xcode_cli/core/shell_tasks.py` | 新增 | 进程状态、输出 drain、后台化、查询、停止和 shutdown |
| `src/xcode_cli/core/tools/shell.py` | 修改 | manager-bound 四工具协议和一次性兼容入口 |
| `src/xcode_cli/core/agent.py` | 修改 | manager 所有权、工具注册和退出清理 |
| `src/xcode_cli/core/sub_agent.py` | 验证 | General sub-agent 不获得后台任务工具 |
| `src/xcode_cli/core/tooling/approval.py` | 修改 | stop 工具复用 shell 审批域 |
| `src/xcode_cli/core/external_turn.py` | 修改 | 禁止远程 shell task 工具 |
| `src/xcode_cli/core/tooling/execution.py` | 修改 | QQchat 执行层阻断伪造 shell task allowlist |
| `tests/test_shell.py` | 修改 | 工具协议、快速命令、硬超时兼容 |
| `tests/test_shell_tasks.py` | 新增 | 状态机、输出、后台化、停止和 shutdown |
| `tests/test_tool_approval.py` | 修改 | shell task 权限域 |
| `tests/test_external_turn.py` | 修改 | 外部入口屏蔽 |
| `tests/test_agent_memory_extraction_v2.py` | 修改 | runtime finally shutdown |

## Task 1：ShellTaskManager 核心状态机（P0）

- [x] 先写快速结束、显式后台、超时原地后台、持续输出、stop/shutdown 的失败测试。
- [x] 实现 `ShellTaskManager`、不可变 snapshot 和 run result。
- [x] 输出 monitor 始终 drain pipe，bounded 写入临时文件和内存缓冲。
- [x] Windows/POSIX 进程树停止、重复 stop 和 shutdown 保持幂等、bounded。
- [x] 运行 `pytest tests/test_shell_tasks.py -q`。

## Task 2：工具协议与 runtime 集成（P0/P1）

- [x] 先写四个 ToolDef schema、只读属性、timeout 行为和兼容 `run_shell()` 失败测试。
- [x] `AgentRuntime` 注册 manager-bound 工具并在 `finally` shutdown。
- [x] General sub-agent 仅保留一次性硬超时 `run_shell`，不得暴露后台任务工具。
- [x] `shell_task_stop` 复用 shell 审批域。
- [x] external/QQchat schema 与执行层双重屏蔽全部 shell task 工具，覆盖伪造 allowlist 回归。
- [x] 运行 shell、权限、external 和 agent loop 聚焦回归。

## Task 3：原生 Windows 验收与文档收口（P0/P1/P2）

- [x] `compileall` 和全量 `pytest -q`。
- [x] PowerShell：快速命令、显式后台、超时自动后台、日志查询、停止 Python 子进程树并确认端口/进程释放。
- [x] cmd.exe：重复核心显式后台、查询和停止路径。
- [x] 验证 `/exit` 清理仍在运行的任务。
- [x] 更新 `ARCHITECTURE.md`、`PROGRESS.md`、`ROADMAP.md`、`DEVNOTES.md`。
- [x] 对中文文档做磁盘级 UTF-8 抽样验证。

## 执行约束

- 不修改用户已有的 README、Auto memory roadmap 和 reference 文档变更。
- 不实现 Ctrl+B、主动完成通知、服务 ready 检测或跨 session 恢复。
- 不使用命令关键词自动判定服务器。
- 不把 `AgentRuntime`、`ToolCallExecutor` 或 REPL 主循环改成 async。
- 不把日志写入项目目录；输出必须 bounded，monitor 必须持续 drain。
- 不声称支持 shell 内部再次 detach 的后代进程管理。

## 最终验证

```text
python -m compileall -q src
pytest tests/test_shell_tasks.py tests/test_shell.py tests/test_tool_approval.py tests/test_external_turn.py tests/test_agent_tool_loop.py tests/test_agent_memory_extraction_v2.py -q
pytest -q
git diff --check
```

原生验收必须记录：

- PowerShell/cmd.exe 下 `run_in_background=true` 立即返回。
- 等待预算到期后同一进程继续运行。
- 输出查询可见后台追加内容。
- stop 和 `/exit` 后子进程与监听端口释放。

## Closeout

状态：已完成。

- 聚焦回归：`84 passed in 17.75s`。
- 全量回归：`672 passed in 54.97s`。
- `python -m compileall -q src` 与 `git diff --check`：通过。
- PowerShell 原生宿主：8 条生命周期/端口/shutdown 用例，`8 passed in 9.34s`。
- cmd.exe 原生宿主：同 8 条用例，`8 passed in 10.10s`。
- 两种宿主额外真实 OS smoke 均输出 `PASS explicit timeout output process-tree-stop runtime-shutdown`，覆盖 worker + grandchild 全树停止。
- 终审发现的后台摘要误报和 shutdown 多任务截止时间竞态已修复并补回归；shell 内自行 detach 仍作为明确非目标保留。
