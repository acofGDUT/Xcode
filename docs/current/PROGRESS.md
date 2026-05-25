# Xcode 开发进度

> 本文档记录项目如何一步步走到现在。当前实现细节见 `ARCHITECTURE.md`，未来计划见 `ROADMAP.md`，已知问题和设计取舍见 `DEVNOTES.md`。

最后更新：2026-05-25

## 1. 当前状态总览

| 阶段 | 名称 | 状态 | 验收 |
|------|------|------|------|
| Phase 1 | 协议与工具升级 | 完成 | `PHASE1_ACCEPTANCE.md` |
| Phase 2 | Agent 架构升级 | 完成 | `PHASE2_ACCEPTANCE.md` |
| Phase 3 | 计划与记忆 | 完成 | `PHASE3_ACCEPTANCE.md` |
| Phase 4 | 安全与体验 | 完成，4.3 已收口 | `PHASE4_ACCEPTANCE.md` |
| Phase 4.5 Batch 1 | 上下文系统修复 + 测试基线 | 完成并通过 review | specs task brief |
| Phase 4.5 Batch 2 | memory 模型验证 + Windows 路径回归 | 完成并通过 review | specs task brief |
| Phase 5 | 生态扩展 | 冻结 | 未开始 |

当前重点不是进入 Phase 5，而是补齐恢复、费用估算和原生 Windows 验收。

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

## 9. 当前阻塞和遗留

| 项目 | 状态 | 说明 |
|------|------|------|
| `--resume` / `--continue` | 未实现 | `SessionStore` 只是 JSONL 日志，不能恢复 runtime history |
| `/context` cost | 未实现 | 当前只有 token 估算，没有价格估算 |
| 工具调用 UI 折叠 | 未实现 | 当前工具调用详情持续向下打印，缺少 Claude Code 式摘要和 `Ctrl+O` 展开 |
| 工具调用轮次不中断 | 待调查 | 实际使用中可能因为多轮 tool_calls 停住，需要检查 `_run_llm_loop()` |
| 原生 Windows E2E | 未完成 | 需要在 cmd.exe/PowerShell 验证完整交互 |
| Phase 5 | 冻结 | 不作为近期默认开发目标 |

## 10. 下一步 3 项

1. 调查并修复工具调用轮次中断问题，补 fake LLM 多轮 tool call 测试。
2. 设计工具调用 UI 折叠/展开机制，默认摘要，`Ctrl+O` 展开完整参数。
3. 设计并实现文本级 `--continue` / `--resume <session_id>`。
