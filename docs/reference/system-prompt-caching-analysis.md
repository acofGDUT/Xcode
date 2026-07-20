# Xcode Message 组装顺序与 Prompt Cache 优化分析

> 状态：当前实现分析已完成；本文提出的缓存优化尚未实施。
> 日期：2026-07-19
> 范围：本地 REPL 主对话、relevant memory selector、memory extraction subagent、tool loop、compact 与 resume。QQchat 和普通 sub-agent 作为独立请求族，仅说明边界。

## 1. 结论摘要

当前 Xcode 的普通对话历史采用追加式组装。在 system prompt 不变、工具 schema 不变且没有 compact 的情况下，后一轮请求天然以前一轮请求为前缀，整体上有利于服务端 prompt cache。

当前最主要的结构性问题不是“每轮重新执行 `build_system_prompt()`”，而是动态内容在 prompt 中的位置：

- `MEMORY.md`、Project `XCODE.md` 和 User `XCODE.md` 位于 skills 与全部对话历史之前。
- 后台 memory extraction 一旦更新 `MEMORY.md`，system prompt 会在中部发生分叉，后面的 skills 和整段历史都无法继续沿用旧前缀缓存。
- relevant memory selector 把每轮变化的 Query 放在 manifest 前面；当 selector 请求将来达到缓存门槛时，这种顺序会阻断 manifest 复用。
- memory extraction subagent 复用完整主 prompt、携带动态 `MEMORY.md`，并在最近历史之后重复附加当前 user/assistant，既扩大输入又使 extraction 自己的跨轮前缀不稳定。
- 模型成功调用 `skill` 后，下一次 tool loop 会从工具 schema 中移除 `skill`，使工具集合发生变化。
- 工具 schema 依赖注册顺序，没有显式按工具名排序；MCP reconnect/refresh 后可能出现相同工具集合、不同序列化顺序的情况。

收益最高的方向是：为本地 REPL 建立稳定的 system prefix，不再把完整 `MEMORY.md` 常驻注入其中；依靠 recall v2 在当前 user message 后注入本轮选中的 topic。其次是让 selector 采用 manifest-first/query-last，并使 manifest 与工具 schema 的顺序确定化。

## 2. 两类“缓存”必须区分

本文讨论的核心是模型服务端 prompt cache，而不是 Python 进程内字符串缓存。

### 2.1 本地 system prompt 字符串缓存

把 `build_system_prompt()` 的结果保存在 `AgentRuntime` 中，可以减少少量文件读取、字符串拼接和对象分配。但当前 `build_system_prompt()` 只读取：

- Project `XCODE.md`；
- User `~/.xcode/XCODE.md`；
- Auto Memory Index `MEMORY.md`；
- 已在 runtime 启动时加载并格式化的 skill listing。

它不会在每轮构建 system prompt 时读取所有 topic 正文，也不会重新加载所有 skill 文件。因此，本地字符串缓存只属于低风险的 CPU/I/O 优化，通常不是端到端延迟的主要来源。

### 2.2 模型服务端 prompt cache

服务端缓存依赖请求前缀精确一致。静态内容应位于前面，动态内容应尽量靠后；messages、图片和工具定义的差异都可能影响缓存命中。

对于 OpenAI，官方文档当前说明：缓存只对精确前缀匹配生效，messages、图片和 tools 都需要保持一致；自动缓存要求 prompt 至少达到 1024 tokens，并通过 `cached_tokens`、新模型的 `cache_write_tokens` 等字段报告实际使用量。GPT-5.6 及后续模型还支持 `prompt_cache_key` 和显式 cache breakpoint；这些模型的 cache write 会单独计量和计费：

- <https://developers.openai.com/api/docs/guides/prompt-caching>

Xcode 当前配置允许使用任意 OpenAI-compatible `base_url`。非 OpenAI 服务商的缓存门槛、缓存键、保留时间、计费和 usage 字段可能不同，不能把 OpenAI 专用参数无条件发送给所有 provider。

## 3. 本地 REPL 的完整组装链路

普通 user turn 从 `src/xcode_cli/core/agent.py::_run_user_turn()` 开始，当前执行顺序如下：

