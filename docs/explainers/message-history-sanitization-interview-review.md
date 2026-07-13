# Message History 清理算法：面试复习手册

> 对应实现：`src/xcode_cli/core/message_history.py`
>
> 关联链路：LLM 请求、context compact、session resume
>
> 日期：2026-07-13

## 1. 一句话说明

`sanitize_model_messages()` 按消息顺序扫描历史，把每个带 `tool_calls` 的 assistant 消息和它后面连续的 tool messages 视为一个协议块：调用结构合法且结果完整时整块保留，否则删除工具调用部分，只保留仍能独立成立的 assistant 文本。

## 2. 为什么需要清理

OpenAI-compatible 工具调用历史必须满足严格的消息顺序：

```text
assistant(tool_calls=[call_1])
    ↓
tool(tool_call_id=call_1)
```

以下情况可能导致 provider 拒绝请求：

- tool result 没有对应的 assistant tool call。
- assistant 发起了 tool call，但缺少对应的 tool result。
- tool result 出现在 assistant 之前，或被 user/system/assistant 消息隔开。
- tool call 缺少 `id`、`function` 或 `function.name`。
- `arguments` 不是 provider 所需的 JSON 字符串。
- compact 或 resume 裁剪后只留下工具协议的一半。

因此，这个函数不是业务功能，而是模型调用边界上的协议防御层。

## 3. 输入与输出

函数签名：

```python
def sanitize_model_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
```

输入是准备发送给模型的 message 列表，输出是清洗后的新列表。函数通过浅拷贝构造结果，不直接重写顶层输入列表。

## 4. 总体流程

```text
输入 messages
    ↓
index = 0
    ↓
读取 messages[index].role
    ↓
┌────────────────────────────────────────────┐
│ user / system / 其他普通消息               │
└────────────────────────────────────────────┘
    ↓
复制到 sanitized
    ↓
index += 1
    ↓
继续循环
```

```text
当前消息是 tool
    ↓
它没有通过前一个 assistant 协议块被接纳
    ↓
判定为 orphan tool message
    ↓
丢弃
    ↓
index += 1
    ↓
继续循环
```

```text
当前消息是 assistant
    ↓
调用 _sanitize_assistant_at(messages, index)
    ↓
同时检查 assistant 和后面连续的 tool messages
    ↓
返回清洗后的 assistant 与 next_index
    ↓
只追加属于该 assistant 的合法 tool results
    ↓
index = next_index
```

所有消息扫描完毕后：

```text
index >= len(messages)
    ↓
返回 sanitized
```

## 5. `sanitize_model_messages()` 主扫描算法

主函数使用索引而不是简单的 `for` 循环，因为处理一条 assistant 消息时，需要一次消费后面整批连续的 tool messages。

伪代码：

```python
sanitized = []
index = 0

while index < len(messages):
    message = messages[index]
    role = message.get("role")

    if role == "assistant":
        assistant, next_index = sanitize_assistant_block(messages, index)

        if assistant is not None:
            sanitized.append(assistant)

        expected_ids = assistant 中保留下来的 tool call IDs

        for tool_message in messages[index + 1:next_index]:
            if tool_message.tool_call_id in expected_ids:
                sanitized.append(tool_message)

        index = next_index
        continue

    if role == "tool":
        index += 1
        continue

    sanitized.append(copy(message))
    index += 1
```

关键点：

- 单独扫描到的 tool message 一律视为孤立消息。
- tool message 只有通过其前一个 assistant block 的校验，才能进入结果。
- `next_index` 让主循环一次跳过整个 assistant/tool block。

## 6. `_sanitize_assistant_at()` 的分支流程

### 6.1 Assistant 没有 tool calls

```text
assistant
    ↓
tool_calls 不存在或为空
    ↓
这是普通 assistant 消息
    ↓
复制并保留
    ↓
next_index = index + 1
```

例如：

```python
{
    "role": "assistant",
    "content": "任务完成了",
}
```

该消息直接保留。

### 6.2 Assistant 存在 tool calls

