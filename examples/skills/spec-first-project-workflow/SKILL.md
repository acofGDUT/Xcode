---
name: spec-first-project-workflow
description: "Use for medium or large project changes requiring requirements clarification and architecture or behavior design and implementation task breakdown and review against an approved design or project-document closeout. Establishes a technology-neutral Spec-first workflow based on docs/superpowers/specs plus docs/superpowers/plans plus docs/current. Suitable for frontend and backend and full-stack and desktop and mobile and library and service and CLI projects."
---

# Spec-first Project Workflow

把设计决策、实施步骤和当前项目事实分开维护。先确定“做什么以及边界”，再决定“如何分批实现”，最后用验证证据更新项目现状。

本 skill 不规定框架、语言或测试工具。读取仓库现有约定，并按项目类型选择构建、测试、lint、类型检查、E2E、性能或手工验收方法。

## 首先判断任务阶段

根据用户请求进入对应阶段，不擅自越级：

| 用户意图 | 执行动作 |
|---|---|
| “先判断”“先分析”“不要设计” | 阅读当前文档和代码，只给判断，不创建 spec/plan |
| “设计一下”“写 spec” | 创建或更新 spec；不拆实现任务，除非用户同时要求 |
| “拆计划”“给 Coding Agent 任务” | 确认 spec 已稳定，再创建 plan/task |
| “实现”“按计划开发” | 按 plan 推进，关键行为先测试，完成后验证 |
| “review” | 以 spec、plan 和用户可见行为为基准，问题优先输出 |
| “收口”“更新文档” | 先核对验证证据，再更新 `docs/current/` 和 task 状态 |

若项目已有自己的 `AGENTS.md`、贡献指南或文档目录，优先遵循现有约定；只在缺少约定时采用本 skill 的默认结构。

## 文档维护职责

保持 `README.md`、`ARCHITECTURE.md`、`DEVNOTES.md`、`PROGRESS.md`、`ROADMAP.md` 等核心文档同步。不要只创建 spec/plan 而让当前事实入口失去线索。

本项目流程默认是 Spec-first：中等以上的行为或架构变更，要先写 `docs/superpowers/specs/`，再拆到 `docs/superpowers/plans/`。

`docs/current/` 是当前项目事实入口。写完 spec/plan 后，如果这件事已经成为近期路线、待实现工作、已知风险或重要设计取舍，就要同步到 `ROADMAP.md`、`PROGRESS.md` 或 `DEVNOTES.md`。否则后续 Coding Agent 只看 current docs 时会漏掉它。

## 阅读项目事实

开始设计或规划前，按以下顺序读取：

1. 项目级 Agent/贡献说明，例如 `AGENTS.md`、`CONTRIBUTING.md`。
2. `docs/current/PROGRESS.md`：已经完成什么，以及验证证据。
3. `docs/current/ARCHITECTURE.md`：系统现在如何工作。
4. `docs/current/ROADMAP.md`：尚未完成和未来候选。
5. `docs/current/DEVNOTES.md`：已知风险、限制和历史取舍。
6. 与需求相关的旧 spec、plan、验收报告和代码。

不要只读 ROADMAP 就开始设计。必须先确认当前实现，避免为已经存在的能力重复设计。

详细文档职责见 [document-contracts.md](references/document-contracts.md)。

## 编写 Spec

中等以上功能、跨模块行为、架构调整、权限、安全、状态、数据迁移、上下文/session、外部集成或用户可见流程变更，先写 spec。

默认路径：

```text
docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md
```

Spec 回答：

- 为什么做，解决什么问题。
- 用户或调用方将看到什么行为。
- 范围和明确不做什么。
- 当前约束、数据流、模块边界和状态模型。
- 安全、兼容性、性能、迁移与失败策略。
- 方案取舍和被拒绝的替代方案。
- 可验证的验收标准。

Spec 是设计合同，不是施工日志。避免写逐行代码方案、提交命令和大量 checkbox。

设计时必须检查：

- 是否符合现有架构和命名。
- 是否改变公开接口、数据格式或用户流程。
- 是否引入新的信任边界、secret、权限或外部依赖。
- 是否需要兼容旧数据、旧客户端或已有配置。
- 失败后系统处于什么状态，是否可重试或回滚。
- 哪些结论必须通过 E2E、性能测试或人工验收证明。

模板见 [templates.md](references/templates.md)。

## 拆分 Plan

只在 spec 的目标和边界稳定后拆 plan。

默认路径：

```text
docs/superpowers/plans/YYYY-MM-DD-<feature>-plan.md
docs/superpowers/plans/YYYY-MM-DD-<feature>/task-01-<topic>.md
```

小型改动可以只有一个 plan；跨模块或多阶段功能使用总 plan 加 task 文件。

