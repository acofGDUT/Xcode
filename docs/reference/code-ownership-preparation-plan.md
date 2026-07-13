# Xcode Agent 代码 Ownership 与面试补强计划

> 状态：进行中（第一天必答问题、第二天学习任务已完成）
>
> 制定日期：2026-07-10
>
> 最近更新：2026-07-12
>
> 建议周期：7 天，每天 2–4 小时
>
> 配套文档：[Xcode Agent 项目面试准备手册](project-interview-guide.md)

## 1. 计划目标

本计划用于把当前的项目能力从“能够定义需求、架构和验收标准”补强为“能够解释、定位、修改和验证核心代码”。

七天结束后，应达到以下结果：

- 不看文档画出六条核心数据流。
- 能在十分钟内把一个行为问题定位到相关模块和测试。
- 能解释核心状态、输入、输出、不变量和失败分支。
- 能先写失败测试，再独立完成一个小型 Runtime 改动。
- 能诚实、准确地说明 AI 在项目中的参与方式和自己的 Ownership。
- 能完成一轮 30–45 分钟的项目技术模拟面试。

本计划不要求逐行背诵约 1.1 万行源码，也不要求一次掌握全部 MCP、QQchat 和终端 UI 细节。优先掌握影响 Agent 正确性和安全性的核心路径。

## 2. 当前基线

当前能力判断：

| 维度 | 当前状态 | 七天目标 |
|------|----------|----------|
| 产品目标与需求定义 | 强 | 保持，并能映射到代码契约 |
| 架构思想与规范设计 | 较强 | 能指出对应模块、状态和测试 |
| 核心流程理解 | 中等 | 能脱稿解释和手动画图 |
| 具体实现理解 | 待补强 | 能逐函数追踪六条核心链路 |
| 调试与修改 | 待补强 | 独立完成一次 TDD 小改动 |
| 面试表达 | 已有素材 | 形成证据驱动的稳定回答 |

## 3. 完成标准

只有同时满足以下条件，计划才算完成：

- [ ] 六条核心链路均完成一页学习卡。
- [ ] 六张数据流图可以脱稿画出。
- [ ] 至少阅读并解释 12 个核心测试。
- [ ] 至少做过 3 次“预测测试结果 → 故意制造失败 → 定位原因 → 恢复代码”的练习。
- [ ] 独立完成主 Tool Loop 的小型改动和回归测试。
- [ ] 能说出项目至少 5 个真实边界或不足。
- [ ] 完成一份 300–500 行 Mini Agent，或完成等价的独立编码练习。
- [ ] 完成一次限时模拟面试，并记录不会的问题。
- [ ] 重新运行聚焦测试和全量测试，保存真实结果。

## 4. 学习规则

### 4.1 每个模块只回答八个问题

学习每个模块时，统一填写：

```text
1. 它解决什么问题？
2. 入口函数是什么？
3. 输入是什么？
4. 输出是什么？
5. 修改了哪些状态？
6. 核心不变量是什么？
7. 失败分支有哪些？
8. 哪些测试证明它正确？
```

学习卡模板：

```markdown
## 模块名称

- 目标：
- 入口：
- 输入：
- 输出：
- 状态变化：
- 核心不变量：
- 失败分支：
- 关键测试：
- 当前不足：
- 如果让我修改：
```

### 4.2 使用测试反推代码

每个模块按以下顺序学习：

1. 先读测试名称和输入，预测预期结果。
2. 运行聚焦测试，确认基线。
3. 从测试调用点追到生产代码入口。
4. 手动画出输入、状态变化和输出。
5. 在专用学习分支中故意改变一个关键条件。
6. 重新运行测试，解释失败原因。
7. 恢复代码，再次运行测试。
8. 关闭代码和 AI 回答，脱稿复述。

不要在当前主分支随意制造失败。建议使用独立学习分支：

```bash
git switch -c learning/code-ownership
```

### 4.3 AI 使用规则

本计划允许使用 AI，但必须遵守：

- 先独立预测，再向 AI 求证。
- AI 解释后必须关闭回答并自己复述。
- AI 可以 Review 你的实现，但不要让 AI 直接完成每日核心练习。
- 遇到 Bug 至少独立定位 20 分钟，再请求提示。
- 请求 AI 时优先要“提示、反例、测试建议”，不直接要完整答案。
- 每天至少保留一段完全不依赖 AI 完成的代码或测试。

## 5. 开始前准备

### 5.1 环境准备

- [ ] 确认 Python 版本为 3.10 或以上。
- [ ] 安装项目和 pytest。
- [ ] 运行一次全量测试并记录基线。
- [ ] 创建专用学习分支。
- [ ] 准备纸笔或绘图工具。

