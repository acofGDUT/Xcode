# 对话历史恢复任务手册

Date: 2026-05-25
Project: Xcode
Owner role: Coding Agent implementation brief
Reviewer role: Codex architecture/review agent

Status: completed - basic functionality accepted

Reference:
- `docs/reference/claude-code-compaction-mechanism.md`
- `docs/current/ROADMAP.md`
- `src/xcode_cli/core/session.py`
- `src/xcode_cli/core/context.py`
- `src/xcode_cli/core/agent.py`

## 1. 目标

本任务实现 Xcode 第一版“可继续工作的对话恢复”能力。

目标不是做完整会话管理系统，而是先建立两个基础：

1. **会话持久化基础设施**
   - 完整 transcript 按 session UUID 写入项目目录。
   - 轻量用户输入历史写入 `~/.xcode/history.jsonl`。
   - 当前运行中的 Xcode 进程写入临时 runtime status 文件。
   - `/resume` 可以列出当前项目历史会话并恢复指定 session。

2. **压缩 checkpoint + 大会话恢复机制**
   - context compression 或用户手动 `/compact` 发生时，把可恢复摘要作为 checkpoint 写入 transcript。
   - `/resume` 不应把超大 transcript 全量塞回 `_history`。
   - 恢复时优先使用最新 compaction checkpoint，再补充 checkpoint 之后的 recent tail。
   - 如果没有 checkpoint，则按 token 预算从 transcript 尾部恢复。

本任务不实现 rollback/fork，不实现跨项目 resume，不实现全文搜索，不实现 `--continue`，不实现图形化 TUI。

## 2. 关键语义

### 2.1 `/resume` 恢复的不是“全量历史上下文”

完整 transcript 永久保留在磁盘，但 LLM 上下文有 token 限制。

因此 `/resume` 的产品语义应明确为：

```text
恢复一个在 token 预算内、可继续工作的上下文。
```

不要在 UI 或文档中暗示“整个历史会话已完整放回模型上下文”。

### 2.2 transcript 和 LLM history 是两种东西

`transcript`：
- append-only 永久日志。
- 记录 user、assistant、tool、system summary、compaction checkpoint 等事件。
- 可很大，不能假设能一次性全部进入模型。

`AgentRuntime._history`：
- 当前要传给 `LLMClient.complete()` 的 OpenAI-compatible messages。
- 必须受 token 预算约束。
- `/resume` 时由 transcript 重新构造，但不等于 transcript 全量内容。

### 2.3 压缩摘要必须是“累积摘要”

参考 Claude Code 行为时要注意一个坑：如果每次压缩只总结“上次压缩之后的增量内容”，那么多次压缩后 `/resume` 只读最后 checkpoint 会丢失早期摘要。

Xcode 第一版应要求每次 compression summary 都是累积摘要。无论是自动 context compression，还是用户手动 `/compact`，都遵循同一个规则：

```text
新的 summary = 旧 summary/checkpoint + 本次被压缩的消息 + 当前关键状态 的综合摘要
```

这样 `/resume` 只读取最新 checkpoint，也能保留早期关键决策、约束、文件、问题、下一步。

## 3. 存储模型

### 3.1 完整 transcript

位置：

```text
~/.xcode/projects/<project-key>/sessions/<session-uuid>.jsonl
```

`project-key` 必须从项目绝对路径稳定生成。

建议规则：

```text
D:\Xcode -> D--Xcode
D:\Work\Xcode -> D--Work--Xcode
```

要求：
- 不要只用 `cwd.name`，避免不同目录同名项目冲突。
- project-key 只能包含文件系统安全字符。
- project-key 生成逻辑必须有单元测试。
- session id 使用 UUID，不再使用 timestamp。

第一版至少支持这些 transcript event：

```json
{"type":"message","role":"user","content":"...","ts":"..."}
{"type":"message","role":"assistant","content":"...","reasoning_content":"...","tool_calls":[...],"ts":"..."}
{"type":"message","role":"tool","tool_call_id":"call_123","content":"...","ts":"..."}
{"type":"message","role":"system","content":"Conversation summary: ...","ts":"..."}
{"type":"compaction_checkpoint","summary":"...","summary_format":"xcode.v1","source_message_count":120,"ts":"..."}
```

说明：
- `message` event 用于重建 OpenAI-compatible history。
- `compaction_checkpoint` event 用于大 transcript 快速恢复。
- assistant `tool_calls` 必须保持 OpenAI-compatible shape。
- tool result 必须保留 `tool_call_id`。

### 3.2 轻量用户输入历史

位置：

