# Xcode 开发笔记

> 本文档记录坑、边界、设计决策和验收风险。当前系统如何工作见 `ARCHITECTURE.md`，未来做什么见 `ROADMAP.md`，阶段过程见 `PROGRESS.md`。

## 状态说明

| 状态 | 含义 |
|------|------|
| `Open` | 仍是当前问题或待办风险，需要后续开发、验证或决策。 |
| `Mitigated` | 已有缓解措施，当前不应阻塞主流程，但根因、完整能力或长期风险仍需注意。 |
| `Resolved` | 已通过实现、测试、验收或明确架构决策收口，后续主要作为约束或背景保留。 |
| `Archived` | 历史问题，仅保留背景；当前不再影响开发判断。 |

## 1. prompt_toolkit 控制台限制

**状态**：Mitigated
**关联**：原生 Windows E2E 验收

现象：在 Git Bash、mingw、cygwin 等非原生 Windows 控制台中，`PromptSession()` 可能抛出 `NoConsoleScreenBufferError`。

原因：prompt_toolkit 的 Windows 输出实现依赖原生控制台能力，模拟 POSIX 的终端环境不一定满足。

影响：不要把 Git Bash 下的失败直接判断为产品不可用。关键交互验收应在 cmd.exe 或 PowerShell 中完成。

## 2. 审批 UI 已从全屏 dialog 改为内联菜单

**状态**：Resolved
**关联**：Phase 4 UI v3

旧问题：`radiolist_dialog` 会接管整个终端，导致用户审批时看不到刚刚渲染的 diff。

当前实现：TTY 环境下使用内联三选项菜单：

```text
Yes
No
Yes, for this conversation
```

支持方向键上下 + Enter，也保留 `y/n/a` 快捷键。非 TTY fallback 才使用单行 `input()`。

Review 注意：后续文档和验收描述不要再写“内联 input() [Y]es / [n]o / [a]ll”作为主路径。

## 3. Rich markup 注入风险

**状态**：Mitigated
**关联**：流式输出和 Rich 渲染

现象：LLM streaming token 中如果包含 `[xxx]` 或 `[/xxx]`，Rich 可能当作 markup 解析并抛错。

规则：打印 LLM 原始 token 时必须使用 `markup=False`。需要样式时用 Rich 的 `style=` 参数，不要手写 `[dim]...[/dim]` 包住模型输出。

## 4. 工具异常必须被捕获

**状态**：Mitigated
**关联**：所有工具实现和 `ToolRegistry.execute()`

`ToolRegistry.execute()` 是最后防线，所有工具异常都应转为字符串结果返回给 Agent。

原因：工具失败是正常运行态，不能让 Agent 主循环因为单个工具失败崩溃。

Review 注意：

- 新工具必须通过 `ToolRegistry` 执行。
- 工具内部可以返回可读错误，但不应让未捕获异常逃逸到主循环。
- UI preview 这类执行前辅助逻辑也需要捕获 `OSError` 等路径异常。

## 5. Windows memory 路径 bug

**状态**：Mitigated
**关联**：Phase 4.5 Batch 2 memory/path regression

曾出现路径：

```text
C:\Users\%USERNAME%\.xcode\projects\D:\Xcode\memory\project_tech_stack.md
```

根因：模型把模板路径和真实工作目录错误拼接，形成 Windows 非法路径；随后 diff preview 读取该路径时抛出 `OSError: [Errno 22] Invalid argument`。

当前收口：

- `build_system_prompt()` 显式注入当前项目 resolved memory paths。
- diff preview 读取文件时把 `OSError` 当作可恢复预览失败。
- 已增加 regression test。

剩余风险：模型仍可能写错路径，但不应再打崩主循环。

## 6. memory 当前不是 CRUD 工具模型

**状态**：Resolved
**关联**：当前 memory 架构决策

当前决策：不提供 `memory_save/list/get/delete` 专用工具。

原因：

- 文件工具已经覆盖 XCODE.md 和 auto memory 的读写。
- 专用 memory 工具会增加 schema 和行为维护成本。
- prompt 驱动的写入更接近 Claude Code 风格，行为可通过工具调用审计。

代价：

