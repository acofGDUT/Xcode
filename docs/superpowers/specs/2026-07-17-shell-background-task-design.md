# Shell 后台任务最小闭环设计

> 状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生进程验收已完成。
> 日期：2026-07-17

## 背景

改造前的 `run_shell` 使用同步 `subprocess.run(..., shell=True, capture_output=True)`。普通短命令可以返回，但 `mvn spring-boot:run`、Vite、nginx、watcher 等不会主动退出的前台服务会长期占住工具调用。Windows 上超时后只杀外层 shell，子进程仍可能持有 stdout/stderr 管道，导致 Python 在无上限的输出收尾阶段继续等待，Agent 主循环无法恢复。

本轮目标不是识别哪些命令属于服务器，而是把进程生命周期与单次工具调用生命周期拆开：命令从启动时就注册为会话内任务，工具调用可以在进程结束或转入后台后返回，同一进程继续运行且可查询、可停止。

## 目标

- `run_shell` 增加 `run_in_background` 显式参数，模型可为服务、watcher 和开发服务器主动选择后台运行。
- 普通命令在等待预算内结束时，继续返回 bounded 输出和 `exit_code`。
- 未显式后台但超过等待预算的命令原地转后台并返回 task ID，不重启进程。
- 提供后台任务输出查询、任务列表和停止接口。
- stdout/stderr 在工具返回后仍被持续 drain，不能因管道无人读取再次卡住子进程。
- `/exit` 或 runtime 退出时停止本会话仍在运行的任务，避免遗留孤儿进程。
- 保持 `AgentRuntime`、`ToolCallExecutor` 和 LLM/tool loop 的同步外观，不做全局 async 化。

## 非目标

- 不实现 `Ctrl+B` 运行中手动转后台。
- 不实现后台完成后的主动消息队列通知；模型第一版通过任务工具查询。
- 不实现 45 秒交互提示识别、实时进度 UI 或服务 ready 判断。
- 不跨 Xcode 进程或 session 恢复后台任务。
- 不识别或穷举 `npm run dev`、Spring Boot、nginx 等命令关键词。
- 不支持在命令内部再次使用 `start`、`Start-Process`、`&` 等方式脱离受管 shell 后仍保证进程树可追踪；调用方应直接运行目标服务并使用 `run_in_background=true`。

## 当前约束

- `ToolRegistry.execute()` 和 `ToolCallExecutor.execute()` 是同步调用链；工具返回普通 `ToolOutput` 后现有 Agent loop 即可继续。
- 现有 `TaskTracker` 管理的是 Agent 计划任务卡片，不能混入 OS 进程句柄和日志生命周期。
- `run_shell` 是危险工具，默认走本地审批；QQchat/external 入口不得看到 shell 任务或读取本地任务日志。
- Python >= 3.10，不新增第三方进程管理依赖。
- Windows 进程树停止第一版使用系统 `taskkill /T /F`，POSIX 使用独立 process group。

## 用户可见行为

### 快速结束

`run_shell(command, timeout=...)` 启动并注册进程。命令在等待预算内结束时返回输出和 `exit_code`，调用方无需接触 task ID。

### 显式后台

`run_shell(command, run_in_background=true)` 在进程启动并注册后立即返回：

- `task_id`
- 当前真实 `status`（通常为 `running`；极短命令可能已完成）
- root shell PID
- `output_file`
- `background_reason=explicit`

进程不会被重新启动。

### 超时自动后台

交互式工具中的 `timeout` 表示前台等待预算。预算耗尽且任务仍未结束时，同一个 task 标记为后台并返回 `background_reason=timeout`。该路径不杀进程。

### 管理接口

为避免与计划任务 `task_list` 混淆，工具名使用 shell 前缀：

- `shell_task_output(task_id, max_chars=20000)`：返回 bounded 最新输出、状态、退出码和截断标记。
- `shell_task_list()`：列出本会话任务快照。
- `shell_task_stop(task_id)`：停止受管进程树；重复停止为幂等结果。

未知 task ID 返回明确工具错误，不能抛异常打断 Agent loop。

## 设计

### 模块边界

新增独立 `ShellTaskManager`，由本地 `AgentRuntime` 持有。Manager 负责：

- spawn 和 task 注册；
- 状态机与线程安全快照；
- stdout/stderr drain 和 bounded 临时日志；
- 前台等待、显式/超时后台化；
- 输出查询、列表、进程树停止和 shutdown。

`core/tools/shell.py` 只负责把 manager 能力适配为 ToolDef 和兼容的一次性 `run_shell()` 函数。一次性 CLI 没有后续任务管理入口，因此其 `timeout` 继续作为硬超时并在到期后停止进程树，不返回无人管理的后台 task。

后台任务工具只注册到本地 `AgentRuntime`。General sub-agent 当前绕过主循环的权限审批，因此不能复用 manager，也不暴露 `shell_task_output/list/stop`；它仅保留既有一次性 `run_shell`，超时后会硬停止进程树。Explore/Plan sub-agent 仍不暴露 shell 工具。