```text
用户输入
  |
  |-- 1. coerce_user_turn_input()
  |-- 2. 清空当前 turn 的 blocked tools / memory-write 状态
  |-- 3. 异步启动 relevant-memory prefetch
  |-- 4. transcript 写入用户可见内容
  |-- 5. _history 追加 user 的 model_content
  |-- 6. 构建本轮 system prompt
  |-- 7. 进入 _run_llm_loop_result()
          |
          |-- 7.1 达到阈值时先自动 compact
          |-- 7.2 处理 MCP refresh safe point
          |-- 7.3 recall 已完成时，把相关记忆追加到 history 尾部
          |-- 7.4 构建当前可见工具 schema
          |-- 7.5 调用 LLMClient.complete()
          |-- 7.6 有 tool_calls 时追加 assistant/tool 配对并继续循环
          `-- 7.7 无 tool_calls 时返回 final text
  |
  `-- 8. _history 追加最终 assistant message
```

关键代码位置：

- `src/xcode_cli/core/agent.py::_run_user_turn()`
- `src/xcode_cli/core/agent.py::_run_llm_loop_result()`
- `src/xcode_cli/core/llm.py::LLMClient.complete()`

## 4. 最终 Chat Completions 请求形状

`LLMClient.complete()` 当前构造的主要字段为：

```python
request_kwargs = {
    "model": model,
    "messages": [
        {"role": "system", "content": system_prompt},
        *sanitize_model_messages(history),
    ],
    "temperature": 0.2,
    "stream": True,
}

if tool_schemas:
    request_kwargs["tools"] = tool_schemas
    request_kwargs["tool_choice"] = "auto"
```

`sanitize_model_messages()` 保持正常消息顺序，只清理 malformed tool-call pairs 和 orphan tool messages。因此正常情况下，请求中的 history 是单调追加的。

第一轮无工具调用时，请求大致为：

```text
system: 完整 system prompt
user: 当前用户输入
system: 本轮 relevant-memory reminder（仅当 prefetch 已及时完成）
```

后续轮次为：

```text
system: 完整 system prompt
user: 历史输入 1
assistant: 历史回答 1
...
user: 当前用户输入
system: 本轮 relevant-memory reminder（可能存在）
```

因为新消息追加在末尾，只要 system prompt 和工具 schema 不变，第 N+1 轮能够复用第 N 轮的大部分输入前缀。

## 5. system prompt 内部顺序

`src/xcode_cli/core/prompting.py::build_system_prompt()` 当前依次拼接：

```text
1. BASE_SYSTEM_PROMPT
2. Working directory
3. Resolved memory paths
4. Project XCODE.md
5. User ~/.xcode/XCODE.md
6. Auto Memory Index（MEMORY.md）
7. Available Skills listing 与 skill usage rules
```

在 2026-07-18 的当前工作区中，用 Xcode 自己的 `ContextManager.estimate_tokens()` 测得：

| 位置 | 累计估算 tokens | 稳定性 |
|---|---:|---|
| `BASE_SYSTEM_PROMPT` 结束 | 约 2274 | 代码版本不变时稳定 |
| Working directory / resolved paths 结束 | 约 2384 | 同一项目内稳定 |
| Project `XCODE.md` 结束 | 约 2569 | 文件修改时变化 |
| User `XCODE.md` 结束 | 约 2634 | 文件修改时变化 |
| Auto Memory Index 结束 | 约 2765 | auto extraction 可能更新 |
| Skills section 结束 | 完整约 3934 | skills 集合不变时稳定 |

补充数据：

- 完整 system prompt：约 15113 字符、3934 tokens；
- 固定 `BASE_SYSTEM_PROMPT`：约 8956 字符、2274 tokens；
- 当前 `MEMORY.md`：432 字符，全部处于 1200 字符注入上限内；
- 当前 model-invocable skills：7 个；skill listing 本体约 4025 字符、1060 tokens；
- 连续构建两次 system prompt，内容和哈希完全一致。

这些数字是项目内估算器结果，不等同于具体 provider tokenizer 的精确账单，但足以判断各段的相对位置与失效范围。

## 6. Memory 的两条注入路径

### 6.1 常驻 Auto Memory Index

`MemoryManager.get_context_for_prompt()` 在 `auto_memory=true` 时读取 `MEMORY.md`，最多截取 1200 字符，并作为以下内容加入基础 system prompt：

