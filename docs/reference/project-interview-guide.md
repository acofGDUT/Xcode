# Xcode Agent 项目面试准备手册

> 适用方向：AI Agent 开发、LLM 应用开发、AI Coding Agent、Agent Runtime、Python 后端。
>
> 项目地址：<https://github.com/acofGDUT/Xcode>
>
> 整理日期：2026-07-10

## 1. 文档用途

本文用于围绕 Xcode Agent 项目准备简历和技术面试，重点回答四类问题：

1. 如何在简历上准确描述项目。
2. 如何在 30 秒、2 分钟和深入追问场景中介绍项目。
3. 如何解释 Agent Runtime、Tool Loop、权限、上下文、Session、Memory、Skills、MCP 和子 Agent 等核心设计。
4. 如何诚实说明当前不足，并提出可信的演进方案。

面试时应以真实实现为准，不应把项目描述成“分布式多 Agent”“高并发 Agent 平台”“生产级 RAG”或“完全兼容 Claude Code”。更准确的定位是：

> 一个具备完整状态管理、安全边界、长上下文、持久记忆和协议扩展能力的单机 AI Coding Agent Runtime。

## 2. 项目事实速查

### 2.1 项目定位

Xcode 是一个 terminal-native AI coding agent。它通过 OpenAI-compatible API 调用大模型，并向模型暴露文件、搜索、Shell、子 Agent、任务追踪、Plan Mode、Skills、MCP 和 Memory 等能力。

### 2.2 技术栈

- Python 3.10+
- OpenAI-compatible API
- Typer
- Rich
- prompt_toolkit
- MCP Python SDK
- websocket-client
- pytest

### 2.3 当前可量化数据

- 86 个 Python 源文件。
- 约 11,272 行 Python 源码。
- 72 个测试文件。
- 约 12,284 行测试代码。
- 13 个内置工具，并支持按配置动态注册 MCP 工具。
- Git 仓库当前包含约 60 个提交。
- 最近一次项目文档记录的全量回归结果为 `649 passed`。

注意：面试或更新简历前应在目标环境重新运行完整测试。简历中推荐写“649 项自动化回归通过”，不要写成“649 个单元测试”，因为其中还包含集成和行为回归测试。

### 2.4 13 个内置工具

| 类别 | 工具 |
|------|------|
| 文件 | `read_file`、`write_file`、`edit_file` |
| 搜索 | `grep`、`glob` |
| Shell | `run_shell` |
| 子 Agent | `dispatch_agent` |
| 任务 | `task_create`、`task_update`、`task_list` |
| Plan Mode | `enter_plan_mode`、`write_plan`、`exit_plan_mode` |

## 3. HR 与技术面试官视角评估

### 3.1 项目竞争力

如果投递校招、实习或 1–3 年经验的 AI Agent 开发岗位，本项目可以作为简历主项目。它已经超过“调用模型 API 加几个工具”的 Demo，涉及了 Agent Runtime 中较难的状态管理和安全问题。

项目最有竞争力的三个方向是：

1. 安全可控的 Tool Loop。
2. 可压缩、可恢复的长上下文与 Session。
3. 受限、异步并且可审计的长期 Memory。

### 3.2 技术优势

- 不只关注 Prompt，还处理模型、工具、权限和 Session 之间的协议状态。
- 理解 assistant tool calls 与 tool results 必须合法配对。
- 对上下文压缩、会话恢复、长期记忆和迟到异步结果等复杂状态问题有实际实现。
- 具备安全意识，包括审批、外部入口隔离、MCP trust、敏感信息脱敏和 Memory sandbox。
- 采用 Spec-first、TDD-core 和风险分层验收，而不是只验证 Happy Path。
- 对 PowerShell、cmd.exe、Rich 和 prompt_toolkit 的终端兼容问题有专项验收经验。

### 3.3 当前短板

- 缺少 Agent 行为层 Benchmark。现有测试主要证明 Runtime 正确，不能直接证明 Agent 的任务完成质量。
- 子 Agent 当前是同步委派，不是真正的并行或分布式多 Agent 调度。
- token 数量使用启发式估算，没有模型级 tokenizer 和 cost 统计。
- API Key 可以明文保存到配置文件，项目级配置目前也能覆盖敏感字段，配置安全仍需加固。
- Skill 的 `allowed-tools` 当前是声明和审计信息，不是严格的执行白名单。
- 可观测性以 JSONL transcript 和本地状态为主，缺少完整 trace、指标和可视化分析。
- QQchat、部分 compact/memory 路径仍保留真实平台或原生终端手工验收缺口。

