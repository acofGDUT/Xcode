# SDD 开发工作流

> SDD = Spec-Driven Development / Specification-Driven Development。  
> 本项目默认采用 SDD，而不是默认采用 TDD。

## 1. 定义

Xcode 项目里的 SDD 指：

```text
Spec -> Plan -> Implementation -> Review -> Progress Tracking
```

也就是先明确规格、边界和验收标准，再交给 coding agent 实现；实现完成后由 Codex 做 review，并同步项目跟踪文档。

SDD 关注的是“规格驱动开发”，不是“测试先行开发”。测试仍然重要，但测试是验收和回归保护的一部分，不要求每个功能或 bugfix 都严格先写 failing test。

## 2. 文档分工

SDD 流程文档默认使用中文，包括 spec、plan、coding brief、review handoff 和项目跟踪更新。代码标识符、命令、路径、类名、函数名、协议名和必要英文术语可以保留英文。

| 阶段 | 文档/产物 | 作用 |
|------|-----------|------|
| Spec | `docs/superpowers/specs/*.md` 或当前对话中的设计稿 | 定义目标、用户体验、架构边界、非目标、风险 |
| Plan | `docs/superpowers/plans/*.md` 或 coding brief | 拆成 coding agent 可执行任务，列出文件范围、约束、验收标准 |
| Implementation | 代码变更 | coding agent 按 plan 实现 |
| Review | Codex review 输出 | 按 P0/P1/P2 找 bug、回归、架构偏移、测试缺口、文档不一致 |
| Progress Tracking | `docs/current/PROGRESS.md`、`ARCHITECTURE.md`、`DEVNOTES.md`、`ROADMAP.md` | 记录当前状态、架构事实、已知风险、后续方向 |

权威项目跟踪文档默认由 Codex 在 review 后更新。Coding Agent 不默认直接修改 `docs/current/PROGRESS.md`、`ARCHITECTURE.md`、`DEVNOTES.md`、`ROADMAP.md`、`AGENTS.md` 或 `XCODE.md`；除非 plan 明确写出允许修改的文件和范围。

## 3. 默认流程

### 新功能或大改动

默认流程：

1. Codex 先和用户明确需求、目标、非目标和验收标准。
2. Codex 写或更新 spec。
3. Codex 写 plan / coding brief，交给 coding agent。
4. Coding agent 实现并运行必要验证。
5. Codex review 实现。
6. Review 通过后，Codex 同步 current docs。

### 已经明确的小批次

如果需求已经足够明确，可以跳过独立 spec，直接写 plan / coding brief。

例如：

- “把 `/resume` 恢复后的信息和 legacy 对齐”
- “清理 Textual UI 新增文件里的 mojibake”
- “把审批选择从按钮改成上下三行”

这类任务可以直接进入 coding brief，但 brief 仍需包含目标、文件范围、约束和验收标准。

### 文档更新分工

默认分工：

- Coding Agent：实现代码、补测试、运行验证，可以记录实现摘要、验收结果或临时 notes。
- Codex：review 实现，判断架构事实是否成立，然后更新 `PROGRESS.md`、`ARCHITECTURE.md`、`DEVNOTES.md`、必要时更新 `ROADMAP.md`。

禁止默认行为：

- Coding Agent 不应在实现未 review 前把状态写成“完成”。
- Coding Agent 不应把愿景写进 `ARCHITECTURE.md`，该文档只记录当前真实架构。
- Coding Agent 不应自行修改 `AGENTS.md` 或 `XCODE.md`。

例外：如果 Codex 写给 Coding Agent 的 plan 明确允许修改某个权威文档的某一节，Coding Agent 可以按限定范围修改；但这些修改仍需 Codex review 后确认。

### Review 后的小修

Review 中发现的小问题可以直接修复，前提是：

- 用户明确授权 Codex 修改。
- 改动范围小且不改变已确认架构方向。
- 修复后运行相应验证。

## 4. 测试策略

本项目不再默认要求 TDD 红绿循环。

默认测试策略：

- 关键业务路径需要自动化测试。
- UI/终端交互可以结合 Textual pilot、单元测试和 cmd.exe/PowerShell 手工验收。
- 对高风险行为必须保留回归测试，例如权限、工具执行、session resume、context compaction、history 污染。
- 文档或计划更新不需要写测试。
- 简单 UI 文案调整可以只做 focused test 或手工验收。

仍然可以使用 TDD 的场景：

- 缺陷可以被清晰复现，而且测试成本低。
- 核心算法、状态机、权限规则、resume/compact 等边界容易回归。
- 用户或计划明确要求 TDD。

## 5. Codex 默认职责

Codex 默认是架构/规划/review agent，不默认直接写功能代码。

默认输出应优先是：

- 架构判断
- 设计规格
- coding agent 执行计划
- review 结论
- 文档同步
- git 状态和提交建议

只有在用户明确要求“你去改”“你直接修改”时，Codex 才直接改代码。

## 6. Coding Agent Brief 必须包含

给 coding agent 的 brief 应尽量包含：

- 背景目标：本次改动解决什么问题。
- 涉及文件：优先查看和修改哪些文件。
- 约束条件：不能破坏什么行为、不能引入什么模式。
- 实现建议：推荐方向，但不锁死唯一写法。
- 验收标准：要跑哪些命令、手工如何验证。
- 文档要求：哪些文档要同步。
- 非目标：本轮明确不做什么，避免 scope 漂移。

默认语言要求：

- 面向用户和 coding agent 的说明使用中文。
- 命令、路径、代码片段、类型名和测试名保持原样。
- 如果引用英文架构术语，应在上下文中说明含义，避免只写英文关键词。

## 7. Review 标准

Codex review 仍按问题优先：

- P0：会崩溃、破坏核心功能、导致权限/文件安全风险。
- P1：用户可见行为错误、状态污染、重要回归、缺少关键测试。
- P2：文档不一致、体验边界、维护性问题、后续风险。

Review 结论必须基于证据：源码、测试结果、文档和必要的手工验收。

## 8. 项目跟踪规则

实现或 review 通过后，根据改动范围同步：

- `docs/current/PROGRESS.md`：记录完成了什么、还缺什么。
- `docs/current/ARCHITECTURE.md`：只写当前真实架构，不写愿景。
- `docs/current/DEVNOTES.md`：记录设计取舍、风险、踩坑。
- `docs/current/ROADMAP.md`：只在后续方向变化时更新。

SDD 的核心原则是：文档不是事后装饰，而是开发输入、验收依据和项目记忆。
