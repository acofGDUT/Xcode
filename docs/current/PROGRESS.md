# Xcode 开发进度

> 本文档记录项目如何一步步走到现在。当前实现细节见 `ARCHITECTURE.md`，未来计划见 `ROADMAP.md`，已知问题和设计取舍见 `DEVNOTES.md`。

最后更新：2026-05-27

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
| Phase 5 | 生态扩展 | 冻结 | 未开始 |

当前重点不是进入 Phase 5，而是补齐费用估算、原生 Windows 验收，以及继续第二轮结构收口。

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
- `~/.xcode/sessions/<pid>.json` 记录运行中 runtime status，退出时删除。
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

## 14. 当前阻塞和遗留

| 项目 | 状态 | 说明 |
|------|------|------|
| CLI `--resume` / `--continue` | 延后 | 当前只做交互内 `/resume`，CLI 恢复入口后续如有明确需求再设计 |
| `/context` cost | 未实现 | 当前只有 token 估算，没有价格估算 |
| 工具调用 UI 折叠 | 基础完成 | 默认已折叠为工具摘要；`Ctrl+O` 展开和原生 Windows 热键验收仍未做 |
| 工具调用轮次不中断 | 完成并待真实终端补充验收 | 已改为 `while True` 多轮 tool loop，并补超过 10 轮、拒绝后继续、空响应 fallback 回归测试 |
| memory 自管理权限 | 完成 | memory-scoped 写入已免用户审核，普通文件仍保持审批 |
| 流式输出重复显示 | 基础收口完成 | 结构化内容已避免 raw + Rich 双重完整输出；可替换区域式 streaming 仍未实现 |
| `agent.py` 重构 | 第一轮完成，第二轮待继续 | 已抽出 slash completer、shell UI、resume/compaction、approval、tool execution、tool display、streaming 状态；command handlers 仍待继续拆 |
| memory deny 回归测试 | 完成 | 已补 explicit `deny` + memory path 场景，防止未来误放行 |
| `/compact` 进度反馈 | 完成 | 压缩期间通过 Rich Live 显示 "Compacting context... (Xs)" 动态进度，手动和自动压缩共用 |
| `/resume` 方向键选择 | 完成 | 改为方向键 ↑/↓ 浏览 + Enter 确认 + Esc 取消，复用审批菜单的 ANSI 光标刷新模式，保留非 TTY 数字输入 fallback |
| 项目级 config merge | 完成 | `.xcode/config.json` 字段级覆盖全局，`max_summary_chars` 从 Config 统一传入 |
| `/env` 仪表盘 | 完成 | 重写为全屏 TUI，管理 max_tokens、max_summary_chars、render_mode、syntax_theme、auto_memory 五项，ANSI 局部刷新 |
| Task 工具免审与 UI 展示 | 基础完成，持久化展示待后续迭代 | `task_create/update` auto-allow + 面板渲染 + `is_read_only` 权限消费已收口；当前面板为瞬时渲染，非 Claude Code 式的持久底部驻留 |
| `/resume` last_user_input 不稳定 | 仅记录 | 同一 session 的预览文案随时间变化，用户难识别；后续可考虑首条输入或固定摘要 |
| 原生 Windows E2E | 未完成 | 需要在 cmd.exe/PowerShell 验证完整交互 |
| Phase 5 | 冻结 | 不作为近期默认开发目标 |

## 15. 下一步

1. 做原生 cmd.exe/PowerShell 交互验收，重点覆盖审批菜单、diff preview、工具摘要折叠、多轮 tool call、`/resume`、`/compact`。
2. 继续第二轮结构收口：拆 `/memory`、`/context`、`/plan` 等 command handlers。（`/env` 已收口为 EnvDashboard）