建议命令：

```bash
python -m pip install -e .
python -m pip install pytest
python -m pytest -q
```

基线记录：

```text
日期：
操作系统：
Python 版本：
Commit：
测试结果：
测试耗时：
```

### 5.2 每日固定产出

每天结束前必须产生：

- 一张数据流图。
- 一页模块学习卡。
- 至少两个能脱稿回答的面试问题。
- 至少一个亲手执行的测试或修改练习。
- 一条“今天仍然不懂什么”的记录。

## 6. 第一天：User Turn、LLM Client 与 Tool Loop

### 6.1 目标

理解一轮用户对话如何从 REPL 输入开始，经过多次 LLM/Tool 循环，最终写入 Assistant Answer 并触发 After-turn Hook。

### 6.2 重点文件

- `src/xcode_cli/core/agent.py`
- `src/xcode_cli/core/llm.py`
- `src/xcode_cli/core/tool_registry.py`
- `src/xcode_cli/core/tooling/execution.py`
- `src/xcode_cli/core/turn.py`

### 6.3 必须回答

- [x] User Turn 为什么不等于一次 LLM Request？
- [x] 用户输入如何进入 `_history` 和 Transcript？
- [x] System Prompt 和 `_history` 是什么关系？
- [x] 流式 Tool Call Arguments 如何拼接和解析？
- [x] Assistant Tool Call 与 Tool Result 如何写回？
- [x] 什么条件结束当前 Tool Loop？
- [x] LLM Request 失败时保存了哪些状态？
- [x] 当前主 Tool Loop 为什么存在无限循环风险？

进度记录（2026-07-11）：已完成第一天全部必答问题；动手练习和当日验收尚未标记完成。

### 6.4 动手练习

1. 手工构造一轮包含两个工具调用的 History。
2. 从 `_run_user_turn()` 开始逐函数追踪到 `LLMClient.complete()`。
3. 给 `ToolRegistry` 注册一个只返回固定文本的练习工具。
4. 运行 Tool Loop 聚焦测试。

建议测试：

```bash
python -m pytest tests/test_agent_user_turn.py tests/test_agent_tool_loop.py tests/test_llm.py -q
```

### 6.5 当日验收

- [ ] 能在五分钟内画出一轮完整对话。
- [ ] 能解释 User Turn、LLM Round 和 Tool Batch 的区别。
- [ ] 能指出 Tool Loop 的正常结束、中断和错误路径。
- [ ] 不看代码写出合法的 assistant/tool 消息序列。

## 7. 第二天：Tool Registry、Permission 与 Approval

### 7.1 目标

理解工具为什么不能直接执行，以及权限、入口范围、Diff 预览和用户中断如何形成安全边界。

### 7.2 重点文件

- `src/xcode_cli/core/permissions.py`
- `src/xcode_cli/core/tool_registry.py`
- `src/xcode_cli/core/tooling/approval.py`
- `src/xcode_cli/core/tooling/execution.py`
- `src/xcode_cli/core/external_turn.py`

### 7.3 必须回答

- [x] session、project、global、default 权限优先级是什么？
- [x] `is_read_only` 与最终执行许可有什么区别？
- [x] 本地审批 `No` 为什么不同于配置 `deny`？
- [x] External Turn 为什么需要 visible-tools 和 execution-allowlist 两层限制？
- [x] 文件修改为什么在审批前生成 Diff？
- [x] Memory 写入为什么可以 auto-allow，但显式 deny 仍优先？
- [x] Tool 异常为什么要转换成 Tool Result？

### 7.4 动手练习

1. 为一个练习工具分别设置 allow、ask、deny，预测执行结果。
2. 阅读本地审批拒绝后中断当前 Turn 的测试。
3. 故意改变一条权限优先级，在学习分支观察测试失败。
4. 解释为什么 QQchat 默认只开放只读工具。

建议测试：

```bash
python -m pytest tests/test_tool_approval.py tests/test_agent_memory_permissions.py tests/test_agent_tool_loop.py tests/test_external_turn.py -q
```

### 7.5 当日验收

- [x] 能画出工具执行前的所有检查顺序。
- [x] 能解释用户拒绝工具后的完整 History。
- [x] 能说出 Prompt 约束和 Runtime 硬约束的区别。

进度记录（2026-07-12）：第二天的必答问题、动手学习和当日验收已完成。

## 8. 第三天：History、Transcript 与 Resume

### 8.1 目标

理解一份会话为什么需要 Transcript、Runtime History 和 API Messages 三个视图，以及 Resume 如何恢复合法 History。

### 8.2 重点文件