对跨模块或多阶段功能，推荐采用“调度页式总 plan + 独立 task 文件”的结构：总 plan 是项目级调度页，保留状态、证据/引用、文件职责表、task 文件列表、全局执行约束和最终验证矩阵；具体 TDD 步骤、代码片段、命令和 review 检查点放到各 task 文件。这样总 plan 便于 review 和收口，task 文件便于 Coding Agent 独立执行。

Plan 回答：

- 以什么顺序实现。
- 每个 task 修改或重点检查哪些文件/模块。
- 每个 task 属于什么风险层级。
- 哪些关键行为先写失败测试。
- 不能破坏的契约和禁止事项。
- 每个 task 的完成条件和验证命令。
- 哪些 `docs/current/` 文件需要同步。

按可独立 review 的行为切分 task，不按文件数量机械切分。优先形成纵向可验证闭环，例如“API + 状态处理 + 测试”，而不是“先改所有模型，再改所有接口”。

计划应提供推荐路径，但不要把实现者锁死在唯一代码写法。对高风险步骤写清约束，对低风险内部实现保留自由度。

写完 spec 和 plan 后，必须立即更新 `docs/current/ROADMAP.md`，至少留下一条待实现记录：

- 状态写成“已写 spec/plan，待实现”或等价说法。
- 下一步指向首个 plan task 或推荐实现入口。
- 链接到对应 spec 和 plan。
- 不要把功能写成已完成，不要更新 `ARCHITECTURE.md` 的当前机制。

如果 spec/plan 产生了重要约束、风险或 non-goal，也可以同步 `DEVNOTES.md`；如果项目习惯记录设计产出，可以在 `PROGRESS.md` 写“设计完成”。但没有实现和验证证据时，只能记录计划状态。

## 实施与验证

实施时遵循：

1. 确认当前 task 和工作区状态。
2. 对核心行为或 bug 先写能失败的测试。
3. 写最小实现使测试通过。
4. 在不改变行为的前提下重构。
5. 运行聚焦验证，再运行与改动规模匹配的更广验证。
6. 记录真实结果，不把“计划运行”写成“已经通过”。

按风险选择证据：

- 核心安全、权限、状态、数据完整性：自动化回归必须覆盖。
- 用户可见行为和跨模块契约：聚焦行为测试，必要时加集成/E2E。
- UI、浏览器、终端、移动端、真实外部服务：使用对应真实环境验收。
- 构建和类型安全：运行项目现有 build/typecheck/lint。
- 低风险文案和胶水：允许 smoke test 或人工检查。

不要为了形式堆重复测试。优先锁住用户行为和模块契约。

## Review

Review 时先比较实现与 spec/plan，再看代码风格。输出顺序：

1. 按严重程度列出 bug、回归、安全问题和缺失测试。
2. 给出文件和行号。
3. 说明触发条件和用户影响。
4. 再列开放问题或假设。
5. 最后才给简短变更总结。

重点检查：

- 实现是否超出 spec，或漏掉 non-goal/约束。
- 异常是否会破坏主流程或留下脏状态。
- 权限、secret、日志、history、缓存和持久化是否泄漏或污染。
- 并发、重试、超时、取消、迁移和兼容路径是否完整。
- 测试是否只验证 mock 调用，而没有验证真实行为。
- 文档是否提前声称完成。

## 更新 `docs/current/`

`docs/current/` 分两次更新：

1. **设计/计划完成后**：更新 `ROADMAP.md`，记录“已写 spec/plan，待实现”，避免设计遗留；必要时同步 `DEVNOTES.md` 的边界和取舍。
2. **实现和验证完成后**：再更新完整当前状态。

实现和验证完成后的文档职责：

- `ARCHITECTURE.md`：写系统现在如何工作，只保留当前机制。
- `PROGRESS.md`：记录已完成内容、日期、验证命令和结果。
- `ROADMAP.md`：移除已完成事项，保留未来和未完成项。
- `DEVNOTES.md`：记录仍有效的限制、风险、经验和设计取舍。
- `README.md`：维护文档导航和项目概览，避免复制其他文档全文。

收口时同时更新 spec/plan 状态和 task checkbox，但不要重写历史证据。若某项只完成自动化、尚未做真实 E2E，明确写出差距。

禁止出现以下状态漂移：

- Spec 写“待实现”，PROGRESS 却写“已完成”。
- Spec/plan 已经写完，但 ROADMAP 没有任何待实现记录。
- ROADMAP 继续列出已经完成的工作。
- ARCHITECTURE 描述旧机制。
- Plan checkbox 全未勾选，但代码已经交付。
- 没有测试或验收证据，却写“完成”“稳定”“已验证”。

## 最终检查

结束前确认：

- Spec、plan、实现和当前文档描述一致。
- 已完成与未完成边界明确。
- 验证结果先于完成结论。
- 没有把项目特定技术假设写成通用规则。
- Git 变更中没有误带日志、构建产物、secret 或无关文件。

默认不要自动提交或推送；只有用户明确要求时才执行 Git 操作。
