# Compact State Restoration And Checkpoint Lineage Design

> 状态：设计和实施计划已完成；代码未实现，自动化回归、PowerShell/cmd.exe 原生 PTY 验收和真实 QQ 平台验收均未执行。
> 日期：2026-06-12
> 风险层级：P0/P1。该设计触及 context compaction、session transcript、`/resume`、tool loop、QQchat external turn 和长期任务恢复。

## 背景

`2026-06-11-compact-reliability-design.md` 已把 compact 从旧的固定裁剪升级为更可靠的 `xcode.v2` 模型：

- no-tool summary request；
- summary quality gate；
- compact boundary；
- pair-safe protected tail；
- old tool result micro-compact；
- QQchat/external turn 的 `No response.` 错误边界。

这解决了坏摘要污染 history、orphan tool message、反复大工具输出触发压缩等问题。但 `xcode.v2` 仍主要依赖 summary 和最近 tail 继续工作。长任务中，模型真正需要的现场往往不是历史叙述，而是可执行状态：

- 当前正在改哪个文件；
- 最近读过哪些文件、读到哪些行、文件是否已变化；
- 最近构建或测试失败在哪里；
- 当前计划下一步是什么；
- 最近加载了哪些 skill 或外部入口约束。

如果这些信息只靠 summary 自由总结，就可能在多次 compact 后逐渐丢失。第二个缺口是 checkpoint 虽然已经累计更新 summary 文本，但 transcript 里还没有清晰的 checkpoint parent/child 链路、summary hash、覆盖范围和 restored-context hash，后续排查长会话时仍不够可审计。

## 目标

1. compact 后额外注入一段 deterministic 的恢复现场，和 summary 分工明确：summary 负责历史脉络，restored context 负责继续工作的当前现场。
2. 恢复现场必须来自运行时结构化状态，不依赖 summary LLM 猜测。
3. checkpoint 从 `xcode.v2` 升级到兼容的 `xcode.v3` metadata，记录 parent checkpoint、hash、累计序号、覆盖范围和 restored-context 摘要信息。
4. `/resume` 从 `xcode.v3` checkpoint 恢复时能重新得到 summary + restored context，而不是只得到 summary。
5. 本地 REPL、QQchat external conversation、未来其他外部入口的现场状态必须隔离，不能互相污染。
6. 所有新增信息必须有 token/字符上限，不能把完整文件、完整日志、secret 或敏感环境变量塞回模型。

## 非目标

- 不引入 embedding、vector DB、索引服务或后台异步任务。
- 不把所有读过的文件全文持久化到 session。
- 不实现真正的 IDE/LSP/Xcode diagnostics 接入；第一版只从现有工具调用和 shell 输出中提取启发式 diagnostics/build/test 信息。
- 不改变工具权限模型，不让 QQchat 远程入口获得新的危险工具能力。
- 不迁移旧 session JSONL。旧 `xcode.v1/v2` checkpoint 继续按现有逻辑恢复。
- 不把 skill body、MCP server secret、完整 MCP schema 或完整 tool instructions 写入 restored context。

## 设计原则

### Summary 和现场恢复分工

summary checkpoint 是长期记忆，回答“之前发生了什么、做过什么决定、为什么走到这里”。

restored context 是当前工作现场，回答“现在继续做需要马上知道什么”。它应该短、结构化、可验证，并且尽量由工具结果和运行时状态直接生成。

### 先沉淀状态，再消费状态

compact 不应该扫描整段历史去猜 active file、build error 或 failed test。它应该从一个持续维护的 `WorkStateTracker` 读取 snapshot。状态更新发生在工具执行完成、plan mode 变化、skill invocation 记录等边界上。

### 保守、可丢弃、可恢复

restored context 是增强信息，不是唯一历史来源。如果状态收集失败、内容超限或没有可用现场，compact 仍应保留 `xcode.v2` 可靠性：summary + boundary + pair-safe tail。状态收集失败不得阻断主循环或写入坏 checkpoint。

## 核心架构

### WorkStateTracker

新增 `src/xcode_cli/core/work_state.py`，负责维护当前会话的轻量现场状态。

建议结构：

```python
@dataclass
class FileExcerpt:
    path: str
    sha256: str
    observed_at: str
    line_start: int
    line_end: int
    excerpt: str
    source: str
    stale: bool = False


@dataclass
class DiagnosticItem:
    source: str
    path: str
    line: int | None
    column: int | None
    severity: str
    message: str
    command: str = ""


@dataclass
class CommandStatus:
    kind: str
    command: str
    cwd: str
    exit_code: int | None
    observed_at: str
    output_excerpt: str
    failed_tests: list[str]


@dataclass
class WorkStateSnapshot:
    active_file: str
    recent_files: list[FileExcerpt]
    diagnostics: list[DiagnosticItem]
    latest_build: CommandStatus | None
    latest_test: CommandStatus | None
    current_plan: str
    invoked_skills: list[dict[str, str]]
```

第一版上限建议：

