# Xcode 开发进度

> 本文档记录项目如何一步步走到现在。当前实现细节见 `ARCHITECTURE.md`，未来计划见 `ROADMAP.md`，已知问题和设计取舍见 `DEVNOTES.md`。

最后更新：2026-06-30

## 1. 当前状态总览

| 阶段 | 名称 | 状态 | 验收 |
|------|------|------|------|
| Phase 1 | 协议与工具升级 | 完成 | `PHASE1_ACCEPTANCE.md` |
| Phase 2 | Agent 架构升级 | 完成 | `PHASE2_ACCEPTANCE.md` |
| Phase 3 | 计划与记忆 | 完成 | `PHASE3_ACCEPTANCE.md` |
| Phase 4 | 安全与体验 | 完成，4.3 已收口 | `PHASE4_ACCEPTANCE.md` |
| Phase 4.5 Batch 1 | 上下文系统修复 + 测试基线 | 完成并通过 review | specs task brief |
| Phase 4.5 Batch 2 | memory 模型验证 + Windows 路径回归 | 完成并通过 review | specs task brief |
| Session Resume Step 1 | session 持久化基础 | 完成并通过 review | `2026-05-25-session-resume-task-brief.md` |
| Session Resume Step 2 | checkpoint 压缩与 `/resume` | 完成并通过基础验收 | `2026-05-25-session-resume-task-brief.md` |
| Memory 自管理权限 | memory-scoped 写入免审 | 完成并通过 review | `2026-05-26-memory-self-management-permissions.md` |
| AgentRuntime 模块化重构第一轮 | commands/conversation/tooling/ui 服务抽离 | 完成并通过 review | `2026-05-27-agent-runtime-refactor.md` |
| 输出与工具轮次稳定化 | streaming 去重、tool loop 收口、工具摘要折叠 | 完成并通过重点回归验收 | `2026-05-27-output-tool-loop-stability.md` |
| `/compact` + `/resume` 体验优化 | compaction Live 进度、resume 方向键菜单 | 完成并通过 review | `2026-05-28-compact-progress-and-resume-ux.md` |
| 项目级配置合并 + /env 仪表盘 | .xcode/config.json merge、max_summary_chars 收口、/env TUI | 完成并通过 review | `2026-05-28-config-merge-plan.md` |
| Task 工具免审 + UI 面板 + is_read_only 权限收口 | task_create/update 免审、瞬时 task 面板、只读工具默认 allow | 完成并通过 review | `2026-05-28-task-auto-allow-and-ui-plan.md` |
| 开发流程与测试分层规范 | Spec-first + TDD-core + E2E-acceptance、P0/P1/P2 测试分层 | 完成 | `AGENTS.md` / `DEVNOTES.md` |
| `/init` prompt command | 旧版 Claude 风格 prompt command，生成或改进仓库级 `XCODE.md` | 完成并通过测试 | `2026-06-04-init-command-plan.md` |
| AgentRuntime Refactor Round 2 | SlashCommandDispatcher、SkillCommandService、普通 user turn 抽离 | 完成并通过 review | `2026-06-04-agent-runtime-refactor-round2-plan.md` |
| Skills As Prompt Commands | `.xcode/skills/<name>/SKILL.md` 加载为 prompt slash command | 完成并通过整体 review | `2026-06-04-skills-as-prompt-commands-plan.md` |
| Model-Invocable Skills | compact listing + `SkillTool` 模型主动调用 skills | 完成并通过整体 review | `2026-06-05-model-invocable-skills-plan.md` |
| MCP Phase 1 | stdio tools 安全接入、trust gate、ToolRegistry adapter、内部 async connection manager、`/mcp` 命令 | 完成；自动化和原生 Windows E2E 通过 | `2026-06-08-mcp-integration-plan.md` |
| MCP Phase 2 | 管理面、动态工具刷新、tool enable-disable、reconnect/events、per-tool output limit | 代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 验收通过 | `2026-06-09-mcp-phase2-plan.md` |
| `/resume` 最近对话 replay | 恢复成功后展示 checkpoint 后 user/assistant 对话 | 完成；自动化和原生 Windows E2E 通过 | `2026-06-09-resume-recent-conversation-rendering-plan.md` |
| compact 可靠性重设计 | `No response.` 外部错误边界、no-tool summary、summary 质量门、pair-safe tail、xcode.v2 checkpoint metadata、tool result micro-compact、QQchat fallback/heartbeat 降噪 | 代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY `/compact` handler 验收完成；真实 QQ 验收由用户接手 | `2026-06-11-compact-reliability-plan.md` |
| compact v3 现场恢复 | `WorkStateTracker`、bounded restored context、checkpoint lineage metadata、v3 resume 和 external work-state isolation | 代码实现和自动化回归完成；PowerShell/cmd.exe 与 QQchat 手工验收未执行/未记录 | `2026-06-12-compact-state-restoration-plan.md` |
| 手动 `/compact` 语义放宽 | 非空 `_history` 均尝试 checkpoint；移除消息数和摘要长度硬门槛；空摘要/summary 请求异常给出明确失败 | 代码实现和自动化回归完成；原生 PTY 手工验收未执行/未记录 | `2026-06-14-manual-compact-semantics-design.md` |
| `dispatch_agent` 免审优化 | 本地主会话子 Agent 分派默认免审批，explicit deny/ask 与 QQchat 远程过滤保持生效 | 代码实现并通过聚焦回归 | `2026-06-11-dispatch-agent-auto-allow-design.md` / `2026-06-11-dispatch-agent-auto-allow.md` |
| Auto memory extraction v2 | Claude-like memory-only extraction subagent、v2 topic policy、后台 single-flight runner | 代码实现和自动化回归完成；原生 PTY 手工验收未执行/未记录 | `2026-06-23-auto-memory-extraction-v2-claude-like-plan.md` |
| Auto memory recall v2 | Claude-like `MEMORY.md` 短索引 + relevant topic prefetch、bounded reminder、安全点注入 | 代码实现和自动化回归完成；PowerShell/cmd.exe 原生 PTY 手工验收未执行/未记录 | `2026-06-23-auto-memory-recall-v2-claude-like-plan.md` |
| 本地审批拒绝中断当前 turn | 本地审批 `No` 后停止当前 turn、保留拒绝配对和 system marker | 代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 验收完成 | `2026-06-30-approval-denial-interrupts-turn-plan.md` |
| Phase 5 | 生态扩展 | 冻结 | 未开始 |

当前重点仍不是全面进入 Phase 5，而是补齐费用估算、QQchat 收口，以及 compact v3 现场恢复和 auto memory recall v2 的原生 Windows/QQchat 手工验收。MCP Phase 1 已完成 stdio tools 安全接入、自动化回归和 PowerShell/cmd.exe 原生 E2E，Phase 2 已完成 stdio tools 管理面与动态刷新代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 验收；后续不得无 spec 扩展到 resources/prompts/HTTP/SSE/OAuth。核心 CLI 的 `/resume`、`/compact` Live 进度、多轮 tool call、本地主会话 `dispatch_agent` 默认免审、本地 REPL auto memory extraction v2、auto memory recall v2 和审批拒绝中断语义已完成聚焦回归；compact v3 的 restored-context `/compact`、v3 `/resume`、recall v2 原生 PTY 和 QQchat continuation/isolation 手工验收仍未记录。

## 2. Phase 1：协议与工具升级

目标：从文本解析工具调用升级为 OpenAI-compatible function calling，并把工具系统整理成可扩展注册表。

完成内容：

- 建立 `ToolDef` / `ToolRegistry`。
- 拆分 `tools/` 目录。
- 新增 `edit_file`、`grep`、`glob`。
- 改造 `LLMClient` 支持 streaming 和 tool calling。
- 更新 system prompt，使 Agent 优先读代码、搜索上下文、用 edit-style 修改。
- CLI 暴露基础 tool run 能力。

结果：Xcode 从原型工具调用进入可用工具协议阶段。

## 3. Phase 2：Agent 架构升级

目标：引入子 Agent 和任务追踪，让复杂任务可以分派和记录。

完成内容：

- 定义 Agent 类型：EXPLORE / PLAN / GENERAL。
- 实现 `SubAgentExecutor`。
- 增加 `dispatch_agent` 工具。
- 使用 `ThreadPoolExecutor` 支持并行子 Agent。
- 实现 `TaskTracker` 和 `task_create/update/list`。
- 子 Agent 工具白名单限制为只读搜索/读取能力，避免递归派发。

结果：主 Agent 能把探索和规划类任务拆给子 Agent，但仍保持同步主循环。

## 4. Phase 3：计划与记忆

目标：支持显式计划模式和跨会话记忆。

完成内容：

- 实现 `/plan` 和 plan mode 状态机。
- 增加 `enter_plan_mode`、`write_plan`、`exit_plan_mode` 工具。
- 建立 Project XCODE.md、User XCODE.md、Auto Memory 三层模型。
- 记忆系统从专用 CRUD 工具转向文件驱动模型。
- `/memory` 支持状态展示和 auto memory 开关。

结果：计划模式可用，memory 模型确定为 “XCODE.md + auto memory index + 文件工具写入”。

## 5. Phase 4：安全与体验

目标：让工具执行更安全，终端交互更可审查。

完成内容：

- 4.1 权限系统：session > project > global。
- 4.2 Rich Markdown、语法高亮、diff 渲染。
- 4.2b UI v2：先审后执行、欢迎屏精简、状态栏增强、工具调用展示。
- 4.2c UI v3：审批内联菜单、Thinking 计时、`/context`、语法主题、工具结果语义化。
- 4.3 上下文管理：token 估算、自动压缩、动态 `max_tokens`、`/env max-tokens`。
- 4.4 reasoning/thinking 流式展示与耗时统计。

结果：危险工具在执行前可审查，diff 在审批时保持可见，context 预算可配置。

## 6. Phase 4.5 Batch 1：上下文系统修复 + 测试基线

背景：Phase 4 验收后发现 context 预算存在实现和文档不一致。

完成内容：

- `ContextManager.MAX_TOKENS` 硬编码改为实例级 `max_tokens`。
- `Config.max_tokens` 成为 runtime 单一来源。
- `/env max-tokens <value>` 更新 config 和 runtime context。
- 压缩摘要提示词改为英文。
- 补充 `tests/test_context.py`、`tests/test_config.py`、`tests/test_agent_env.py`。

Review 结论：通过。后续 context 工作转为 cost 估算和更真实的端到端验收。

## 7. Phase 4.5 Batch 2：memory 模型验证 + Windows 路径回归

背景：memory 文档曾描述旧模型，实际代码已经转向 prompt 驱动的文件模型；同时发现 Windows 路径可能拼成非法路径并在 diff preview 阶段崩溃。

完成内容：

