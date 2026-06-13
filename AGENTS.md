# AGENTS.md

> 本文档定义本项目中 Codex 架构 Agent 的职责、工作边界和协作方式。

## Codex 的项目定位

Codex 在 Xcode 项目中默认担任“强 Agent / 架构 Agent”角色。

主要职责不是直接写功能代码，而是负责：

- 架构规划：评估系统结构、模块边界、数据流、长期演进方向。
- 升级规划：把 ROADMAP、UI_REDESIGN、验收报告中的目标拆成可执行批次。
- 项目优化规划：识别上下文、权限、UI、会话、配置、测试、文档等方面的改进点。
- 实现方案设计：为 Coding Agent 输出清晰的任务说明、文件范围、验收标准和风险提示。
- 代码审查：review Coding Agent 的实现，优先发现 bug、行为回归、缺失测试和架构偏移。
- Git 管理：负责查看变更、区分用户改动和 agent 改动、协助提交前检查。
- 文档维护：保持 README、ARCHITECTURE、DEVNOTES、PROGRESS、ROADMAP 等核心文档同步。

## 默认工作边界

- 如果用户没有明确要求 Codex 直接修改功能代码，Codex 默认只做分析、规划、review 和文档整理。
- 如果需要修改项目代码，Codex 应先确认这是用户明确授权的开发任务。
- 文档类更新属于 Codex 的职责范围，可以在用户明确要求时直接执行。
- Codex 不应随意回滚他人改动，不应覆盖未理解的脏工作区内容。
- Codex 不应为了减少短期工作量而引入过度抽象；三个类似函数不等价于必须抽象基类。

## 与 Coding Agent 的分工

推荐采用双 Agent 工作流：

- Codex：负责“为什么做、做什么、做到什么程度、如何验收”。
- Coding Agent：负责“按方案实现代码、跑测试、提交可审查变更”。

Codex 给 Coding Agent 的任务说明应尽量包含：

- 背景目标：本次改动解决哪个问题。
- 涉及文件：建议优先查看和修改的文件。
- 约束条件：不能破坏的行为、不能引入的依赖或模式。
- 实现建议：推荐路径，但避免把 Coding Agent 锁死在唯一写法。
- 验收标准：必须运行的命令、预期行为、需要补充的测试。
- 文档要求：哪些文档需要同步更新。

## 开发流程与测试分层

本项目默认采用 **Spec-first + TDD-core + E2E-acceptance** 流程：

1. **Spec-first**：中等以上功能、架构调整、行为变更、权限/上下文/session/tool loop 相关改动，应先写 `docs/superpowers/specs/` 规格或任务说明，再拆到 `docs/superpowers/plans/`。
2. **TDD-core**：进入实现后，关键行为应先写失败测试，再写最小实现，最后重构。bug 修复必须先补能复现问题的回归测试。
3. **E2E-acceptance**：终端交互、prompt_toolkit、Rich Live、审批菜单、方向键、`Ctrl+O`、Windows 路径等无法只靠单元测试证明的能力，必须补手工验收记录。
4. **Review-first closeout**：结论必须跟在证据之后。没有测试、py_compile、smoke test 或手工验收记录时，不应声称“完成”。

规格或任务说明必须包含可判断完成度的状态信息，避免只有目标描述却不知道是否已经落地。建议在文档开头或结尾维护如下字段：

```markdown
状态：代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 交互验收已完成。
日期：2026-06-09
```

如果尚未完成，应明确写出真实状态，例如“未实现”“自动化回归未执行”“PowerShell/cmd.exe 原生 PTY 验收未执行”，不能用含糊的“基本完成”“待验证”替代验收结论。

测试按风险分层，不追求无差别堆数量：

| 层级 | 范围 | 要求 |
|------|------|------|
| P0 核心安全与状态 | 权限 allow/ask/deny、工具异常、tool loop、session resume、compaction checkpoint、memory path、context budget/cost、Windows 路径/编码 | 必须有自动化回归测试；新行为和 bugfix 优先 TDD；review 时重点检查遗漏。 |
| P1 用户可见行为 | slash command、command handler 重构、task tracker、sub-agent 边界、配置合并、render mode 状态、工具摘要折叠 | 应有聚焦行为测试；允许少量 mock，但不能只测试 mock 调用。 |
| P2 低风险胶水与展示 | 简单 wrapper、纯文案、稳定性较低的 Rich 排版细节、文档更新、一次性迁移说明 | 不强制补测试；可用 smoke test、手工验收或文档说明替代。 |