| 内容 | 上限 |
|------|------|
| restored context 总长度 | 8000 chars |
| recent files | 4 个 |
| 每个文件 excerpt | 80 行或 4000 chars，先到为准 |
| diagnostics | 12 条 |
| failed tests | 20 个 |
| command output excerpt | 2000 chars |
| invoked skills | 8 个，只保留 name/source_hash，不保留 body |

### 状态更新来源

`ToolCallExecutor.execute()` 在每个 tool call 结束后，把 tool 名称、参数、`ToolOutput` 和执行范围交给 tracker。

建议第一版记录：

| 工具 | 记录内容 |
|------|----------|
| `read_file` | path、offset/limit、实际 excerpt、文件 sha256、active file |
| `edit_file` / `write_file` | path、active file、修改后的 sha256；不记录写入正文 |
| `grep` | pattern/path、命中文件摘要；不把所有命中内容当文件 excerpt |
| `glob` | pattern/path、命中文件数量和前若干路径 |
| `run_shell` | command/cwd/exit_code/output excerpt；解析 build/test/diagnostic |
| `skill` | skill name、source_hash、source_path；不记录 skill body |
| `task_list` | 当前 task 摘要可作为 current plan 的候选补充 |

`run_shell` 第一版只做启发式解析：

- `xcodebuild`、`swift build`、`npm run build`、`pnpm build` 等归为 `kind="build"`；
- `pytest`、`npm test`、`pnpm test`、`xcodebuild test` 等归为 `kind="test"`；
- 识别 `path:line:column: error: message`、`path:line: error: message`、`FAILED tests/...::name` 等常见格式；
- 解析失败时只保留 command status 和 output excerpt。

### 会话隔离

本地 REPL 使用 `AgentRuntime.work_state`。

QQchat/external turn 不能复用本地 REPL 的 work state。`ExternalTurnRunner` 的 per-conversation state 应增加独立 `WorkStateTracker`，或由 `AgentRuntime._run_external_llm_loop()` 按 external session id 取独立 tracker。目标是不让远程 QQ 用户看到本地 REPL 刚读过或正在改的文件现场。

### Restored Context Builder

新增 builder，把 `WorkStateSnapshot` 渲染为 system message：

```text
Compact restored context:
- Active file: src/xcode_cli/core/context.py
- Recently read files:
  - src/xcode_cli/core/context.py sha256=abc123 lines 58-170
    excerpt:
    ...
- Latest diagnostics:
  - src/foo.py:42 error: Cannot convert value ...
- Latest build:
  - failed at 2026-06-12T14:20:00Z
  - command: xcodebuild ...
- Latest tests:
  - failed: tests/test_context.py::test_rejects_bad_summary
- Current plan:
  - fix summary rejection path
  - rerun compact regression
- Invoked skills:
  - superpowers:systematic-debugging sha256:...
```

渲染优先级：

1. active file；
2. diagnostics；
3. latest failed build/test；
4. current plan；
5. recent files；
6. invoked skills；
7. recent searches。

如果超出预算，按低优先级裁剪。裁剪必须显式写出 omitted count，例如 `- omitted 3 older files due to restored-context budget`。

### Compact 历史重写

`xcode.v3` compact 后的运行时 `_history` 应为：

```text
first user
system: Compact boundary
system: Conversation summary checkpoint
system: Compact restored context
pair-safe protected tail
```

如果 restored context 为空，则省略该 system message。

summary 失败或被 quality gate 拒绝时：

- 不改写 `_history`；
- 不写 checkpoint；
- 不写 restored context message；
- 可追加 `compaction_failed` audit event，但不得进入模型 history。

### Checkpoint Lineage Metadata

`compaction_checkpoint` event 从 `summary_format=xcode.v2` 升级为 `xcode.v3`，并保持向后兼容。

建议字段：

```json
{
  "type": "compaction_checkpoint",
  "summary_format": "xcode.v3",
  "checkpoint_id": "ckpt_20260612_001",
  "parent_checkpoint_id": "ckpt_20260612_000",
  "checkpoint_index": 3,
  "summary": "...",
  "summary_hash": "sha256:...",
  "previous_summary_hash": "sha256:...",
  "restored_context_hash": "sha256:...",
  "restored_context_sections": ["active_file", "diagnostics", "latest_build", "recent_files"],
  "source_message_count": 188,
  "source_token_estimate": 64000,
  "remaining_message_count": 14,
  "protected_tail_messages": 8,
  "micro_compacted_tool_results": 3,
  "covered_message_range": {
    "start_message_seq": 120,
    "end_message_seq": 188
  },
  "tail_start_message_seq": 181,
  "rejected_summary": false
}
```

兼容策略：

- 新 transcript message events 可以在 `metadata` 中写入 `message_id` 和 `message_seq`；`SessionResumeBuilder` 必须继续把 `metadata` 从 model history 中移除，避免协议字段进入模型。
- 旧 transcript 没有 `message_seq` 时，`covered_message_range` 和 `tail_start_message_seq` 可以缺省。
- `checkpoint_id` 和 hashes 即使在旧 transcript 上也可以从当前 checkpoint 生成。

### Transcript 写入顺序

为了让 `/resume` 能恢复 restored context，`xcode.v3` 建议写入顺序为：