- 文档和实现统一到当前 memory 模型。
- `build_system_prompt()` 显式注入 resolved memory paths。
- 增加 memory 相关测试：
  - `tests/test_memory.py`
  - `tests/test_prompting_memory.py`
  - `tests/test_agent_memory_command.py`
  - `tests/test_agent_memory_bug.py`
- diff preview 读取目标文件时将 `OSError` 视为可恢复预览失败，不再打崩主循环。

Review 结论：通过。memory 当前不是 CRUD 工具方向，而是由 prompt 指引 LLM 使用文件工具。

## 8. 文档重构：2026-05-25

背景：`ROADMAP.md`、`PROGRESS.md`、`ARCHITECTURE.md`、`DEVNOTES.md`、`日期计划.md` 之间职责重叠。用户希望保留详细内容，但降低冗余。

完成方向：

- 旧主文档归档到 `docs/old/2026-05-25-before-docs-restructure/`。
- 当前权威文档迁移到 `docs/current/`。
- 根目录同名文档保留为兼容入口。
- `日期计划.md` 降级为 journal，副本放到 `docs/journal/2026-05-25-日期计划.md`。

结果：文档分层调整为 README 入口、ARCHITECTURE 当前实现、ROADMAP 未来计划、PROGRESS 历史进度、DEVNOTES 坑和决策、journal 原始工作日志。

## 9. Session Resume：2026-05-26

背景：原 `SessionStore` 只是简化 JSONL 日志，无法恢复 tool_calls、tool result、context summary 等 runtime history。用户希望借鉴 Claude Code 的 transcript + history 模型，但当前先聚焦交互内 `/resume`，不做 CLI `--resume` 和 `--continue`。

Step 1 完成内容：

- session id 改为 UUID。
- transcript 写入 `~/.xcode/projects/<project-key>/sessions/<uuid>.jsonl`。
- `project-key` 从项目绝对路径稳定生成。
- `~/.xcode/history.jsonl` 记录轻量用户输入历史。
- `~/.xcode/sessions/<pid>.json` 记录运行中 runtime status，正常退出时删除。
- transcript 支持 user、assistant、tool、system message event。
- `/resume` 可以列出当前项目 session，并恢复小 transcript。

Step 2 完成内容：

- `ContextManager.compress()` 返回 `CompressionResult`，包含 compressed messages、summary 和 checkpoint message。
- 压缩摘要改为累积摘要，避免多次压缩丢早期上下文。
- 自动 compression 和 `/compact` 都会写入 `message(system)` + `compaction_checkpoint`。
- `SessionResumeBuilder` 支持最新 checkpoint + recent tail 恢复。
- 无 checkpoint 时使用 recent tail fallback。
- 恢复时按 token budget 裁剪，并保护 tool_calls / tool result pair。
- `max_summary_chars` 已做成可配置、可关闭。
- `/compact` 没有真实压缩时提示 `Nothing to compact`，不写 checkpoint。

Review 状态：Step 1 已通过 review；Step 2 已修复复审问题，并完成基础验收。原生 Windows 端到端交互仍需单独验收。

2026-06-08 追加发现：runtime status 只在 `run_chat()` 正常展开到 `finally` 时删除；强杀进程、断电、native crash 或 `os._exit()` 等意外退出会留下 `~/.xcode/sessions/<pid>.json`。当时没有启动时 stale cleanup 或 pid liveness 检查。该问题已记录到 `DEVNOTES.md`。

2026-06-09 修复收口：`RuntimeStatusStore.create()` 写入当前状态前调用 `prune_stale()`，扫描 `~/.xcode/sessions/*.json`；dead pid 文件会删除，alive/current pid 文件保留，无法可靠判断 liveness 时使用 24 小时 TTL 兜底，损坏 JSON 或删除失败不影响 REPL 启动。验证：`pytest tests\test_runtime_status.py -q` 与 `/resume` 聚焦套件通过；原生 Windows 活跃进程视图手工验收仍可随 dashboard/list 场景补记录。

## 10. Memory 自管理权限：2026-05-27

背景：Xcode 通过文件工具维护自己的 memory 文件时，仍会走普通 `write_file` / `edit_file` 审批流程。用户期望 Agent 管理自身记忆时不必反复手动审核，但不能放宽普通文件写权限。

完成内容：

- `MemoryManager.is_memory_write_target()` 负责判断 resolved memory 写入目标。
- `AgentRuntime` 在 `write_file` / `edit_file` 命中 memory-scoped 路径时跳过用户审批。
- 显式 `deny` 仍优先生效，普通项目文件仍走原有审批流程。
- 增加 memory path detection 测试和 AgentRuntime 审批路径测试。

Review 结论：通过。建议后续补一个 explicit `deny` + memory path 的回归测试，防止未来重排审批分支时误放行。

## 11. AgentRuntime 模块化重构第一轮：2026-05-27

背景：`src/xcode_cli/core/agent.py` 同时承载 REPL、slash command、审批 UI、tool call 执行、session resume、context compaction 和 streaming/render 状态，session resume 接入后 review 成本继续升高。

完成内容：

- 新增中文任务手册：`docs/superpowers/plans/2026-05-27-agent-runtime-refactor.md`。
- `COMMANDS` 和 `SlashCompleter` 抽到 `src/xcode_cli/core/commands/slash.py`。
- welcome、命令建议、bottom toolbar、用户/助手基础输出抽到 `src/xcode_cli/core/ui/shell.py`。
- `/resume` 命令编排抽到 `src/xcode_cli/core/conversation/resume.py`。
- `/compact` 和自动 compression checkpoint 编排抽到 `src/xcode_cli/core/conversation/compaction.py`。
- 工具审批菜单和 TTY / non-TTY fallback 抽到 `src/xcode_cli/core/tooling/approval.py`。
- tool call 执行、diff preview、memory auto-allow、工具结果摘要抽到 `src/xcode_cli/core/tooling/execution.py`。
- 补充 `tests/test_agent_tool_loop.py`，覆盖多轮 tool call 不应中途停住。
- 补充 `tests/test_tool_approval.py`，覆盖审批 scope、auto approve 和 non-TTY fallback。
- 补齐 explicit `deny` + memory path 回归测试，锁定 deny 优先于 memory auto-allow。

Review 结论：第一轮通过。`pytest -q` 为 `184 passed`，`py_compile` 和 `git diff --check` 通过；已提交并推送 `fb18243 refactor: modularize agent runtime`。

保留后续项：

- `/env`、`/memory`、`/context`、`/plan` 等具体 command handlers 仍在 `agent.py`，后续可继续拆到 `core/commands/`。
- `_run_llm_loop()` 的 streaming/render orchestration 仍在 `agent.py`，但状态判断已经收口到 `core/ui/streaming.py`；后续可以继续细化边界。
- 工具调用 UI 折叠已实现默认摘要；`Ctrl+O` 展开尚未实现。

## 12. `/compact` + `/resume` 体验优化：2026-05-28

背景：`/compact` 调用 LLM 时用户看不见进度，`/resume` 只能用数字输入选择 session。两者都已有基础能力但交互体验差。

完成内容：

- `ConversationCompactor.compact_history()` 在 `ContextManager.compress()` 前后包裹 Rich `Live` 进度显示（"Compacting context... (Xs)"），复用 `_run_llm_loop()` 的 Thinking Live 模式：`Live(transient=True)` + daemon thread 更新 elapsed time。
- 手动 `/compact` 和自动 compression 共用 `compact_history()`，进度展示自然统一。
- `finally` 保护确保 `compress()` 异常时 `Live` 也停止。
- `ResumeCommandService.run()` TTY 路径改为方向键 ↑/↓ 浏览 + Enter 确认 + Esc 取消。
- `read_key()` 从 `ToolApprovalController._read_key()` 提取为 `approval.py` 模块级函数，`ResumeCommandService` 直接复用。
- `_render_session_list()` / `_refresh_session_list()` 复用审批菜单的 ANSI 光标上移+清行刷新模式。
- 非 TTY 环境回退到 `_run_number_input()`，保持数字输入方式。
- 方案文档：`docs/superpowers/plans/2026-05-28-compact-progress-and-resume-ux.md`。
- 测试：`tests/test_compaction.py`（Live 进度生命周期、异常安全）、`tests/test_resume.py`（TTY 导航、Esc 取消、非 TTY 回退）。

Review 结论：通过。`pytest -q` 为 `208 passed`；已提交并推送 `3f8cb4e feat: add /compact live progress and /resume arrow-key selection`。

2026-06-08 追加发现：`/resume` 方向键菜单在 session 很多、终端较窄或中文预览换行时，可能因为 `_refresh_session_list()` 按固定行数清理而出现重复渲染或旧行残留。该问题已记录到 `DEVNOTES.md`，后续建议改为固定高度窗口或 prompt_toolkit 可控渲染区域，并补原生 PowerShell/cmd.exe 手工验收。

2026-06-09 修复收口：`ResumeCommandService` 的 TTY 菜单改为固定 9 行窗口，header 显示 `current/total`，预览先单行化并按显示宽度截断，刷新固定清理 `header + visible rows + footer` 行，不再按 `len(sessions) + 1` 清理。验证：`python -m py_compile src\xcode_cli\core\conversation\resume.py src\xcode_cli\core\runtime_status.py src\xcode_cli\core\agent.py` 通过；`pytest tests\test_agent_resume_command.py tests\test_resume.py tests\test_runtime_status.py -q` 为 44 passed。尚未补真实 PowerShell/cmd.exe 长列表连续滚动手工记录。

## 13. 项目级配置合并 + /env 仪表盘：2026-05-28

背景：`ConfigStore.load()` 只读全局 `~/.xcode/config.json`，项目级无法覆盖；`max_summary_chars` 在 `ContextManager` 硬编码为 6000，Config 和 `/env` 都管不到；`/env` 子命令散落各处，没有统一的配置入口。

完成内容：

- `Config` dataclass 新增 `max_summary_chars: int = 6000` 字段。
- `ConfigStore.load()` 增加项目级 merge：加载全局配置后检查 `<project>/.xcode/config.json`，存在则字段级浅覆盖，损坏时打印 warning 不崩。
- `ConfigStore.save()` 只写全局文件，项目级 config 由用户手动维护。
- `ContextManager` 压缩 prompt 中 300/400 词软约束统一为 `max_summary_chars` 字符上限；`agent.py` 初始化 `ContextManager` 时补传 `max_summary_chars`。
- `/env` 重写为 `EnvDashboard`（`core/ui/env_dashboard.py`）全屏 TUI：5 项参数（max_tokens / max_summary_chars / response_render_mode / syntax_theme / auto_memory），↑↓ 导航，Enter 编辑，s 保存，q 退出。
- 仪表盘使用 ANSI 局部刷新（同 `approval.py` 模式），导航时不清屏不重绘 banner。
- 旧的 `_handle_env_command` 所有子命令（show/set/unset/base-url/model/theme/max-tokens/edit）移除，改为启动 dashboard + 退出后同步关键字段。
- `SlashCompleter` 和 `ShellUI` 帮助文案同步更新。
- spec + plan 文档：`docs/superpowers/specs/2026-05-28-config-merge-design.md`、`docs/superpowers/plans/2026-05-28-config-merge-plan.md`。
- 测试：`tests/test_config.py`（merge、序列化、损坏文件）、`tests/test_env_dashboard.py`（init、bool 切换、choice 循环、int 校验、save、quit no save、非 TTY）。