## 4. 简历写法

### 4.1 推荐项目名称

由于 Xcode 容易与 Apple Xcode 混淆，简历中建议写成：

> Xcode Agent（个人 AI Coding Agent，非 Apple Xcode）

仓库后续可以考虑改名为 `Xcode-Agent`、`XAgent-CLI` 或其他辨识度更高的名称。

### 4.2 简历项目介绍

**Xcode Agent（个人项目）**

Python / OpenAI-compatible API / Typer / Rich / prompt_toolkit / MCP

2026.05–至今

> 独立设计并实现终端原生 AI Coding Agent，支持流式 Function Calling、文件与 Shell 工具、子 Agent、Plan Mode、Skills、MCP、会话恢复、上下文压缩和跨会话长期记忆。

推荐项目要点：

- 自研 Agent Runtime 与多轮 Tool Loop，接入 OpenAI-compatible 流式 API，向模型提供 13 个内置工具，并支持 Skills 按需加载、MCP 动态工具注册和 Explore/Plan/General 子 Agent。
- 设计分层工具安全体系，实现 `allow/ask/deny` 权限覆盖、文件修改 Diff 预览、单次/会话级审批、外部入口工具白名单及异常隔离；保证工具异常和用户拒绝不会破坏主循环及 assistant/tool 消息配对。
- 实现长上下文与可恢复会话机制：在 80% 上下文阈值触发累积摘要，结合 pair-safe tail、旧工具结果 micro-compaction、JSONL transcript 和 checkpoint lineage，支持 `/compact`、`/resume` 及异常历史清洗。
- 设计长期记忆 extraction/recall v2：通过受限 memory-only 子 Agent 后台提取记忆，并使用 no-tool selector 异步预取相关主题，加入敏感信息过滤、读取上限、late-result 丢弃和 external session 隔离。
- 采用 Spec-first、TDD 和风险分层验收流程；仓库包含 72 个测试文件，最近一次项目验收记录为 `649 passed`，并针对 PowerShell/cmd.exe 的审批菜单、会话恢复和 Tool Loop 完成原生 PTY 验收。

简历空间有限时，优先保留前四条。QQchat 可以在面试深入追问时介绍，不建议占用核心项目描述的大量篇幅。

### 4.3 不建议使用的表述

- 不要写“分布式多 Agent 系统”。
- 不要写“高并发 Agent 平台”。
- 不要把 Memory Recall 直接包装成生产级 RAG。
- 不要写“完全兼容 Claude Code”。
- 不要写“生产级安全”，因为 secret 存储和 prompt injection 防御仍有缺口。
- 不要写“649 个单元测试”，应写“649 项自动化回归通过”。

## 5. 项目介绍话术

### 5.1 30 秒版本

> 我开发了一个终端原生 AI Coding Agent。它基于 OpenAI-compatible Function Calling 实现了完整 Tool Loop，支持 13 个内置工具、Skills、MCP、子 Agent、Plan Mode、会话恢复和长期记忆。项目重点不是聊天 UI，而是解决工具执行安全、长上下文压缩、消息协议一致性和跨会话记忆问题。仓库目前包含 72 个测试文件，最近一次完整回归记录为 649 passed。

### 5.2 2 分钟版本

> 我开发了一个终端原生 AI Coding Agent。项目核心不是聊天界面，而是完整的 Agent Runtime：模型可以通过 Function Calling 调用文件、搜索、Shell、任务管理、Plan Mode 和子 Agent 工具。
>
> 我重点解决了三个问题。第一是工具安全，通过分层权限、Diff 预览和外部入口白名单控制副作用；第二是长会话，通过累积摘要、工具消息配对保护和 checkpoint 实现 compact/resume；第三是跨会话记忆，通过受限后台 Agent 提取记忆，再异步召回当前问题相关的主题。
>
> 项目还接入了 Skills 和 MCP，当前有 72 个测试文件，最近全量回归记录为 649 passed。这个项目让我认识到，Agent 真正困难的不是让模型调用工具，而是保证它在失败、拒绝、压缩和恢复后仍保持一致状态。

### 5.3 5 分钟展开顺序

