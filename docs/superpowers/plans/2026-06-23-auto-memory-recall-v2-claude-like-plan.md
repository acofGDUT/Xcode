# Auto Memory Recall v2 Claude-like 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐 task 执行。本计划使用 checkbox（`- [ ]`）跟踪状态。

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工交互验收未执行、未记录。QQchat/external/headless 隔离目前由自动化回归覆盖，未做真实平台手工记录。
日期：2026-06-30

**目标：** 在 auto memory extraction v2 已稳定写入 v2 topic 的基础上，把 relevant auto memory recall 从 v1 轻量 selector 升级为 Claude-like 双路径召回：`MEMORY.md` 短索引常驻主 prompt，后台 non-blocking relevant topic prefetch 只把确定相关的 bounded topic 正文作为 point-in-time system reminder 注入当前本地 REPL turn。

**架构：** 复用现有 `MemoryManager.get_context_for_prompt()`、`MemoryManifestScanner`、`MemoryRecallService`、`RelevantMemoryState`、`AgentRuntime._start_memory_prefetch()` 和 tool loop 安全点注入骨架。不要引入 embedding、vector DB、daemon、公开 memory CRUD tool 或全局 `asyncio`。Recall v2 只服务本地 REPL state；QQchat/external/headless turn 不共享本地 recall state。

**技术栈：** Python 3.10+、pytest、现有同步 `AgentRuntime`、`LLMClient`、`MemoryManager`、`MemoryManifestScanner`、`MemoryRecallService`、`ThreadPoolExecutor`。

---

## 证据和引用

- 父级 spec：[2026-06-23-auto-memory-recall-v2-claude-like-design.md](../specs/2026-06-23-auto-memory-recall-v2-claude-like-design.md)。
- 前置已完成计划：[2026-06-23-auto-memory-extraction-v2-claude-like-plan.md](2026-06-23-auto-memory-extraction-v2-claude-like-plan.md)。
- 前置实现状态：`docs/current/PROGRESS.md` 的 “Auto memory extraction v2” 已记录代码实现和自动化回归完成；原生 PTY 手工验收仍缺失。
- 当前实现入口：`src/xcode_cli/core/memory_recall.py`、`src/xcode_cli/core/memory_manifest.py`、`src/xcode_cli/core/agent.py`。
- 当前 backlog：`docs/current/ROADMAP.md` 中 `Auto memory recall v2`。

## 范围

本计划只实现 **Auto Memory Recall v2**。

它不重新实现 extraction v2，不迁移旧 topic，不新增公开 `memory_search` / `memory_get` / `memory_list` 工具，不把 topic 正文常驻塞进 base system prompt，也不让 QQchat、MCP、sub-agent 或 external/headless turn 共享本地 REPL 的 recall state。