Review 结论：通过。合并后 `pytest -q` 为 `221 passed`；已提交并推送 `906e663 feat: add project-level config merge, unified params, and /env TUI dashboard`。Review 后发现三个问题（banner 文案暗示 API 配置、首次 banner 重绘、方向键全屏刷新），修复于 `03ffdbc docs: update project docs for config merge and /env dashboard`。

## 14. 开发流程与测试分层规范：2026-06-04

背景：项目已经形成 `docs/superpowers/specs/` + `docs/superpowers/plans/` + pytest 回归 + acceptance 记录的开发习惯，但此前没有明确写成统一规格。为了让后续 Codex / Coding Agent 协作更稳定，也方便把项目包装成“AI Agent 项目经理”简历叙事，需要把流程和测试取舍文档化。

当前收口：

- 开发流程定为 **Spec-first + TDD-core + E2E-acceptance**。
- `AGENTS.md` 明确 Codex 和 Coding Agent 在规格、任务说明、测试、验收、review 中的职责。
- 测试按 P0/P1/P2 分层：
  - P0 覆盖权限、安全、状态、session、memory、context、Windows 兼容等核心风险，必须有自动化回归测试。
  - P1 覆盖 slash command、task/sub-agent、配置、render state 等用户可见行为，应有聚焦行为测试。
  - P2 覆盖简单 wrapper、文案、低风险展示和文档，可用 smoke test、手工验收或说明替代。
- `DEVNOTES.md` 记录测试噪音边界：不机械测试私有 helper、不重复测试同一分支、不用脆弱 UI 快照替代语义验收。

结果：后续任务 brief 应显式说明本轮属于 P0/P1/P2 哪一层，以及需要运行哪些验证命令。Review 时优先检查 P0/P1 是否有足够测试或手工验收证据。

## 15. `/init` prompt command 实现：2026-06-04

背景：为了让 Xcode 更像一个能接手新仓库的 AI 项目经理，需要补一个旧版 Claude 风格的 `/init`。该命令不直接扫描项目，而是把固定初始化 prompt 当作普通用户任务交给 Agent，使 Agent 自己读取 README、AGENTS、CLAUDE、规则文件和代码结构，最后创建或改进 `XCODE.md`。

设计决策：

- `/init` 定位为 prompt command，不是本地项目扫描器。
- 第一版只做薄命令注册和普通 agent turn 复用，不引入新的工具或后台流程。
- 目标文件使用 `XCODE.md`，保持项目辨识度。
- 如果已有 `XCODE.md`，prompt 要求 Agent 建议改进并优先 edit，不直接覆盖。
- prompt 末尾要求 Agent 总结学到的项目信息和使用过的来源文件，方便 demo 展示。

实现后验收：

- `/init` 已注册到 help 和 slash completion。
- prompt command handler 只返回固定 prompt，不扫描项目、不写文件。
- `AgentRuntime` 将展开后的 prompt 作为普通 user message 写入 `_history` 和 transcript，并复用普通 LLM/tool loop。
- 侧效命令（`/help`、`/context` 等）行为不变，仍返回 `None` 直接处理。
- 测试：`pytest tests/test_init_command.py tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q` 通过（36 passed）。

相关文档：

- 规格文档：`docs/superpowers/specs/2026-06-04-init-command-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-04-init-command-plan.md`

## 16. AgentRuntime Refactor Round 2 完成：2026-06-04

背景：第一轮 AgentRuntime 模块化已经抽出 slash completion、shell UI、resume/compaction、approval、tool execution、streaming 状态等模块，但 `agent.py` 仍然保留 slash command 具体 handler、skill 命令逻辑、普通 user turn 流程和 `_run_llm_loop()` orchestration。下一步准备开发更完整的 skills 功能，如果继续在 `agent.py` 和 `main.py` 中各自扩展 skill 命令，会增加重复和耦合。

本轮完成内容：

- 新增 `src/xcode_cli/core/commands/skill.py`，提供 `SkillCommandService`，让 CLI `xcode skill ...` 和 REPL `/skill ...` 共用 list/install/enable/disable 行为。
- 新增 `src/xcode_cli/core/commands/dispatcher.py`，提供 `SlashCommandDispatcher` 和 `SlashDispatchResult`，把 slash command 路由从 `AgentRuntime` 中移出。
- 新增 `_run_user_turn(user_input: str)`，让普通用户消息和 `/init` prompt command 复用同一条 user turn 路径。
- 保持 `_run_llm_loop()` 不做整体搬迁或重写，避免扩大 streaming、tool loop、Thinking Live、session tool transcript 等高风险回归面。

协作分工：

- Coding Agent 负责代码任务：dispatcher、SkillCommandService、`_run_user_turn()` 抽离和 focused tests。
- Codex 负责文档收口、最终验证、架构 review 和是否进入下一阶段的判断。

验收结果：

- `agent.py` 行数下降，`run_chat()` 更接近 REPL 输入循环，普通 turn 由 `_run_user_turn()` 处理。
- `/help`、`/init`、`/skill`、`/memory`、`/plan`、`/context`、`/resume`、`/compact` 行为在聚焦测试中保持不变。
- `main.py` 和 `agent.py` 不再重复实现 skill 命令业务逻辑。
- `_run_llm_loop()` 未做整体搬迁或重写。
- 每个代码任务完成后均经过 Codex review；测试隔离问题已修复，避免 `/init` 测试触发 ripgrep 网络下载。
- 最终验证通过：
  - `python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/skill.py src/xcode_cli/main.py`
  - `pytest -q`：272 passed
  - `git diff --check -- docs/current/ARCHITECTURE.md docs/current/DEVNOTES.md docs/current/PROGRESS.md docs/current/ROADMAP.md src/xcode_cli/core/agent.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/skill.py src/xcode_cli/main.py tests/test_agent_user_turn.py tests/test_init_command.py tests/test_skill_command_service.py tests/test_slash_dispatcher.py`

开发文档：

- 规格文档：`docs/superpowers/specs/2026-06-04-agent-runtime-refactor-round2-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-04-agent-runtime-refactor-round2-plan.md`

## 17. Skills As Prompt Commands 实现：2026-06-04

背景：在 `/init` prompt command 和 AgentRuntime 第二轮重构之后，skills 可以复用 `SlashCommandDispatcher`、`CommandRegistry` 和 `_run_user_turn()`，不需要另开一条 runtime 分支。本轮目标是实现 Phase 1：把项目内 `.xcode/skills/<skill-name>/SKILL.md` 加载为手动调用的 prompt slash command。

本轮完成内容：

- 移除旧 `skill.json` / `enabled_skills` / system prompt 全量注入壳子。
- 新增 `Skill` model、`SkillLoader`、`SkillPromptExpander`、`SkillValidation` 和动态 `CommandRegistry`。
- 支持 `.xcode/skills/*/SKILL.md` frontmatter 解析，supporting files 只作为按需读取资源，不自动注入上下文。
- 将 user-invocable skill 注册为 `/skill-name` prompt command；skill 与 built-in slash command 冲突时 built-in 优先。
- 新增 `UserTurnInput`，让 UI/session user history 显示 `/skill-name args`，LLM `_history` 使用展开后的 hidden/model prompt。
- `allowed-tools` 采用 Claude-compatible 语义，作为 skill 的工具需求/允许/可预授权声明；当前解析、归一化并记录，不作为 tool schemas 或 execution 白名单。
- `/skill` 与 CLI `xcode skill` 改为 list/show/validate 项目 skills；旧 install/enable/disable 仅提示迁移。
- session transcript 保存 skill invocation metadata，`/resume` 恢复时优先使用 `metadata.model_content`。
- `context: fork` 当前报 unsupported；`hooks` 只解析保存，不执行。

Review 与验证：

- Task 1-8 每个 task 完成后均做 Codex review，并分别提交。
- 最终验证通过：
  - `python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/registry.py src/xcode_cli/core/commands/skill.py src/xcode_cli/core/commands/slash.py src/xcode_cli/core/turn.py src/xcode_cli/skills/model.py src/xcode_cli/skills/loader.py src/xcode_cli/skills/prompt.py src/xcode_cli/skills/validation.py`
  - `pytest tests/test_skill_loader.py tests/test_skill_prompt.py tests/test_skill_validation.py tests/test_skill_command_registry.py tests/test_skill_prompt_command_flow.py tests/test_skill_allowed_tools.py tests/test_init_command.py tests/test_slash_dispatcher.py tests/test_agent_user_turn.py -q`：50 passed
  - `pytest -q`：291 passed
  - `git diff --check`

后续：Phase 2 已在下一轮实现 `SkillTool` 和模型主动调用 skills；Phase 1 不做 fork skill runtime、hooks 执行、paths 自动激活或 `.claude/skills` 自动读取。

## 18. Model-Invocable Skills Phase 2 实现：2026-06-05

背景：Skills As Prompt Commands 完成后，项目 skills 只能由用户手动输入 `/skill-name args` 调用。Phase 2 目标是让模型基于 compact skill listing 主动调用 project skills，同时复用 Phase 1 的 skill prompt expansion、metadata、allowed-tools 和 session/resume 机制。

本轮完成内容：

- 新增 `SkillCatalog` 管理 user/model invocation eligibility，并处理 built-in 冲突。
- 新增 `SkillListingFormatter`，在 system prompt 中注入预算内 compact skill listing。
- 新增 `SkillInvocationService`，作为用户 slash skill 和模型 SkillTool 的共享展开入口。
- 新增 read-only `skill` tool，支持 `skill` 和 `args` 参数。
- SkillTool 成功加载后，当前 user turn 后续 tool schemas 不再包含 `skill`，避免递归调用。
- `user-invocable=false` 但未禁用 model invocation 的 skill 可由模型调用。
- `disable-model-invocation=true` 和 `context=fork` 会被拒绝。
- `allowed-tools` 不再作为 SkillTool 后续工具白名单；SkillTool 只记录这些声明，并通过 blocked-tools 防止递归调用。
- SkillTool 成功加载后作为 tool batch barrier，同一 assistant response 中排在它后面的 sibling tool calls 会被拒绝，要求模型下一步再继续。
- session/resume/compact 保留 loaded skill marker 和 invocation audit metadata。
- `skill_invocation` audit event 不包含完整 `model_content`。

Review 与验证：

