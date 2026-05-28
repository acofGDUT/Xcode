# Claude Code 与 Xcode：工具调用轮次与子 Agent 差异分析

> 2026-05-27，基于 Claude Code 自述和 Xcode 当前实现。给后续架构 agent 做决策参考。

## 1. 工具调用轮次

### Claude Code

- **无硬性轮次上限**。一次 turn 可以做任意多轮工具调用，由 context budget 自然限制。
- **自动 compaction**：上下文接近预算时自动压缩早期轮次为累积摘要，腾出空间继续。
- **并行工具执行**：一条消息里可以同时发出多个独立的 tool call，运行时并行执行。
- **退出条件**：产出一条没有 tool_calls 的纯文本回复时结束 turn。

### Xcode

- **硬编码 10 轮上限**（`_run_llm_loop()` 的 `max_tool_rounds = 10`）。
- **自动 compaction**：`ContextManager.should_compress()` 在每轮开始前检查，超预算时 `ConversationCompactor.compact_history()` 压缩后继续。
- **串行工具执行**：同一批 tool_calls 是 `for tc in response.tool_calls` 逐个同步执行，不做并行。
- **退出条件**：模型返回空 tool_calls + 纯文本 / `KeyboardInterrupt` / 跑满 10 轮。
- **DEVNOTES #15 风险**：实际使用中可能因为多轮 tool_calls 停下，后续需排查 `_run_llm_loop()` 的状态推进。

### 差异对照

| | Claude Code | Xcode |
|---|---|---|
| 轮次上限 | 无（context 决定） | 硬编码 10 轮 |
| 并行工具 | 原生支持 | 串行 for 循环 |
| compaction | 自动 + 累积摘要 | 自动 + `/compact`，同一套逻辑 |
| 中断行为 | Ctrl+C 终止整个回复 | Ctrl+C 只中止当前操作，循环继续 |

### 后续建议

- 10 轮上限对大多数场景足够，但如果模型在复杂任务中反复搜索后停下，可以尝试提高到 15-20 轮。
- 并行工具执行的收益取决于使用场景；代码编辑/搜索类任务串行通常足够。
- 增加 fake LLM 多轮 tool call 测试（计划中）可优先做，锁定当前循环行为。

## 2. 子 Agent（Sub-Agent）

### Claude Code

**类型和工具集：**
- Explore — 只读搜索/读取（Glob, Grep, Read, WebFetch, WebSearch）。
- Plan — 只读 + TaskCreate 等规划工具，不写代码。
- general-purpose — 完整工具集，包括代码编辑。
- claude-code-guide — 只读 + WebFetch/WebSearch，回答 FAQ。

**隔离机制：**
- 支持 `isolation: "worktree"`，子 Agent 跑在临时 git worktree 里，文件操作不影响主工作区。
- 无隔离模式直接操作主工作区文件。
- worktree 无变更时自动清理；有变更时保留，返回分支名。

**上下文模型：**
- 子 Agent 拥有**独立的上下文窗口**，不消耗主对话 token 预算。
- 接收一段自包含的 prompt，返回**一个文本结果**（不是消息历史）。

**并行和后台：**
- 同一轮可派发多个子 Agent，并行执行。
- 支持 `run_in_background: true`，后台跑完后通知主对话。

**防递归：**
- 子 Agent 不能派发子 Agent，系统层面禁止。

### Xcode

**类型和工具集：**
- EXPLORE / PLAN — 只注册 `read_file`、`grep`、`glob` 三个只读工具。
- GENERAL — 注册所有工具，但排除 `dispatch_agent` 本身。

**隔离机制：**
- 无隔离。子 Agent 和主 Agent 共享同一个项目目录，文件操作直接作用。

**上下文模型：**
- 子 Agent 有自己独立的 LLM 循环（最多 15 轮），不占用主对话 history。
- 接收 prompt → 跑循环 → 返回结果字符串。与 Claude Code 一致。

**并行：**
- `SubAgentExecutor` 设计支持 `ThreadPoolExecutor`，但 `dispatch_agent` 工具本身是同步阻塞调用。
- 并行依赖模型在同一次 tool_calls 里发出多个 `dispatch_agent`。