如果面试官允许深入介绍，按以下顺序展开：

1. 项目动机：为什么希望理解 Agent Runtime，而不是只调用框架。
2. 普通 user turn 与多轮 Tool Loop。
3. 权限和审批模型。
4. 上下文压缩、Session transcript 与恢复。
5. Auto Memory Extraction/Recall v2。
6. Skills 和 MCP 扩展机制。
7. 最复杂的 Bug：用户拒绝工具后如何中断当前 turn。
8. 测试证据、当前不足和下一步 Eval 计划。

## 6. 核心架构速记

### 6.1 一次普通 User Turn

```text
用户输入
  -> 写入 runtime history 和 append-only session transcript
  -> 构造 system prompt
  -> 启动 relevant memory prefetch
  -> 判断是否需要 context compression
  -> 调用 LLM
  -> 无 tool_calls：生成最终回答
  -> 有 tool_calls：权限判断、预览、审批、执行
  -> 写回 assistant/tool messages
  -> 继续调用 LLM，直到最终回答或中断
  -> 成功 turn 后异步提交 memory extraction
```

### 6.2 Tool Loop 的关键不变量

- 单个工具异常不能打崩主循环。
- assistant 声明的每个 tool call 必须有对应 tool result。
- orphan、乱序或 malformed tool message 不能发给 provider。
- 用户交互式拒绝与配置 `deny` 的语义不同。
- external turn 不能复用本地交互审批能力。
- blocked tool 即使被模型再次返回，也不能执行。
- 成功加载 Skill 后，同 batch 后续 sibling tools 应被 barrier 阻断。

### 6.3 Context、Session 与 Memory

| 概念 | 解决的问题 | 生命周期 | 当前实现 |
|------|------------|----------|----------|
| Context | 当前请求让模型看到什么 | 单次请求/当前运行时 | token 估算、自动压缩、pair-safe tail |
| Session | 上次对话和工具执行发生了什么 | 跨进程恢复 | JSONL transcript、checkpoint、`/resume` |
| Memory | 跨 Session 应长期记住什么 | 长期 | XCODE.md、MEMORY.md、topic files、recall |

一句话回答：

> Context 是工作窗口，Session 是完整交互记录，Memory 是跨会话稳定知识。

还要区分“存储位置”和“语义类型”：Project XCODE.md、User XCODE.md、Auto Memory 是三个存储位置；`user`、`feedback`、`project`、`reference` 是 Auto Memory topic 的四种语义类型，不应混为“四个存储层”。

## 7. 高频面试问题与参考回答

### Q1：Agent 的一次完整 Tool Loop 是怎样的？

参考回答：

> 用户输入先进入统一的 user-turn 流程，写入内存 history 和 append-only session transcript。Runtime 构造 system prompt，并判断是否需要压缩上下文，然后把消息和工具 schema 发给模型。
>
> 如果模型返回普通文本，当前 turn 结束；如果返回 tool calls，Runtime 先检查 blocked tools、权限和外部工具范围，再展示预览和审批。执行结果以 `role=tool` 写回 history，然后继续请求模型，直到得到最终答案或达到轮次限制。
>
> 所有工具异常都会转换为结构化工具结果，不能让异常直接打崩主循环。

追问准备：

- 为什么工具异常要返回给模型，而不是直接抛出？
- 模型一次返回多个 tool calls 怎么处理？
- tool call 参数不是合法 JSON 怎么办？
- API 请求在 tool batch 中间失败怎么恢复？

### Q2：为什么不用 LangChain、AutoGen，而要自己实现？

参考回答：

> 我的目标是学习和控制 Agent Runtime 的核心协议，尤其是 assistant/tool 消息配对、权限审批、Session 恢复和上下文压缩。直接基于 OpenAI-compatible API 实现，可以明确控制每个状态转换，也更容易为边界条件写测试。
>
> 这并不代表框架没有价值。如果目标是快速交付业务 Agent，我会根据生态、可观测性和维护成本选择框架；这个项目选择自研，是为了获得底层控制力和可解释性。

不要回答成“框架都不好用”。面试官更关心你能否基于目标做技术选型。

### Q3：工具权限是如何设计的？

参考回答：