- Task 1-6 每个 task 完成后均做 Codex review，并分别提交；Task 7 完成文档和最终验证。
- 编译检查通过：
  - `python -m py_compile src/xcode_cli/skills/catalog.py src/xcode_cli/skills/listing.py src/xcode_cli/skills/invocation.py src/xcode_cli/core/tools/skill_tool.py src/xcode_cli/core/tool_registry.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/commands/registry.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/prompting.py src/xcode_cli/core/agent.py`
- 聚焦测试通过：
  - `pytest tests/test_skill_catalog.py tests/test_skill_listing.py tests/test_skill_invocation_service.py tests/test_skill_tool.py tests/test_model_invocable_skill_flow.py tests/test_prompting_skills.py tests/test_skill_prompt_command_flow.py tests/test_skill_allowed_tools.py tests/test_resume.py tests/test_compaction.py -q`：38 passed
- 全量测试通过：
  - `pytest -q`：315 passed

不包含范围：

- fork skill runtime。
- hooks 执行。
- remote skills。
- skill search。
- paths 条件自动激活。

## 19. QQ `/QQchat` 第一版代码实现：2026-06-05

证据：

- 编译检查通过：`python -m py_compile src\xcode_cli\core\agent.py src\xcode_cli\core\external_turn.py src\xcode_cli\core\commands\dispatcher.py src\xcode_cli\core\commands\slash.py src\xcode_cli\qqchat\config.py src\xcode_cli\qqchat\auth.py src\xcode_cli\qqchat\message_client.py src\xcode_cli\qqchat\events.py src\xcode_cli\qqchat\dedupe.py src\xcode_cli\qqchat\gateway.py src\xcode_cli\qqchat\service.py` 退出码 0。
- 聚焦测试通过：`pytest tests\test_qqchat_config.py tests\test_qqchat_auth.py tests\test_qqchat_events.py tests\test_qqchat_message_client.py tests\test_qqchat_gateway.py tests\test_qqchat_service.py tests\test_external_turn.py tests\test_slash_dispatcher.py tests\test_agent_tool_loop.py -q` 为 `62 passed`。
- 全量测试通过：`pytest -q` 为 `356 passed`。
- `git diff --check` 退出码 0；仅有 Windows LF/CRLF 行尾提示。
- PowerShell/cmd.exe 手工验收：未执行。
- QQ 单聊被动回复验收：未执行。
- QQ 群聊 @ 被动回复验收：未执行。
- 危险工具请求真实 QQ 验收：未执行。

当前实现内容：

- 新增 `xcode_cli.qqchat` 包，包含 config、auth、events、dedupe、message_client、gateway、service。
- 新增 `ExternalTurnRunner` 和入口级 `ToolScope`，QQ turn 按 conversation key 维护独立 session/history。
- `/QQchat start|stop|status` 已注册为 side-effect slash command，不进入普通 LLM prompt command。
- QQ C2C 和 group @ 事件会归一化为内部消息；group 默认按 `group_openid + member_openid` 隔离。
- 默认只暴露并执行 `read_file`、`grep`、`glob`、`task_list`；危险工具即使被配置加入也会被过滤。
- AppSecret、AccessToken、Authorization header 的配置 summary、错误字符串和 external metadata 均有脱敏回归测试。

结论：

- 代码和自动化回归已进入最终验证前状态。
- 真实 QQ 平台和原生 Windows 终端手工验收未执行，不能声称 `/QQchat` 已完整完成真实接入。

## 20. QQ `/QQchat` review 加固：2026-06-08

背景：QQ 第一版实现完成后，review 发现四类风险：gateway callback 内同步跑带 UI 的 LLM loop、配置访问控制字段未执行、QQ `ToolScope` 不是严格只读、gateway reconnect/status 不完整。

本次修复：

- `QQChatService.handle_gateway_event()` 改为 normalize -> config policy -> dedupe -> queue；`qqchat-worker` 串行执行 `ExternalTurnRunner` 和 `QQMessageClient`。
- `AgentRuntime._run_external_llm_loop()` 走 headless `_run_llm_loop()` 参数，不渲染 terminal UI、不启动 Rich Live、不更新本地工具统计，并使用 external turn 独立 blocked-tools set。
- `ToolCallExecutor` 对 `tool_scope.source == "qqchat"` 强制 `ToolDef.is_read_only`，防止 `task_create`、`task_update`、`write_plan` 等非只读工具通过配置 allowlist 修改本地状态。
- `QQChatConfig` 的 `enabled`、`enable_c2c`、`enable_group_at`、`group_allowlist`、`owner_openids`、`max_reply_chars`、C2C/group timeout 已在 service 层执行。
- `QQGatewayClient` 支持 `op=7 Reconnect`、`op=9 Invalid Session`、`run_forever()` 意外返回后的 reconnect/backoff，并将 status 回传到 `/QQchat status`。

新增/更新回归覆盖：

- service queue 不在 gateway callback 内同步跑 runner。
- 禁用 C2C、非 allowlist 群、非 owner openid 不进入 runner。
- 长回复按 `max_reply_chars` 截断，过期群消息丢弃。
- external loop 不渲染终端、不更新本地工具计数。
- QQ scope 中 allowlisted 非只读工具被 execution 层拒绝。
- gateway op7/op9/reconnect/status 回传。

仍未执行：

- 真实 QQ 单聊被动回复验收。
- 真实 QQ 群聊 @ 被动回复验收。
- 原生 PowerShell/cmd.exe 中 `/QQchat start` 与 prompt_toolkit 并存手工验收。

## 21. MCP Phase 1 设计：2026-06-08

背景：用户希望为 Xcode 设计 MCP 接入，并特别强调不要把 MCP 做成“随便启动外部程序并自动暴露给模型”的后门。设计目标是参考主流 Agent 的 MCP 接入方式，但让 Xcode Phase 1 聚焦安全接入 stdio tool provider。

调研依据：

- MCP 官方 transport 文档：stdio 是 client 启动的本地子进程，通过 stdin/stdout 传输 JSON-RPC。
- MCP 官方 tools 文档：server 通过 `tools/list` 暴露工具，通过 `tools/call` 调用，tool schema/result 都来自外部 provider。
- OpenAI Agents SDK：stdio MCP server 作为 local subprocess 管理，server manager 能区分 active/failed servers。
- Claude Code / Claude Agent SDK：MCP tool 命名采用 `mcp__<server>__<tool>`，MCP tools 需要显式 permission。
- VS Code / Claude 安全文档：本地 MCP server 可运行任意代码，新 server 需要 trust verification。
- Windsurf/Cascade：主流 MCP client 提供 server 配置和工具 enable/disable，但 Xcode Phase 1 不做 marketplace。

本次产出：

- 规格文档：`docs/superpowers/specs/2026-06-08-mcp-integration-design.md`
- 总计划：`docs/superpowers/plans/2026-06-08-mcp-integration-plan.md`
- Task 分文件目录：`docs/superpowers/plans/2026-06-08-mcp-integration/`

设计收口：

- Phase 1 只做 `.xcode/mcp.json` 中的 stdio tools。
- trust gate 必须先于启动；trust 绑定配置 hash，写入本机 `~/.xcode/mcp_trust.json`。
- `MCPConnectionManager` 内部允许 async event loop/thread；`AgentRuntime` Phase 1 保持同步 wrapper，后续再逐步 async 化。
- MCP tool 注册为 `mcp__<server>__<tool>`，sanitize 后防冲突。
- MCP tool 默认 `is_read_only=False`，信任 server 不等于允许 tool 调用，仍走 `PermissionManager`。
- `inputSchema` 防御式转换，异常 tool skip + warning。
- `tools/call` result 文本化并按 `max_mcp_output_chars` 截断后再进入 `_history`。
- `/mcp status|trust|untrust|reload` 作为 side-effect slash command。
- failed/untrusted server 不影响 Xcode 启动。

明确不包含：

- resources、prompts、HTTP、SSE、OAuth、`list_changed`。
- MCP prompts 注册 slash command。
- 自动安装、marketplace 或 registry。
- tool search / lazy schema loading。
- AgentRuntime 全局 async 化。

实现计划：进入实现时按 `2026-06-08-mcp-integration-plan.md` 的 8 个 task 执行；每个 task 完成后停下做 Codex review。该功能属于 P0 安全路径，实现时必须先写失败测试。

## 22. MCP Phase 1 实现：2026-06-09

背景：按 `docs/superpowers/plans/2026-06-08-mcp-integration-plan.md` 完成 Phase 1 MCP stdio tools 安全接入。范围保持为 `.xcode/mcp.json` 中的 stdio servers，不做 resources、prompts、HTTP、SSE、OAuth、`list_changed`、marketplace 或自动安装。

本次实现内容：

- 新增 `xcode_cli.mcp` 包：`config.py`、`trust.py`、`naming.py`、`schema.py`、`result.py`、`status.py`、`connection.py`、`tools.py`。
- `.xcode/mcp.json` 支持 `mcpServers`、`${workspace}`、环境变量展开、allow/block/read-only tool 配置和 `max_mcp_output_chars`。
- trust store 写入本机 `~/.xcode/mcp_trust.json`；fingerprint 绑定 project key、server name、type、command、args、resolved cwd 和 env keys，不保存 env values。
- `MCPConnectionManager` 内部使用 async event loop/thread 和同步 wrapper；未信任或 disabled server 不启动，failed server 不影响 AgentRuntime 构造。
- MCP tool 注册为 `mcp__<server>__<tool>`，schema 防御式转换，命名冲突或 invalid schema 会 skip + warning。
- MCP tool 默认 `is_read_only=False`；只有 `.xcode/mcp.json` 中 `read_only_tools` 显式声明才可只读，仍受 `PermissionManager` 显式 deny/ask/allow 约束。
- `tools/call` result 在返回 `ToolOutput` 前文本化并按 `max_mcp_output_chars` 截断；image/audio/resource 只写 omitted 占位。
- 新增 `/mcp status|trust|untrust|reload` side-effect slash command；trust 流展示 command、args、cwd、env keys、hash 和 `npx -y`/`pnpm dlx`/`uvx`/`docker run` 风险提示。
- AgentRuntime 初始化时加载 MCP 配置、启动 trusted servers、注册 MCP ToolDefs；`run_chat()` finally 中 shutdown MCP manager。
- 2026-06-09 follow-up：修复连接/初始化 timeout cancellation 清理风险；`_run_sync()` 取消后等待 coroutine cleanup，`SDKStdioSession.open()` 在 `CancelledError` 路径关闭已进入的 async context。

逐 task review 结论：

