# Manual Compact Semantics Relaxation Design

> 状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工验收未执行/未记录。
> 日期：2026-06-15

## 背景

当前 compact v3 已经解决坏摘要、工具消息配对、现场恢复和 checkpoint 链路问题，但手动 `/compact` 的可用性曾经过于保守。用户明确触发 `/compact` 时，仍可能反复看到 `Nothing to compact.`，即使会话里确实有消息。

历史上触发该现象的主要路径有四类：

- `/compact` handler 在 `_history` 少于 4 条时提前返回 `Nothing to compact.`。
- `ContextManager.compress()` 在消息数 `<= 20` 时直接返回空 checkpoint。
- 压缩时先保留 pair-safe protected tail，若剩余 `middle` 为空，也直接返回空 checkpoint。
- 摘要质量门会拒绝低于动态最小长度的摘要；当前分档为 80 / 300 / 600 / 1000 字符。被拒绝后，上层同样只显示 `Nothing to compact.`。

这导致 `Nothing to compact.` 实际混合了几种完全不同的状态：真的没有消息、消息太少被硬门槛挡住、没有可摘要中间段、摘要太短、摘要疑似协议泄漏或摘要请求失败。对用户来说，这不像“没东西可压”，更像“我要求压缩但系统不听”。

## 目标

- 区分自动压缩和手动压缩的语义。
- 自动压缩继续主要由 token 阈值触发，避免频繁无意义压缩。
- 手动 `/compact` 只要当前 `_history` 非空，就应尝试生成 checkpoint。
- 去掉 `message > 20` 的压缩硬门槛。
- 去掉摘要最小长度质量门，包括固定 80 字符和动态 80 / 300 / 600 / 1000 字符分档。
- 摘要质量门只拒绝空摘要和摘要接口错误。
- `Nothing to compact.` 只用于真正没有可压缩输入的情况。
- 压缩失败时必须保留原 `_history` 和 transcript，不写半成品 checkpoint。

## 非目标

- 不改变 `xcode.v3` checkpoint schema 的核心字段含义。
- 不移除 pair-safe protected tail。
- 不移除 restored context、secret redaction、tool result micro-compact 和 message history 清洗。
- 不改变 `/resume` 对旧 `xcode.v1/v2/v3` checkpoint 的兼容策略。
- 不引入新的后台索引、向量库、异步框架或外部依赖。

## 当前约束

- `AgentRuntime._run_llm_loop()` 当前在每次请求模型前调用 `context.should_compress(history)`，该方法只看 token 估算是否达到 `max_tokens * 0.8`。
- `/compact` 当前走 `_handle_compact_command()`，再进入 `ConversationCompactor.compact_history()` 和 `ContextManager.compress()`。
- `ConversationCompactor.write_checkpoint()` 负责写入 boundary message、summary message、`compaction_checkpoint` event 和 restored context message。
- compact 成功后运行时 `_history` 被替换为 compressed messages。
- compact 失败时不能污染 `_history`，不能写 checkpoint，不能插入 restored context。
- summary 请求已经是 no-tool 路径，不应向模型发送工具定义或工具选择参数。

## 用户可见行为

手动 `/compact` 的新行为：

- 如果 `_history` 为空，显示 `Nothing to compact.`。
- 如果 `_history` 非空，开始 compact，显示现有进度提示。
- 如果摘要请求成功且返回非空摘要，即使消息很少、摘要很短、节省 token 很少或没有节省，也写入 checkpoint。
- 成功提示应允许 `saved ~0 tokens`，因为手动 compact 的目的可以是建立 checkpoint，而不只是缩小上下文。
- 如果摘要为空，显示明确失败原因，例如 `Compact failed: empty summary.`。
- 如果摘要接口异常，显示明确失败原因，例如 `Compact failed: summary request failed: ...`，并保留原 history。
- 不再把摘要过短、消息数不足、没有中间段等情况包装成 `Nothing to compact.`。

自动压缩的新行为：

- 仍只在 token 估算达到阈值时触发。
- 自动压缩不因为消息数少而提前拒绝；是否触发由 token 阈值决定。
- 自动压缩遇到空摘要或接口错误时保留原 history，不写 checkpoint，继续使用原 history 请求模型或按现有错误路径返回。

## 设计

### 1. 引入压缩触发语义

压缩流程需要显式区分触发来源，例如：

```text
trigger = manual | auto
```

建议在 `ConversationCompactor.compact_history()` 或 `ContextManager.compress()` 增加等价参数，而不是继续用消息数隐式判断。

语义约束：

- `manual`：用户明确要求 checkpoint。只要输入消息非空，就尝试摘要。
- `auto`：系统为了控制上下文预算触发。入口仍由 token 阈值控制。

### 2. 去掉消息数硬门槛

删除或绕过 `len(messages) <= 20` 直接拒绝的逻辑。

手动压缩不应要求消息数超过 20。自动压缩也不需要该硬门槛，因为自动入口已经由 token 阈值保护。

### 3. 调整摘要源选择

现有 pair-safe tail 仍保留，但摘要源需要支持短会话。

推荐规则：

- 先对工作副本执行 tool result micro-compact 和 message history 清洗。
- 继续构造 pair-safe protected tail。
- 常规摘要源优先使用 protected tail 之前的消息。
- 如果触发来源是 `manual` 且常规摘要源为空，则使用清洗后的完整 history 作为摘要源。

这样可以保证短会话手动 `/compact` 仍能生成 checkpoint。该路径可能让摘要和 protected tail 出现部分重复，这是可接受代价，因为用户此时表达的是“请现在建立压缩边界”。