```text
## Auto Memory Index
<MEMORY.md 内容>

(Use read_file on individual memory files for full details.)
```

这里只注入索引，不会把所有 topic 正文常驻塞入 system prompt。

### 6.2 本轮 relevant memory reminder

`MemoryRecallService` 扫描 topic frontmatter，选择最多 5 个相关文件，每个文件最多读取 4096 bytes 或 200 行。选择结果被渲染为 `<system-reminder>`，由 `_maybe_inject_relevant_memories()` 追加到 history 尾部。

这个位置对缓存较友好：动态正文出现在当前 user message 后，不会破坏 system prompt 和此前历史的公共前缀。

如果 prefetch 在首次 LLM 调用前没有完成：

- 首次模型响应无 tool call：该 recall 被标记为 `late`，不会污染后续无关 turn；
- 首次模型响应有 tool call：下一次 tool loop safe point 可以在新增 tool messages 后消费该 recall。

## 7. 当前实现中有利于缓存的部分

### 7.1 普通历史单调追加

user、assistant、assistant tool_calls 和 tool results 都按协议顺序追加。只要前面的 system prompt 与工具 schema 不变，后一轮天然继承前一轮前缀。

### 7.2 relevant memory 正文位于尾部

召回正文不会插入 system prompt 中部，也不会回写到较早历史位置。

### 7.3 skill listing 已稳定排序

`SkillCatalog` 和 `SkillListingFormatter` 都按 skill name 排序。同一 runtime 中，只要没有 reload 或 skill 文件变化，listing 输出稳定。

### 7.4 prompt 重建本身是确定性的

当前工作区连续两次构建结果一致。只要输入文件与配置未变化，重新执行拼接不会降低服务端命中率。

### 7.5 recall、main 与 extraction 不会因调用顺序互相覆盖缓存

一个满足条件的普通 turn 可能依次或并发产生三个模型请求族：

```text
relevant memory selector
main agent
memory extraction subagent
```

三者当前共用同一个 `LLMClient`，因而通常使用同一套 model、API key 和 `base_url`。但服务端 prompt cache 不是“每个 API key 只有一个槽位”；recall 或 extraction 插在两次 main 请求之间，本身不会自动覆盖第一轮 main 的缓存。只要第二轮 main 仍与第一轮 main 具有相同的精确前缀，它仍可能命中原有缓存。

真正会让第二轮 main 前缀分叉的是请求内容变化，例如：

- extraction 更新了主 prompt 中常驻的 `MEMORY.md`；
- model、system prompt 或 tools schema 改变；
- compact 重写 history；
- provider 缓存过期、路由未命中或根本不支持相同缓存契约。

不过，如果 provider 控制台把 main、selector、extraction 和 compact 汇总统计，不同请求族会稀释整体命中率。特别是当前 selector 请求较短，而 extraction 的 prompt 形状与 main 不同，所以“聚合命中率低”不等价于“main 的连续轮次没有复用”。这也是必须按 `call_kind` 分开采集 usage 的原因。

## 8. 当前主要缓存失效点

### 8.1 `MEMORY.md` 位于 skills 和历史之前

这是当前最重要的问题。

当后台 memory extraction 更新 `MEMORY.md` 时，下一轮 system prompt 会在约 2634 tokens 后发生分叉。旧缓存即使还能覆盖前约 2.6k tokens，也无法继续覆盖：

```text
新的 Auto Memory Index 后半段
Available Skills
全部历史 user / assistant / tool messages
当前 user message
```

因此损失的不只是几行记忆，而是后面可能已经很长的对话历史。如果 auto extraction 频繁更新索引，缓存收益会显著下降。

### 8.2 Project/User XCODE.md 位于 skills 前

这两个文件变化频率较低，影响小于 `MEMORY.md`。但一旦修改，后面的 skills 和整段历史同样不能继续沿用旧前缀。

### 8.3 selector 把 Query 放在 manifest 前

当前 selector user message 为：

```text
Query: <当前问题>

Available memories:
<完整 manifest>

Recently successful tools:
<动态工具名>
```

当前工作区只有 3 个有效 topic，实测 selector system prompt 约 235 tokens，user message 约 178 tokens，总计约 413 tokens。按照 OpenAI 的 1024-token 门槛，它目前不会产生 prompt cache 命中。