- `src/xcode_cli/core/session.py`
- `src/xcode_cli/core/session_resume.py`
- `src/xcode_cli/core/message_history.py`
- `src/xcode_cli/core/conversation/resume.py`
- `src/xcode_cli/core/turn.py`

### 8.3 必须回答

- [ ] Transcript、`_history` 和 API Messages 有什么区别？
- [ ] 什么是 orphan Tool Message？
- [ ] 什么是 malformed Tool Call？
- [ ] 为什么 Tool Result 必须紧随对应 Assistant Tool Call？
- [ ] History Sanitizer 如何线性扫描消息？
- [ ] Skill 的 display/model 双视图如何落盘和恢复？
- [ ] Resume 为什么使用 60% Token Budget？
- [ ] 裁剪 History 时如何防止制造新的 orphan？

### 8.4 动手练习

1. 手写四组非法 History，并预测 Sanitizer 输出。
2. 运行 `test_message_history.py`，逐个解释断言。
3. 构造包含 Skill `metadata.model_content` 的临时 Transcript。
4. 比较 Model History Builder 与 UI Replay Builder 输出。

建议测试：

```bash
python -m pytest tests/test_message_history.py tests/test_session.py tests/test_session_resume.py tests/test_agent_resume_command.py -q
```

### 8.5 当日验收

- [ ] 能不看代码写出 Sanitizer 伪代码。
- [ ] 能解释为什么不直接把 Transcript 原样发送给模型。
- [ ] 能解释 Skill Hidden Prompt 的边界：UI 隐藏但磁盘未加密。
- [ ] 能说明 Checkpoint 前的 Skill Prompt 为什么不会逐字恢复。

## 9. 第四天：Context Compact 与 Work State

### 9.1 目标

理解长会话达到 Context 阈值后，如何在不破坏工具协议的前提下压缩历史并保存现场。

### 9.2 重点文件

- `src/xcode_cli/core/context.py`
- `src/xcode_cli/core/conversation/compaction.py`
- `src/xcode_cli/core/work_state.py`
- `src/xcode_cli/core/message_history.py`

### 9.3 必须回答

- [ ] 为什么不能简单保留最近 N 条消息？
- [ ] pair-safe tail 如何保证 Assistant/Tool 配对？
- [ ] micro-compaction 清除了什么、保留了什么？
- [ ] 累积摘要如何使用 Previous Summary？
- [ ] Work State 保存哪些现场？
- [ ] Checkpoint lineage 和 hash 能证明什么、不能证明什么？
- [ ] Summary 请求失败时为什么不能改写 `_history`？

### 9.4 动手练习

1. 手工构造 12 条包含 Tool Calls 的 History，计算 pair-safe tail。
2. 对照代码解释 `middle`、`tail` 和 restored context。
3. 修改一个 Compact 阈值或 tail 数量，在学习分支观察测试变化。
4. 写出 Compact 前后 History 示例。

建议测试：

```bash
python -m pytest tests/test_context.py tests/test_compaction.py tests/test_work_state.py tests/test_resume.py -q
```

### 9.5 当日验收

- [ ] 能画出 Compact 完成后的 History 结构。
- [ ] 能解释摘要幻觉为什么仍是当前边界。
- [ ] 能说明 Transcript 为什么不被物理重写。

## 10. 第五天：Memory Extraction 与 Recall

### 10.1 目标

完整理解 Agent 的记忆机制，包括存储位置、四种 Auto Memory 类型、异步提取和相关性召回。

### 10.2 重点文件

- `src/xcode_cli/core/memory.py`
- `src/xcode_cli/core/memory_manifest.py`
- `src/xcode_cli/core/memory_recall.py`
- `src/xcode_cli/core/memory_extraction_policy.py`
- `src/xcode_cli/core/memory_extraction_runner.py`
- `src/xcode_cli/core/memory_extraction_subagent.py`
- `src/xcode_cli/core/memory_tools.py`

### 10.3 必须回答

- [ ] Project、User、Auto Memory 三个存储位置分别是什么？
- [ ] `user`、`feedback`、`project`、`reference` 四种语义类型分别存什么？
- [ ] 什么信息不应写入 Memory？
- [ ] 为什么 Extraction 使用 memory-only Subagent？
- [ ] single-flight 与 latest pending 解决什么问题？
- [ ] no-tool selector 如何从 Manifest 选择 Topic？
- [ ] 为什么 Selector 输入包含最近成功工具名？
- [ ] 为什么 Topic 正文不常驻 Base Prompt？
- [ ] 为什么 late Prefetch 必须丢弃？

### 10.4 动手练习