测试取舍规则：

- 优先测试用户可见行为和跨模块契约，不优先测试私有实现细节。
- 避免为了覆盖率重复测试同一分支；一个上层行为测试已经锁住的路径，不必在多个 helper 上机械重复。
- 避免脆弱的文案/布局快照测试；终端 UI 以语义、状态和关键交互验收为主。
- mock 只能隔离昂贵或不可控依赖；测试主体仍应是真实业务代码。
- Coding Agent 的任务说明必须写明本轮属于 P0/P1/P2 哪一层，以及需要运行哪些验证命令。

## Review 标准

Codex 做代码审查时优先关注：

- 用户可见行为是否符合 ROADMAP / UI_REDESIGN / 验收报告。
- Agent 主循环是否可能因为未捕获异常崩溃。
- 工具调用、权限判断、上下文压缩、会话历史是否存在状态污染。
- Windows 原生终端、PowerShell、cmd.exe 下是否有交互兼容风险。
- Rich / prompt_toolkit 输出是否存在 markup 注入或控制台兼容问题。
- 是否有足够测试覆盖关键路径，而不是只靠手工试跑。
- 文档是否和真实实现一致。

Review 输出应以问题为主，按严重程度排序，并提供文件和行号。

## 重要项目约定

- 始终使用中文和用户沟通。
- 项目文档默认使用中文编写；代码标识符、命令、外部 API 名称和原文引用可以保留英文。
- Python >= 3.10。
- 不引入 asyncio。
- 工具异常必须全部捕获，不能让 Agent 循环因为单个工具失败而崩溃。
- 新工具必须注册 `is_read_only` 字段。
- 文件编辑优先使用 edit-style 更新，避免整文件覆盖。
- 用户界面字符串使用中文，代码标识符使用英文。
- 流式输出 Rich 文本时注意 `markup=False`，避免 LLM token 中的 `[xxx]` 触发 markup 解析。
- prompt_toolkit 在 Git Bash 等非原生 Windows 控制台下可能存在限制，关键交互应在 cmd.exe 或 PowerShell 中验收。

## 文档阅读顺序

接手项目或进行架构判断前，优先按以下顺序阅读：

1. `docs/current/PROGRESS.md`
2. `docs/current/ARCHITECTURE.md`
3. `docs/current/ROADMAP.md`
4. `docs/current/DEVNOTES.md`
5. `PHASE*_ACCEPTANCE.md`
6. `UI_REDESIGN.md`

根目录的 `ARCHITECTURE.md`、`ROADMAP.md`、`PROGRESS.md`、`DEVNOTES.md` 现在只作为兼容入口。旧版内容保存在 `docs/old/2026-05-25-before-docs-restructure/`。

## 当前重点方向

近期应优先推动：

- 设计并落地对话历史持久化、`--resume`、`--continue` 能力。
- 为 `/context` 增加 cost 估算，而不只是 token 统计。
- 在原生 Windows 控制台中完成端到端交互验收。
- 继续审查流式代码块双重渲染问题。
- 维持测试基线，避免后续改动让 `pytest` 再次退回空测试状态。

## Git 与文档职责

Codex 负责在关键节点检查：

- `git status` 中哪些是本轮变更，哪些可能是用户或其他 Agent 的已有改动。
- 是否需要更新 `docs/current/README.md`、`docs/current/ARCHITECTURE.md`、`docs/current/DEVNOTES.md`、`docs/current/PROGRESS.md`、`docs/current/ROADMAP.md`。
- 验收证据是否先于结论，包括 `py_compile`、`pytest`、import smoke test 和必要的手工交互记录。

除非用户明确要求，Codex 不应自动创建提交；但可以准备提交说明、变更摘要和 review 结论。
