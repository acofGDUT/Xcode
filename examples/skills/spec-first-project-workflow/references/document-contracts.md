# 文档职责与事实边界

## 目录模型

```text
docs/
├── current/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── PROGRESS.md
│   ├── ROADMAP.md
│   └── DEVNOTES.md
└── superpowers/
    ├── specs/
    └── plans/
```

项目已有其他目录命名时，映射职责即可，不要求强制迁移。

## 文档维护原则

核心文档必须同步维护：

- `README.md`
- `ARCHITECTURE.md`
- `DEVNOTES.md`
- `PROGRESS.md`
- `ROADMAP.md`

项目默认走 Spec-first 流程。中等以上的行为或架构变更，应先写 `docs/superpowers/specs/`，再拆到 `docs/superpowers/plans/`。

`docs/current/` 是当前项目事实入口。写完 spec/plan 后，如果该事项已经进入近期路线、形成待实现工作、暴露已知风险或产生重要设计取舍，必须同步到 `ROADMAP.md`、`PROGRESS.md` 或 `DEVNOTES.md`。这样后续 Coding Agent 即使只阅读 current docs，也不会漏掉已经设计但尚未实现的事项。

## `docs/superpowers/specs/`

保存稳定的需求和设计合同，回答“为什么做、做什么、边界是什么”。

适合存放：

- 功能设计
- 架构变更
- 用户流程和 API 契约
- 数据/状态模型
- 权限和安全边界
- 迁移与兼容方案
- 验收标准

不适合存放：

- 每一步 Git 命令
- 逐文件施工顺序
- 测试运行日志
- 当前项目总状态

## `docs/superpowers/plans/`

保存可执行实施计划，回答“按什么顺序、改哪里、怎么验证”。

适合存放：

- 总 plan 和 task 索引
- task 风险等级
- 建议文件范围
- TDD 顺序
- 实现约束
- 验证命令与预期结果
- review 检查点
- closeout 记录

Plan 可以随着实施勾选状态并追加实际验证结果，但不要反过来修改已批准的 spec 边界来迁就实现。

## `docs/current/ARCHITECTURE.md`

当前系统的事实说明。描述现在运行的模块、数据流、状态、接口和边界。

规则：

- 使用现在时。
- 删除或迁移已经失效的旧机制。
- 不写未来候选清单。
- 不堆积逐次开发日志。

## `docs/current/PROGRESS.md`

项目已经完成事项的时间线和证据索引。

应记录：

- 完成日期和范围
- 关键实现结果
- Review 结论
- 实际测试、构建、E2E 或人工验收结果
- 尚未完成的验收边界

结论必须跟在证据后面。

## `docs/current/ROADMAP.md`

未来工作和未完成风险列表。

规则：

- spec/plan 写完但尚未实现时，必须在 ROADMAP 留下一条“已写 spec/plan，待实现”的待办记录，并链接 spec 与 plan。
- 记录下一步入口，例如第一个 task、推荐实现批次或待决问题。
- 已完成事项只保留必要状态索引，或移入 PROGRESS。
- 明确优先级、状态和下一步。
- 不把脑暴候选写成已经承诺的范围。
- 不用 ROADMAP 描述当前实现细节。

## `docs/current/DEVNOTES.md`

保存仍对开发有价值的工程经验：

- 已知坑和复现条件
- 兼容性限制
- 设计取舍及其代价
- 后续 review 注意事项
- 尚未彻底消除的风险

问题彻底解决后标记为 resolved，保留仍有教育价值的原因和边界；纯历史流水应移入 PROGRESS 或归档。

## `docs/current/README.md`

作为文档入口，说明各文档职责和阅读顺序。保持简短，避免复制 ARCHITECTURE、ROADMAP 或 PROGRESS 的正文。

## 信息流

```text
需求/问题
  -> spec：冻结目标和边界
  -> plan：拆解任务和验证
  -> ROADMAP：记录已写 spec/plan 且待实现
  -> 实现与 review
  -> PROGRESS：记录结果和证据
  -> ARCHITECTURE：同步当前机制
  -> ROADMAP：移除完成项、保留剩余项
  -> DEVNOTES：沉淀仍有效的风险和取舍
```

任何文档发生冲突时，以代码和真实验证证据为事实基础，再统一修正文档；不能只挑最乐观的一份作为结论。