> 权限优先级是 session rule、project config、global config、default policy。只读工具默认允许，文件写入和 Shell 默认询问，显式 deny 的优先级最高。
>
> 文件修改在审批前展示 Diff，用户可以单次允许或本会话允许。外部 QQ 入口没有交互式审批能力，因此额外使用 visible-tools 和 execution-allowlist 双重限制，默认只开放只读工具。
>
> `is_read_only` 只是工具属性，真正的执行许可仍由 PermissionManager 和 ToolCallExecutor 决定。

### Q4：用户拒绝工具后，为什么不能简单把错误交给模型继续？

参考回答：

> 本地审批菜单中的 No 表达的是“用户希望停止当前动作”，不是普通工具失败。如果继续请求模型，模型可能马上寻找其他方式执行同一目标，这会违背用户意图。
>
> 我的实现会写入完整的 assistant tool call 和 denial tool result，停止同批次后续工具，再追加固定 system interruption marker，结束当前 turn。同时不生成伪 assistant 回复，也不运行成功后的 memory hook。这样既符合用户语义，也保持了 OpenAI 消息协议的合法配对。

这是项目中最适合用于回答“最复杂 Bug”或“如何处理状态一致性”的案例。

### Q5：为什么上下文压缩不能直接保留最近 N 条消息？

参考回答：

> 因为 tool call 是一个协议块：assistant 声明多个 tool calls 后，必须紧跟对应的 tool results。简单截取最近 N 条可能留下 orphan tool message，或者留下没有结果的 assistant tool call，导致下一次 API 请求失败。
>
> 我的实现使用 pair-safe tail，成对保留 assistant/tool 消息；旧的大型工具结果会 micro-compact 成带工具名和调用 ID 的占位信息；其余历史生成累积摘要，并写入 checkpoint。发送给模型前还会再次清洗 malformed 或乱序的历史。

### Q6：摘要本身发生幻觉怎么办？

参考回答：

> 当前系统通过累积摘要、保留最近 pair-safe tail 和恢复 bounded work state 来降低信息丢失，但没有办法完全证明模型摘要无幻觉。checkpoint hash 能证明摘要是否被篡改，不能证明语义正确。
>
> 下一步可以加入结构化 summary schema、关键事实引用、压缩前后约束检查，以及专门的 compact Eval，统计任务约束保留率和恢复后的任务成功率。

这里要承认边界，不要声称摘要完全可靠。

### Q7：Session、Context 和 Memory 有什么区别？

参考回答：

> Context 是当前模型请求能看到的工作窗口，会受到 token 上限约束；Session 是可恢复的完整交互记录，使用 JSONL append-only transcript 持久化；Memory 是跨 Session 保存的稳定知识。
>
> Session 解决“上次聊了什么”，Context 解决“这次请求带什么”，Memory 解决“长期应该记住什么”。如果把三者混在一起，就会出现上下文无限增长、旧信息污染或恢复状态不一致的问题。

### Q8：Session 为什么使用 JSONL，而不是数据库？

参考回答：

> JSONL 适合单机 CLI 的 append-only transcript：实现简单、崩溃时已写入记录容易保留、便于人工审计，也方便逐行跳过损坏事件。当前数据规模和单用户模型下没有必要先引入数据库。
>
> 如果未来支持多进程写入、全文查询、云同步或多用户隔离，我会迁移到 SQLite 或事件存储，并增加事务、索引、schema migration 和并发控制。

### Q9：长期记忆如何避免把错误和隐私永久保存？

参考回答：

> 自动提取只在本地成功 turn 后触发，QQ、external 和 headless turn 默认不写长期记忆。提取 Agent 只能访问 memory 目录，不允许 Shell、Git、MCP、项目任意读取或继续派发 Agent。
>
> 写入前要求 Evidence，并过滤通用任务摘要、无意义 slug 和 secret-like 内容。单次最多五轮模型调用、最多保存三个主题。召回时只允许选择 manifest 中已有文件，非法 JSON、编造文件名或路径分隔符都会 fail closed。

### Q10：Agent 的记忆机制是怎样的？四种记忆类型分别“存什么、怎么存、什么时候取”？

参考回答：