```text
~/.xcode/history.jsonl
```

用途：
- 快速检索用户输入。
- 给 `/resume` 展示 session 最近活动和摘要线索。
- 后续可接入方向键历史增强。

每次用户输入普通消息时追加一行：

```json
{
  "display": "用户原始输入",
  "timestamp": 1779447643035,
  "project": "D:\\Xcode",
  "sessionId": "session-uuid"
}
```

要求：
- slash command 默认不写入 history。
- `timestamp` 使用毫秒时间戳。
- history 只做轻量索引，不用于重建 LLM history。

### 3.3 runtime status

位置：

```text
~/.xcode/sessions/<pid>.json
```

启动时创建：

```json
{
  "pid": 220512,
  "sessionId": "session-uuid",
  "cwd": "D:\\Xcode",
  "status": "idle",
  "updatedAt": 1779717903772
}
```

运行中更新：
- 等待用户输入时：`status = "idle"`。
- LLM 推理、工具执行、context compression 时：`status = "busy"`。
- 每次状态变化更新 `updatedAt`。

退出时：
- 删除 `~/.xcode/sessions/<pid>.json`。

要求：
- 正常 `/exit`、`exit`、`quit` 应删除。
- KeyboardInterrupt 或异常退出可先不保证删除，但实现应尽量用 `try/finally`。
- runtime status 不是 resume 的历史来源。

## 4. 压缩 checkpoint 设计

### 4.1 当前问题

当前 `ContextManager.compress()` 只返回压缩后的 messages：

```python
compressed = self.context.compress(history, self.llm)
history[:] = compressed
```

这会让运行时上下文变小，但 session transcript 里没有可靠的“最新可恢复摘要 checkpoint”。如果一个 session 很大，`/resume` 只能在两个坏选择中二选一：

- 全量加载 transcript 到 `_history`，可能超 token。
- 只加载尾部，早期关键决策可能丢失。

因此需要把 compression 结果持久化为 checkpoint。

### 4.2 `/compact` 手动压缩命令

本任务应显式增加交互内 slash command：

```text
/compact
```

`/compact` 的语义：

1. 找到当前 `_history` 中上一次 compaction checkpoint 对应的 summary。
2. 取“上一次 checkpoint 之后到当前最新消息”的增量消息。
3. 调用 LLM 生成新的累积 summary。
4. 将 `_history` 替换为：
   - 最新累积 summary message
   - 必要的 recent tail
5. 向 transcript 追加：
   - `message(system)`：压缩后注入 `_history` 的 summary message
   - `compaction_checkpoint`：结构化 checkpoint event

关键约束：
- `/compact` 不压缩整个永久 transcript，也不删除 transcript 中的旧消息。
- `/compact` 压缩的是“从上次 checkpoint 到当前”的增量消息，但生成结果必须合并旧 checkpoint summary，成为新的累积 checkpoint。
- 如果当前没有 checkpoint，则把当前可压缩的历史作为第一段 summary 来源。
- 如果当前消息太少，不值得压缩，应提示 `Nothing to compact`，不要写空 checkpoint。
- `/compact` 失败不应污染 `_history`；只有 LLM summary 成功并写 transcript 成功后，才替换运行时 history。

### 4.3 建议改造

建议在 `src/xcode_cli/core/context.py` 中新增结果对象：

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class CompressionResult:
    messages: list[dict[str, Any]]
    summary: str
    checkpoint_message: dict[str, Any]