- prompt 规则必须非常清楚。
- 模型可能写错路径，所以 resolved memory paths 很重要。
- memory 文档必须和 `BASE_SYSTEM_PROMPT` 保持一致。

## 7. session resume 当前模型

**状态**：Resolved
**关联**：ROADMAP P0 对话历史恢复

旧问题：`SessionStore` 曾只把 user/assistant 最终文本写入 JSONL，因此不能恢复 runtime history。

当前收口：

- transcript 写入 `~/.xcode/projects/<project-key>/sessions/<uuid>.jsonl`。
- transcript 使用 append-only event，包括 user、assistant、tool、system summary 和 `compaction_checkpoint`。
- `~/.xcode/history.jsonl` 只作为轻量用户输入历史，不用于重建 LLM history。
- `~/.xcode/sessions/<pid>.json` 只表示当前活跃进程，退出时删除。
- `/compact` 和自动 compression 会写入 checkpoint。
- `/resume` 使用最新 checkpoint + recent tail 恢复可继续工作的 `_history`；无 checkpoint 时使用 tail-only fallback。

当前边界：

- 本轮不做 CLI `--resume` / `--continue`。
- 不做 rollback/fork。
- checkpoint summary 长度策略集中在 `ContextManager`，`max_summary_chars=None` 或 `0` 时关闭代码层截断。
- 后续如重构 `agent.py`，应把 compaction/session resume glue 从主循环中继续拆出去。

## 8. memory 自管理权限缺口

**状态**：Resolved
**关联**：memory 模型 / 权限系统

现象：Xcode 通过文件工具维护自己的 memory 文件时，仍会走普通 `write_file` / `edit_file` 审批流程。实际体验上，Agent 管理自身记忆属于预期行为，不应该每次都要求用户审核。

当前收口：

- `MemoryManager.is_memory_write_target()` 负责判断 resolved memory 写入目标。
- `AgentRuntime` 仅对 memory-scoped `write_file` / `edit_file` 跳过用户审批。
- 显式 `deny` 仍优先生效。
- 普通项目文件仍走原有审批流程。

边界必须清楚：

- 免审范围只能覆盖明确解析后的 memory 文件或 memory 目录，不能扩展到任意项目文件。
- 路径必须使用 `MemoryManager` / prompt 注入的 resolved paths 做校验，避免模型拼错 Windows 路径后绕过审批。
- 普通代码、配置、测试文件仍应保持现有审批规则。
- 最好仍保留可审计日志，例如工具结果里显示写入了哪个 memory 文件。

Review 注意：不要简单地对所有 `write_file` 放行；这里要做的是”memory path scoped approval bypass”，不是降低整体写权限。

Review 结果：已跑 `pytest tests/test_agent_memory_permissions.py tests/test_memory.py tests/test_agent_memory_bug.py -q`、全量 `pytest -q`、`py_compile` 和 `git diff --check`。建议后续补 explicit `deny` + memory path 的回归测试，让“显式 deny 仍优先生效”不只依赖当前代码顺序。

## 9. 流式输出会和最终渲染重复显示

**状态**：Open
**关联**：流式输出 / Rich final render / ROADMAP P1 渲染模式完善

现象：在流式输出模式下，Xcode 会先把 token 逐段打印到终端；随后如果 final answer 触发 Rich Markdown 渲染，终端上方仍保留已经流式打印过的原始结构，导致用户看到两遍 assistant 输出。

根因方向：普通终端不能可靠“回收”已经打印的多行流式内容；当前 `streaming_plus_final_render` 同时追求即时 token 和最终美观渲染，容易在 Markdown、表格、代码块场景出现重复。

当前收口：

- `StreamingTurnRenderer` 已独立承载 token buffer、结构化内容检测和 final render 触发。
- `streaming_plus_final_render` 在检测到代码块、表格、标题后会停止继续 raw streaming，只保留 buffer，并最终渲染一次。
- `buffer_then_render` 模式下已补回归，确保最终回答一定会真正渲染到终端。

剩余方向：

- 明确三种模式的行为边界：纯流式、buffer 后渲染、可替换区域流式 + final render。
- 如果继续保留 `streaming_plus_final_render`，长期更稳的方案仍是用 Rich Live/可替换区域承载流式内容，而不是普通向下打印。
- 文档和配置说明必须明确：即时反馈与最终排版之间存在取舍。