### 状态模型

任务状态使用：

- `running`：root shell/命令尚未完成；可带 `backgrounded=false|true`。
- `completed`：退出码为 0。
- `failed`：退出码非 0 或监控失败。
- `stopped`：用户或 session shutdown 请求停止。

关键转换：

```text
spawn -> running foreground
running foreground -> completed | failed
running foreground -> running background (explicit | timeout)
running background -> completed | failed
running foreground/background -> stopped
runtime shutdown -> stop all running tasks
```

后台化只改变 task 元数据并唤醒工具调用，不 spawn 第二个进程。

### 输出模型

进程从启动起使用 `stdout=PIPE`、`stderr=STDOUT`，由 manager 的 daemon monitor 使用固定大小二进制块持续读取。输出写入 bounded 会话临时文件，内存保留 bounded tail；达到硬上限后继续 drain 但停止落盘并标记 `output_truncated=true`，防止磁盘无限增长和 pipe 反压。进程退出后必须等待 bounded `drain_done` 再发布终态，避免丢失快速命令的尾部输出。

工具结果只返回 bounded 文本。临时输出目录位于用户本机 `~/.xcode/shell_tasks/<runtime-id>/`，不写项目仓库；runtime shutdown 后 best-effort 删除。

### 工具与权限

- `run_shell`、`shell_task_stop`：`is_read_only=False`，走 shell 审批域。
- `shell_task_output`、`shell_task_list`：`is_read_only=True`，本地默认免审。
- 四个工具全部加入 external/QQchat 禁止集合，并在 schema 清洗和 `ToolCallExecutor` 执行层双重阻断，避免伪造 scope 后远程读取本地命令日志或控制进程。

## 安全与可靠性

- 所有 monitor、stop、shutdown 异常都转换为可控工具错误或 best-effort cleanup，不得打崩 Agent loop。
- stdin 使用 `DEVNULL`，第一版不支持交互式 shell 程序，避免后台任务等待终端输入。
- shutdown 和重复 stop 必须幂等并有 bounded wait。
- Windows 停止优先杀 root PID 的整个任务树；若只能 fallback 杀 root，则返回明确错误且不得标记 `stopped`。
- 任务输出和任务列表只在本地入口可见；输出进入 tool history 前仍受返回字符上限约束。
- 直接调用 shell 自己再 detach 的后代不保证可管理，工具说明必须引导模型直接运行服务命令。

## 兼容性

- 快速命令继续返回文本输出和 `exit_code=<n>`。
- 交互式 `run_shell.timeout` 从“不可靠的硬超时”迁移为“前台等待预算”；到期结果从 timeout error 改为后台 task。
- `xcode tool run shell` 等一次性调用没有持久 manager，仍采用硬超时并清理进程树。
- 不改变 session transcript schema；task ID 和状态作为普通 tool result 保存。
- 不新增配置文件或第三方依赖。

## 备选方案

- **仅为 `run_shell` 增加 `Popen + DEVNULL` 后台分支**：无法查询、停止或退出清理，会留下孤儿进程，拒绝。
- **按关键词猜测服务命令**：无法覆盖自定义脚本，且误判构建命令，拒绝。
- **复用 `TaskTracker`**：混淆计划状态和进程生命周期，拒绝。
- **本轮实现 Ctrl+B 和主动通知**：需要终端输入监听和通用消息队列，扩大 UI/状态边界，延期。
- **全局 async 化**：与当前同步架构不符，拒绝。

## 验收标准

- 快速命令返回输出和真实退出码。
- `run_in_background=true` 在短时间内返回 task ID，同一 PID 继续运行。
- 等待预算耗尽后返回同一 task ID，进程未被重启或杀死。
- 后台输出在工具调用返回后继续增长，并可通过 `shell_task_output` 查询。
- `shell_task_list` 正确反映 running/completed/failed/stopped。
- `shell_task_stop` 在 Windows 上释放 root shell、未 detach 的子进程树和监听端口。
- `/exit` 后本会话受管任务退出，不残留进程。
- QQchat/external schema 和执行层均不能访问 shell task 工具，即使输入的是伪造 allowlist。
- General sub-agent 不暴露后台任务查询、列表和停止工具。
- 聚焦自动化、全量 pytest、compileall、PowerShell/cmd.exe 原生启动/查询/停止验收均有真实证据。

## 完成证据

- 聚焦生命周期、工具、权限、external 和 runtime 回归通过。
- 全量 `pytest -q`、`python -m compileall -q src` 和 `git diff --check` 通过。
- PowerShell 与 cmd.exe 原生宿主均通过显式后台、超时原地后台、持续输出、进程树 stop 和 runtime shutdown 验收；额外真实 OS smoke 覆盖 worker + grandchild 全树停止。