```

`ContextManager.compress()` 可以改为返回 `CompressionResult`，或新增 `compress_with_checkpoint()`，避免一次改动太大。

`checkpoint_message` 建议使用 OpenAI-compatible system message：

```python
{
    "role": "system",
    "content": "Conversation summary checkpoint:\n..."
}
```

transcript 中另外写入结构化 event：

```json
{
  "type": "compaction_checkpoint",
  "summary": "...",
  "summary_format": "xcode.v1",
  "source_message_count": 120,
  "source_token_estimate": 180000,
  "remaining_message_count": 9,
  "ts": "..."
}
```

### 4.4 摘要格式

summary prompt 应要求输出结构化摘要，至少包含：

```text
Primary request:
Key decisions:
Current architecture/state:
Files touched or relevant:
User preferences and constraints:
Tool results and errors:
Open problems:
Current work:
Next step:
```

要求：
- prompt 使用英文，与现有英文 system prompt 保持一致。
- 摘要内容可以保留用户原语言。
- 新摘要必须整合旧 checkpoint summary，不能只总结本轮增量。
- 压缩摘要不要保存 secret、API key、token 等敏感信息。
- summary 长度控制必须作为 compaction 层的策略，而不是写死在 `agent.py` 主循环中。
- 第一版允许设置默认上限，例如 `max_summary_chars=6000`，但该上限必须可配置、可关闭。
- 当 `max_summary_chars` 为 `None` 或 `0` 时，不做代码层截断，只依赖 LLM prompt 控制摘要长度。
- 如果启用截断，`CompressionResult.summary` 和 `checkpoint_message["content"]` 必须使用同一个截断后的 summary。

### 4.5 压缩发生时要写 transcript

`_run_llm_loop()` 中自动 context compression 成功后，或 `/compact` 手动压缩成功后，必须写入：

1. `message` event：压缩后注入 `_history` 的 system summary message。
2. `compaction_checkpoint` event：结构化 checkpoint 元数据。

注意：
- 不要把被压缩掉的旧消息从 transcript 删除。
- transcript 是完整历史，压缩只改变运行时 `_history`。
- 写 checkpoint 失败不应让 Agent 主循环崩溃，但必须给出可见 warning。
- 自动 compression 和 `/compact` 应复用同一套 checkpoint 生成逻辑，避免两套摘要语义分叉。

## 5. 恢复策略

### 5.1 `/resume` 交互入口

本任务主要入口是交互内 slash command：

```text
/resume
```

用户输入 `/resume` 后：

1. 读取当前项目 session transcript 列表。
2. 结合 `~/.xcode/history.jsonl` 找到每个 session 最近的用户输入。
3. 展示可恢复会话列表。
4. 用户选择一个 session。
5. 使用 `SessionResumeBuilder` 从 transcript 构造 budgeted history。
6. 当前运行中的 sessionId 切换到 selected session。
7. runtime status 中的 sessionId 更新。
8. 后续新消息继续追加到该 transcript。

第一版选择方式可以简单，不要求完整 TUI：

```text
Recent sessions:
1. 9c462299...  2026-05-25 16:20  最近输入...
2. 2a9da52c...  2026-05-25 15:10  最近输入...

Select session number, or empty to cancel:
```

### 5.2 大 transcript 恢复算法

建议新增 `SessionResumeBuilder`，可以放在：

```text
src/xcode_cli/core/session.py
```

如果 `session.py` 变大，则新建：

```text
src/xcode_cli/core/session_resume.py
```

建议 API：

```python
class SessionResumeBuilder:
    def __init__(self, context: ContextManager, token_budget: int) -> None: ...
    def build(self, transcript_path: Path) -> ResumeResult: ...
```

`ResumeResult` 至少包含：

```python
history: list[dict[str, Any]]
message_count: int
restored_from_checkpoint: bool
checkpoint_summary_chars: int
tail_message_count: int
estimated_tokens: int
```

恢复算法：

1. 流式读取 transcript，不要求一次性把全部 event 放进内存。
2. 找到最后一个 `compaction_checkpoint`。
3. 如果存在 checkpoint：
   - 先构造一个 system summary message。
   - 再追加 checkpoint 之后的 message events。
   - 如果超出 token budget，从 tail 端保留最近消息，summary message 始终保留。
4. 如果不存在 checkpoint：
   - 从 transcript 尾部按 token budget 恢复最近 message events。
   - UI 提示“未找到压缩 checkpoint，仅恢复最近上下文”。
5. 恢复出的 history 必须保持 OpenAI-compatible message 顺序。
6. assistant `tool_calls` 和后续 tool messages 必须成对保留；如果 tail 裁剪会破坏 pair，优先丢弃不完整 pair。

### 5.3 token budget

建议第一版使用：

```text
resume_budget = int(Config.max_tokens * 0.6)
```

理由：
- 给 system prompt、memory、下一轮用户输入、模型输出预留空间。
- 避免一恢复就立刻触发 compression。

如果实现成本更低，也可以使用：

```text
resume_budget = int(ContextManager.max_tokens * 0.7)
```

但必须写测试覆盖“超大 transcript 恢复后 estimated_tokens 不超过预算”。

### 5.4 恢复后的提示文案

成功恢复时建议输出：

```text
Resumed session 9c462299...
Restored from checkpoint: yes
Restored messages: 18
Estimated context: ~42000 tokens
Latest user input: ...
```

如果没有 checkpoint：

```text
Resumed recent context only: no compaction checkpoint was found.
```

不要输出“完整恢复全部历史”这类误导文案。

## 6. 批次拆分

### Step 1: Session persistence foundation

目标：先把 session 存储、runtime status、结构化 transcript 和 `/resume` 基础交互打通。

涉及文件：
- `src/xcode_cli/core/session.py`
- `src/xcode_cli/core/runtime_status.py`（建议新建）
- `src/xcode_cli/core/agent.py`
- `src/xcode_cli/paths.py`
- `tests/test_session.py`
- `tests/test_runtime_status.py`
- `tests/test_agent_resume_command.py`

要求实现：
1. `SessionStore` 使用 UUID session id。
2. 实现 project-key。
3. transcript 写入到 `~/.xcode/projects/<project-key>/sessions/<uuid>.jsonl`。
4. 支持 append `message` event。
5. 支持 `history.jsonl` 轻量用户输入历史。
6. 支持 `list_sessions()`。
7. 支持 runtime status create/update/delete。
8. `AgentRuntime` 使用 `self._session_id`，不要再只用局部变量。
9. `_run_llm_loop()` 写入 assistant tool_calls 和 tool result。
10. `/resume` 能列出 session，并恢复小 transcript 的合法 history。

建议 API：

```python
class SessionStore:
    def __init__(self, cwd: str | None = None) -> None: ...
    def new_session_id(self) -> str: ...
    def project_key(self) -> str: ...
    def transcript_path(self, session_id: str) -> Path: ...
    def append_event(self, session_id: str, event: dict) -> None: ...
    def append_message(self, session_id: str, message: dict) -> None: ...
    def append_user_history(self, session_id: str, display: str) -> None: ...
    def list_sessions(self) -> list[SessionInfo]: ...
    def load_history(self, session_id: str) -> list[dict]: ...
