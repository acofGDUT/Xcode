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

```markdown
# <Feature> Implementation Plan

> Parent spec: <relative link>

## Goal

本计划交付的结果。

## Constraints

- 不可破坏的行为。
- 禁止引入的依赖或模式。

## Task Order

1. Task 1: 建立核心状态或契约
2. Task 2: 接入用户/API 流程
3. Task 3: 失败恢复与兼容
4. Task 4: E2E、文档和最终验证

## Cross-task Validation

- 项目级 build/test/lint/typecheck。
- 集成、E2E、性能或人工验收。
- 文档一致性和 Git diff 检查。
```

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