> 我的 Agent 采用文件驱动的分层记忆机制，先区分存储位置和语义类型。存储位置有三类：项目级 `XCODE.md` 保存团队共同遵守的项目宪法；用户级 `~/.xcode/XCODE.md` 保存跨项目用户画像；Auto Memory 使用 `MEMORY.md` 短索引加独立 topic 文件，保存 Agent 从交互中学习到的、未来可能复用的信息。
>
> Auto Memory topic 又分为 `user`、`feedback`、`project` 和 `reference` 四种语义类型。成功的本地 REPL turn 会异步提交给受限 Memory Extraction Subagent；它只能访问 memory 目录，写入前必须通过 evidence、slug 和敏感信息检查。读取时，Project/User XCODE.md 和 Auto Memory Index 会以有界长度进入基础 Prompt；具体 topic 不常驻上下文，而是在当前问题相关时由 no-tool selector 选择，经过 bounded read 后在当前 turn 的安全点注入，迟到结果直接丢弃。

四种 Auto Memory 类型：

| 类型 | 存什么 | 怎么存 | 什么时候取 |
|------|--------|--------|------------|
| `user` | 用户角色、目标、知识背景、解释偏好等不能从代码推导的信息 | 跨项目且重要的信息写入 User XCODE.md；仅对当前项目有效的信息写入 `type: user` topic，并附 Evidence | 所有项目通用偏好从 User XCODE.md 常驻注入；项目特定信息在当前问题与用户背景相关时按需召回 |
| `feedback` | 用户对工作方法的纠正，或被确认有效的非显然做法 | 写成 `type: feedback` topic，正文包含规则、Why、How to apply 和 Evidence，并更新 `MEMORY.md` 索引 | 当未来任务涉及相同工具、测试策略、Review 方法或工作方式时召回 |
| `project` | 不能从代码或 Git 推导的项目目标、人员分工、绝对日期、截止时间、事故背景和临时决策 | 写成 `type: project` topic；相对日期转成绝对日期，并记录来源证据。团队长期规范仍应写 Project XCODE.md | 当当前任务涉及对应模块、项目阶段、负责人、事故或时间约束时召回，并用当前代码和文档再次验证 |
| `reference` | 外部资源的指针及用途，例如文档 URL、看板、监控面板或外部系统入口 | 写成 `type: reference` topic，保存资源名称、位置、用途和 Evidence，不复制大量外部内容 | 当任务需要查找对应外部信息或用户提到相关系统时召回；真正使用前重新访问权威来源 |

“存什么”的总原则：

- 只保存持久、非显然、不能从当前代码或 Git 直接推导，并且未来可能改变 Agent 行为的信息。
- 不保存临时任务进度、普通实现总结、文件修改清单、测试结果、Git 历史和已经存在于项目文档里的内容。
- 项目共同规范进入 Project XCODE.md；跨项目用户偏好进入 User XCODE.md；具体反馈、项目背景和外部指针进入 Auto Memory topic。

“怎么存”的链路：

```text
本地成功 assistant turn
→ AfterTurn hook 非阻塞提交
→ single-flight MemoryExtractionRunner
→ memory-only Extraction Subagent
→ Policy 校验 Evidence、slug、内容类型和 secret
→ 写入 <slug>.md topic
→ 更新 MEMORY.md 短索引
```

手动记忆也可以由模型通过普通 `read_file`、`write_file`、`edit_file` 完成，但只能写入解析后的 Memory 路径；显式权限 `deny` 始终优先。

“什么时候取”的链路：

```text
构造基础 Prompt
→ 有界注入 Project XCODE.md、User XCODE.md、Auto Memory Index
→ 本地用户输入触发 turn-local prefetch
→ no-tool selector 从 manifest 选择相关 topic
→ 最多读取 5 个 topic，每个最多 4096 bytes 或 200 行
→ 当前 turn 安全点注入 system reminder
→ late/stale 结果丢弃，不污染下一轮
```

触发 Recall 前还会检查：`auto_memory` 是否开启、用户是否要求忽略记忆、query 是否有效、manifest 是否为空，以及当前 Session 已展示的 Memory 是否达到 60 KiB 上限。Memory 与当前代码冲突时，以代码、Git 和权威文档为准。

面试总结句：

> 我的记忆设计不是把全部历史塞进 Prompt，而是把“长期稳定信息”分层保存：短索引常驻、topic 正文按需召回；写入时有受限提取和质量门，读取时有相关性选择、长度预算、当前状态复核和 turn-local 隔离。

### Q11：异步 Memory Recall 如何防止污染下一轮对话？

参考回答：

