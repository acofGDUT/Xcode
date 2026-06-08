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

## 22. 开发流程与测试分层规范

**状态**：Resolved
**关联**：项目协作流程 / review 标准 / 测试基线

当前项目采用 **Spec-first + TDD-core + E2E-acceptance**。

含义：

- **Spec-first**：中等以上功能、架构调整、权限、上下文、session、tool loop、终端 UI 等改动，先写规格或任务说明，再进入实现。
- **TDD-core**：核心行为和 bugfix 先写失败测试，再写最小实现，最后重构。测试的价值在于锁住行为，不是追求表面覆盖率。
- **E2E-acceptance**：prompt_toolkit、Rich Live、审批菜单、方向键、Windows 路径、真实 PowerShell/cmd.exe 交互等场景，必须用手工验收记录补足自动化测试的盲区。

测试按风险分层：

| 层级 | 典型范围 | 验收口径 |
|------|----------|----------|
| P0 | 权限 allow/ask/deny、工具异常捕获、tool loop、session resume、compaction、memory path、context budget/cost、Windows 路径/编码 | 必须有自动化回归测试；bugfix 必须先补复现测试；review 时优先查缺口。 |
| P1 | slash command 行为、command handler 重构、task tracker、sub-agent 边界、配置合并、render mode 状态、工具摘要折叠 | 应有聚焦行为测试，测试用户可见行为和模块契约。 |
| P2 | 简单 wrapper、纯文案、低风险展示细节、文档更新、一次性说明 | 不强制补测试；可用 smoke test、手工验收或文档说明替代。 |

测试噪音边界：

- 不为了覆盖率机械测试每个私有 helper。
- 不重复测试已经被上层行为覆盖的同一分支。
- 不写脆弱的 Rich 文案/布局快照测试，除非该布局本身就是稳定契约。
- 不用 mock-only 测试替代真实行为测试；mock 只能隔离昂贵、外部或不可控依赖。

Review 注意：

- Coding Agent 的任务说明应标明本轮改动属于 P0/P1/P2 哪一层。
- P0/P1 改动如果没有测试，需要明确解释为什么只能用手工验收覆盖。
- 终端交互类改动不能只靠 pytest 结论收口，必须记录原生 Windows 验收情况。

## 23. AgentRuntime 第二轮重构边界

**状态**：Resolved
**关联**：AgentRuntime Refactor Round 2 / skills 功能前置解耦

当前收口：第二轮重构已经完成，目标是为后续 skills 功能降耦合，而不是提前设计完整的 SkillRuntime。`agent.py` 仍是主编排入口，但 slash command 路由、skill 命令服务和普通 user turn 已从大块主循环里拆出。

已完成的边界：

- `SlashCommandDispatcher` 负责 slash command 解析和分发，明确区分 prompt command 与 side-effect command。
- `SkillCommandService` 在当时负责旧 `list/install/enable/disable` 薄命令服务；后续 Skills As Prompt Commands 已把它迁移为项目 skills 的 list/show/validate 入口。
- `_run_user_turn()` 负责普通 user turn：session 持久化、history 更新、system prompt 构建、LLM 调用、错误短路、assistant 响应追加和 plan approval 展示。
- `_run_llm_loop()` 未做整体搬迁或重写，继续承载 streaming、Thinking Live、tool loop、task panel 和 session tool transcript 写入。

保留的设计取舍：

- 不为了降低行数而拆散稳定的 tool loop。
- 不引入抽象基类、事件总线或异步模型。
- 不改变 `/help`、`/init`、`/skill`、`/memory`、`/plan`、`/context`、`/resume`、`/compact` 的用户可见行为。
- skills 后续能力必须优先复用 `SkillCommandService` 和 `CommandRegistry`，不要再在 `main.py` 和 `agent.py` 各写一份 skill 命令逻辑。
- 第二轮重构只是解耦前置，不代表最终 skill 机制已定型；实际 Phase 1 设计已在后续 Skills As Prompt Commands 中收口。

Review 结果：

- 这轮是 P1 结构性重构，以行为回归测试为主。
- Coding Agent 分三步完成 `SkillCommandService`、`SlashCommandDispatcher`、`_run_user_turn()`，每步均经过 Codex review。
- 最终验证记录见 `PROGRESS.md` 的 AgentRuntime Refactor Round 2 章节。

## 24. Skills As Prompt Commands 边界