当 topic 数量增长、请求超过门槛后，Query 仍然位于最前；不同 query 的 selector user content 只共享 `Query: ` 这 7 个字符，后面的稳定 manifest 无法被复用。

### 8.4 manifest 按 `mtime` 倒序

`MemoryManifestScanner.scan()` 目前按 `mtime_ms` 倒序排列候选。编辑一个 topic 会同时改变它的 mtime 和位置，可能使大量后续条目整体位移，扩大精确前缀失效范围。

### 8.5 skill 成功后工具 schema 改变

模型成功调用 `skill` 后，`SkillTool` 返回 `blocked_tools=["skill"]`。`AgentRuntime` 随后从下一次 LLM 请求的 tool schema 中移除 `skill`。

虽然 messages 只是追加了 skill tool result，但工具列表发生变化。对于把 tools 纳入缓存匹配的 provider，这会削弱同一 tool loop 内第二次请求的缓存命中。该场景通常还会加载较长的 skill 正文，因此值得优化。

### 8.6 tool schema 缺少显式确定性排序

`ToolRegistry.get_openai_schemas()` 当前遍历字典插入顺序。内置工具在同一 runtime 中通常稳定，但 MCP server 返回顺序、reconnect 或 refresh 可能使相同工具集合得到不同排列。

### 8.7 compact 重写历史

当 history token 估算达到 context window 的 80% 时，自动 compact 将历史替换为：

```text
Compact boundary
Conversation summary checkpoint
Compact restored context（存在时）
pair-safe protected tail（通常最近约 8 条）
```

compact 后，旧历史前缀无法继续复用，只能继续复用稳定的 system prompt。这是摘要替换历史的固有代价。当前 80% 阈值已经避免过于频繁地 compact，不建议仅为缓存而盲目推迟压缩。

### 8.8 plan mode 是另一类 system prefix

进入 plan mode 后，system prompt 改为 `PlanMode.get_system_prompt()` 加 skill listing，不再使用普通模式的完整 `build_system_prompt()`。普通模式与 plan mode 应视为两个独立缓存族；模式切换时出现一次缓存失效是预期行为。

### 8.9 resume 只能稳定复用 system prompt

`/resume` 会恢复 checkpoint boundary、summary 和 post-checkpoint tail。恢复后的历史与原请求前缀通常不同，因此跨 resume 最可靠的复用部分仍是稳定 system prompt。

### 8.10 memory extraction 请求过重且存在当前 turn 重复

`MemoryExtractionSubagent.run()` 当前执行：

```text
system:
  build_system_prompt(ConfigStore().load(), event.cwd)

messages:
  event.recent_history[-12:]
  extraction 控制消息
    Existing memory manifest
    Current user turn
    Assistant reply

tools:
  memory-scoped read/write/edit/glob schema
```

这里有两个独立问题：

1. extraction 复用了面向主 Agent 的完整基础 prompt，其中包含大量与记忆提取无关的通用规则和动态 `MEMORY.md`。上一次 extraction 如果更新了索引，下一次 extraction 的 system prefix 也会发生变化。
2. `recent_history[-12:]` 已经包含刚结束的当前 user/assistant，而 extraction 控制消息又附加 `Current user turn` 和 `Assistant reply`，造成同一内容重复输入。

同一次 extraction 内最多 5 轮 tool loop 使用的是运行开始时构建的一份 system prompt，随后只追加 assistant/tool messages，因此单次 extraction 内部仍然具有追加式前缀。问题主要发生在不同用户 turn 之间，以及无谓的输入 token 消耗。

## 9. 优化方案

### 9.1 推荐方案：为本地 REPL 移除常驻 Auto Memory Index

本地 REPL 已有 recall v2。selector 直接扫描 topic frontmatter，不依赖主模型常驻看到完整 `MEMORY.md`。因此本地主对话可以采用：

```text
固定 system prefix
  BASE_SYSTEM_PROMPT
  Available Skills
  固定路径与记忆使用规则

历史消息
当前 user message
本轮选中的 relevant memory reminder
```

`MEMORY.md` 继续作为 memory 管理索引存在，但不再常驻本地 REPL 主模型的基础 system prompt。

不能直接对所有入口全局删除：

