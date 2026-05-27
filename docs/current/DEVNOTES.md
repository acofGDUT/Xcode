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

**状态**：Open
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

后续方向：

- 明确三种模式的行为边界：纯流式、buffer 后渲染、可替换区域流式 + final render。
- 短期可考虑默认使用 `buffer_then_render`，或在 streaming 模式下不再对同一段内容做完整 final render。
- 如果继续保留 `streaming_plus_final_render`，需要用 Rich Live/可替换区域承载流式内容，而不是普通向下打印。
- 文档和配置说明必须明确：即时反馈与最终排版之间存在取舍。

Review 注意：修复时要重点覆盖代码块、Markdown table、长列表和中断场景，避免“重复消失了，但流式又静默了”的回归。

## 10. AgentRuntime 需要模块化重构

**状态**：Open
**关联**：ROADMAP P1 AgentRuntime 重构

现象：`src/xcode_cli/core/agent.py` 已经承载 REPL、slash command、审批 UI、LLM loop、工具执行、session resume、context compaction、render state 等多类职责。session resume 接入后，主循环更难 review。

后续方向：在功能稳定后做结构性重构，不改变行为，优先拆出：

- slash command handlers。
- tool call execution / approval flow。
- conversation compaction service。
- session resume orchestration。
- streaming/render mode state。

Review 注意：重构必须先有测试保护，尤其是多轮 tool_calls、审批拒绝、`/compact`、`/resume`、streaming render 这些容易被拆坏的路径。

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

**状态**：Open
**关联**：ROADMAP P2 项目级配置合并

当前权限系统能读取项目 `.xcode/settings.json` 的 permissions，但 `ConfigStore.load()` 还没有通用项目级 merge。

影响：不要假设 `.xcode/settings.json` 已经能覆盖 model、base_url、max_tokens、syntax_theme 等配置。

## 14. 工具调用 UI 仍会刷屏

**状态**：Open
**关联**：ROADMAP P1 工具调用 UI 折叠与展开

当前 `_render_tool_call()` 会把每个工具调用的完整参数逐条打印。连续 tool call 场景下，终端会持续向下滚动，容易把 assistant 正文、diff preview 和审批上下文推离视野。

后续方向：默认把连续工具调用合并成一行摘要，例如 `3 tools: read_file, grep, glob`；按 `Ctrl+O` 切换展开，查看每个工具的完整参数。

Review 注意：

- 折叠只应用于工具调用详情，不应隐藏 diff preview、审批菜单和危险操作提示。
- `Ctrl+O` 需要在原生 Windows 控制台验收，确认不干扰 prompt_toolkit 输入和审批菜单。

## 15. 工具调用轮次可能中断

**状态**：Open
**关联**：ROADMAP P1 工具调用轮次不中断

实际使用中发现 Xcode 可能因为工具调用轮次停下来。后续排查应聚焦 `_run_llm_loop()` 的多轮 tool_calls 状态推进，而不是只看单个工具是否执行成功。

重点风险：

- assistant `tool_calls` 和 tool result 的 `tool_call_id` 对不上。
- 工具拒绝、权限 denied、工具异常没有作为 tool result 继续喂回模型。
- streaming、context compression、KeyboardInterrupt 或空响应边界提前结束循环。
- UI 没有给出 round 状态，用户难以区分“正在继续下一轮”和“已经停住”。

建议增加 fake LLM 的多轮 tool call 测试，至少覆盖“第一轮工具 -> 第二轮工具 -> 最终文本”的完整链路。

## 16. `/compact` 需要进度反馈

**状态**：Open
**关联**：session resume 体验优化

现象：`/compact` 会调用 LLM 生成摘要。如果模型响应较慢，用户会看到终端停住，难以判断是在压缩、卡住，还是没有输入被接收。

后续方向：压缩期间显示进度或动态状态。第一版可以复用 Thinking/Live 风格，显示类似 `Compacting context...` 和 elapsed time；不要等摘要完成后才一次性输出结果。

Review 注意：

- 自动 compression 和手动 `/compact` 最好复用同一套状态展示。
- 进度 UI 不能吞掉异常或导致 checkpoint 半写入。
- 原生 PowerShell/cmd.exe 需要手工验收。

## 17. `/resume` 选择体验需要方向键菜单

**状态**：Open
**关联**：session resume 体验优化

当前 `/resume` 使用数字输入选择 session。实际体验上，用户更希望像审批菜单一样，用方向键上下浏览已有记录，按 Enter 恢复选中的 session。

后续方向：

- `/resume` 列表改为方向键上下选择 + Enter 确认。
- 列表项展示 session 时间、最近用户输入、是否有 checkpoint。
- 保留非 TTY fallback，例如数字输入或取消。
- 选择菜单不应破坏当前 runtime status，也不应在取消时污染 `_history`。

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