```

`SessionInfo` 至少包含：

```python
session_id: str
path: Path
updated_at: float
last_user_input: str
message_count: int
has_checkpoint: bool
```

验收：
- `pytest tests/test_session.py tests/test_runtime_status.py`
- project-key 对 Windows 路径稳定。
- transcript 可写可读。
- assistant tool_calls / tool message 可恢复。
- runtime status 退出删除。
- `/resume` 无 session、取消、非法选择、成功恢复都有测试。

### Step 2: Compaction checkpoint and budgeted resume

目标：让大 session 的 `/resume` 安全可用，不全量塞回上下文。

涉及文件：
- `src/xcode_cli/core/context.py`
- `src/xcode_cli/core/session.py`
- `src/xcode_cli/core/session_resume.py`（建议新建）
- `src/xcode_cli/core/agent.py`
- `tests/test_context.py`
- `tests/test_session_resume.py`
- `tests/test_agent_session.py`

要求实现：
1. `ContextManager.compress()` 暴露 summary/checkpoint 信息。
2. compression summary 改为累积摘要。
3. compression 成功后写入 `compaction_checkpoint` event。
4. 新增 `/compact` slash command，手动触发同一套累积 checkpoint 逻辑。
5. 新增 `SessionResumeBuilder`。
6. `/resume` 使用 `SessionResumeBuilder`，而不是无条件 `load_history()` 全量加载。
7. 有 checkpoint 时恢复：summary checkpoint + checkpoint 之后的 recent tail。
8. 无 checkpoint 时恢复：token budget 内的 recent tail。
9. 恢复时保护 assistant tool_calls / tool result pair，不产生非法 message 顺序。
10. 恢复成功提示是否来自 checkpoint、恢复消息数量、估算 token。
11. summary 长度策略必须集中在 compaction 层，并支持关闭，避免后续调整摘要策略时修改 `agent.py`。

验收：
- 构造 500+ 条 transcript，`/resume` 后 `_history` token 不超过预算。
- 构造带 checkpoint 的 transcript，只读取最新 checkpoint + tail。
- 构造多次 checkpoint，确认最新 checkpoint 是累积摘要，不丢早期关键信息。
- 手动 `/compact` 会写入 `compaction_checkpoint`，且新 checkpoint 覆盖“旧 summary + 上次 checkpoint 后的消息”。
- 构造超长 summary，确认默认启用长度策略时会被限制。
- 构造关闭 summary 长度策略的场景，确认超长 summary 不会被代码层截断。
- 构造 tool_calls 被 tail 裁剪的场景，确认不会留下孤立 tool message。
- compression 发生后 transcript 中同时有 `message(system)` 和 `compaction_checkpoint`。

### Deferred: CLI `--resume`

当前不作为本轮 session resume 收口目标。

涉及文件：
- `src/xcode_cli/main.py`
- `src/xcode_cli/core/agent.py`
- `tests/test_main_resume.py`

后续如果确有从命令行直接恢复指定 session 的需求，再单独设计：
- `xcode --resume <session-id>`
- `xcode chat --resume <session-id>`

本轮只要求交互内 `/resume` 可用；不做 `--continue`。

## 7. Out of Scope

本任务不要做：
- rollback
- fork
- `--continue`
- CLI `--resume`
- 跨项目 resume
- session 全文搜索
- transcript 压缩或删除旧日志
- 自动清理历史 session
- 图形化 TUI
- Phase 5 生态扩展

## 8. 测试要求

必须新增或更新测试，至少覆盖：

- UUID session id。
- Windows path project-key。
- transcript 写入和读取。
- `history.jsonl` 轻量历史写入。
- runtime status create/update/delete。
- assistant tool_calls 和 tool result 持久化。
- context compression 产生 checkpoint。
- `/compact` 产生 checkpoint。
- checkpoint summary 是累积摘要。
- checkpoint summary 长度策略可配置、可关闭。
- 大 transcript budgeted resume。
- 无 checkpoint 的 tail-only fallback。
- tool_calls / tool result pair 裁剪安全。
- `/resume` 无 session、取消、非法选择、成功恢复。
- 恢复后新消息继续写入被恢复的 transcript。

推荐命令：

```powershell
pytest tests/test_session.py tests/test_runtime_status.py tests/test_session_resume.py tests/test_agent_resume_command.py
pytest
python -m py_compile src/xcode_cli/core/session.py src/xcode_cli/core/context.py src/xcode_cli/core/agent.py src/xcode_cli/main.py
```

## 9. 验收标准

当前基础功能已按本手册完成并进入项目文档。CLI `--resume` / `--continue`、`/compact` 进度反馈、`/resume` 方向键选择体验仍作为后续增强项，不属于本轮完成条件。

本任务完成必须满足：

1. `pytest` 全部通过。
2. 新 session 文件位于 `~/.xcode/projects/<project-key>/sessions/<uuid>.jsonl`。
3. `~/.xcode/history.jsonl` 会记录普通用户输入。
4. `~/.xcode/sessions/<pid>.json` 只在进程运行时存在，退出后删除。
5. `/resume` 能列出当前项目历史 session。
6. `/resume` 选择 session 后能恢复 budgeted `_history`。
7. 恢复后的下一轮问题能带着旧上下文继续进入 LLM。
8. 大 transcript 不会被全量塞进 `_history`。
9. 有 checkpoint 时优先恢复 checkpoint summary + recent tail。
10. 无 checkpoint 时有清晰 fallback 提示。
11. `/compact` 手动压缩后，transcript 中有新的 `compaction_checkpoint`。
12. 工具调用 transcript 恢复后仍保持 OpenAI-compatible message 顺序。
13. 文档同步更新：
    - `docs/current/ARCHITECTURE.md`
    - `docs/current/ROADMAP.md`
    - `docs/current/PROGRESS.md`
    - `docs/current/DEVNOTES.md`

## 10. Review 重点

Codex review 时会重点检查：

- 是否真的持久化了 tool_calls 和 tool result，而不是只存文本。
- `tool_call_id` 是否能对应上。
- transcript 恢复后的 history 是否可直接传给 `LLMClient.complete()`。
- 大 transcript 是否按预算恢复，而不是全量加载到 `_history`。
- checkpoint summary 是否是累积摘要。
- checkpoint summary 长度策略是否集中在 compaction 层，且是否能关闭。
- `/compact` 是否复用自动 compression 的 checkpoint 逻辑。
- 多次 compression 后是否只靠最新 checkpoint 也能保留早期关键上下文。
- runtime status 是否退出删除。
- `/resume` 是否会污染当前未保存消息。
- 旧 `~/.xcode/sessions/<timestamp>.jsonl` 是否有兼容策略或明确不兼容说明。
- 是否有测试覆盖 Windows 路径、多轮 tool_calls、大 transcript、无 checkpoint fallback。

## 11. 给 Coding Agent 的执行建议

先做 Step 1，把 session 存储和 `/resume` 基础链路跑通。这个阶段可以只验证小 transcript 的完整恢复，但代码结构要为 Step 2 预留 `SessionResumeBuilder`。

再做 Step 2，把 compression checkpoint 和 budgeted resume 接上。不要把“大 session 恢复”推给现有 `ContextManager.compress()` 临时处理，因为 `/resume` 应该是本地读取 checkpoint，不应该为了恢复历史额外调用 LLM。

本轮不要继续做 CLI `--resume`。当前收口目标是交互内 `/resume` 和 `/compact`，避免同时碰 Typer、PromptSession、history、runtime status 和 resume builder，review 面会过大。