```text
assistant.tool_calls
    ↓
逐个调用 _normalize_tool_call()
    ↓
是否全部合法？
    ├── 否 → 整批工具调用降级
    └── 是 → 检查后续 tool results 是否完整
```

这里采用“整批成功或整批降级”的策略：一批 tool calls 中只要有一个结构损坏，就不尝试保留其他调用。

## 7. `_normalize_tool_call()` 的具体流程

```text
tool_call 是否为 dict？
    ├── 否 → 返回 None
    └── 是
          ↓
id 转字符串并 strip
          ↓
id 是否非空？
    ├── 否 → 返回 None
    └── 是
          ↓
function 是否为 dict？
    ├── 否 → 返回 None
    └── 是
          ↓
function.name 是否为非空字符串？
    ├── 否 → 返回 None
    └── 是
          ↓
arguments 是否为字符串？
    ├── 是 → 原样使用
    └── 否 → 使用 json.dumps() 转换
          ↓
返回标准 function tool call
```

输入：

```python
{
    "id": " call_1 ",
    "type": "anything",
    "function": {
        "name": " read_file ",
        "arguments": {"path": "README.md"},
    },
}
```

输出：

```python
{
    "id": "call_1",
    "type": "function",
    "function": {
        "name": "read_file",
        "arguments": "{\"path\": \"README.md\"}",
    },
}
```

规范化行为包括：

- 清理 `id` 和 `function.name` 两端空格。
- 强制设置 `type="function"`。
- 把字典或列表形式的 `arguments` 转成 JSON 字符串。
- 参数无法序列化时使用 `"{}"` 兜底。

## 8. 任意 tool call 非法时如何降级

```text
一批 tool calls 中出现非法调用
    ↓
找到 assistant 后连续 tool messages 的结束位置
    ↓
删除 assistant.tool_calls
    ↓
跳过这批连续 tool messages
    ↓
assistant 是否还有非空 content？
    ├── 是 → 保留普通 assistant 文本
    └── 否
          ↓
是否还有 reasoning_content？
    ├── 是 → 保留 assistant
    └── 否 → 删除整条 assistant
```

输入：

```python
{
    "role": "assistant",
    "content": "我准备读取文件",
    "tool_calls": [
        {"id": "", "function": {"name": ""}},
    ],
}
```

输出：

```python
{
    "role": "assistant",
    "content": "我准备读取文件",
}
```

如果 `content=None` 且没有 `reasoning_content`，整条 assistant 会被删除。

## 9. “连续 tool messages”如何定义

`_next_after_consecutive_tools()` 从 assistant 的下一条消息开始，只要角色仍然是 `tool` 就继续向后移动。

```text
assistant
    ↓
tool call_1
    ↓
tool call_2
    ↓
user
```

这里的连续 tool block 是 `call_1` 和 `call_2`。

下面的 `call_1` 不算合法结果：

```text
assistant calls=[call_1]
    ↓
system message
    ↓
tool result call_1
```

因为 system message 已经终止了连续 tool block。即使 ID 相同，也不能跨越其他角色消息配对。

## 10. Tool result 完整性检查

规范化全部 tool calls 后，算法构造两个集合：

```python
expected_ids = assistant 发起的 tool call IDs
result_ids = 后面连续 tool messages 的 tool_call_id
```

完整性条件：

```python
expected_ids <= result_ids
```

即 assistant 发起的每一个调用都必须有结果。

### 结果完整

```text
expected_ids = {call_1, call_2}
result_ids   = {call_1, call_2}
    ↓
保留规范化后的 assistant
    ↓
保留 call_1 和 call_2 的 tool messages
```

### 结果缺失

```text
expected_ids = {call_1, call_2}
result_ids   = {call_1}
    ↓
call_2 缺少结果
    ↓
整个工具调用批次降级
    ↓
删除 assistant.tool_calls
    ↓
跳过后面连续的 tool messages
    ↓
只保留可独立成立的 assistant 文本或 reasoning
```

### 存在额外的孤立结果

```text
expected_ids = {call_1}
result_ids   = {call_1, orphan}
    ↓
assistant 的调用是完整的
    ↓
保留 call_1
    ↓
过滤 orphan
```

