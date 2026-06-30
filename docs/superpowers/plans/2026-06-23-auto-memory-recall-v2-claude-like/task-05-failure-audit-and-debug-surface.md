# Task 05: Failure Audit And Debug Surface

状态：未实现；自动化回归未执行；PowerShell/cmd.exe 原生 PTY 手工验收未执行。

**风险层级：** P1/P2

## 目标

让 recall v2 的失败、跳过和迟到状态可审计，但不污染普通对话输出。默认只保留本地 runtime 状态，后续可由 `/memory` 或 debug 视图展示。

## 建议文件

- 修改：`src/xcode_cli/core/memory_recall.py`
- 修改：`src/xcode_cli/core/agent.py`
- 可选修改：`src/xcode_cli/core/agent.py` 的 `/memory` handler
- 创建/修改：`tests/test_memory_recall_v2.py`
- 创建/修改：`tests/test_agent_memory_recall_v2.py`

## 约束

- selector 失败、超时、非法 JSON、编造文件名、文件读取失败、late prefetch 都不影响主回复。
- 默认不在普通对话中打印审计字段。
- 审计信息不能包含 selector prompt 全文、manifest 全量列表、tool args、tool output 或 secret。
- 如果扩展 `/memory` 输出，必须保持中文 UI 文案，并避免 Rich markup 注入。

## 步骤

- [ ] **Step 1: 添加 audit result 测试**

覆盖 `RelevantMemoryResult` 或新增 audit dataclass：

- `selected_count`
- `surfaced_count`
- `skipped_reason`
- `warnings`
- `selector_model`（如果现有 `LLMClient` 可安全提供）
- `elapsed_ms`
- `late_or_consumed`

字段可以按实现实际裁剪，但必须能解释“为什么本轮没有注入 memory”。

- [ ] **Step 2: 添加 fail-closed 测试**

覆盖：

- selector 抛异常。
- selector 返回非法 JSON。
- selector 返回路径分隔符。
- memory 文件读取失败。
- prefetch future 抛异常。

预期：主流程不抛异常，result/reminder 为空或只带 warning。

- [ ] **Step 3: 让测试先失败**

运行：

```text
pytest tests/test_memory_recall_v2.py tests/test_agent_memory_recall_v2.py -q
```

预期：audit 字段或 late 状态相关测试失败。

- [ ] **Step 4: 实现 audit 状态**

优先把审计状态保存在内存对象里：

- `RelevantMemoryResult` 可增加 summary 字段。
- `AgentRuntime` 可保存 `self._last_memory_recall_result`。
- 不写 session transcript，不写项目文件。

- [ ] **Step 5: 可选扩展 `/memory` debug 输出**

如果实现范围允许，在 `/memory` 状态里追加一行最近 recall 摘要，例如：

```text
Relevant recall: selected=2 surfaced=1 skipped=late warnings=0
```

保持这是状态摘要，不输出 memory 正文或 selector 输入。

- [ ] **Step 6: 运行聚焦测试**

运行：

```text
pytest tests/test_memory_recall_v2.py tests/test_agent_memory_recall_v2.py -q
```

预期：

- fail-closed 路径全部通过。
- 普通对话输出不出现 debug/audit 噪声。

- [ ] **Step 7: 停止 review**

Review 检查：

- 审计字段是否足够定位问题，但不泄漏敏感上下文。
- 是否误把 recall failure 写入 transcript 或用户可见回复。
- `/memory` 输出如有新增，是否使用中文且不解析模型文本为 Rich markup。