1. 手写四种类型各一个合法 Topic。
2. 手写一个缺 Evidence 和一个包含 Secret 的非法 Topic。
3. 构造 Manifest 和 Query，预测 Selector 应选择什么。
4. 阅读 invalid path、duplicate、overflow、late-result 测试。

建议测试：

```bash
python -m pytest tests/test_memory_manifest_v2.py tests/test_memory_recall_v2.py tests/test_agent_memory_recall_v2.py tests/test_memory_extraction_policy.py tests/test_memory_extraction_runner.py -q
```

### 10.5 当日验收

- [ ] 能用“存什么、怎么存、什么时候取”完整回答 Memory 问题。
- [ ] 能解释 Memory 与 Session、Context、RAG 的区别。
- [ ] 能指出 Recall 当前至少三个局限。

## 11. 第六天：Skills、Plan Mode 与 MCP

### 11.1 目标

理解扩展机制和规划机制的真实边界，避免把 Prompt 指令误认为执行层安全保证。

### 11.2 重点文件

- `src/xcode_cli/skills/loader.py`
- `src/xcode_cli/skills/catalog.py`
- `src/xcode_cli/skills/invocation.py`
- `src/xcode_cli/skills/prompt.py`
- `src/xcode_cli/core/tools/skill_tool.py`
- `src/xcode_cli/core/planning.py`
- `src/xcode_cli/core/sub_agent.py`
- `src/xcode_cli/mcp/config.py`
- `src/xcode_cli/mcp/connection.py`
- `src/xcode_cli/mcp/tools.py`
- `src/xcode_cli/mcp/trust.py`

### 11.3 必须回答

- [ ] Skill Loader、Catalog、Invocation Service 各负责什么？
- [ ] 用户 Slash Skill 与模型 SkillTool 有什么区别？
- [ ] barrier 和 blocked-tools 为什么同时存在？
- [ ] `allowed-tools` 为什么不是严格白名单？
- [ ] 当前 Plan Mode 已实现什么、缺少什么？
- [ ] Planning Skill 能替代什么，不能替代什么？
- [ ] 当前子 Agent 为什么不是并行多 Agent 系统？
- [ ] MCP stdio server 为什么需要 Trust Fingerprint？
- [ ] MCP 工具如何处理命名冲突、Schema 和输出上限？

### 11.4 动手练习

1. 创建一个最小 Skill，分别通过用户命令和模型工具路径调用。
2. 画出 Skill 双视图的落盘和 Resume 流程。
3. 检查 Plan Mode 下实际暴露的工具，解释 Prompt 约束缺口。
4. 用 `examples/fake_mcp_server.py` 理解 MCP 工具发现流程。

建议测试：

```bash
python -m pytest tests/test_skill_invocation_service.py tests/test_skill_prompt_command_flow.py tests/test_model_invocable_skill_flow.py tests/test_mcp_connection.py tests/test_mcp_tools.py tests/test_mcp_trust.py -q
```

### 11.5 当日验收

- [ ] 能准确说出“Skill 负责认知策略，Runtime 负责确定性约束”。
- [ ] 能指出文档中的 `enter_plan_mode` 与当前实现之间的差异。
- [ ] 能解释 MCP Trust Fingerprint 为什么只保存 env keys、不保存 values。

## 12. 第七天：独立改动与模拟面试

### 12.1 目标

用一次不依赖 AI 直接实现的 TDD 修改，证明自己已经能够维护核心 Runtime。

### 12.2 推荐任务

为主 Agent Tool Loop 增加可配置的最大工具轮次，并在超限时安全结束当前 Turn。

该任务需要先形成自己的设计结论：

- 配置字段叫什么，默认值是多少？
- 计数单位是 LLM Round、Tool Batch 还是单个 Tool Call？
- 达到上限前是否执行当前 Batch？
- 超限信息使用 Assistant、System 还是 Runtime Error？
- 是否写入 Transcript？
- 是否触发 After-turn Success Hook？
- 是否保留下一轮继续对话所需的上下文？
- External Turn 和 Subagent 是否复用相同限制？

### 12.3 TDD 步骤

1. 写出行为规格和非目标。
2. 找到最小修改范围。
3. 先写至少三个失败测试：
   - 正常轮次不受影响。
   - 达到上限后不再调用 LLM 或工具。
   - History 和 Transcript 不产生孤儿 Tool Message。
4. 运行测试，确认测试确实失败。
5. 编写最小实现。
6. 运行聚焦测试。
7. 运行全量测试。
8. 检查 Diff，并用自己的语言解释每一处改动。

注意：本计划只定义练习，不代表已经授权立即修改生产代码。实际执行时应在学习分支完成，并保留可审查 Diff。

