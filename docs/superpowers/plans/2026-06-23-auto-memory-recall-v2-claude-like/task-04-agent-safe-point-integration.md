# Task 04: Agent Safe-Point Integration

状态：未实现；自动化回归未执行；PowerShell/cmd.exe 原生 PTY 手工验收未执行。

**风险层级：** P0/P1

## 目标

把 recall v2 prefetch 安全接回 `AgentRuntime`：主 LLM 请求和 streaming 不等待 prefetch；只有 prefetch 在当前 turn 的安全点已经完成时才注入 reminder；迟到或 stale prefetch 不得污染后续 turn。

## 建议文件

- 修改：`src/xcode_cli/core/agent.py`
- 创建/修改：`tests/test_agent_memory_recall_v2.py`
- 修改/复用：`tests/test_agent_user_turn.py`
- 修改/复用：`tests/test_external_turn.py`

## 约束

- 主模型第一次请求前不能阻塞等待 recall。
- 工具轮次后的安全点可检查已完成 prefetch 并注入一次。
- 当前 turn 结束仍未完成的 prefetch 必须丢弃或标记 late，不能注入下一轮 unrelated turn。
- 同一 turn 已消费的 prefetch 不得重复注入。
- 已 surfaced 或本轮 touched 的 memory 注入前再次过滤。
- QQchat/external/headless turn 不共享本地 REPL recall state。

## 步骤

- [ ] **Step 1: 添加 non-blocking 集成测试**

在 `tests/test_agent_memory_recall_v2.py` 覆盖：

- `_run_user_turn()` 启动 recall future 后立即调用主 `llm.complete()`，不等待 future 完成。
- prefetch 未完成时，第一轮主 LLM request 的 history 不包含 relevant memory reminder。
- future 在工具轮后完成时，下一次主 LLM request 前追加一次 reminder。

- [ ] **Step 2: 添加 late/stale 测试**

覆盖：

- final assistant response 前 prefetch 仍未完成时，本 turn 不注入 reminder。
- 下一轮 unrelated turn 不消费上一轮 future。
- `late_prefetch_count` 或等价 audit 状态可记录迟到，不影响用户回复。

- [ ] **Step 3: 添加 touched-path 二次过滤测试**

覆盖：

- selector 选中的 memory 如果在本轮已经被主模型 `read_file` / `write_file` / `edit_file` 触碰，注入前过滤掉。
- 已 surfaced 的 memory 不重复注入。

- [ ] **Step 4: 让测试先失败**

运行：

```text
pytest tests/test_agent_memory_recall_v2.py -q
```

预期：late/stale 丢弃和工具轮安全点注入测试先失败或需要迁移旧逻辑。

- [ ] **Step 5: 实现 turn-local prefetch token**

在 `_run_user_turn()` / `_run_llm_loop()` 传递当前 turn 的 future 时，确保：

- future 只属于当前 turn。
- 注入后将 active future 置空。
- turn 结束后如 future 未消费，不再保留给下一轮。

- [ ] **Step 6: 实现注入前二次过滤**

继续使用 `_filter_relevant_memories()` 和 `_mark_relevant_memories_surfaced()`，但确认它们基于当前 runtime state，而不是只信任 prefetch snapshot。

- [ ] **Step 7: 运行聚焦测试**

运行：

```text
pytest tests/test_agent_memory_recall_v2.py tests/test_agent_user_turn.py tests/test_external_turn.py -q
```

预期：

- 本地 REPL recall 注入时机正确。
- external/headless 路径不触发本地 recall。
- 主回复和工具执行不等待 selector。

- [ ] **Step 8: 停止 review**

Review 检查：

- 是否存在 stale future 被下一轮消费的路径。
- 注入的 system message 是否会破坏 OpenAI-compatible assistant/tool 配对。
- 触碰路径过滤是否仍限制在 auto memory scope。