Review 注意：修复时要重点覆盖代码块、Markdown table、长列表和中断场景，避免“重复消失了，但流式又静默了”的回归。

## 10. AgentRuntime 模块化重构第一轮

**状态**：Partially Resolved
**关联**：ROADMAP P1 AgentRuntime 重构

原现象：`src/xcode_cli/core/agent.py` 承载 REPL、slash command、审批 UI、LLM loop、工具执行、session resume、context compaction、render state 等多类职责。session resume 接入后，主循环更难 review。

第一轮已完成：

- `core/commands/slash.py`：slash command 列表和补全。
- `core/ui/shell.py`：welcome、命令建议、bottom toolbar、基础输出。
- `core/conversation/resume.py`：`/resume` 编排。
- `core/conversation/compaction.py`：`/compact` 和自动 compression checkpoint 编排。
- `core/tooling/approval.py`：审批 scope、方向键菜单、TTY fallback。
- `core/tooling/execution.py`：tool call 执行、diff preview、memory auto-allow、工具结果摘要。

Review 结论：第一轮通过，`pytest -q` 为 `184 passed`。已补多轮 tool_calls、审批拒绝、explicit `deny` + memory path、`/compact`、`/resume` 等回归覆盖。

剩余边界：

- `/env`、`/memory`、`/context`、`/plan` 等 command handlers 仍在 `agent.py`，后续如果继续收缩可以迁移到 `core/commands/`。
- streaming/render 的状态判断已经有 `core/ui/streaming.py` 承载，但 Thinking Live 和最终 orchestration 仍在 `_run_llm_loop()`；后续第二轮重构不要为了“继续拆文件”而打散现有稳定边界。
- 工具调用 UI 折叠已实现默认摘要；`Ctrl+O` 展开还没有实现，后续如果继续改 tool display state，需要保护 diff preview 和审批菜单可见性。

## 11. 不引入 asyncio

**状态**：Resolved
**关联**：当前同步架构约束

当前项目保持同步调用链。子 Agent 并发使用 `ThreadPoolExecutor`。

原因：

- LLM 调用是 I/O 密集，线程池已经足够。
- 引入 asyncio 会传染 `complete()`、`_run_llm_loop()`、`run_chat()` 整条调用链。
- 当前规模下，同步模型更容易 review 和调试。

## 12. 子 Agent 不递归派发

**状态**：Resolved
**关联**：SubAgentExecutor 工具白名单

子 Agent 不注册 `dispatch_agent`，避免子 Agent 再派发子 Agent。

原因：递归派发会让成本、延迟和状态变得不可控。当前子 Agent 更适合做探索、规划和局部分析。

## 13. 项目级配置仍不完整

**状态**：Resolved
**关联**：ROADMAP P2 项目级配置合并

旧问题：`ConfigStore.load()` 只读全局 `~/.xcode/config.json`，没有项目级覆盖。

当前收口：

- `ConfigStore.load()` 在加载全局配置后，检查 `<project>/.xcode/config.json` 是否存在，存在则字段级浅覆盖。
- 项目文件格式错误时打印 warning 并忽略，不崩。
- `save()` 仍只写全局文件，项目级 config 由用户手动维护。
- `max_summary_chars` 补入 Config dataclass，`ContextManager` 通过 `agent.py` 从 Config 传入，不再硬编码。
- 压缩 prompt 中 300/400 词软约束统一为 `max_summary_chars` 字符上限。
- `/env` 重写为 `EnvDashboard` TUI，管理 5 项非 API 参数。

## 14. 工具调用 UI 仍会刷屏

**状态**：Open
**关联**：ROADMAP P1 工具调用 UI 折叠与展开

旧问题是工具调用完整参数会持续刷屏。当前已经默认折叠成一行摘要，但展开热键和原生 TTY 体验仍未补齐。

当前收口：

- 默认把连续工具调用合并成一行摘要，例如 `tools: 3 calls: read_file, grep, glob`。
- `write_file`、`edit_file`、`run_shell` 会在摘要中保留危险标记。
- diff preview、审批菜单、命令预览和工具结果摘要不受折叠影响。