- Task 1 通过：未信任状态先于进程启动；trust store 不写项目目录；env secret 不落盘；hash 变化会重新 untrusted。
- Task 2 通过：名称冲突 skip，不覆盖内置工具；schema/result 对外部输入做防御；输出截断发生在进入 tool message 前。
- Task 3 通过：async 异常落到 status/error；shutdown 可重复；sync wrapper 有 timeout，且 timeout 后 cancel pending task 并等待 cleanup。
- Task 4 通过：adapter 默认非只读；read-only 只来自配置；allow/blocklist 按 provider 原名过滤；执行错误被 `ToolRegistry`/adapter 转成 tool result。
- Task 5 通过：`/mcp` 不进入 LLM；trust prompt 展示关键配置和风险提示；usage 输出关闭 Rich markup。
- Task 6 通过：MCP tool 复用现有 `PermissionManager`；explicit deny 覆盖 read-only；failed server 不破坏 AgentRuntime；runtime shutdown 接入。
- Task 7 通过：自动化安全矩阵覆盖完成；2026-06-10 用户确认 PowerShell/cmd.exe 手工验收完成，手工验收步骤已勾选。

验证证据：

- 编译检查通过：`python -m py_compile src\xcode_cli\mcp\config.py src\xcode_cli\mcp\trust.py src\xcode_cli\mcp\naming.py src\xcode_cli\mcp\schema.py src\xcode_cli\mcp\result.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\dispatcher.py src\xcode_cli\core\commands\slash.py` 退出码 0。
- MCP 聚焦安全矩阵通过：`pytest tests/test_mcp_config.py tests/test_mcp_trust.py tests/test_mcp_naming_schema.py tests/test_mcp_result.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_command.py tests/test_mcp_agent_integration.py -q` 为 `57 passed`。
- Task 6 集成聚焦回归通过：`pytest tests/test_mcp_agent_integration.py tests/test_agent_tool_loop.py tests/test_task_permissions.py -q` 为 `27 passed`。
- 全量测试通过：`pytest -q` 为 `432 passed`。
- `git diff --check` 退出码 0；仅有 Windows LF/CRLF 行尾提示。
- 原生 PowerShell fake stdio server 手工验收：2026-06-10 用户确认通过；覆盖 untrusted 不启动、trust/reload 后 connected、工具调用审批 UI 和 `/exit` 后子进程退出。
- 原生 cmd.exe fake stdio server 手工验收：2026-06-10 用户确认通过；覆盖 Windows 路径、中文输出、审批菜单和进程退出。
- MCP tool 审批 UI 真实交互验收：2026-06-10 用户确认通过。
- `/exit` 后真实 stdio server 子进程退出验收：2026-06-10 用户确认通过。

## 23. MCP Phase 2 设计：2026-06-09

背景：Phase 1 已完成 stdio tools 安全接入后，用户确认可以进入 Phase 2 设计。根据 MCP 官方 `tools/list_changed`、Claude Code 动态刷新/tool search、VS Code server 管理与独立 enable state、Cursor tool toggle、Windsurf/Cascade tool toggle 和工具数量上限等主流 MCP 集成模式，本轮不直接扩展 HTTP/OAuth/resources/prompts，而是先设计 stdio tools 的管理面与动态刷新。

本次产出：

- 规格文档：`docs/superpowers/specs/2026-06-09-mcp-phase2-design.md`
- 总计划：`docs/superpowers/plans/2026-06-09-mcp-phase2-plan.md`
- Task 分文件目录：`docs/superpowers/plans/2026-06-09-mcp-phase2/`

设计收口：

- 新增 project-scoped 本机 `mcp_state.json`，保存 server/tool enable-disable 和 per-tool output limit，不写项目仓库。
- 新增 `/mcp status --verbose`、`/mcp tools`、`/mcp enable|disable`、`/mcp tool enable|disable`、`/mcp refresh`、`/mcp reconnect`、`/mcp events`、`/mcp output-limit`。
- 支持 `notifications/tools/list_changed` 或等价 pending refresh event，但 ToolRegistry mutation 只允许在 AgentRuntime safe point 发生。
- 新增 lifecycle event ring buffer，status/events 不泄露 env values。
- 保持 Phase 1 trust gate、PermissionManager、schema/result 防御和 shutdown 约束。

明确不包含：

- HTTP / Streamable HTTP / SSE。
- OAuth / browser auth / token refresh。
- resources、prompts、MCP Apps。
- marketplace、registry、企业 policy。
- 子 Agent 独立 MCP scope。
- model-driven tool search / lazy schema loading。

执行计划：进入实现时按 `2026-06-09-mcp-phase2-plan.md` 的 8 个 task 执行；每个 task 完成后停下做 Codex review。该功能仍涉及 P0 安全路径，实现时必须先写失败测试。

## 23.1 MCP Phase 2 实现：2026-06-10

背景：按 `docs/superpowers/plans/2026-06-09-mcp-phase2-plan.md` 继续实现 Phase 2。范围保持为 stdio tools 管理面与动态刷新，不做 HTTP、SSE、OAuth、resources、prompts、MCP Apps、marketplace、registry 或 model-driven tool search。

本次实现内容：

- 新增 `src/xcode_cli/mcp/state.py`：project-scoped 本机 `mcp_state.json`，保存 server/tool enable-disable 和 per-tool output limit；缺失/损坏 state 可恢复，不写项目仓库。
- 新增 `src/xcode_cli/mcp/catalog.py`：区分 registered、disabled_by_config、disabled_by_state、invalid_schema、name_conflict；disabled/invalid/conflict tools 不进入 OpenAI schema。
- 新增 `src/xcode_cli/mcp/events.py`：lifecycle event 模型和 ring buffer。
- 扩展 `MCPConnectionManager`：pending refresh、manual refresh、reconnect、refresh failure 降级、event 脱敏、旧 session 关闭。
- 扩展 `/mcp`：`status --verbose`、`tools`、`enable|disable`、`tool enable|disable`、`refresh`、`reconnect`、`events`、`output-limit`。
- `AgentRuntime` 使用 effective MCP config，local state 只能额外禁用，不能覆盖 config `enabled=false` 或 trust gate。
- `ToolRegistry` 增加公开 `unregister()` / `unregister_prefix()`，MCP registry rebuild 不再直接操作 `_tools`。
- `notifications/tools/list_changed` 已通过 MCP SDK `ClientSession(..., message_handler=...)` 桥接到 `MCPConnectionManager.mark_tools_changed()`；ToolRegistry mutation 仍只在 AgentRuntime safe point 发生。
- per-tool output limit 在 `render_mcp_tool_result()` 生成 `ToolOutput` 前生效，优先级为 local state override > 全局 `max_mcp_output_chars`。
- enabled MCP tools 超过 100 时只显示 warning，用户可通过 `/mcp tools` 和 `/mcp tool disable` 收敛。

逐 task review 结论：

- Task 1 通过：state store 默认路径为本机 project-scoped；损坏 JSON 不放大权限；secret-like 内容不进入 state/warning。
- Task 2 通过：config/state/schema/name conflict 过滤顺序固定；disabled/invalid/conflicting tools 不进入 schema；read-only 仍只来自 `.xcode/mcp.json`。
- Task 3 通过：管理命令只写本机 state，不写项目 config/trust；server disable 进入 effective config 阻止启动；tool disable 从 registry/schema 移除。
- Task 4 通过：list_changed 只置 pending，不从 background thread 改 ToolRegistry；safe point refresh 成功更新 schema，失败移除旧 tools。
- Task 5 通过：reconnect 先关闭旧 session，再走 trust/effective enabled；失败不崩且移除旧 tools；events/status 脱敏。
- Task 6 通过：per-tool output limit 覆盖全局上限并在 ToolOutput 前截断；工具数量过多只 warning，不做 tool search。
- Task 7 通过：自动化安全矩阵、PowerShell 原生 PTY、cmd.exe 原生 PTY 和 MCP 工具名审批 UI 冒烟均通过。

验证证据：

- 编译检查通过：`python -m py_compile src\xcode_cli\mcp\state.py src\xcode_cli\mcp\catalog.py src\xcode_cli\mcp\events.py src\xcode_cli\mcp\status.py src\xcode_cli\mcp\connection.py src\xcode_cli\mcp\tools.py src\xcode_cli\core\tool_registry.py src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py`。
- MCP Phase 2 聚焦矩阵通过：`pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_management_command.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py -q` 为 `77 passed`。
- cmd.exe 下同一聚焦矩阵通过：`cmd /c pytest tests\test_mcp_state.py tests\test_mcp_catalog.py tests\test_mcp_dynamic_refresh.py tests\test_mcp_management_command.py tests\test_mcp_connection.py tests\test_mcp_tools.py tests\test_mcp_agent_integration.py -q` 为 `77 passed`。
- 全量测试通过：`pytest -q` 为 `504 passed`。
- `git diff --check` 退出码 0；仅有 Windows LF/CRLF 行尾提示。

仍未执行：

- PowerShell 原生 PTY 验收：`winpty.PtyProcess` 启动 `powershell.exe` + `python -m xcode_cli.main`，临时项目设置 `XCODE_PROJECT_ROOT`，临时 fake MCP server 支持 mode 切换。结果：`config_hash_unchanged=True`、`process_exitstatus=0`、`secret_absent_from_transcript=True`、`connected_seen=True`、`tool_disable_seen=True`、`tool_enable_seen=True`、`output_limit_seen=True`、`refresh_extra_seen=True`、`reconnect_seen=True`、`events_seen=True`、`exit_seen=True`；fake server log 显示 `start=3`、`stop=3`。
- cmd.exe 原生 PTY 验收：同一临时项目与同一组 `/mcp` 命令在 `cmd.exe /d /c python -m xcode_cli.main` 下通过，结果同样为 `config_hash_unchanged=True`、`process_exitstatus=0`、`secret_absent_from_transcript=True`、`refresh_extra_seen=True`、`reconnect_seen=True`、`events_seen=True`、`exit_seen=True`，fake server log `start=3`、`stop=3`。
- 审批 UI 原生 PTY 冒烟：PowerShell 和 cmd.exe 中直接调用 `ToolApprovalController.prompt("mcp__fake__echo", "mcp__fake__echo")`，真实菜单渲染 `Apply mcp__fake__echo for mcp__fake__echo?`，输入 `y` 后 `approval_result=yes`。

结论：MCP Phase 2 代码实现、自动化安全回归和 PowerShell/cmd.exe 原生 PTY 交互验收已完成；Phase 2 仍只覆盖 stdio tools 管理面，不包含 HTTP/OAuth/resources/prompts/MCP Apps。

Review follow-up（2026-06-10）：
- P1 修复：真实 SDK `notifications/tools/list_changed` 已接到 `mark_tools_changed(server.name)`，补 `SDKStdioSession.open()` message handler 回归测试。
- P1 修复：`call_tool_sync()` 执行异常会按 server env value、token、secret-like 文本脱敏后再返回 tool result，避免 secret 进入 history。
- P2 修复：动态 refresh 后 `_mcp_tool_warnings` 重新按当前 catalog 计算，bad schema 修复后旧 warning 会消失。
- P2 修复：`/mcp refresh` 和 `/mcp reconnect` 遇到 failed/untrusted/disabled 状态时输出 `requested; check /mcp status`，不再无条件提示成功。