> Prefetch Future 与当前 turn 绑定，主模型请求不会等待它。只有在当前 turn 的安全点完成，结果才会注入一次；如果完成过晚，就标记为 late 并丢弃，不能留给下一轮无关问题。
>
> 注入前还会过滤本 Session 已经展示过的 memory，以及本轮刚刚读写过的 memory 文件，减少重复和陈旧信息。

### Q12：这套 Memory 是不是 RAG？

参考回答：

> 它具备检索增强的思想，但当前不是典型的向量 RAG。系统先扫描结构化 topic manifest，再通过 no-tool LLM selector 选择相关文件，最后做 bounded read 并以 system reminder 注入。
>
> 这种设计适合 topic 数量有限、希望保持文件可审计的个人 Coding Agent。规模增大后可以比较 BM25、embedding 或 hybrid retrieval，并通过 Eval 判断是否值得增加复杂度。

### Q13：Tool、Skill 和 MCP 的区别是什么？

参考回答：

> Tool 是模型可以直接调用的原子能力，例如读文件或执行 Shell；Skill 是按需加载的任务说明和工作流，指导模型如何组合工具；MCP 是外部工具提供者的标准连接协议。
>
> 在项目中，Skill 正文不常驻 system prompt，只注入轻量目录，模型需要时再加载。MCP 工具通过命名空间注册到本地 ToolRegistry，并经过 trust、schema 转换、名称冲突检测和输出长度限制。

### Q14：Skill 为什么需要 barrier 和 blocked-tools？

参考回答：

> 模型加载 Skill 后，完整 Skill prompt 要到下一次模型请求才真正可见。如果同一个 assistant response 中 Skill 后面还有写文件或 Shell 调用，这些调用是在模型尚未读取 Skill 约束时生成的，所以不能直接执行。
>
> barrier 会拒绝 Skill 后面的 sibling tool calls；blocked-tools 则在后续 schema 和执行层同时隐藏或拒绝 SkillTool，防止递归调用。

### Q15：Skill 的 `allowed-tools` 是严格白名单吗？

参考回答：

> 当前不是。它表示 Skill 声明的工具需求和审计 metadata，不会收窄 ToolRegistry schema，也不会自动提权。危险工具仍需要经过统一权限系统。
>
> 如果需要严格能力限制，应新增独立的 `visible-tools` 或 `tool-scope` 语义，不能把声明性字段和执行安全混在一起。

### Q16：MCP 为什么需要 trust fingerprint？

参考回答：

> MCP stdio server 本质上会启动本地命令，因此不能因为配置文件存在就自动执行。系统根据 project key、server name、command、args、cwd 和 env keys 计算 fingerprint，用户明确 trust 后才启动。
>
> 如果命令、参数或工作目录变化，fingerprint 变化，原 trust 自动失效。env 只记录 key 不记录 value，避免把 secret 写入 trust 文件。这里仍需要结合命令预览和风险提示，因为 `npx`、`uvx`、`docker run` 等命令可能下载和执行外部代码。

### Q17：你的子 Agent 真的是多 Agent 系统吗？

参考回答：

> 当前更准确地说是“单 Runtime 下的委派式子 Agent”，不是分布式或并行多 Agent 系统。Explore 和 Plan 子 Agent 有独立上下文及只读工具范围，General Agent 可以使用普通工具；每个子 Agent 最多执行 15 轮，而且不能继续递归派发。
>
> 当前 dispatch 是同步的。下一步如果并行化，需要补充任务预算、取消、超时、结果合并、写冲突和审批归属，而不只是加线程池。

### Q18：为什么主 Agent 没有整体改成 asyncio？

参考回答：

> 主 REPL、流式 Rich 输出和 prompt_toolkit 审批交互都涉及终端状态，整体 async 化会扩大状态竞争和兼容风险，因此当前主循环保持同步。
>
> 对真正适合后台执行的部分采用受控并发：Memory Recall 使用单 worker prefetch，Memory Extraction 使用 single-flight runner，MCP SDK 在专用 event loop/thread 中运行，并向主流程暴露同步、带 timeout 的接口。

### Q19：Prompt Injection 怎么防？

参考回答：

> 当前系统主要控制执行后果，而不是声称可以完全识别 Prompt Injection。只读和危险工具分离，写入/Shell 需要审批，external turn 有独立工具范围，Memory 和 MCP 也有 sandbox 或 trust 边界，所以即使模型受到恶意内容影响，也不能自动获得全部执行权限。
>
> 但语义层 Prompt Injection 仍没有完全解决。后续需要进一步标注不可信内容、分离数据与指令、增加 Shell policy 和工作目录 sandbox，并对高风险操作建立独立 Eval。