后续方向：按 `Ctrl+O` 切换展开，查看每个工具的完整参数。

Review 注意：

- 折叠只应用于工具调用详情，不应隐藏 diff preview、审批菜单和危险操作提示。
- `Ctrl+O` 需要在原生 Windows 控制台验收，确认不干扰 prompt_toolkit 输入和审批菜单。

## 15. 工具调用轮次可能中断

**状态**：Mitigated
**关联**：ROADMAP P1 工具调用轮次不中断

这类问题的核心是 `_run_llm_loop()` 的多轮 tool_calls 状态推进，而不是单个工具是否执行成功。当前核心逻辑已经做过一轮收口。

当前收口：

- `_run_llm_loop()` 已改为 `while True`，不再有固定 10 轮上限。
- 已补多轮 tool call、用户拒绝后继续、空响应 fallback、`buffer_then_render` 最终渲染等回归测试。
- 当前重点回归已覆盖 `40 passed`。

剩余风险：

- 真实终端体验仍需结合 streaming、工具摘要显示、`/resume`、`/compact` 做原生 Windows E2E 验收。
- UI 仍没有显式 round 状态提示，用户在超长链路里不一定容易判断“还在继续推理”还是“真的停住”。

## 16. `/compact` 需要进度反馈

**状态**：Resolved
**关联**：session resume 体验优化

现象：`/compact` 会调用 LLM 生成摘要。如果模型响应较慢，用户会看到终端停住，难以判断是在压缩、卡住，还是没有输入被接收。

当前收口：

- `ConversationCompactor.compact_history()` 在调用 `ContextManager.compress()` 前后包裹 Rich `Live` 进度显示。
- 显示 "Compacting context... (Xs)" 动态计时，复用 `_run_llm_loop()` 的 Thinking Live 模式（`Live(transient=True)` + daemon thread）。
- 手动 `/compact` 和自动 compression 共用 `compact_history()`，进度展示自然统一。
- `finally` 保护确保 `compress()` 异常时 Live 也停止，不残留终端状态。
- `Nothing to compact.` 路径（history < 4）在 `_handle_compact_command` 中提前返回，不启动 Live。

## 17. `/resume` 选择体验需要方向键菜单

**状态**：Resolved
**关联**：session resume 体验优化

当前 `/resume` 使用数字输入选择 session。实际体验上，用户更希望像审批菜单一样，用方向键上下浏览已有记录，按 Enter 恢复选中的 session。

当前收口：

- `ResumeCommandService.run()` TTY 路径改为方向键 ↑/↓ 浏览 + Enter 确认 + Esc 取消，复用 `read_key()` 从 `approval.py` 提取的模块级键盘读取函数。
- `_render_session_list()` / `_refresh_session_list()` 复用审批菜单的 ANSI 光标上移+清行刷新模式。
- 列表项展示 session 时间、最近用户输入（截断 60 字符）、checkpoint 标记，保留数字快捷键。
- 非 TTY 环境回退到 `_run_number_input()`，行为与旧版数字输入一致。
- 取消时返回 `None`，不污染 `_history` 和 runtime status。

## 18. 验收证据优先

**状态**：Open
**关联**：所有开发和 review 流程

项目约定：结论必须跟在证据后面。

推荐验证顺序：

```powershell
python -m py_compile src/xcode_cli/core/agent.py
pytest
python -c "from xcode_cli.core.agent import AgentRuntime; print('ok')"
```

涉及 prompt_toolkit、审批菜单、方向键交互时，必须补原生 cmd.exe/PowerShell 手工验收记录。

## 19. Windows subprocess 解码问题

**状态**：Resolved
**关联**：`run_shell` 工具 / 中文 Windows 控制台

现象：在中文 Windows 环境下，`run_shell` 读取外部命令输出时，可能因为 `subprocess.run(..., text=True)` 走系统默认 GBK 解码而触发 `UnicodeDecodeError`。

根因：外部命令输出并不一定是 GBK；当 UTF-8 或混合编码字节流被系统默认编码解码时，reader thread 可能直接抛异常。

当前收口：

- `src/xcode_cli/core/tools/shell.py` 显式使用 `encoding="utf-8"`。
- 同时使用 `errors="replace"`，把不可解码字符降级为可显示占位，而不是打崩工具调用。
- 已增加回归测试，锁定 `run_shell()` 必须传入 `encoding` 和 `errors`。