**状态**：Resolved
**关联**：P1 Skills As Prompt Commands / skill package 设计

当前收口：Phase 1 skills 已实现为项目内 prompt slash command。唯一自动加载来源是 `<project>/.xcode/skills/<skill-name>/SKILL.md`，`SKILL.md` 提供 metadata 和入口 prompt，supporting files 只按需读取，不自动注入上下文。

已移除的旧壳子：

- `skill.json` 安装模型。
- `Config.enabled_skills`。
- system prompt 中全量注入 enabled skills 的 `SKILL.md`。
- `/skill enable` / `/skill disable` 的启用状态语义。

当前设计边界：

- skill 是 prompt command，不是独立 runtime 分支；必须复用 `_run_user_turn()`、session、tool loop 和权限系统。
- `/skill-name args` 的 UI 展示文本和模型可见 prompt 必须分离：session user history 显示 slash command，LLM `_history` 使用展开后的 `model_content`。
- transcript 必须保存 skill invocation metadata；`/resume` 恢复时优先用 `metadata.model_content`，不能只恢复 `/skill-name args`。
- `allowed-tools` 采用 Claude-compatible 语义：它是 skill 声明的工具需求/允许/可预授权信息，不是当前 turn 的 exhaustive whitelist。当前 Xcode 只解析、归一化、展示和审计记录，不用它收窄 tool schemas 或 execution。
- skill 与 built-in slash command 冲突时，built-in command 保持优先。
- `context: fork` 当前不 inline 执行；`hooks` 当前只解析保存，不执行。

Review 注意：

- 不要把完整 project skills 再塞回 system prompt，否则会回到旧壳子的上下文膨胀问题。
- 不要为了兼容旧 CLI 继续维护 `skill.json` 语义；旧 install/enable/disable 只保留迁移提示。
- 不要自动读取 `.claude/skills`；迁移策略应单独设计，尤其是 `${CLAUDE_SKILL_DIR}` 到 `${XCODE_SKILL_DIR}`。
- Phase 2 才设计 `SkillTool`、模型主动调用 skills、fork/sub-agent skill execution、hooks 安全策略和 paths 自动激活。

Review 结果：

- Task 1-8 均按 TDD/聚焦验证完成，并逐 task review。
- 最终验证记录见 `PROGRESS.md` 的 Skills As Prompt Commands 章节。

## 25. Model-Invocable Skills / SkillTool 边界

**状态**：Resolved
**关联**：P1 Model-Invocable Skills / `SkillTool`

Phase 2 已实现模型主动调用项目 skills 的核心链路。当前模型不会看到完整 skill body 列表，只会在 system prompt 看到 compact listing；当 listing 明确匹配当前任务时，模型应先调用 read-only `skill` 工具加载完整 prompt。

开发约束：

- 新 skill 入口必须走 `SkillInvocationService`，不要在 slash command、模型工具或其他入口各自实现 prompt expansion、metadata、allowed-tools。
- `SkillTool` 成功加载 skill 后必须通过 blocked-tools 机制禁用当前 user turn 后续 `SkillTool` 递归调用。
- `SkillTool` 的 audit metadata 不能包含完整 skill prompt；完整 prompt 只放在模型可见 tool message 中。
- 不要让模型工具调用 `SlashCommandDispatcher`，也不要把模型工具调用拼成 `/skill-name args` 再走 slash command registry。
- `allowed-tools` 不能被当作严格白名单使用；如未来需要限制工具可见性，应设计独立字段，而不是复用 Claude skill 的 `allowed-tools`。
- `SkillTool` 是 tool batch barrier。成功加载 skill 后，同一 assistant response 中排在它后面的 sibling tool calls 应返回错误，要求模型在 loaded skill prompt 生效后的下一步再调用。
- 新增 SkillTool 相关测试时，优先测真实 loader/catalog/service/tool 链路；mock 只用于隔离 LLM response 或终端 UI。
- listing 测试必须证明完整 body、allowed-tools、paths、hooks 不进入 system prompt。

Review 注意：

- `user-invocable=false` 与 `disable-model-invocation=true` 是独立语义，review 时不要把两者混为一个 enable 开关。
- `context: fork` 当前仍应拒绝，不能悄悄 inline 执行或派发子 agent。
- `skill_invocation` audit event 只记录 source、skill、args、source_path、skill_source_hash 等审计字段，不记录 `model_content`。
- resume/compact 不需要重新展开 skill；只要 history 中保留 SkillTool 的 tool message loaded marker 即可。

