# Model-Invocable Skills Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让模型基于 compact skill listing 主动调用 project skills，并复用 Phase 1 的 skill prompt expansion、metadata、allowed-tools 和 session/resume 机制。

**Architecture:** 新增 `SkillCatalog` 管理所有 project skills，新增 `SkillListingFormatter` 生成预算内 listing，新增 `SkillInvocationService` 作为 user slash command 和 model SkillTool 的共享展开入口。`SkillTool` 不依赖 slash command registry，而是通过 catalog/service 调用 model-invocable skills；成功加载后通过 blocked-tools 禁用本 turn 后续 SkillTool 递归调用，并把模型恢复 metadata 与审计 metadata 分开保存。

**Tech Stack:** Python 3.10+、pytest、现有 OpenAI-compatible tool schema、Rich/prompt_toolkit、xcode SessionStore/ConversationCompactor。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/xcode_cli/skills/catalog.py` | 新建 | skill 查询、user/model invocation eligibility、built-in 冲突判断 |
| `src/xcode_cli/skills/listing.py` | 新建 | compact skill listing 预算和格式化 |
| `src/xcode_cli/skills/invocation.py` | 新建 | 共享 skill prompt expansion、metadata、allowed-tools |
| `src/xcode_cli/core/tools/skill_tool.py` | 新建 | 模型可调用 `skill` 工具 |
| `src/xcode_cli/core/tools/__init__.py` | 修改 | 注册 SkillTool 的工厂或导出位置 |
| `src/xcode_cli/core/tool_registry.py` | 修改 | 支持 tool 返回 structured metadata |
| `src/xcode_cli/core/tooling/execution.py` | 修改 | 隐藏 skill prompt UI、传递 activated allowed-tools、blocked-tools 和 invocation audit metadata |
| `src/xcode_cli/core/commands/registry.py` | 修改 | slash skill command 改为调用 `SkillInvocationService` |
| `src/xcode_cli/core/commands/dispatcher.py` | 修改 | 接收 service 返回的 `UserTurnInput` |
| `src/xcode_cli/core/prompting.py` | 修改 | 注入 available skills listing 和 SkillTool guidance |
| `src/xcode_cli/core/agent.py` | 修改 | 构造 catalog/listing/service/tool；SkillTool 后更新 current allowed-tools |
| `src/xcode_cli/core/session.py` | 修改 | 如有必要，支持写入 `skill_invocation` event |
| `docs/current/ARCHITECTURE.md` | 修改 | 记录 Phase 2 技术路径 |
| `docs/current/ROADMAP.md` | 修改 | 更新 Skills Phase 2 状态 |
| `docs/current/PROGRESS.md` | 修改 | 更新实现验收记录 |
| `docs/current/DEVNOTES.md` | 修改 | 记录 SkillTool 边界和测试规范 |

## Task 文件

- [Task 1: 建立 SkillCatalog](2026-06-05-model-invocable-skills/task-01-skill-catalog.md)
- [Task 2: 建立 compact skill listing 预算器](2026-06-05-model-invocable-skills/task-02-skill-listing.md)
- [Task 3: 抽 SkillInvocationService](2026-06-05-model-invocable-skills/task-03-skill-invocation-service.md)
- [Task 4: 增加 SkillTool 和 structured tool result](2026-06-05-model-invocable-skills/task-04-skill-tool.md)
- [Task 5: 接入 AgentRuntime、system prompt 和 allowed-tools 续接](2026-06-05-model-invocable-skills/task-05-agent-runtime-integration.md)
- [Task 6: session/resume/compact 验收](2026-06-05-model-invocable-skills/task-06-session-resume-compact.md)
- [Task 7: 文档和最终验证](2026-06-05-model-invocable-skills/task-07-docs-final-verification.md)

## 执行约束

- 每个 task 单独提交。
- 每个行为变更先写失败测试，再写实现。
- 不实现 fork、hooks、remote skills、skill search。
- 不把 SkillTool 实现为 “拼出 `/review args` 再喂给 SlashCommandDispatcher”。
- SkillTool 成功加载 skill 后，本 user turn 后续 tool schemas 必须排除 `skill`。
- `skill_invocation` audit event 不得保存完整 `model_content`。
- 不让 `allowed-tools` 绕过 PermissionManager。
- 不把完整 skill prompt 打印到用户 UI。
