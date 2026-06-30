# Task 01: Trigger Gates And Recall State

状态：未实现；自动化回归未执行；PowerShell/cmd.exe 原生 PTY 手工验收未执行。

**风险层级：** P0/P1

## 目标

收紧 recall v2 的启动条件和 session state，使本地 REPL 只在值得召回时启动 non-blocking prefetch，并为后续安全点注入提供可审计状态。

## 建议文件

- 修改：`src/xcode_cli/core/memory_recall.py`
- 修改：`src/xcode_cli/core/agent.py`
- 创建：`tests/test_agent_memory_recall_v2.py`
- 修改/复用：`tests/test_memory_recall.py`

## 约束

- `auto_memory=false`、用户要求不使用/忽略记忆、过短 query、session surfaced bytes 达上限时不启动 recall。
- 只对本地 REPL turn 启动 recall；QQchat/external/headless turn 不共享本地 state。
- `submit`/`prefetch` 启动路径不得等待 selector LLM。
- 不新增公开 memory CRUD tool。

## 步骤

- [ ] **Step 1: 添加 trigger gate 回归测试**

在 `tests/test_agent_memory_recall_v2.py` 覆盖：

- `auto_memory=false` 时 `_start_memory_prefetch()` 返回 `None`。
- 用户输入包含 “ignore memory” / “不使用记忆” 时返回 `None`。
- 单字、单词或无空白极短 query 默认跳过。
- `RelevantMemoryState.surfaced_bytes >= MAX_SESSION_SURFACED_BYTES` 时返回 `None`。
- 本地 REPL 成功 turn 才可能启动 recall；external/headless 测试保持不会触发本地 recall state。

- [ ] **Step 2: 添加 state 字段测试**

在 `tests/test_memory_recall_v2.py` 或现有 `tests/test_memory_recall.py` 覆盖：

- `RelevantMemoryState.snapshot()` 复制 `surfaced_paths`、`touched_paths`、`surfaced_bytes`。
- 新增 `late_prefetch_count` / `warnings` / `last_result` 等审计字段时，snapshot 不共享可变集合。

- [ ] **Step 3: 让测试先失败**

运行：

```text
pytest tests/test_agent_memory_recall_v2.py tests/test_memory_recall.py -q
```

预期：过短 query、session cap 或新增审计字段相关测试先失败。

- [ ] **Step 4: 实现 trigger gates**

在 `AgentRuntime._start_memory_prefetch()` 或 `MemoryRecallService` 的入口层实现：

- `query.strip()` 为空直接跳过。
- `state.surfaced_bytes` 达上限直接跳过。
- 极短 query 跳过，建议规则为：去空白后长度很短，且不包含空格/中文短语上下文时跳过；具体阈值以测试固定。
- 保留现有 `_memory_disabled_for_turn()` 中英文短语，并根据 spec 补齐“不使用记忆/忽略记忆”语义。

- [ ] **Step 5: 保持 non-blocking 边界**

确认 `_start_memory_prefetch()` 只做轻量 gating、manifest scan 和 `ThreadPoolExecutor.submit()`，不得调用 `future.result()` 或等待 selector。

- [ ] **Step 6: 运行聚焦测试**

运行：

```text
pytest tests/test_agent_memory_recall_v2.py tests/test_memory_recall.py -q
```

预期：

- Trigger gate 测试通过。
- 现有 v1 recall 基础行为未回归。

- [ ] **Step 7: 停止 review**

Review 检查：

- 是否把 recall state 限定在本地 `AgentRuntime`。
- 是否避免了任何 external/headless 共享 state。
- 是否没有把“过短 query”规则写得过度激进，导致正常中文短句都不召回。