### 12.4 模拟面试

完成改动后进行 30–45 分钟模拟面试，至少覆盖：

1. 两分钟项目介绍。
2. 一轮对话如何运行。
3. History 如何组装和清洗。
4. Session、Context、Memory 的区别。
5. Memory 的四种类型和 Recall。
6. Skill 双视图和 Resume。
7. 权限与用户拒绝语义。
8. Plan Mode 的真实边界。
9. 最大工具轮次改动的设计与测试。
10. AI 在项目中的参与方式。

### 12.5 当日验收

- [ ] 独立完成失败测试。
- [ ] 独立完成生产代码修改。
- [ ] 聚焦测试通过。
- [ ] 全量测试通过。
- [ ] 能解释为什么选择当前设计，而不是其他方案。
- [ ] 能说出实现仍存在哪些不足。

## 13. 可选延伸：亲手实现 Mini Agent

如果完成七天计划后仍对 Tool Loop 缺乏把握，再用 2–3 天从零实现一个 300–500 行 Mini Agent。

只实现：

```text
OpenAI-compatible 请求
read_file 和 grep 两个工具
Tool Registry
Tool Loop
Assistant/Tool 消息配对
JSONL Session
简单 allow/deny 权限
History Sanitizer
最大工具轮次
```

明确不实现：

```text
Rich UI
prompt_toolkit
MCP
Skills
QQchat
复杂 Memory
Context Compact
多 Agent
```

完成标准：

- [ ] 不复制 Xcode 生产代码。
- [ ] 能运行一个真实或 Fake LLM Tool Loop。
- [ ] 至少包含 10 个测试。
- [ ] 能从空白文件重新写出核心循环。
- [ ] 能对比 Mini Agent 与 Xcode Runtime 的差异。

## 14. 面试 Ownership 表述

推荐表述：

> 这个项目采用 Spec-driven、AI-assisted 开发。我负责产品目标、架构边界、规范文档、任务拆分、验收标准和 Review，AI 参与部分具体实现和测试生成。项目早期我的角色偏架构和项目负责人，之后我重点补齐了 Runtime、Tool Loop、Session、Memory 和权限路径的代码理解与调试能力，并亲自完成了核心路径的小型 TDD 改动。

当面试官问“你的核心贡献是什么”时：

> 我的核心贡献是定义系统应该具有什么行为和不变量，例如用户拒绝工具后的 Turn 语义、Session/Context/Memory 的边界、Memory 的写入与召回策略，以及 Compact 后的恢复要求。我不仅用文档描述这些契约，还通过聚焦测试、代码 Review 和真实终端验收确认实现符合契约。

这两段表述必须以真实完成本计划为前提，不应提前宣称尚未完成的独立实现或验证。

## 15. 模拟面试评分表

每项 0–2 分：0 表示不能回答，1 表示能讲概念但缺少代码证据，2 表示能结合代码、测试和边界完整回答。

| 项目 | 分数 |
|------|------|
| 项目定位与个人贡献 | /2 |
| User Turn 与 Tool Loop | /2 |
| Permission 与 Approval | /2 |
| History 与 Transcript | /2 |
| Session Resume | /2 |
| Context Compact | /2 |
| Memory Extraction/Recall | /2 |
| Skills 与 MCP | /2 |
| 当前不足与演进方案 | /2 |
| 独立编码与测试能力 | /2 |

总分判断：

```text
17–20：可以把项目作为主项目深入展开
13–16：可以写入简历，但需要控制追问深度
9–12：先继续补核心代码理解
0–8：暂时只作为架构/产品经历介绍
```

## 16. 每日复盘模板

```markdown
# Day N 复盘

## 今天理解的核心流程

## 我能脱稿回答的问题

## 今天亲手运行的测试

## 今天亲手修改的代码

## 一个关键不变量

## 一个失败分支

## 一个当前不足

## 仍然不懂的问题

## 明天开始前要复述的内容
```

## 17. 最终交付清单

- [ ] 六张核心数据流图。
- [ ] 六页模块学习卡。
- [ ] 一份真实测试基线记录。
- [ ] 一份最大 Tool Round 改动 Spec。
- [ ] 一组先失败后通过的回归测试。
- [ ] 一份可审查的代码 Diff。
- [ ] 一份模拟面试问题清单和评分。
- [ ] 一段真实准确的 AI-assisted Ownership 表述。
- [ ] 可选：一个独立实现的 Mini Agent。

完成这份计划的核心标准不是“阅读了多少代码”，而是：

> 面对新问题时，能够定位入口、追踪状态、写出失败测试、完成修改并用证据证明行为正确。