- QQchat/external turn 当前没有本地 REPL 的 relevant-memory prefetch；
- memory extraction subagent 使用 `build_system_prompt()` 构建写入提示词；
- 未来其他 headless 入口可能有不同的记忆边界。

建议把 prompt 构建拆成显式 profile：

| Profile | Auto Memory Index | Relevant recall | 说明 |
|---|---|---|---|
| `local_repl` | 不常驻 | 启用 | 推荐目标结构 |
| `external` | 暂时保留 | 当前未启用 | 等外部入口有独立 recall 后再调整 |
| `memory_writer` | 按写入需要决定 | 不适用 | 使用专用 memory writer prompt |
| `sub_agent` | 按 agent 类型决定 | 独立状态 | 不与本地 REPL 共享 recall state |

该方案的核心收益是：即使后台 extraction 更新 `MEMORY.md`，主请求仍可复用固定 system prompt 与此前完整历史。会话越长，收益越大。

### 9.2 过渡方案：把 skills 移到文件记忆之前

如果暂时不改变 memory 注入语义，可先调整为：

```text
BASE_SYSTEM_PROMPT
Available Skills
Working directory / resolved paths
Project XCODE.md
User XCODE.md
Auto Memory Index
```

这样记忆变化时，至少可以继续复用约 1000 多 tokens 的 skill listing 与规则。但动态记忆仍位于全部 history 之前，所以它不能保护长对话历史，只适合作为过渡方案。

### 9.3 selector 改为 manifest-first/query-last

建议改为：

```text
Available memories:
<按 filename 稳定排序的 manifest>

Recently successful tools:
<动态工具名>

Query: <当前问题>
```

具体要求：

- manifest 使用 filename 稳定排序，不按 mtime 重排；
- mtime 可以保留为字段，但不负责列表顺序；
- Query 永远放在最后；
- recent successful tools 属于动态内容，放在 manifest 之后；
- selector cache key 与主对话使用不同请求族。

当前 3 个 topic 的 selector 请求不足 OpenAI 缓存门槛，短期收益主要是为记忆规模增长做准备。其他 provider 可能具有不同门槛。

### 9.4 工具 schema 确定化

建议：

- `ToolRegistry.get_openai_schemas()` 按 tool name 排序；
- schema 中需要参与序列化的 properties 采用稳定顺序；
- 为最终 tool schema 计算 fingerprint；
- MCP refresh 后只有实际 schema fingerprint 变化才建立新缓存族；
- local、external、sub-agent 按可见工具范围使用不同 toolset fingerprint。

### 9.5 skill 工具保持 schema 稳定

不要在一次成功调用后从下一轮 schema 中移除 `skill`。可以改为执行层维护“当前 turn 已加载 skill”的 barrier：

- schema 始终保持不变；
- 重复调用时返回受控结果；
- 已加载 skill 的 tool result 中保留 `<xcode_loaded_skill>` marker；
- system rule 继续要求看到 marker 后不要重复调用。

该设计需要回归验证模型不会陷入重复 skill 调用循环，不能只为了缓存删掉现有 barrier。

### 9.6 为 memory extraction 建立专用短 prompt

memory extraction 不应继续调用通用 `build_system_prompt()`。建议建立明确的 `memory_writer` prompt profile，仅包含：

```text
固定部分：
  extraction 角色与 durable memory 判断规则
  v2 topic 格式和索引更新契约
  memory-scoped 工具边界
  topic 数量上限与禁止调查项目的约束

动态部分：
  按 filename 稳定排序的 manifest
  最近历史
  当前 turn（只保留一份）
```

具体要求：

- 不常驻注入 `MEMORY.md`；manifest 已经承担候选索引职责；
- 不包含主 Agent 的 Skills listing、项目操作说明和无关工具规则；
- 在“最近历史已经包含当前 turn”和“单独传当前 turn”之间二选一，不能重复；
- extraction 自己使用独立的 prompt family/cache key；
- 单次 extraction tool loop 的 tools schema 保持稳定。

这项改动首先是输入成本和边界清晰度优化，同时也能使不同 turn 的 extraction 共享更长、更稳定的 system prefix。它不会直接提高 main 请求的缓存命中，但能避免 extraction 请求拉低整体成本指标。

### 9.7 增加真实缓存观测