**防递归：**
- `dispatch_agent` 不注册进子 Agent 工具白名单。和 Claude Code 原则相同，实现方式不同（白名单 vs 系统限制）。

### 差异对照

| | Claude Code | Xcode |
|---|---|---|
| 隔离级别 | 可选 worktree 隔离 | 无隔离 |
| 上下文 | 独立窗口，不影响主对话 | 独立循环，不影响主 history |
| 并行 | 原生并行 + 后台模式 | ThreadPoolExecutor，同步阻塞 |
| 工具集 | 按类型完整分配 | 白名单过滤 |
| 递归 | 禁止 | 禁止（白名单排除） |
| 审批 | 子 Agent 内部无审批 | 子 Agent 内部无审批 |
| 子 Agent 数量 | 按需，多种专用类型 | 3 种（EXPLORE/PLAN/GENERAL） |

### 后续建议

- worktree 隔离是 Claude Code 子 Agent 最安全的特性。如果 Xcode 后续支持子 Agent 编辑代码，隔离会是优先要补齐的能力。
- 目前探索类子 Agent 最常见的使用场景不需要编辑权限，白名单策略已够用。
- 后台模式（`run_in_background`）对于长时间搜索任务有体验价值，但需要异步通知机制，当前 Xcode 的同步架构暂不适合。

## 3. 流式输出与渲染策略

### Claude Code

- **默认流式**：普通文本逐 token 流式输出。
- **结构化内容缓冲**：遇到代码块、表格、标题等 Markdown 结构时，前端会缓冲到完整结构后再渲染，避免格式错乱。
- **工具调用不流式**：tool_use block 必须 JSON 完整后才能执行，前端等完整结构再展示。
- **不回收前缀**：已流式打印的文本不会被"收回"，最终渲染时可能出现轻微重复。

### Xcode（v0 实现）

**渲染模式配置：** `response_render_mode` 支持两种模式：

| 模式 | 行为 |
|------|------|
| `buffer_then_render` | 完全不流式，收完后 Rich render 一次 |
| `streaming_plus_final_render` | 智能流式 + 结构化检测 |

**智能流式机制（`StreamingTurnRenderer`）：**

```
token 到达
  ↓
加入 content_buffer（总是）
  ↓
检查累积文本是否需要 Rich render
  ↓
┌─ 不需要 → 直接流式打印 token
└─ 需要 → 停止流式，标记 _streaming_stopped_for_final_render
           ↓
           finish() 时调用 render_markdown(完整文本) 一次
```

**结构化内容检测启发式：**

```python
def _needs_rich_render(text: str) -> bool:
    return "```" in text or "\n|" in text or "\n#" in text or text.startswith("#")
```

- 代码块：检测到 ` ``` `
- 表格：检测到 `\n|`
- 标题：检测到 `\n#` 或文本以 `#` 开头

**效果：**
- 普通文本：逐 token 流式打印，finish() 不再重复渲染
- 包含代码块/表格/标题：前几个 token 可能已流式打印，检测到结构化内容后停止，finish() 完整 Rich render 一次

**已知限制：**
- 不回收已打印的前缀——如果前 20 个 token 是普通文本已经打印，后面检测到代码块，前 20 个 token 保留，最终只渲染完整版本（轻微重复，但比"整段 raw + 整段 Rich"好）

### 差异对照

| | Claude Code | Xcode |
|---|---|---|
| 流式默认 | 是 | 可配置（默认 streaming_plus_final_render） |
| 结构化检测 | 前端自动处理 | 启发式检测（```、\|、#） |
| 工具调用 | 不流式，等完整 JSON | 不流式，等完整 JSON |
| 前缀回收 | 不回收 | 不回收（第一版） |
| buffer_then_render | 无 | 有，完全不流式 |

### 后续建议

- 前缀回收是优化项，当前第一版不做，因为实现复杂且收益有限。
- 结构化检测启发式可能漏判（如嵌套列表、引用块），后续可根据实际使用补充规则。
- `buffer_then_render` 模式适合网络慢或 token 生成慢的场景，避免"打一半卡住"的体验。