## 24. `/resume` 恢复后最近对话渲染：2026-06-10

背景：此前 `/resume` 成功后只打印恢复摘要和最近一条用户输入，用户无法直接看到最新 checkpoint 之后这段 session 的最近对话。用户希望恢复后能看到 checkpoint 后所有用户输入和助手最终输出，以便确认当前 session 最近聊到了哪里。

本次产出：

- 规格文档：`docs/superpowers/specs/2026-06-09-resume-recent-conversation-rendering-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-09-resume-recent-conversation-rendering-plan.md`
- 代码实现：`src/xcode_cli/core/session_resume.py` 新增 `ResumeReplayMessage` 和 `build_resume_replay_messages()`；`src/xcode_cli/core/conversation/resume.py` 在恢复成功后渲染 replay。

当前实现：

- 只做 `/resume` 成功后的用户可见 replay，不改变 `SessionResumeBuilder` 构造 LLM `_history` 的语义。
- replay 使用 transcript display content；skill prompt command 不展示 `metadata.model_content`。
- 只展示 user 和有文本 `content` 的 assistant final message；跳过 tool result、system summary 和 audit event。
- 第一版按最新 checkpoint 边界展示全部 post-checkpoint user/assistant 对话；无 checkpoint 时展示 transcript 中已有 user/assistant 对话。
- TTY 与非 TTY `/resume` 成功路径共用 `_restore_selected_session()`，只有恢复成功后才读取 replay；失败、取消、无 session 不渲染。
- Rich 输出使用 `markup=False` / `highlight=False`，避免用户输入中的 `[xxx]` 被当作 markup。

验证：

- 先补失败测试，确认缺少 replay helper 时聚焦套件失败。
- PowerShell：`pytest tests\test_session_resume.py tests\test_resume.py tests\test_agent_resume_command.py -q`：45 passed。
- cmd.exe：`cmd /c pytest tests\test_session_resume.py tests\test_resume.py tests\test_agent_resume_command.py -q`：45 passed。
- 原生 PowerShell/cmd.exe 手工验收：2026-06-10 用户确认通过；覆盖 checkpoint 后多轮 replay、tool result 不显示、skill hidden prompt 不泄露，以及固定 9 行长列表连续操作。
- 同轮核心 CLI E2E 还确认 `/compact` Rich Live 进度正常，多轮 tool call 在 PowerShell/cmd.exe 中可持续推进且不会被 UI 状态中断。

## 25. Compact 可靠性重设计文档：2026-06-11

背景：QQchat 长会话在多次 compaction 后出现连续 `No response.`。复核用户提供的 session JSONL 后，确认失败链路是：坏 compact summary 污染 history、重复压缩放大上下文退化、模型返回空 assistant message，随后 `ExternalTurnRunner` 把 `No response.` 当作正常 assistant 文本写入外部会话历史。

本节记录 2026-06-11 的设计和实施文档阶段；当时未修改运行时代码。2026-06-12 的代码实现和验证见下一小节。

本次产出：