当前 `LLMResponse` 没有 usage 字段，`/context` 只显示本地估算 token，无法回答真实命中率。

建议按 provider 能力读取：

```text
prompt_tokens
cached_tokens
cache_write_tokens
completion_tokens
```

并在 `/context` 或独立诊断入口展示：

```text
最近一次请求缓存命中率
当前 session 累计 cached tokens
当前 session 累计 cache writes
main / selector / compact / sub-agent 分请求族统计
```

基础计算：

```text
cache_hit_ratio = cached_tokens / prompt_tokens
```

但需要同时观察 cache write 成本，不能只追求命中率数字。

### 9.8 provider-aware cache policy

建议新增明确的缓存能力配置，而不是根据 `base_url` 猜测：

```text
prompt_cache.mode = auto | off | openai
prompt_cache.metrics = true | false
prompt_cache.key_strategy = project
```

确认 provider 支持后，可为 OpenAI 请求使用稳定的 prompt cache key，例如：

```text
xcode:local:<project-key>:<prompt-version>:<toolset-hash>
```

key 不应包含：

- session ID；
- 当前 query；
- 当前时间；
- `MEMORY.md` 完整内容哈希；
- 每轮都会变化的计数器。

否则请求会被分散到过多缓存族。缓存键也不能替代精确前缀匹配；它主要用于把共享长前缀的请求稳定路由到同一缓存族。

对于 OpenAI GPT-5.6 及后续支持显式 cache breakpoint 的模型，可以把 system message 改为结构化 content blocks，并在稳定 system block 后设置 breakpoint。当前 `LLMClient.complete()` 只发送纯字符串 system content，因此尚不能表达这个边界。

显式模式还需要同时发送 `prompt_cache_options`，并遵循 provider 当前支持的 TTL。该能力必须通过 provider/model capability gate；旧模型或兼容服务商可能拒绝 `prompt_cache_key`、`prompt_cache_options`、`prompt_cache_breakpoint` 或 streaming usage 相关未知字段。

### 9.9 本地 system prompt 对象缓存

在服务端缓存结构优化之后，可以再增加进程内缓存：

```python
self._cached_system_prompt: str | None
self._prompt_version: PromptVersion
```

失效来源应由内容版本驱动，而不是把 `/compact`、`/resume` 一律视为 system prompt 变化：

| 事件 | 是否需要重建普通 system prompt |
|---|---|
| 普通 user turn | 否 |
| assistant/tool result 追加 | 否 |
| `/compact` | 通常否；变化的是 history |
| `/resume` | system 输入源未变时否；变化的是 history |
| Project/User XCODE.md 变化 | 是 |
| prompt profile 变化 | 是 |
| skills reload | 是 |
| model/context budget 导致 skill listing 预算变化 | 是 |
| working directory/project root 变化 | 是 |
| provider capability/prompt version 变化 | 是 |

如果本地 REPL 已移除常驻 `MEMORY.md`，auto memory topic/index 更新不应再使主 system prompt 失效。

## 10. 建议实施批次

### Batch 1：缓存观测基线

风险层级：P0，涉及 context/cost 可观测性和 provider usage 契约。

目标：

- 扩展 `LLMResponse` usage；
- streaming 模式安全读取最终 usage；
- provider 不返回 usage 时 fail closed，不影响主循环；
- `/context` 显示真实 cache read/write 指标；
- main、selector、extraction、compact、普通 sub-agent 分开统计。

验收重点：

- 没有 usage 的 OpenAI-compatible provider 不崩溃；
- `cached_tokens=0` 与字段缺失明确区分；
- usage 解析异常全部捕获；
- 不记录 API key、Authorization header 或敏感 prompt 正文。

### Batch 2：主请求与 memory writer 稳定前缀

风险层级：P0，涉及 system prompt、memory recall 和 external scope。

目标：

- 引入 prompt profile；
- local REPL 不再常驻注入 Auto Memory Index；
- relevant recall 行为保持不变；
- extraction 使用专用短 prompt，不再复用完整主 prompt；
- extraction 不再重复输入当前 user/assistant；
- external/QQchat 行为不回归；
- skills 与固定规则进入稳定 prefix。

验收重点：

