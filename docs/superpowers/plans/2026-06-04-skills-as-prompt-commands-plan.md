# Skills As Prompt Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 xcode skills Phase 1：按主流 skill package 设计，把 `.xcode/skills/<skill-name>/SKILL.md` 加载为 prompt slash command，并移除旧 `skill.json` / `enabled_skills` / system prompt 注入壳子。

**Architecture:** 新 skill 机制以项目内 skill package 为唯一来源：`SKILL.md` 负责 metadata 和入口 prompt，references/scripts/templates/assets 作为 supporting files 按需读取。`SkillLoader` 负责磁盘加载和 frontmatter 解析，`CommandRegistry` 合并 built-in prompt commands 与 skill prompt commands，`AgentRuntime._run_user_turn()` 接收 `UserTurnInput` 以区分 UI 展示内容和模型可见内容。

**Tech Stack:** Python 3.10+、pytest、Rich、prompt_toolkit、现有同步 AgentRuntime；不引入 asyncio。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/xcode_cli/skills/model.py` | 新建 | `Skill`、`SkillLoadNotice`、frontmatter metadata 数据结构 |
| `src/xcode_cli/skills/loader.py` | 新建 | 加载 `.xcode/skills/*/SKILL.md`，解析 frontmatter |
| `src/xcode_cli/skills/prompt.py` | 新建 | 展开 `$ARGUMENTS` 和 `${XCODE_SKILL_DIR}`，处理 unsupported 字段 |
| `src/xcode_cli/skills/validation.py` | 新建 | 检查 description 缺失、命令冲突、未知工具、unsupported 字段 |
| `src/xcode_cli/core/turn.py` | 新建 | `UserTurnInput` 和 skill invocation metadata |
| `src/xcode_cli/core/commands/registry.py` | 新建 | 合并 built-in command 与 project skill command |
| `src/xcode_cli/core/commands/slash.py` | 修改 | `SlashCommand` 增加 `source`、`argument_hint`、`metadata`；移除硬编码 prompt command 全局依赖 |
| `src/xcode_cli/core/commands/dispatcher.py` | 修改 | 从 `CommandRegistry` 查找 prompt command；支持返回 `UserTurnInput` |
| `src/xcode_cli/core/commands/skill.py` | 修改 | 旧 list/install/enable/disable 改为基于 `.xcode/skills` 的 list/show/validate 入口 |
| `src/xcode_cli/skills/manager.py` | 删除或改为空兼容层 | 移除 `skill.json` 安装和旧 enabled skill 语义 |
| `src/xcode_cli/core/config.py` | 修改 | 移除 `enabled_skills` 字段及序列化路径 |
| `src/xcode_cli/core/prompting.py` | 修改 | 移除 enabled skills 全量注入 system prompt |
| `src/xcode_cli/core/tool_registry.py` | 修改 | 支持按工具白名单生成 schemas |
| `src/xcode_cli/core/tooling/execution.py` | 修改 | 增加当前 turn allowed-tools 执行层兜底 |
| `src/xcode_cli/core/agent.py` | 修改 | 注入 registry，`_run_user_turn()` 接收 `UserTurnInput | str` |
| `src/xcode_cli/core/ui/shell.py` | 修改 | `/help` 展示动态 user-invocable skills |
| `tests/test_skill_loader.py` | 新建 | loader/frontmatter/fallback/错误处理测试 |
| `tests/test_skill_prompt.py` | 新建 | prompt 展开和 unsupported 字段测试 |
| `tests/test_skill_validation.py` | 新建 | 命令冲突、description warning、未知工具 notice 测试 |
| `tests/test_skill_command_registry.py` | 新建 | command registry 合并和动态 skill 注册测试 |
| `tests/test_skill_prompt_command_flow.py` | 新建 | `/review args` 进入普通 user turn 的行为测试 |
| `tests/test_skill_allowed_tools.py` | 新建 | allowed-tools schemas 和执行层兜底测试 |
| `tests/test_prompting_memory.py` | 修改 | 移除旧 enabled skill system prompt 注入断言 |
| `tests/test_skill_command_service.py` | 修改 | 从旧 install/enable/disable 测试改为 list/show/validate |

## Task Index

每个 Task 的完整执行步骤已拆到独立文件，便于逐步发给 Coding Agent 执行和 review。

- [Task 1: 移除旧 skill 壳子并锁定新边界](2026-06-04-skills-as-prompt-commands/task-01-remove-legacy-skill-shell.md)
- [Task 2: 实现 Skill 数据结构和 loader](2026-06-04-skills-as-prompt-commands/task-02-skill-loader.md)
- [Task 3: 实现 skill prompt 展开](2026-06-04-skills-as-prompt-commands/task-03-skill-prompt-expander.md)
- [Task 4: 建立动态 CommandRegistry](2026-06-04-skills-as-prompt-commands/task-04-command-registry.md)
- [Task 4.5: 增加 skill validation](2026-06-04-skills-as-prompt-commands/task-04-5-skill-validation.md)
- [Task 5: 接入 UserTurnInput，防止 skill prompt 污染 UI](2026-06-04-skills-as-prompt-commands/task-05-user-turn-input.md)
- [Task 6: 实现 allowed-tools 当前 turn 白名单](2026-06-04-skills-as-prompt-commands/task-06-allowed-tools-scope.md)
- [Task 7: UI、completion 和 `/skill` 服务改为新模型](2026-06-04-skills-as-prompt-commands/task-07-skill-ui-completion-service.md)
- [Task 8: Session/resume 记录 skill invocation](2026-06-04-skills-as-prompt-commands/task-08-session-resume-skill-invocation.md)
- [Task 9: 最终回归和文档收口](2026-06-04-skills-as-prompt-commands/task-09-final-verification-docs.md)

## Review 检查清单

Codex review 时重点检查：

- 是否彻底移除了旧 skill 壳子，尤其是 `enabled_skills` 注入 system prompt。
- `.xcode/skills` loader 是否只读项目目录，不偷偷读 `.claude/skills`。
- `context: fork` 是否没有 inline 执行。
- `hooks` 是否只解析保存，不执行。
- skill prompt 是否没有作为普通用户消息刷到 UI。
- `allowed-tools` 是否同时限制 schemas 和 execution。
- `allowed-tools` 是否仍然尊重 PermissionManager 的显式 deny 和 ask。
- skill 与 built-in slash command 冲突时是否不会覆盖 built-in command。
- supporting files 是否没有被 loader 自动塞进 prompt。
- session/resume 是否恢复 hidden/model prompt，而不只是展示文本。
- `/init` 作为 built-in prompt command 行为是否不变。
- 普通 user turn 是否仍然走同一条 `_run_user_turn()` 路径。
- focused tests 与全量 `pytest` 是否都通过。

## 执行建议

Task 1-8 由 Coding Agent 分步实现，每个 task 完成后提交并交给 Codex review。Task 9 的文档收口和最终整体 verification 由 Codex 完成。

