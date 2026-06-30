# Spec 与 Plan 模板

模板用于保持信息完整，不要求机械保留所有标题。删除与任务无关的部分。

## Spec 模板

```markdown
# <Feature> Design

> Status: Draft | Approved | Implemented

## Background

当前问题、用户影响和已有能力。

## Goals

- 本轮必须实现的结果。

## Non-goals

- 本轮明确不做的能力。

## Current Constraints

- 现有架构、兼容性、依赖、权限或数据约束。

## User-visible Behavior

- 正常路径。
- 错误、空状态和降级路径。

## Design

- 模块边界。
- 数据流或状态转换。
- API、事件或存储契约。

## Security and Reliability

- 信任边界、secret、权限。
- 超时、取消、重试、回滚和失败状态。

## Compatibility and Migration

- 旧版本、旧数据、旧客户端或旧配置如何处理。

## Alternatives

- 考虑过但未采用的方案及原因。

## Acceptance Criteria

- 可观察、可验证的完成条件。

## Open Questions

- 尚未决定且会影响实现的问题。
```

## 总 Plan 模板

跨模块或多阶段功能优先使用“调度页式总 plan”。总 plan 是项目级调度页，不承载逐步代码施工细节；细节放到独立 task 文件。

```markdown
# <Feature> Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Status: Plan and task files are drafted. Code implementation, automated regression, and manual/E2E acceptance have not been executed.

**Goal:** <one-sentence result>

**Architecture:** <2-3 sentences about approach and major boundaries>

**Tech Stack:** <runtime, test tools, existing modules, forbidden dependencies if important>

---

## Evidence and References

- Parent spec: [<spec-file>](../specs/<spec-file>).
- Prior plan/spec/incident/transcript links when relevant.
- Current docs entry, such as `docs/current/ROADMAP.md`.

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/path/module.py` | Modify | Short responsibility |
| `tests/test_feature.py` | Create | Behavior regression |

## Task Files

- [Task 1: <behavior title>](<feature>/task-01-<topic>.md)
- [Task 2: <behavior title>](<feature>/task-02-<topic>.md)
- [Task N: Docs and final verification](<feature>/task-NN-docs-final-verification.md)

## Execution Constraints

- Execute one task at a time; stop for review after each task.
- State non-goals and forbidden dependencies/patterns.
- State safety, permission, migration, UI, or external-entry constraints.

## Recommended Final Verification

```text
<focused commands>
<full commands>
git diff --check
```

Manual/E2E acceptance records required:

- <entry point and acceptance evidence>
```

Small changes may still use a single concise plan without task files. For multi-task work, keep task files detailed with TDD steps, code snippets, exact commands, expected failure/pass behavior, and review checkpoints.

## Task 模板

```markdown
# Task NN: <Behavior-oriented title>

**Risk layer:** P0 | P1 | P2

## Goal

该 task 独立交付的用户行为或跨模块契约。

## Suggested Files

- Modify: `path/to/module`
- Test: `path/to/test`

## Constraints

- 必须保持的行为。
- 不允许越过的边界。

## Steps

- [ ] 写失败测试或建立可复现证据。
- [ ] 实现最小行为。
- [ ] 补失败/边界路径。
- [ ] 运行聚焦验证。
- [ ] Review 检查点。

## Acceptance

```text
<真实项目验证命令>
```

Expected:

- 用户可见结果。
- 状态或数据结果。
- 失败路径结果。

## Documentation

- 需要同步的 `docs/current/` 文件。
- 如果本 task 只是完成 spec/plan 而尚未实现，必须更新 `docs/current/ROADMAP.md`，记录“已写 spec/plan，待实现”并链接 spec/plan。
```

## Closeout 模板

```markdown
## Closeout

- Implementation: completed | partial
- Focused tests: `<command>` -> `<actual result>`
- Full validation: `<command>` -> `<actual result>`
- E2E/manual acceptance: completed | not executed
- Remaining risks: <explicit list>
- Current docs updated: ARCHITECTURE / PROGRESS / ROADMAP / DEVNOTES
```

不要把 `Expected: PASS` 当作实际证据。只有命令真实执行并得到结果后，才能填写 closeout。