## 11. 完整箭头流程图

```text
输入 messages
    ↓
index = 0
    ↓
index 是否越界？
    ├── 是 → 返回 sanitized
    └── 否
          ↓
读取当前 role
          ↓
┌────────────────────────────────────────────────┐
│ role 是 user / system / 其他普通角色           │
└────────────────────────────────────────────────┘
          ↓
复制消息到 sanitized
          ↓
index += 1
          ↓
回到循环顶部
```

```text
当前 role 是 tool
    ↓
当前 tool 未通过 assistant block 接纳
    ↓
判定为 orphan tool
    ↓
丢弃
    ↓
index += 1
    ↓
回到循环顶部
```

```text
当前 role 是 assistant
    ↓
是否存在 tool_calls？
    ├── 否
    │     ↓
    │   保留 assistant
    │     ↓
    │   index += 1
    │
    └── 是
          ↓
        逐个规范化 tool call
          ↓
        是否全部合法？
          ├── 否
          │     ↓
          │   删除整个 tool_calls 字段
          │     ↓
          │   跳过后面连续的 tool messages
          │     ↓
          │   assistant 有文本或 reasoning？
          │     ├── 是 → 保留剩余 assistant
          │     └── 否 → 删除 assistant
          │
          └── 是
                ↓
              收集 expected_ids
                ↓
              收集后面连续 tool messages 的 result_ids
                ↓
              expected_ids 是否全部存在于 result_ids？
                ├── 否
                │     ↓
                │   删除整个 tool_calls 字段
                │     ↓
                │   跳过连续 tool messages
                │     ↓
                │   只保留可独立成立的 assistant 内容
                │
                └── 是
                      ↓
                    保留规范化后的 assistant
                      ↓
                    只保留 ID 属于 expected_ids 的 tool messages
                      ↓
                    过滤额外 orphan tool messages
                      ↓
                    index 跳到整个 assistant/tool block 之后
```

## 12. 三个典型案例

### 12.1 合法配对

输入：

```text
user: 读取 README
assistant: tool_calls=[call_1]
tool: tool_call_id=call_1, content="README 内容"
assistant: 已完成
```

流程：

```text
user → 保留
    ↓
assistant tool call 结构合法
    ↓
找到紧邻的 call_1 result
    ↓
调用与结果完整配对
    ↓
assistant + tool 全部保留
    ↓
最终 assistant 文本保留
```

输出与输入语义一致。

### 12.2 缺少 tool result

输入：

```text
user: 读取 README
assistant: content=None, tool_calls=[call_1]
assistant: 工具似乎失败了
```

流程：

```text
assistant 期望 call_1
    ↓
后面没有连续 tool result
    ↓
工具批次不完整
    ↓
删除 tool-call-only assistant
    ↓
保留后面的普通 assistant
```

输出：

```text
user: 读取 README
assistant: 工具似乎失败了
```

### 12.3 Tool result 出现在 assistant 之前

输入：

```text
tool: tool_call_id=call_1, content="提前出现的结果"
assistant: content=None, tool_calls=[call_1]
```

流程：

```text
第一条 tool 没有前置 assistant block
    ↓
作为 orphan 删除
    ↓
assistant 期望 call_1
    ↓
assistant 后面没有对应结果
    ↓
删除 assistant.tool_calls
    ↓
assistant 没有文本或 reasoning
    ↓
删除整条 assistant
```

输出：

```text
[]
```

## 13. 为什么裁剪前后要各清理一次

Session resume 和 compact 通常采用：

```text
原始 history
    ↓
sanitize_model_messages()
    ↓
按 token budget 裁剪
    ↓
sanitize_model_messages()
    ↓
发送给模型
```

第一次清理解决 transcript 原本存在的问题：

- 旧版本写入了 malformed tool call。
- 进程中断导致 tool result 未落盘。
- transcript 中存在孤立或乱序 tool result。

第二次清理解决裁剪过程可能产生的问题：

- assistant tool call 被删除，但 tool result 仍在。
- tool result 被删除，但 assistant tool call 仍在。
- 多调用批次只剩部分结果。