- 规格文档：`docs/superpowers/specs/2026-06-11-compact-reliability-design.md`
- 总实施计划：`docs/superpowers/plans/2026-06-11-compact-reliability-plan.md`
- 逐 task 文档：
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-01-no-response-error-boundary.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-02-tool-free-summary-request.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-03-summary-quality-gate.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-04-pair-safe-compact-tail.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-05-boundary-restoration-metadata.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-06-tool-result-microcompact.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-07-qqchat-compact-resilience.md`
  - `docs/superpowers/plans/2026-06-11-compact-reliability/task-08-docs-final-verification.md`

设计结论：

- `No response.` 必须在 QQchat/external turn 边界视为 LLM 错误，不能作为普通 assistant message 进入 session/history。
- compact summary 生成要进入显式 no-tool 模式，且必须增加质量门，拒绝 `<tool_call>`、JSON tool call、空摘要和 provider/protocol 泄漏。
- compact 后的 tail 必须保护 OpenAI-compatible `assistant.tool_calls` / `tool` 配对，不得保留 orphan tool message。
- 旧大工具结果应先做 micro-compact，减少大输出触发反复 full compaction。
- 压缩结果应升级为有 boundary、`summary_format=xcode.v2`、可观测 metadata 和恢复上下文的上下文重写流程。

验证状态：

- 已核对 Claude Code 官方文档中 `/compact`、context window、cost/context management 相关说明，并在 spec/plan 中记录引用。
- 已核对当前 Xcode 相关代码路径：`ContextManager.compress()`、`ConversationCompactor.compact_history()`、`AgentRuntime._run_llm_loop()`、`ExternalTurnRunner.run()`、QQ gateway reconnect/heartbeat 路径。
- 未运行代码测试，因为本轮只写规划文档，未修改运行时代码。

### 25.1 Compact 可靠性实现收口：2026-06-12

状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY `/compact` handler 验收已完成；真实 QQ 单聊/群聊回归由用户接手。

本次实现：

- `ExternalTurnRunner` 把 `No response.` 和外部 LLM 异常归入错误边界，不再把空回复兜底文本写入 assistant history；QQchat 发送安全中文 fallback。
- `LLMClient.complete(tool_schemas=[])` 不再传 `tools` / `tool_choice`，summary 请求进入真正 no-tool 模式。
- `ContextManager.compress()` 使用结构化 summary prompt 和 `validate_compact_summary()` 质量门，拒绝空摘要、`<tool_call>`、tool/function-call JSON 泄漏和低于动态最小长度的摘要；最小长度按 `source_token_estimate` 分档为 80 / 300 / 600 / 1000 字符，拒绝时保留原 history。
- compact tail 改为 pair-safe：保留完整 `assistant.tool_calls` / `tool` 配对，移除 orphan tool 和缺 result 的 assistant tool call。
- checkpoint 升级为 boundary system message + summary system message + `compaction_checkpoint` event，`summary_format=xcode.v2`，记录 `protected_tail_messages`、`micro_compacted_tool_results` 等元数据。
- 旧的大型 tool result 会在 protected tail 之外 micro-compact，保留 `role`、`tool_call_id` 和简短来源说明，降低反复 full compaction 风险。
- QQchat 对 benign heartbeat close 降噪，避免 reconnect/stop 期间的 `Connection is already closed.` 覆盖真实 compact/LLM 错误。

逐 task review 结论：Task 1-7 均按 TDD 写入回归测试并通过聚焦验证；未发现会让 `No response.`、坏 summary、orphan tool message 或 benign heartbeat close 继续污染长期历史的实现缺口。

最终验证证据：

- 编译检查通过：`python -m compileall -q src`，退出码 0。
- compact/QQchat 聚焦回归通过：`pytest tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_gateway.py tests/test_llm.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q`，`95 passed`。
- 全量测试通过：`pytest -q`，`533 passed`。
- whitespace 检查通过：`git diff --check`，退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。
- 原生 PTY `/compact` handler 验收通过：`winpty.PtyProcess` 分别启动 PowerShell 和 cmd.exe，临时 session 通过 slash dispatcher 触发 `/compact`；两者均写出 `summary_format=xcode.v2` checkpoint，`handled=true`、`boundary_written=true`、`protected_tail_messages=8`、`micro_compacted_tool_results=1`、`rejected_summary=false`、summary request 未传 `tools` / `tool_choice`，且 compacted model history 无 orphan `tool` message。
- 真实 QQ 平台验收由用户接手：脱敏 QQ auth 连通性检查曾在沙箱内失败为本地 socket 权限拒绝（`WinError 10013`）；2026-06-12 用户明确表示 QQ 测试由用户自己执行，本轮功能代码完成即可。
- 2026-06-12 malformed tool call follow-up：复现 `messages[22].tool_calls[0] is missing a function name`，确认本地 session `D--Xcode/sessions/df9c728e-59e5-4008-a9f6-d4fbd5476970.jsonl` line 22 存在 `id=""` / `function.name=""` 的旧 assistant tool call。新增清洗层后，该 session 经 `SessionResumeBuilder` 恢复结果为 `bad_tool_calls=[]`；聚焦回归 `pytest tests/test_llm.py tests/test_session_resume.py tests/test_context.py tests/test_compaction.py tests/test_agent_resume_command.py tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_gateway.py -q` 为 `116 passed`，全量 `pytest -q` 为 `537 passed`。
- 2026-06-13 review follow-up：`sanitize_model_messages()` 改为按 assistant 后面的连续 tool result batch 校验配对，避免乱序 tool result 让 assistant `tool_calls` 被误判为完整；新增 `tests/test_message_history.py` 覆盖乱序 result 和正常连续配对。重新验证 `python -m compileall -q src`、相关回归 `119 passed`、全量 `pytest -q` 为 `546 passed`，`git diff --check` 仅有 LF/CRLF 提示。

## 26. Compact 现场恢复与 checkpoint 链路：2026-06-12

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY restored-context `/compact`、v3 `/resume` 和 QQchat 平台手工验收未执行/未记录，因此本项仍保留手工验收缺口。

背景：`xcode.v2` compact 已解决坏 summary、orphan tool message、旧大工具结果和 QQchat `No response.` 污染问题，但 compact 后仍主要依赖 summary 和 pair-safe tail。长任务继续工作时，模型还需要 deterministic 的当前现场，例如 active file、最近 read_file excerpt/hash、build/test diagnostics、当前 plan 和已调用 skill metadata。多次 compact 的 summary 虽然已有累计文本，但 transcript 中还缺少 checkpoint parent/hash 等可审计链路。

文档：
- `docs/superpowers/specs/2026-06-12-compact-state-restoration-design.md`
- `docs/superpowers/plans/2026-06-12-compact-state-restoration-plan.md`

实现结果：

- 新增 `src/xcode_cli/core/work_state.py`，`WorkStateTracker` 作为 in-memory 现场状态层，记录 `read_file` excerpt/hash/line range、`edit_file`/`write_file` 路径与 hash、`grep`/`glob` 摘要、`run_shell` build/test diagnostics 和 skill metadata；记录过程 best-effort，异常不会冒泡到 Agent loop。
- `ToolCallExecutor`、本地 `AgentRuntime` 和 `ExternalTurnRunner` 已接入 optional work state；本地 REPL、不同 QQ/external conversation 之间使用独立 tracker。
- compact 成功后在 summary checkpoint 后插入单独的 `Compact restored context` system message；summary 负责历史脉络，restored context 负责继续工作的现场。运行时 `_history` 不再固定保留第一条 user message，首轮意图和约束由累计 summary 覆盖；若第一条 user 同时也是最新 user，则只通过 pair-safe protected tail 保留。summary rejection 时不改写 `_history`、不写 checkpoint、不插入 restored context。
- checkpoint metadata 升级到兼容的 `summary_format=xcode.v3`，新增 `checkpoint_id`、`parent_checkpoint_id`、`checkpoint_index`、`summary_hash`、`previous_summary_hash`、`restored_context_hash` 和 `restored_context_sections`。
- transcript 写入顺序为 compact boundary `message(system)`、checkpoint summary `message(system)`、`compaction_checkpoint` event、restored context `message(system)`；运行时 `_history` 中 restored context 位于 summary 后、protected tail 前。
- `/resume` 对 v3 checkpoint 重建 boundary + summary，并保留 checkpoint event 后的 restored context message；旧 `xcode.v1/v2` checkpoint 继续兼容。
- restored context 有字符上限和 secret redaction，覆盖 Authorization Bearer/QQBot/Basic/Token、JSON/YAML/冒号/等号形式的 `client_secret`、`access_token`、`api_key`、`app_secret`、`QQ_BOT_CLIENT_SECRET`，以及常见 CLI secret 参数；不写完整文件、完整 shell 输出、skill body、MCP secret 或 QQ token。
- `xcodebuild test`、`swift test`、`npm/pnpm/yarn test`、`npm/pnpm/yarn run test` 会归为 latest tests；plan-mode 的 `write_plan` 和 `exit_plan_mode` 会更新 `WorkStateTracker.current_plan`，供 compact restored context 恢复当前计划。

自动化证据：

- `python -m compileall -q src`：退出码 0。
- 聚焦回归：`pytest tests/test_work_state.py tests/test_agent_tool_loop.py tests/test_external_turn.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py tests/test_agent_resume_command.py -q`，2026-06-14 追加修复后为 `119 passed in 15.65s`。
- summary 动态最小长度回归：`pytest tests/test_context.py tests/test_work_state.py tests/test_compaction.py tests/test_session_resume.py tests/test_agent_tool_loop.py -q`，`94 passed in 22.52s`。
- 全量回归：`pytest -q`，`570 passed in 40.41s`。
- whitespace 检查：`git diff --check` 退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。

手工验收记录：

- PowerShell/cmd.exe 原生 PTY `/compact` with restored context：未执行/未记录。
- PowerShell/cmd.exe 或真实 session `/resume` from v3 checkpoint：自动化覆盖 v3 恢复结构；原生 PTY 手工验收未执行/未记录。
- QQchat same-conversation continuation：自动化覆盖 external work-state 隔离；真实或 controlled QQchat compact continuation 手工验收未执行/未记录。
- QQchat conversation isolation：自动化覆盖不同 conversation tracker 隔离；真实 QQ 平台隔离验收未执行/未记录。
- Transcript inspection：自动化覆盖 v3 parent/hash metadata、写入顺序和 secret redaction；真实 session 手工检查未执行/未记录。

### 26.1 手动 `/compact` 语义放宽：2026-06-15

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工验收未执行/未记录。

本轮实现：

- `/compact` handler 只有在 `_history` 为空时显示 `Nothing to compact.`；非空短会话会进入 compact 流程。
- `ContextManager.compress()` 去掉 `len(messages) <= 20` 硬门槛；手动触发且常规 middle 为空时，使用清洗后的完整 history 作为摘要源。
- `validate_compact_summary()` 只拒绝空摘要；不再因摘要少于 80 字符、低于动态长度分档、出现 `<tool_call>`、`tool_calls`/`function_call` 或 tool-call JSON 形态而拒绝。
- `CompressionResult` 增加 `status` / `failure_reason`，区分 `no_input`、`empty_summary` 和 `summary_request_failed`；失败路径不改写 `_history`，不写 checkpoint。
- 成功路径继续写 `xcode.v3` boundary、summary checkpoint、`compaction_checkpoint` event 和可选 restored context，pair-safe tail 与 message history 清洗保持不变。

验证：

- `pytest tests/test_work_state.py tests/test_agent_tool_loop.py tests/test_external_turn.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py tests/test_agent_resume_command.py -q`：`110 passed in 14.25s`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`557 passed in 31.27s`。

剩余缺口：PowerShell/cmd.exe 原生 PTY 下手动 `/compact` 的真实交互验收未执行/未记录。

## 27. Roadmap 完成项迁移：2026-06-13

本轮按“ROADMAP 只保留未来计划、未完成能力和仍需验收风险”的原则，清理 `docs/current/ROADMAP.md` 中已经完成或已经有详细进度记录的内容。以下条目不再在 ROADMAP 中展开，后续查实现细节看 `ARCHITECTURE.md`，查过程和证据看本文件对应章节：

- compact 可靠性重设计：实现与验证证据见 `25.1 Compact 可靠性实现收口`。
- `dispatch_agent` 本地主会话免审：实现状态已进入当前状态总览，设计和任务文档保留在 `docs/superpowers/specs/2026-06-11-dispatch-agent-auto-allow-design.md` 与 `docs/superpowers/plans/2026-06-11-dispatch-agent-auto-allow.md`。
- runtime status stale cleanup：实现与验证已记录在 `9. Session Resume` 的 2026-06-09 修复收口。
- `/resume` 固定 9 行长列表、最近对话 replay、多轮 tool call 原生终端验收：实现与 PowerShell/cmd.exe 验收记录见 `12. /compact + /resume 体验优化` 和 `24. /resume 恢复后最近对话渲染`。
- MCP Phase 1/2：安全接入、管理面、动态刷新和 PowerShell/cmd.exe 原生 PTY 验收已在 `23. MCP Phase 2` 及此前 MCP Phase 1 记录中收口；ROADMAP 只保留后续生态候选，不再重复 MCP 已完成范围。
- 已完成归档表从 ROADMAP 移除；完成项以本文件的历史章节和顶部状态总览为准。

## 28. 当前未完成项入口

当前阻塞、遗留项和下一步 backlog 已迁移到 `docs/current/ROADMAP.md`。本文件只维护历史推进过程、完成证据和迁移记录，避免与 ROADMAP 双写不同步。

## 29. Skill args 兜底注入：2026-06-15

状态：代码实现和自动化回归已完成。

本轮实现：

- `SkillPromptExpander.expand()` 保留既有 `$ARGUMENTS` 替换和 `${XCODE_SKILL_DIR}` 替换。
- 当传入 args 非空且 skill 正文没有 `$ARGUMENTS` 时，在展开后的 prompt 末尾追加：

```text
ARGUMENTS:
<args>
```

- 追加判断只用 `args.strip()` 判断是否为空，模型可见内容保留原始 args 文本。
- 用户 slash skill 路径和模型 `skill` tool 路径共享同一 expander 行为；未改变 session display content、`metadata.model_content` 恢复语义、SkillTool read-only、blocked-tools 或 audit metadata 边界。
- 未实现 `$0/$1/$foo/$ARGUMENTS[0]`、shell-like quoting、命名参数或新的 frontmatter 字段。

验证：

- TDD RED：`pytest tests/test_skill_prompt.py::test_appends_arguments_when_body_has_no_arguments_placeholder tests/test_skill_prompt.py::test_does_not_append_arguments_when_placeholder_was_used tests/test_skill_prompt.py::test_does_not_append_arguments_when_args_are_blank -q`，`1 failed, 2 passed`，失败点为无占位符时未追加 `ARGUMENTS:`。
- `pytest tests/test_skill_prompt.py -q`：`5 passed`。
- `pytest tests/test_skill_prompt_command_flow.py::test_skill_dispatch_appends_args_when_body_has_no_placeholder -q`：`1 passed`。
- `pytest tests/test_skill_prompt_command_flow.py -q`：`6 passed`。
- `pytest tests/test_skill_tool.py::test_skill_tool_appends_args_when_body_has_no_placeholder -q`：`1 passed`。
- `pytest tests/test_skill_tool.py -q`：`4 passed`。
- `pytest tests/test_skill_prompt.py tests/test_skill_prompt_command_flow.py tests/test_skill_tool.py tests/test_skill_invocation_service.py -q`：`18 passed`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`565 passed`。
- `git diff --check`：退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。

## 30. QQchat 多段回复：2026-06-15

状态：代码实现和自动化回归已完成；真实 QQ 平台单聊/群聊多段回复验收未执行。

本轮实现：
- QQchat 不再把超过 `max_reply_chars` 的 assistant 回复直接截断为单条消息。
- `QQChatService` 会按 `max_reply_chars` 将回复切成多段，连续调用 QQ 被动文本回复接口。
- 第一段沿用当前 `msg_seq`，后续段使用 `msg_seq + 1`、`msg_seq + 2` 递增，保留 QQ 单条 HTTP 消息长度保护。
- `max_reply_chars <= 0` 保留不分段发送的语义；空回复仍不发送。
- external turn error 的安全中文 fallback 继续由 QQchat 发送，若超过上限也走同一分段逻辑。

验证：
- TDD RED：`pytest tests/test_qqchat_service.py::test_reply_content_is_split_into_multiple_messages_with_incrementing_msg_seq -q` 先失败，确认为旧实现只发送 `["abc"]`。
- GREEN：`pytest tests/test_qqchat_service.py::test_reply_content_is_split_into_multiple_messages_with_incrementing_msg_seq -q`：`1 passed`。
- QQchat service 回归：`pytest tests/test_qqchat_service.py -q`：`14 passed`。
- QQchat 邻近回归：`pytest tests/test_qqchat_service.py tests/test_qqchat_config.py tests/test_qqchat_message_client.py -q`：`23 passed`。
- 编译检查：`python -m compileall -q src`：退出码 0。

## 31. Auto memory extraction v2：2026-06-24

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工交互验收未执行、未记录。Auto memory recall v2 已另于 2026-06-30 完成代码实现和自动化回归。

本轮实现：

- 主 agent auto memory prompt 和 `MemoryWriter` 已升级到 v2 topic：frontmatter 使用 `name`、`description`、顶层 `type`，正文必须包含 `Evidence:`。
- 新增 `memory_extraction_policy.py`，在写入前拒绝缺失 evidence、泛化 slug、任务摘要和 secret-like 内容；显式 `deny write_file` 仍优先。
- `MemoryManifestScanner` 默认读取 v2 顶层 `type`，旧 `metadata.type` topic 会以 warning 跳过。
- 新增 `memory_tools.py`，为 extraction subagent 提供 memory-only `read_file`、`write_file`、`edit_file`、`glob` sandbox；不暴露 shell、git、MCP、项目读、`dispatch_agent` 或 skill/user hooks。
- 新增 `MemoryExtractionSubagent`，继承主 v2 memory prompt，注入 manifest 和 extraction user message，最多 5 个模型 turn，单次最多保存 3 个 topic。
- 新增 `MemoryExtractionRunner`，after-turn hook 非阻塞 submit，runner single-flight，overlap 只保留 latest pending event，完成后执行 trailing run，支持 bounded shutdown。
- `AgentRuntime` 已接入 background runner；本地 REPL 成功 turn 才提交，QQchat/external/headless turn 不触发 long-term memory extraction。

逐 task review 结论：

- Task 01：通过。v2 prompt、writer 和 policy guard 覆盖 evidence、legacy format、generic slug、task summary 和 secret-like 拒绝。
- Task 02：通过。manifest scanner 默认 v2 顶层 `type`，legacy `metadata.type` 只 warning/skip。
- Task 03：通过。memory-only sandbox 限制 read/write/edit/glob 到 auto memory scope，且不暴露高风险工具。
- Task 04：通过。subagent loop 有 5 turn 上限、3 topic 保存上限和 manifest 去重上下文。
- Task 05：通过。runner single-flight、latest pending、trailing run 和 shutdown 语义有回归覆盖。
- Task 06：通过。Agent hook 非阻塞接入，本地 REPL 与 QQchat/external/headless turn 隔离。
- Task 07：通过。文档同步和最终验证完成；原生 PTY 手工验收缺口明确保留。

验证：

- `pytest tests/test_prompting_memory_v2.py -q`：`2 passed in 0.33s`。
- `pytest tests/test_memory_manifest_v2.py -q`：`4 passed in 0.23s`。
- `pytest tests/test_memory_extraction_policy.py -q`：`5 passed in 0.20s`。
- `pytest tests/test_memory_extraction_subagent.py -q`：`8 passed in 0.46s`。
- `pytest tests/test_memory_extraction_runner.py -q`：`4 passed in 0.22s`。
- `pytest tests/test_agent_memory_extraction_v2.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q`：`16 passed in 2.49s`。
- `pytest tests/test_memory_extraction.py tests/test_memory_manifest.py tests/test_memory.py -q`：`50 passed in 3.49s`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`614 passed in 32.39s`。
- `git diff --check`：退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。

## 32. Auto memory recall v2：2026-06-30

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工交互验收未执行、未记录。QQchat/external/headless 隔离目前由自动化回归覆盖，未做真实平台手工记录。

本轮实现：

- `RelevantMemoryState` 增加 surfaced/touched/surfaced bytes 之外的 late、warnings 和 last_result 审计字段，snapshot 会复制可变集合。
- `AgentRuntime._start_memory_prefetch()` 增加 auto-memory、忽略记忆语义、空/过短 query、session cap 和 manifest gate；只在本地 REPL user turn 提交后台 prefetch。
- `MemoryManifestEntry` 增加 `name`；selector 输入使用 v2 manifest 的 filename/name/description/type/mtime/source。
- `MemoryRecallService` selector 保持 no-tool side query（`tool_schemas=[]`），默认复用主 agent LLM，不新增独立 recall model。
- Agent tool loop 只记录本地 REPL 成功执行的工具名，最多 10 个 distinct names，并传给 selector；不记录 args、path、command、output 或 secret。
- selector 输出严格过滤：只接受 manifest 中的 `.md` 文件名，重复、编造、路径分隔符、非法 JSON 和 selector 异常均 fail closed。
- 选中 topic 每轮最多 5 个；每个文件最多 4096 bytes 或 200 行；截断时追加 `read_file` 完整读取提示。
- reminder 改为 `<system-reminder>`，包含 memory age 和 point-in-time verification 提醒。
- `_run_llm_loop()` 只在当前 turn 的安全点消费已完成 prefetch；迟到 prefetch 标记 late，不注入下一轮 unrelated turn。
- 注入前再次过滤 session 已 surfaced 和本轮 touched 的 auto memory 文件。
- `RelevantMemoryAudit` 和 `/memory` 最近 recall 摘要提供本地 debug surface；普通回复和 transcript 不写 selector 输入、manifest 全量列表、工具参数、工具输出或 memory 正文。

逐 task review 结论：

- Task 01：通过。trigger gates 和 recall state 已收紧；短 query 规则没有挡住正常中文短句；external/headless 不共享本地 recall state。
- Task 02：通过。selector 输入使用 v2 manifest 和 bounded recent tool names；没有解析工具结果文案，也没有泄漏工具参数、路径或输出。
- Task 03：通过。bounded read、截断提示、UTF-8 byte 计数和 point-in-time reminder 已覆盖；topic 正文不常驻 base prompt。
- Task 04：通过。prefetch future turn-local，安全点注入一次；late/stale future 不污染后续 turn；touched-path 二次过滤生效。
- Task 05：通过。fail-closed 和 audit summary 覆盖 selector/future 异常、非法 JSON、路径分隔符和读取失败；普通对话输出无 debug 噪声。
- Task 06：通过。文档同步和最终验证完成；原生 PTY/真实平台手工验收缺口明确保留。

验证：

- `pytest tests/test_memory_manifest_v2.py -q`：`4 passed in 0.21s`。
- `pytest tests/test_memory_recall_v2.py -q`：`13 passed in 0.57s`。
- `pytest tests/test_agent_memory_recall_v2.py -q`：`13 passed in 2.66s`。
- `pytest tests/test_prompting_memory_v2.py -q`：`2 passed in 0.19s`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`642 passed in 39.93s`。
- `git diff --check`：退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。

## 33. 本地审批拒绝中断当前 turn：2026-06-30

状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 交互验收已完成。

本轮实现：

- `ToolExecutionResult` 增加 `interrupted_by_user` 和 `interruption_message`，只有本地 `ToolApprovalController.prompt()` 返回 `No` 时置位。
- 审批 `No` 后写入 `"User denied tool: <tool>"` 的 tool result，并停止同 batch 后续 sibling tool calls；被拒绝工具和后续工具均不会执行。
- `AgentRuntime` 新增 `LLMLoopResult` 作为 `_run_llm_loop()` 的内部结构化结果；旧 `_run_llm_loop(...) -> str` wrapper 保持兼容。
- runtime 在写入 assistant/tool 配对后追加 system marker `[Request interrupted by user for tool use]`，并结束当前 turn，不再向 LLM 发起第二次请求。
- `_run_user_turn()` 对 `append_assistant=False` 的中断结果不追加伪 assistant final text，也不运行 after-turn success hooks，因此不会触发 auto memory extraction。
- session/resume 回归证明：下一次 user turn 的模型请求能看到上一轮拒绝记录和中断 marker；`last_user_input` 不会被 system marker 替换；`SessionResumeBuilder` 恢复后不产生 orphan tool message。
- 显式配置 `deny`、外部入口 `remote_approval=False`、blocked tool、unknown tool 和工具执行异常仍按普通 tool error 进入下一轮模型。

逐 task review 结论：

- Task 01：通过。发现并改写旧“用户拒绝后继续”的测试残留；执行层只在本地审批 `No` 时中断，explicit deny 仍继续模型 follow-up。
- Task 02：通过。新增结构化 loop result 后，review 发现并修复了 `_run_user_turn()` 中 plan mode 分支缩进回归；相关 user-turn、memory hook 和 skill prompt command 测试通过。
- Task 03：通过。新增 session/resume/下一轮上下文回归测试；现有实现天然满足，无需额外生产代码。
- Task 04：通过。自动化验证、PowerShell/cmd.exe 原生 PTY 验收、文档更新和 UTF-8 编码抽样完成。

验证：

- `pytest tests/test_agent_tool_loop.py tests/test_agent_user_turn.py tests/test_session_resume.py -q`：`46 passed in 16.36s`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`649 passed in 39.90s`。
- `git diff --check`：退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。
- PowerShell 原生 PTY `run_shell` 拒绝验收：WinPTY 驱动 `powershell.exe -NoLogo -NoProfile`，审批菜单输入 `n`；`calls=2`（第二次来自下一条用户输入）、`executed=[]`、拒绝后到下一条用户输入前无第二次模型请求、history 包含 tool denial 和 system marker，下一轮模型请求角色序列为 `user, assistant, tool, system, user`。
- cmd.exe 原生 PTY `run_shell` 拒绝验收：WinPTY 驱动 `cmd.exe`，同场景同结果，`executed=[]` 且拒绝记录和中断 marker 保留。
- PowerShell 原生 PTY `write_file` 拒绝验收：WinPTY 驱动 `powershell.exe -NoLogo -NoProfile`，diff preview 中可见 `old text` -> `new text`，审批输入 `n`；`calls=1`、`executed=[]`、文件内容仍为 `old text`，history 包含 tool denial 和 system marker。

## 34. Shell 后台任务最小闭环：2026-07-17

状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生进程验收已完成。

本轮按以下设计和计划完成：

- `docs/superpowers/specs/2026-07-17-shell-background-task-design.md`
- `docs/superpowers/plans/2026-07-17-shell-background-task-plan.md`

完成内容：

- 新增 `ShellTaskManager`，从 spawn 起注册同一进程，支持快速完成、`run_in_background=true` 显式后台和等待预算耗尽原地后台三条路径。
- 新增 `shell_task_output`、`shell_task_list`、`shell_task_stop`；后台输出继续以固定二进制块 drain，内存与临时日志 bounded，未知 task ID 和 stop 失败均转换为可控工具错误。
- Windows 使用 `taskkill.exe /T /F` 停止未 detach 的受管进程树，POSIX 使用独立 process group；root-only fallback 不标记 `stopped`。重复 stop/shutdown 幂等，监听端口和子进程树释放已有回归与原生 smoke 证据。
- `AgentRuntime` 持有 manager-bound 四工具并在 `run_chat()` 的 `finally` shutdown；一次性 CLI 和 General sub-agent 保留硬超时 `run_shell`，General/Explore/Plan 均不获得后台任务管理工具。
- `shell_task_stop` 复用 shell 审批域；QQchat/external 在 scope sanitize 和执行层双重禁止 shell task 工具，伪造只读 allowlist 也不能读取本地日志。
- 未实现 `Ctrl+B`、后台完成主动通知、ready 探测、跨 session 恢复或命令关键词识别；shell 内部自行 detach 的后代不承诺可管理。

验收证据：

- 聚焦回归：`pytest tests/test_shell_tasks.py tests/test_shell.py tests/test_tool_approval.py tests/test_task_permissions.py tests/test_external_turn.py tests/test_agent_tool_loop.py tests/test_agent_memory_extraction_v2.py -q`，`84 passed in 17.75s`。
- `python -m compileall -q src`：退出码 0。
- 全量 `pytest -q`：`672 passed in 54.97s`。
- `git diff --check`：退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。
- PowerShell 原生宿主：8 条生命周期、监听端口和并发 shutdown 聚焦测试，`8 passed in 9.34s`。
- cmd.exe 原生宿主：同 8 条聚焦测试，`8 passed in 10.10s`。
- 两种宿主额外运行真实 OS smoke，均输出 `PASS explicit timeout output process-tree-stop runtime-shutdown`：覆盖显式后台短时间返回、后台追加 `LATE`、50ms 后同 task/PID 自动后台、worker + grandchild 全树停止，以及 `/exit` finally shutdown。该场景无 stdin 或终端热键，不需要 WinPTY。