```text
message(system): Compact boundary
message(system): Conversation summary checkpoint
event: compaction_checkpoint
message(system): Compact restored context
```

原因是当前 `/resume` 以最新 `compaction_checkpoint` event 为边界，只读取 event 之后的 message events。把 restored context message 写在 event 后面，可以让旧的 post-checkpoint 读取模型自然保留它。

`SessionResumeBuilder` 对 `xcode.v3` 还应重建 boundary message，然后使用 checkpoint summary 和 event 后的 restored-context message。旧 `xcode.v1/v2` 继续按现有规则恢复。

### 累计 Summary 更新

当前 `xcode.v2` 已经把 `previous_summary + new content` 交给模型生成累计 summary。`xcode.v3` 保留该行为，但要补两点：

- summary prompt 的 new content 应过滤旧 checkpoint/restored-context system messages，避免把恢复附件反复总结进去；
- checkpoint metadata 应记录 parent/hash，让“累计文本”也有可审计链路。

### 安全和隐私

- restored context 不记录环境变量值、Authorization header、QQ access token、MCP secret、完整 shell 命令输出中的明显 secret。
- `run_shell` output excerpt 进入 restored context 前应复用或新增 redaction helper，至少处理 `Authorization: Bearer ...`、`client_secret=...`、`access_token=...`、`api_key=...` 等常见模式。
- QQchat external state 独立；远程入口不得看到本地 REPL work state。
- restored context 是 system message，不是 tool result；不能包含未配对 tool protocol 字段。

## 测试要求

### P0 自动化回归

- `tests/test_work_state.py`
  - `read_file` tool result 记录 path、hash、line range 和 excerpt。
  - `edit_file` / `write_file` 只记录 path/hash，不记录写入正文。
  - `run_shell` 识别 build failure diagnostics。
  - `run_shell` 识别 failed pytest test name。
  - secret redaction 生效。
  - restored context 超预算时按优先级裁剪。
- `tests/test_agent_tool_loop.py`
  - 本地 tool loop 会更新 `AgentRuntime.work_state`。
  - 工具结果 message 内容不因 work state 记录而改变。
- `tests/test_external_turn.py`
  - 不同 QQ conversation 的 work state 隔离。
  - QQ external state 不复用本地 REPL work state。
- `tests/test_context.py`
  - compact 成功时 restored context message 插入 checkpoint 后、tail 前。
  - restored context 为空时不插入 message。
  - summary 失败时不插入 restored context。
  - 旧 checkpoint/restored-context system messages 不进入 new-content summary 请求。
- `tests/test_compaction.py`
  - `write_checkpoint()` 写 `summary_format=xcode.v3`、checkpoint id、parent id、hash 和 restored context metadata。
  - v3 写入顺序满足 resume 边界。
- `tests/test_session_resume.py`
  - v3 checkpoint resume 后包含 boundary、summary 和 restored context。
  - v1/v2 checkpoint resume 兼容。
  - message metadata 中的 message id/seq 不进入 model history。

### 建议验证命令

```powershell
python -m compileall -q src
pytest tests/test_work_state.py tests/test_agent_tool_loop.py tests/test_external_turn.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q
pytest -q
git diff --check
```

### 手工验收

- PowerShell/cmd.exe 原生 PTY：构造读文件、构建失败、测试失败、计划中的长会话，触发 `/compact`，检查模型继续回答时能引用 restored context。
- `/resume`：恢复 v3 checkpoint session，确认 summary 和 restored context 同时进入恢复后的 `_history`。
- QQchat：同一 QQ conversation compact 后能继续当前现场；不同 QQ conversation 和本地 REPL 不共享 restored context。
- Transcript inspection：检查 `checkpoint_id`、`parent_checkpoint_id`、hash 和可选 `covered_message_range` 链路。

## 被拒绝的方案

### 只增强 summary prompt

成本低，但仍然依赖模型自己记住文件、诊断和计划。长任务多次 compact 后，具体行号、hash、failed test name 仍容易漂移。

### compact 时重新扫描整个 transcript

可以从历史中提取现场，但会把 compact 本身变成复杂、昂贵、脆弱的历史解析器。更好的边界是在工具执行时记录结构化状态，compact 只读取 snapshot。

### 把完整最近文件全文写入 checkpoint

短期效果强，但 token 成本不可控，也容易把 secret、生成产物或大日志塞回模型。第一版只保留 bounded excerpt 和 hash。

### 引入向量库或文件索引

超出当前 compact 可靠性增强的范围，也会引入新的持久化、权限和性能问题。本项目当前阶段应保持小步、可审计、同步主循环。

## 完成标准

该设计实现完成后，必须同时满足：

1. compact 后 `_history` 中存在 bounded restored context system message，且 OpenAI-compatible message 顺序合法。
2. 多次 compact 的 summary 仍是累计更新，并且 checkpoint metadata 能形成 parent/hash 链。
3. `/resume` 能恢复 `xcode.v3` 的 summary + restored context。
4. 本地 REPL 和 QQchat external conversation 的 work state 隔离。
5. 自动化回归和原生 Windows PTY 验收记录先于“完成”结论。