## 26. QQ 外部聊天入口边界

**状态**：Mitigated
**关联**：ROADMAP Phase 6 / `/QQchat`

2026-06-05 已实现 `/QQchat start|stop|status` 第一版代码。2026-06-08 对 review findings 做了安全加固：QQ event 进入 service 后先做配置策略、去重和入队，真正的 external turn 在 `qqchat-worker` 中串行执行；external loop 使用 headless 模式，不在前端渲染、不启动 Rich Live、不更新本地工具计数。真实 QQ 平台验收、原生 PowerShell/cmd.exe 手工验收仍未执行，因此不能把该能力标记为完整完成。

设计结论：

- `/QQchat` 应是 side-effect slash command，用于启动、停止和查看 QQ bot 连接状态，不是 prompt command。
- 第一版推荐 WebSocket，而不是 Webhook。WebSocket 更适合本地 CLI，不要求公网 HTTPS 回调地址。
- 第一版只支持 QQ 单聊 `C2C_MESSAGE_CREATE` 和群聊 @ 机器人 `GROUP_AT_MESSAGE_CREATE`。
- 两类事件都使用 QQ 文档中的 `GROUP_AND_C2C_EVENT (1 << 25)` intents。
- QQ 消息必须视为外部不可信输入，默认通过入口级 `ToolScope` 只暴露 `read_file`、`grep`、`glob`、`task_list` 等只读能力。
- QQchat 的 `ToolScope` / `entry_tool_scope` 是外部入口安全边界，不复用 skill frontmatter 的 `allowed-tools`；后者只表示 skill 的工具需求/允许/可预授权 metadata，不是 turn 级严格白名单。
- 远程 QQ 用户不能审批危险工具。`write_file`、`edit_file`、`run_shell` 这类工具即使未来开放，也必须由本机 owner 在终端内确认。
- QQ turn 不复用当前 REPL 的 `_history`；`ExternalTurnRunner` 为每个 QQ conversation key 维护独立 session/history。
- QQ turn 不在前端做渲染。不要从 gateway callback 或 worker 直接调用会打印 Rich/Live/prompt_toolkit UI 的路径。
- `ToolScope.visible_tools` 和 `execution_allowlist` 会先移除危险工具，再取交集；如果配置只列危险工具，则回退到安全默认只读工具。
- execution 层对 `source == "qqchat"` 还会强制 `ToolDef.is_read_only`；`task_create`、`task_update`、`write_plan` 这类本地状态修改工具即使出现在 allowlist 里也会被拒绝。
- `QQChatConfig.enabled`、`enable_c2c`、`enable_group_at`、`group_allowlist`、`owner_openids`、`max_reply_chars` 和回复时间窗口已在 service 层执行；后续新增配置字段要补同层回归测试。
- Gateway 要处理 `op=7 Reconnect`、`op=9 Invalid Session` 和 `run_forever()` 意外退出；status 必须回传到 `/QQchat status`，不要只写后台线程日志。
- AppSecret、AccessToken、完整 Authorization header 不得进入项目配置、session transcript metadata、audit event、错误输出或测试快照。
- 被动回复受 `msg_id`、`msg_seq` 和 QQ 平台时间窗口限制；重复 `msg_id` 不会再次触发 runner。
- 后续如果做 Webhook，需要单独设计签名校验、公网 HTTPS 回调、端口限制和重放防护。

文档：

- `docs/reference/qq-bot-integration-guide.md`
- `docs/superpowers/specs/2026-06-05-qq-chat-integration-design.md`
- `docs/superpowers/plans/2026-06-05-qq-chat-integration-plan.md`

Review 注意：

- 不要使用会把主调用链拖入 `asyncio` 的 QQ SDK。
- 不要把 AppSecret 或 AccessToken 写入项目级配置、session transcript、错误日志或测试快照。
- 群聊默认按 `group_openid + member_openid` 隔离上下文，避免多人上下文污染。
- 被动回复要按 `msg_id + msg_seq` 去重，防止 QQ 重复投递导致重复回复。
- 群聊被动回复窗口只有 5 分钟，长时间 coding 任务不适合直接在 QQ 群里跑。
- QQchat 相关测试应覆盖 service queue、headless external loop、只读 tool scope、配置策略、gateway reconnect/status；不能只测 happy path payload。