Review 注意：这次修复只覆盖 `run_shell`。其他使用 `subprocess.run(..., text=True)` 的工具如果后续也在 Windows 下读取非默认编码输出，需要单独审查，不要默认已经一起解决。

## 20. Task 工具免审与 UI 展示

**状态**：Resolved
**关联**：task 工具 / 权限系统 / 输出渲染

现象有两个：

1. **权限**：Xcode 的 `task_create`、`task_update` 是 `is_read_only=False`，默认走 `ask` 审批。但 task 是项目自管理基础设施（和 memory 同类），不应该每次要用户确认。
2. **展示**：当前工具结果只输出 JSON 字符串，用户需要展开工具结果才能看到 Task 变更。Claude Code 的做法是在 Thinking 区域下方展示格式化的 task 卡片，一目了然。

2026-05-28 已完成：

- `task_create` / `task_update` 在 `_default_level()` 中返回 `allow`（权限免审）。
- `PermissionManager.check()` 新增 `is_read_only` 参数：只读工具无显式 deny 时自动 allow。收口了 `task_list`、`exit_plan_mode` 等 `is_read_only=True` 但之前未生效的工具。
- `ToolRegistry.is_read_only()` 查询方法，供 `ToolExecutor` 传参。
- `AgentRuntime._render_task_panel()` 在一轮工具执行后检测 task 工具调用并渲染 task 面板（◻/◐/✓ + 标题 + 颜色区分）。
- 用户仍可通过 settings.json 显式 deny/ask 覆盖。
- 测试：`test_task_permissions.py`（8）、`test_task_display.py`（4），全量 236 passed。

**当前实现边界 — 瞬时渲染而非持久展示**：

当前 task 面板是在每轮 LLM 工具调用执行完毕后渲染一次：用户看到 task 面板出现在输出流中，新的工具结果和 LLM 输出会把它向上推出可视区域。Claude Code 的做法是将 task 列表持续挂在终端底部 toolbar 区域，始终可见。

这不是 bug，是刻意保持简单的第一版实现：
- 瞬时渲染不挑终端（普通 print 即可，不依赖 prompt_toolkit 的 bottom_toolbar 或 ANSI 区域预留）。
- 不引入额外的输出区域管理（在 Rich Live + Thinking 动画 + 流式输出之上再加一层驻留区域会显著增加终端控制复杂度）。
- 原生 Windows cmd.exe 对 bottom_toolbar 和固定区域的兼容性需要单独验证。

**待优化方向**（后续迭代，不是当前任务）：

- 探索用 prompt_toolkit `bottom_toolbar` 或 Rich `Live` 固定区域将 task 面板持续挂在终端底部。
- 或者在每次新一轮 Thinking/输出前做轻量刷新，让用户一眼看到当前 task 状态而不用回滚。
- 优先在原生 Windows cmd.exe/PowerShell 验证热键和固定区域的行为之后再决定方案。

## 21. `/resume` 的 last_user_input 预览不稳定

**状态**：Open
**关联**：`/resume` 选择体验

现象：`/resume` 列表展示的 `last_user_input` 是 transcript 中最后一条 user 消息。每次用户发新消息后，这个预览就会变化，导致同一个 session 在不同时间点看到的预览文案完全不一样。用户很难通过"最后一条消息"来识别这是哪个 session。

后续方向（仅记录，暂不实现）：

- 可以考虑记录 session 的"简要摘要"或"第一条用户输入"作为不变标识，而非动态变化的最后一条消息。
- 或者在 session 创建时让用户起名。

## 22. Textual Batch 4/5 hardening

**状态**：Mitigated
**关联**：Textual Claude-style UI / slash command / task slots / resume selection / compacting state

背景：Batch 4/5 要求 Textual path 支持必需 slash command，并补 task/status/pet 插槽。第一轮只做了入口和事件骨架，`/resume`、`/compact`、`/env`、`/plan` 仍偏浅；本轮 hardening 将这些路径接到真实 runtime 服务和 ChatApp 消费层，但仍不做默认入口切换。

当前收口：