这种“两次清洗”是防御式设计，不依赖裁剪算法永远正确维护协议边界。

## 14. 代码中的使用位置

`sanitize_model_messages()` 当前用于三个关键边界：

| 调用位置 | 作用 |
|----------|------|
| `core/llm.py` | 真正发送 provider 前的最后防线 |
| `core/context.py` | compact 工作副本上的清理 |
| `core/session_resume.py` | resume 重建和 token 裁剪前后的清理 |

这说明它不是 resume 专用 helper，而是整个 Agent Runtime 的模型消息协议层。

## 15. 复杂度

主循环会按顺序消费消息；assistant 后连续的 tool messages 会作为同一个 block 一次处理。

在正常消息结构下：

```text
时间复杂度：O(n + t)
空间复杂度：O(n)
```

其中：

- `n` 是 message 数量。
- `t` 是所有 assistant tool calls 的总数。

## 16. 面试回答模板

### 16.1 30 秒回答

> Agent 的历史消息里，assistant tool call 和 tool result 必须严格配对，否则 OpenAI-compatible provider 会拒绝请求。我实现了一个顺序清洗器，把 assistant 和后面连续的 tool messages 视为协议块，先规范化 tool call，再检查每个 call ID 是否都有紧邻结果。完整就整块保留，不完整就删除工具调用部分，只保留仍能独立成立的 assistant 文本。这个清洗器同时用于 LLM 请求边界、compact 和 session resume。

### 16.2 为什么不只按 `tool_call_id` 全局查找

> 因为工具协议不仅要求 ID 相同，还要求 tool result 紧跟在发起调用的 assistant 后面。远处出现相同 ID 可能属于损坏历史、重复 ID 或错误顺序，不能据此认定配对完整。

### 16.3 为什么一个调用损坏就删除整批 tool calls

> 同一个 assistant 可能并行发起多个工具调用。如果只保留部分调用，恢复后会改变原始执行语义，并可能留下部分完成的批次。整批降级更保守，也更容易保证 provider 协议合法。

### 16.4 为什么保留 assistant 文本

> Tool call 损坏不代表 assistant 的普通文本也无效。如果 `content` 或 `reasoning_content` 仍能独立成立，就删除 `tool_calls` 后保留文本；如果 assistant 只是一个 tool-call-only 中间消息，就整条删除。

### 16.5 为什么 resume 裁剪后还要再次清理

> 裁剪可能从工具协议块中间切开，产生孤立 tool result 或缺少结果的 assistant tool call。再次清理可以把裁剪后的 history 恢复到 provider 可接受的协议状态。

## 17. 面试追问与当前边界

### 17.1 是否修改原始输入

函数构造新的顶层 message 字典和标准化后的 tool call 字典，不直接改写输入列表。但普通消息使用浅拷贝，不能把它描述成完整深拷贝。

### 17.2 是否执行工具

不会。该模块只清理历史消息结构，不做权限判断，也不执行任何工具。

### 17.3 是否验证工具名称真的已注册

不会。它只验证 `function.name` 是非空字符串；工具是否注册、是否可见和是否允许执行，由工具注册表、tool scope 和权限系统负责。

### 17.4 是否保证精确 token 数量

不会。Token 估算和裁剪属于 `ContextManager` 与 `SessionResumeBuilder`；本模块只负责消息协议合法性。

## 18. 复习检查表

面试前应能不看代码回答：

- 为什么孤立 tool message 必须删除？
- 为什么只认可 assistant 后连续的 tool messages？
- `_normalize_tool_call()` 校验哪些字段？
- 为什么 `arguments` 必须转成 JSON 字符串？
- 为什么一个 tool call 损坏会让整批调用降级？
- Assistant 去掉 tool calls 后，什么情况下仍会保留？
- `expected_ids <= result_ids` 表达什么含义？
- 为什么额外的 orphan result 不会被保留？
- 为什么 compact 和 resume 裁剪后要再次清理？
- 这个函数在 LLM、compact、resume 三条链路中的位置分别是什么？