### Q20：你怎么证明 Agent 做得好？

参考回答：

> 当前自动化回归主要证明 Runtime 的确定性行为，例如权限、消息配对、compact、resume、memory 和 MCP；它们不能直接证明模型完成编码任务的效果。
>
> 下一步我会建立固定仓库任务集，统计任务完成率、最终测试通过率、无效工具调用率、审批拒绝恢复率、平均轮次、延迟、token 和成本，并固定模型与参数做版本间回归。这会把“功能可运行”升级为“Agent 效果可度量”。

### Q21：项目最大的技术不足是什么？

参考回答：

> 第一是缺少模型行为层的 Eval；第二是 sub-agent 仍为同步委派；第三是可观测性主要依赖 JSONL transcript，缺少结构化 trace 和指标；第四是配置安全仍需要把 API Key 从明文 JSON 迁移到环境变量或系统 Keyring，并禁止项目配置覆盖敏感字段。
>
> 我会优先建设 Eval，因为它决定后续的并发、Memory、Prompt 和模型优化是否真的有效。

### Q22：API Key 当前如何存储，安全吗？

参考回答：

> 当前支持环境变量，也可以保存到 `~/.xcode/config.json`。后者是明文文件，因此只能算本地开发便利方案，不能称为生产级 secret storage。项目级配置合并目前也需要排除 `api_key` 等敏感字段。
>
> 改进方案是默认只从环境变量或系统 Keyring 读取 secret，配置文件只保存非敏感参数，并校验文件权限和日志脱敏。

### Q23：这个项目是不是主要由 AI 写的？

推荐回答模板：

> 项目采用 AI-assisted 开发流程，但我负责需求定义、架构边界、Spec、任务拆分、验收标准和代码 Review，AI 辅助部分实现和测试。我的 ownership 不体现在逐字符手写，而在于我能解释每个核心状态转换、指出当前限制，并独立定位和修复审批中断、tool pairing、compact 与 memory late-result 等问题。

这段回答必须按照真实参与情况调整。不要宣称完全手写，也不要把 AI 生成的代码直接当作自己的设计成果。面试官最终会通过连续追问判断 ownership。

## 8. 最复杂问题案例：审批拒绝中断当前 Turn

这段经历可以用于回答“最难的 Bug”“如何保证一致性”“一次完整的排障过程”等行为题。

### 8.1 问题

用户在本地审批菜单拒绝 `run_shell` 或文件写入后，如果 Runtime 把 denial 当作普通工具错误继续请求模型，模型可能继续寻找替代方案，导致用户已经拒绝但 Agent 仍主动执行。

### 8.2 难点

- 不能直接丢弃工具调用，否则会形成缺少 tool result 的 assistant tool call。
- 不能追加伪 assistant final text。
- 不能让同 batch 后续 sibling tools 继续执行。
- 不能把中断 marker 写成 `role=user`，否则会污染 session preview。
- 中断 turn 不能触发成功后的 auto memory extraction。
- 下一轮用户输入仍要能看到上一轮拒绝记录。

### 8.3 解决方案

1. `ToolExecutionResult` 增加结构化 `interrupted_by_user` 状态。
2. 写入 `User denied tool: <tool>` 的 tool result，保持 assistant/tool 配对。
3. 停止当前 batch 后续工具。
4. Runtime 追加固定 system interruption marker。
5. 当前 turn 直接结束，不再请求模型。
6. 不追加 assistant final text，不运行 after-turn success hooks。
7. 增加 Session、Resume、下一轮上下文和原生 PowerShell/cmd.exe PTY 回归。

### 8.4 面试总结句

> 这个问题让我意识到，Agent Runtime 不是普通的请求循环，而是一个需要明确状态和不变量的协议状态机。工具失败、配置拒绝和用户中断看起来都像“工具没执行”，但它们的业务语义和后续状态转换完全不同。

## 9. 测试与质量保障回答框架

### 9.1 当前测试覆盖重点