- `RuntimeController` 的 `/resume` 已读取真实 `SessionStore.list_sessions()`，发出包含 session id、最近输入、消息数、checkpoint 标记的 `ResumeListLoaded`。
- `ResumeSessionCommand` 已改用 `SessionResumeBuilder` 做 checkpoint-aware 历史恢复：找到最后一个 `compaction_checkpoint`，取 summary + checkpoint 后的消息，按 `max_tokens * 0.6` token budget 裁剪。行为与 legacy `ResumeCommandService` 一致。无 `context_manager` 时回退到原始 `load_history()`。
- `ResumeSessionCommand` 失败语义已修复：session store 不存在或 session id 不在 `list_sessions()` 结果中时发 `UICommandFailed`；`SessionResumeBuilder` 返回空 history 时也发 `UICommandFailed`。
- ChatApp 收到 `ResumeListLoaded` 后进入 resume selection 状态：`ResumeSelector` 作为 transient widget 渲染为纯文本样式（无边框、无背景），通过 `render()` 输出带 `>` 选中标记的 session 列表。长列表最多显示 10 条 session，并显示当前范围；选中项越过窗口底部/顶部时窗口跟随滚动。导航时只更新 widget 内部状态，不向 `RichLog` 写入重复内容。
- `ResumeCompleted` 事件携带 legacy 恢复元数据（`restored_from_checkpoint`、`estimated_tokens`、`last_user_input`），ChatApp 渲染为与 legacy `/resume` 一致的多行系统通知。
- 取消显示 `Cancelled.`，空 session 提示为 `No recent sessions found for this project.`。
- `CompactCommand` 已直接调用 `ContextManager.compress()`，不复用 legacy Rich Live；成功发 `CompactionCompleted`，无内容发 `CompactionSkipped`，异常发 `CompactionFailed`。
- `/compact` 是原子 session mutation：`RuntimeController._is_compacting` 标记在 compact 开始时设置，完成/跳过/失败时清除；compacting 期间 `SubmitUserInputCommand` 和 `RunSlashCommandCommand` 被拒绝并返回 `UICommandFailed`。
- ChatApp 消费 `CompactionStarted/Completed/Skipped/Failed` 管理 UI 层 `_is_compacting`，期间输入提交显示 "Compacting context... please wait." 提示。
- `/compact` 继续保持 active turn / pending permission 并发保护。
- `/plan enter/show/approve/reject` 已接入 `PlanMode` 状态机，并通过 `PlanUpdated` / `StatusUpdated` 通知 UI。
- `/env` 明确是 read-only display；`SaveEnvCommand` 仍可用于后续最小编辑 UI，事件进入 UI 前会脱敏。
- `ChatApp` 已消费 `ResumeListLoaded`、`ResumeCompleted`、`ConfigUpdated`、`PlanUpdated`、`PlanApprovalRequested`。
- `ChatApp` 维护当前 task 列表，`TaskStateChanged` 会生成聚合后的精简 `TaskSnapshotBlock`，并把 in-progress task 显示到 active-turn 区域。
- `StatusBar` 已通过 `StatusPresenter` 生成单行状态；`PetSurface` 仍是隐藏插槽，不加载资源。
- 已检查 `docs/current/DEVNOTES.md`，当前 UTF-8 读取未发现明显 mojibake 模式。

风险：

- Textual path 目前仍不能标记 default-ready；它还缺 `/env` 编辑 screen、`run_shell` stdout/stderr capture 和原生 Windows E2E。
- `/resume` 选择器已是纯文本 transient widget，恢复反馈已与 legacy 对齐，但还不是最终 screen（无搜索、无预览扩展）。
- `/env` 当前明确为只读展示；如果要编辑，后续必须通过 `SaveEnvCommand`，不能让 Widget 直接写配置。
- `/compact` 同步执行，未做 worker 化；长 LLM 压缩可能导致 UI 冻结，但至少输入已被阻塞不会误操作。

验证记录：

- Batch 4/5 hardening 第四轮全量回归：`pytest -q`，passed。
- 编译检查：`python -m py_compile src/xcode_cli/core/runtime/controller.py src/xcode_cli/core/ui/textual/app.py src/xcode_cli/core/ui/textual/widgets.py`，OK。