## 文件职责

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/xcode_cli/core/memory_recall.py` | 修改 | v2 selector prompt/input、recent tool context、bounded read、point-in-time reminder、audit result 和 failure/late 状态 |
| `src/xcode_cli/core/memory_manifest.py` | 检查/小改 | 确认 scanner 默认只接受 v2 顶层 `type`、跳过旧 `metadata.type` 并记录 warning |
| `src/xcode_cli/core/agent.py` | 修改 | 本地 REPL prefetch gating、recent successful tool names 记录、安全点注入、late prefetch 丢弃、external/headless 隔离 |
| `src/xcode_cli/core/tooling/execution.py` | 检查/小改 | 如需准确记录成功工具名，提供 bounded executed tool names；不能泄漏 args/path/output |
| `tests/test_memory_recall_v2.py` | 创建 | selector 输入、v2 manifest、recent tools、selection 过滤、bounded read、reminder 渲染回归 |
| `tests/test_agent_memory_recall_v2.py` | 创建 | Agent non-blocking prefetch、gating、安全点注入、late/stale 丢弃、external/headless 隔离回归 |
| `tests/test_memory_manifest_v2.py` | 修改/复用 | 保持 v2 top-level `type` 与 legacy skip 行为 |
| `tests/test_prompting_memory_v2.py` | 复用 | 确认 `MEMORY.md` 短索引仍进入主 prompt，topic 正文不常驻 |
| `docs/current/ROADMAP.md` | 修改 now | 记录 spec/plan 已写、待实现，并指向首个 task |
| `docs/current/ARCHITECTURE.md` | 实现后修改 | 只在代码和验证完成后同步当前 recall v2 架构 |
| `docs/current/PROGRESS.md` | 实现后修改 | 只记录真实实现和验证证据 |
| `docs/current/DEVNOTES.md` | 实现后视风险修改 | 记录仍有效的 recall v2 边界、风险和 review 注意事项 |

## Task 文件

- [Task 1: Trigger gates and recall state](2026-06-23-auto-memory-recall-v2-claude-like/task-01-trigger-gates-and-state.md)
- [Task 2: Selector input and recent tools](2026-06-23-auto-memory-recall-v2-claude-like/task-02-selector-input-and-recent-tools.md)
- [Task 3: Bounded read and point-in-time reminders](2026-06-23-auto-memory-recall-v2-claude-like/task-03-bounded-read-and-reminders.md)
- [Task 4: Agent safe-point integration](2026-06-23-auto-memory-recall-v2-claude-like/task-04-agent-safe-point-integration.md)
- [Task 5: Failure audit and debug surface](2026-06-23-auto-memory-recall-v2-claude-like/task-05-failure-audit-and-debug-surface.md)
- [Task 6: Docs and final verification](2026-06-23-auto-memory-recall-v2-claude-like/task-06-docs-and-final-verification.md)

## 全局执行约束

- 每次只执行一个 task；每个 task 完成后停下来让 Codex review。
- 代码 task 必须遵循 TDD-core：先写失败回归测试，再写最小实现，最后重构。
- 保持 `MEMORY.md` 短索引每轮可见，但 topic 正文不得常驻 base system prompt。
- Recall selector 必须是 no-tool side query：`tool_schemas=[]`，默认复用主 agent LLM/model，不固定 Sonnet。
- 不实现 `memory_recall_model` 配置；如未来需要独立 selector 模型，另写 spec/成本说明。
- 不兼容旧 `metadata.type` 作为 recall v2 验收要求；旧 topic 迁移另行处理。
- 不泄漏 selector prompt、manifest 全量列表、工具参数、文件路径参数、tool output 或 secret 到 reminder。
- recent tool context 只能包含最近成功工具名，最多 10 个 distinct names。
- 每轮最多读取 5 个 topic；每个 topic 最多 4096 bytes 或 200 行；session surfaced 上限默认 60 KiB。
- Prefetch 不得阻塞主模型请求、streaming 或工具执行；迟到 prefetch 不得注入后续 unrelated turn。
- 同一 session 已 surfaced 或本轮已 touched 的 memory 不重复注入。
- QQchat/external/headless turn 不共享本地 REPL recall state，也不触发本地 recall reminder 注入。
- selector 失败、非法 JSON、编造文件名、文件读取失败或超时都 fail closed，不影响主回复。
- 终端 UI 输出 provider/model 文本时保持 `markup=False` 边界。
- `ARCHITECTURE.md` 只能在实现和验证完成后更新为当前事实。

## 推荐最终验证

```powershell
pytest tests/test_memory_manifest_v2.py -q
pytest tests/test_memory_recall_v2.py -q
pytest tests/test_agent_memory_recall_v2.py -q
pytest tests/test_prompting_memory_v2.py -q
python -m compileall -q src
pytest -q
git diff --check
```

如要声明超过“自动化回归完成”，还必须补手工验收记录：

- PowerShell/cmd.exe：本地 REPL 普通 turn 不等待 recall selector 即开始主回复或工具执行。
- PowerShell/cmd.exe：已完成 prefetch 在安全点注入 reminder，迟到 prefetch 不注入下一轮 unrelated turn。
- Memory 目录检查：v2 topic frontmatter、bounded read、截断提示和 `MEMORY.md` 相对链接均符合预期。
- External entry inspection：QQchat/external/headless turn 不共享本地 REPL recall state。