- Tool Loop 与工具异常。
- 权限 allow/ask/deny。
- 用户审批拒绝和 turn interruption。
- Context token 估算和 compaction。
- assistant/tool message 清洗。
- Session transcript 与 resume。
- Auto Memory Extraction/Recall。
- Skills 加载、调用、barrier 和防递归。
- MCP config、trust、connection、dynamic refresh 和 output limit。
- QQchat auth、gateway、message、service 和 external turn。
- Rich/prompt_toolkit 终端行为及 Windows 原生 PTY 验收。

### 9.2 为什么不能只说“测试很多”

测试数量不是最终目标。面试时要区分：

- Runtime regression：证明确定性代码路径没有回归。
- Agent Eval：证明模型在真实任务中的完成质量。
- E2E acceptance：证明真实终端、网络和平台集成可工作。

当前项目第一类较强，第三类部分完成，第二类是最明显缺口。

### 9.3 推荐新增 Eval 指标

- Task success rate。
- 最终项目测试通过率。
- Tool selection precision。
- 无效或重复工具调用率。
- 用户审批拒绝后的恢复正确率。
- 平均 LLM 轮次和工具调用次数。
- 首 token 延迟与总耗时。
- Prompt、completion 和总 token。
- 单任务成本。
- Compact 前后任务约束保留率。
- Memory recall precision、污染率和重复注入率。

## 10. 面试前准备清单

### 10.1 必须完成

- [ ] 在干净环境执行 `pip install -e .`。
- [ ] 安装测试依赖并重新执行 `pytest -q`。
- [ ] 记录 Python 版本、操作系统、测试数量和运行时间。
- [ ] 准备一个不会暴露真实 API Key 的演示配置。
- [ ] 准备 30 秒和 2 分钟项目介绍。
- [ ] 能画出 user turn、Tool Loop、compact 和 Memory Recall 数据流。
- [ ] 熟悉审批拒绝中断当前 turn 的完整问题链。
- [ ] 能明确说明哪些能力已经实现，哪些只是 Roadmap。

### 10.2 推荐改进

- [ ] 增加 10–20 个固定 Coding Agent Eval 任务。
- [ ] 输出成功率、延迟、token 和成本报告。
- [ ] 禁止项目级配置覆盖 `api_key` 等敏感字段。
- [ ] 接入环境变量或系统 Keyring 存储 secret。
- [ ] 在 README 增加架构图、演示 GIF 和测试结果。
- [ ] 为关键 runtime event 增加结构化 trace id、turn id 和 tool call timing。
- [ ] 补齐 Roadmap 中标记的真实 QQ/Windows 手工验收。

### 10.3 三分钟演示脚本

推荐演示路径：

1. 让 Agent 读取一个小型项目并定位问题。
2. 进入 Plan Mode，输出修改计划。
3. 调用 `edit_file`，展示 Diff 和审批菜单。
4. 执行测试并展示工具结果摘要。
5. 演示拒绝一个危险工具后立即回到输入提示符。
6. 执行 `/compact`，展示 checkpoint。
7. 退出并通过 `/resume` 恢复最近对话。

演示应使用固定模型、固定代码仓库和固定问题，避免现场网络或模型随机性让演示失控。

## 11. 复习路线

建议按以下顺序复习：

1. OpenAI Function Calling 消息协议。
2. ReAct 和 Agent Loop 基础思想。
3. 状态机、事件日志和 append-only transcript。
4. Tool sandbox、capability security 和 Prompt Injection。
5. Context engineering、compaction 和 RAG/Memory 区别。
6. `asyncio`、线程池、Future、timeout、cancel 和 backpressure。
7. MCP 的 server lifecycle、schema 和 trust model。
8. LLM/Agent Eval、可观测性、token 和成本分析。

## 12. 最终面试原则

1. 先讲问题和设计目标，再讲文件和类名。
2. 用真实约束解释取舍，不要把所有选择包装成“最优方案”。
3. 主动区分已实现、已测试、手工验收和未来规划。
4. 遇到不足不要回避，要给出风险、优先级和演进方案。
5. 任何简历指标都应能在仓库、测试输出或演示中复现。
6. 如果项目使用 AI 辅助开发，应如实说明自己的 ownership，并确保能够解释核心代码和设计边界。

最值得让面试官记住的一句话：

> 我做的不只是让模型调用工具，而是让 Agent 在工具失败、用户拒绝、上下文压缩、进程退出和会话恢复后，仍然保持安全、合法且可继续执行的状态。