- 修改 `MEMORY.md` 前后，local REPL stable system prefix 完全一致；
- 本轮相关 topic 仍能在安全点注入；
- late prefetch 不污染后续 turn；
- `/memory auto off` 仍关闭 selector 和自动写入；
- extraction system prompt 不包含动态 `MEMORY.md`、Skills listing 或无关主 Agent 规则；
- extraction 输入中的当前 user/assistant 各只出现一次；
- extraction 的 topic/index 写入和最多 5 轮 tool loop 契约保持不变；
- QQchat/external 不意外读取或共享本地 recall state。

### Batch 3：selector 与工具 schema 稳定化

风险层级：P1；skill barrier 涉及 tool loop，应按 P0 风险重点回归。

目标：

- selector manifest-first/query-last；
- manifest filename 稳定排序；
- tool schema 稳定排序与 fingerprint；
- skill 调用后保持 schema 不变，同时阻止重复调用循环；
- MCP schema 只有实际变化时才切换缓存族。

验收重点：

- 不同 query 共享完整 manifest 前缀；
- 只修改一个 topic 时不会引起全表重排；
- 相同工具集合跨两次注册得到完全一致 schema JSON；
- skill 成功调用后的下一次 LLM 请求仍暴露相同 schema；
- skill 不会在同一 turn 被无限重复调用；
- MCP refresh、disable、invalid schema 和 name conflict 的既有安全边界不变。

### Batch 4：provider cache controls

风险层级：P1，必须兼容非 OpenAI provider。

目标：

- capability-gated `prompt_cache_key`；
- capability-gated retention/breakpoint；
- stable prompt family 与 toolset fingerprint；
- 配置和 `/env` 可观测性。

验收重点：

- 未声明能力的 provider 不收到未知参数；
- provider 返回 400 时给出明确、可恢复错误；
- cache key 不含用户 query、session ID 或 secret；
- 切换 model/provider/tool scope 后使用新的缓存族。

## 11. 测试建议

优先测试用户可见行为和跨模块契约，不测试 Python 字符串对象是否为同一引用。

建议增加：

- system prompt section 顺序测试；
- local/external/memory-writer profile 测试；
- 修改 `MEMORY.md` 后 local stable prefix 不变测试；
- 修改 `MEMORY.md` 后 extraction stable system prefix 不变测试；
- extraction 当前 user/assistant 不重复测试；
- Project/User XCODE.md 更新的明确失效测试；
- selector Query 位于 manifest 后的行为测试；
- manifest 稳定排序测试；
- tool schema 确定性序列化测试；
- skill tool loop schema 稳定与重复调用保护测试；
- usage 字段存在、为零、缺失、格式异常测试；
- compact/resume 后 system prefix 不发生无关变化测试；
- OpenAI 专用参数不泄漏给普通 compatible provider 测试。

缓存效果不能只靠单元测试声称完成。最终还应使用真实 provider 连续执行多轮固定前缀请求，记录：

```text
prompt_tokens
cached_tokens
cache_write_tokens
首 token 延迟
总响应延迟
```

至少比较：

1. 普通连续对话；
2. 两次 main 请求之间插入 recall/extraction，但所有 main 输入源不变；
3. 后台更新 `MEMORY.md` 后的下一轮；
4. extraction 专用 prompt 改造前后；
5. relevant memory 命中与未命中；
6. skill tool call 前后；
7. MCP schema 不变的 refresh 前后；
8. compact 前后；
9. resume 后首轮。

## 12. 推荐决策

推荐按以下顺序推进：

1. 先接入真实 `cached_tokens` / `cache_write_tokens`，建立可验证基线；
2. 为本地 REPL 移除常驻 Auto Memory Index，保留 recall v2 的尾部注入；
3. 为 memory extraction 建立专用短 prompt，并消除当前 turn 重复；
4. 将 selector 改为 manifest-first/query-last，并稳定 manifest 顺序；
5. 稳定 tool schema，重新设计 skill barrier；
6. 最后按 provider capability 接入 cache key 和 breakpoint；
7. 在服务端缓存收益明确后，再决定是否需要本地 system prompt 对象缓存。

其中第 2 项预期收益最大。当前实现只要 `MEMORY.md` 不变化，增长中的对话历史本来就具有良好的公共前缀；真正需要解决的是动态长期记忆位于 system prompt 中部，导致一次索引更新连带破坏后续 skills 和完整历史缓存。