### 4. 放宽摘要质量门

`validate_compact_summary()` 的质量门改为只检查：

- 摘要内容去掉首尾空白后非空。
- 摘要请求没有接口错误。

不再拒绝：

- 摘要长度小于 80。
- 摘要长度小于动态分档 80 / 300 / 600 / 1000。
- 文本中出现 `<tool_call>`。
- 文本中出现 `tool_calls` 或 `function_call`。
- 看起来像工具调用 JSON 的摘要。
- `(middle conversation compressed)` 这类短占位文本。

保留 no-tool summary 请求作为主要防线。也就是说，本轮设计把“摘要内容质量”从硬拒绝改为信任模型输出，由用户手动 compact 的明确意图优先。

### 5. 明确失败状态

当前 `CompressionResult` 用 `checkpoint_message={}` 表示所有失败，会导致上层只能显示 `Nothing to compact.`。新设计需要让调用方区分至少三种状态：

- `no_input`：没有消息可压缩。
- `empty_summary`：摘要请求成功但内容为空。
- `summary_request_failed`：摘要接口异常或 provider 返回不可用结果。

可选做法：

- 扩展 `CompressionResult`，增加 `status` / `failure_reason`。
- 或返回专门的 compact outcome 类型，由 `ConversationCompactor` 转换为用户可见消息。

关键约束是：失败状态不能写 checkpoint，不能改写 `_history`。

### 6. 保持 checkpoint 写入顺序

成功路径继续保持当前顺序：

```text
message(system): Compact boundary
message(system): Conversation summary checkpoint
event: compaction_checkpoint
message(system): Compact restored context
```

运行时 `_history` 继续保持：

```text
compact boundary system message
+ summary checkpoint system message
+ optional restored context system message
+ pair-safe protected tail
```

本轮不恢复固定 first user。

## 安全与可靠性

- no-tool summary 请求必须保留，避免摘要阶段触发工具调用。
- compact 失败必须是原子失败：原 `_history` 不变，transcript 不追加 checkpoint 相关事件。
- restored context 的 secret redaction 不变。
- pair-safe tail 不变，不能引入 orphan tool message 或半截 assistant tool call。
- message history 清洗不变，继续防止旧 transcript 中 malformed tool call 污染 provider 请求。
- 放宽摘要质量门会增加“低质量摘要进入 checkpoint”的概率，这是本设计为了响应手动压缩意图接受的风险。
- 若后续发现低质量摘要再次造成严重污染，应优先增加用户可见诊断或二次确认，而不是恢复隐式 `Nothing to compact.`。

## 兼容与迁移

- 新 checkpoint 仍使用 `summary_format=xcode.v3`。
- 旧 session 不需要迁移。
- `/resume` 恢复逻辑应继续兼容旧 checkpoint。
- 现有 transcript 中已经写入的短摘要、长摘要、restored context 都按当前逻辑读取。
- 文档中的当前架构只有在代码实现完成后才能更新；本 spec 阶段只更新 ROADMAP/DEVNOTES 的待实现记录。

## 被拒绝的替代方案

- 保留 `message > 20` 门槛：会继续导致用户手动 compact 被系统拒绝，不符合“只要消息不为空”的目标。
- 保留摘要最小长度质量门：会继续让短但有效的摘要失败，也会让用户看见不透明的 `Nothing to compact.`。
- 手动 compact 只在 token 超阈值时允许：这会让手动命令失去意义，和自动压缩没有区别。
- 将 protocol-looking summary 改为警告但仍拒绝：仍然违背“质量门只挡空摘要和接口错误”的目标。
- 把最近文件全文塞入 restored context 弥补短摘要：会破坏 restored context 的 bounded 和 secret 安全边界。

## 验收标准

- `_history` 非空但消息数少于 4 时，手动 `/compact` 不再直接显示 `Nothing to compact.`，而是尝试摘要。
- 消息数 `<= 20` 的手动 `/compact` 可以成功写入 checkpoint。
- 摘要内容少于 80 字符时，只要非空且请求成功，也能成功写入 checkpoint。
- `source_token_estimate` 很大但摘要短于旧动态门槛时，不再因为长度被拒绝。
- 空摘要仍失败，并且不改写 `_history`、不写 checkpoint、显示明确失败原因。
- 摘要接口异常仍失败，并且不改写 `_history`、不写 checkpoint、显示明确失败原因。
- 自动压缩仍由 token 阈值触发，不因手动压缩语义放宽而频繁触发。
- 成功 checkpoint 仍写入 boundary、summary、`compaction_checkpoint` event 和可选 restored context。
- compact 后的 `_history` 仍无 orphan tool message，pair-safe tail 仍有效。
- `/resume` 能从新写入的 checkpoint 正常恢复。

2026-06-15 自动化执行记录：

- `pytest tests/test_work_state.py tests/test_agent_tool_loop.py tests/test_external_turn.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py tests/test_agent_resume_command.py -q`：`110 passed in 14.25s`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`557 passed in 31.27s`。

PowerShell/cmd.exe 原生 PTY 手工验收尚未执行/未记录；不能把本项写成真实终端整体验收完成。

## 待确认问题

- 手动 compact 成功但没有节省 token 时，提示文案是否继续显示 `saved ~0 tokens`，还是改成更明确的 `checkpoint written`。
- 摘要接口异常是否应该在本地 REPL 显示原始脱敏错误，QQchat/headless 场景是否继续使用安全 fallback。
- protocol-looking summary 不再拒绝后，是否需要在 `compaction_checkpoint` metadata 中记录 `summary_warning`，仅供诊断，不影响成功。
