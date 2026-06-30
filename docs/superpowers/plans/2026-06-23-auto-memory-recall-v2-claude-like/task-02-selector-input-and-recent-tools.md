# Task 02: Selector Input And Recent Tools

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工验收未执行、未记录。

**风险层级：** P1

## 目标

把 recall selector 升级为 v2 no-tool side query：使用 v2 manifest 的 `filename/name/description/type/mtime/source`，加入 bounded recent successful tool names，并严格过滤 selector 输出。

## 建议文件

- 修改：`src/xcode_cli/core/memory_recall.py`
- 修改：`src/xcode_cli/core/agent.py`
- 检查/小改：`src/xcode_cli/core/tooling/execution.py`
- 创建/修改：`tests/test_memory_recall_v2.py`
- 创建/修改：`tests/test_agent_memory_recall_v2.py`

## 约束

- selector 必须使用 `tool_schemas=[]`。
- 默认复用主 agent `LLMClient` 和当前模型配置，不新增 `memory_recall_model`。
- selector 输入可以包含最近成功工具名，但不能包含工具参数、路径、输出或 secret。
- selector 输出最多 5 个 filename，必须来自 manifest，且不能带 `/` 或 `\`。
- 最近成功工具只用于抑制普通 usage/API reference；warning/gotcha/known issue 不应被抑制。

## 步骤

- [x] **Step 1: 添加 selector prompt/input 测试**

在 `tests/test_memory_recall_v2.py` 覆盖：

- selector request 的 `tool_schemas == []`。
- selector system prompt 包含“Return JSON only”“Do not invent filenames”“recently successful tools”相关规则。
- selector user input 包含 query、最多 200 条 manifest、`[type] filename (mtime/source): description`。
- manifest 中包含 `name` 时也可进入输入，帮助 LLM 区分 slug 和标题。

- [x] **Step 2: 添加 recent tools 测试**

覆盖：

- `recent_successful_tools=["read_file", "edit_file", "read_file"]` 渲染为最多 10 个 distinct tool names。
- 不渲染 tool args、path、command、output。
- 无 recent tools 时省略该段。

- [x] **Step 3: 添加 selection 过滤测试**

覆盖：

- selector 编造 filename 被过滤。
- 重复 filename 去重。
- `../foo.md`、`dir/foo.md`、`dir\foo.md` 被过滤。
- 输出超过 5 个时截断。
- 非 dict、缺 `selected_memories`、非法 JSON 都 fail closed。

- [x] **Step 4: 让测试先失败**

运行：

```text
pytest tests/test_memory_recall_v2.py -q
```

预期：recent tools 和 v2 prompt/input 相关测试失败。

- [x] **Step 5: 实现 selector input**

在 `MemoryRecallService.prefetch()` 增加可选参数，例如：

```python
recent_successful_tools: list[str] | None = None
```

并升级 `_SELECTOR_PROMPT` 和 `_render_selector_input()`：

- 输入包含 query。
- 输入包含候选 manifest 的 type、filename、mtime/source、description，可包含 name。
- recent tools 只输出工具名，去重并限制为 10 个。

- [x] **Step 6: 记录最近成功工具名**

在本地 `AgentRuntime` tool loop 中，基于执行结果维护最近成功工具名：

- 只记录成功执行的工具名。
- 只保留最近 10 个 distinct names。
- 不记录 args、path、command 或 output。
- QQchat/external/headless path 不写入本地 REPL recent tools。

如果 `ToolCallExecutor.execute()` 目前没有直接暴露成功工具名，优先做小而明确的返回字段，而不是解析 tool result 文案。

- [x] **Step 7: 运行聚焦测试**

运行：

```text
pytest tests/test_memory_recall_v2.py tests/test_agent_memory_recall_v2.py -q
```

预期：

- selector no-tool、input 渲染和 output 过滤通过。
- recent tools 只包含工具名。

- [x] **Step 8: 停止 review**

Review 检查：

- 是否有任何工具参数、路径、shell command、输出片段进入 selector input。
- selector 是否仍能选择 warning/gotcha/known issue 类 memory。
- 是否没有为了 recent tools 引入脆弱的 tool result 文案解析。
