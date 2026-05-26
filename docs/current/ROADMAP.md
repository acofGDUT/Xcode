# Xcode 路线图

> 本文档只写目标态、未来计划和未完成能力的具体实现设想。已完成内容只保留状态，不再复述完整实现过程；当前真实实现见 `ARCHITECTURE.md`，历史过程见 `PROGRESS.md`。

## 1. 当前状态

Xcode v0.1.0 已完成 Phase 1-4 和 Phase 4.5 Batch 1-2 的稳定化工作。

已具备：

- 13 个工具：文件、搜索、shell、子 Agent、任务、计划模式。
- OpenAI-compatible streaming + tool calling。
- Plan mode、task tracker、sub-agent dispatch。
- 三层权限系统：session > project > global。
- 内联审批菜单：Yes / No / Yes for this conversation。
- 文件驱动 memory 模型：Project/User XCODE.md + auto memory index。
- Context token 估算和自动压缩，`max_tokens` 可配置。
- `/context`、`/env max-tokens`、syntax theme、工具结果语义化显示。
- Phase 4.5 memory/path/context 测试基线。
- 对话历史恢复基础能力：`/compact`、`/resume`、UUID transcript、checkpoint + recent tail 恢复。

Phase 5 生态扩展当前冻结，不作为近期默认开发目标。

## 2. 近期优先级

| 优先级 | 能力 | 状态 | 目标 |
|--------|------|------|------|
| P0 | 对话历史恢复 | 基础完成 | 已支持 `/compact` + `/resume`，基于 checkpoint + recent tail 恢复可继续推理的 history；后续只保留体验增强和 CLI 入口延后 |
| P0 | 原生 Windows E2E 验收 | 未完成 | 在 cmd.exe/PowerShell 验证真实交互链路 |
| P1 | `/context` cost 估算 | 未实现 | 在 token 统计外展示近似费用 |
| P1 | 工具调用 UI 折叠 | 未实现 | 连续工具调用默认合并为摘要，`Ctrl+O` 展开完整参数 |
| P1 | 工具调用轮次不中断 | 待调查 | 避免 Xcode 因多轮 tool_calls 停在中间状态 |
| P1 | 对话回退/分叉设计 | 未实现 | 提供非破坏性的 fork-based rollback |
| P2 | 项目级配置合并 | 部分实现 | 让 `.xcode/settings.json` 覆盖更多 Config 字段 |
| P2 | 渲染模式完善 | 部分实现 | 明确 streaming/buffer 模式的用户配置和验收 |

## 3. P0：对话历史恢复

### 当前状态

基础能力已完成：

- session id 使用 UUID。
- 完整 transcript 写入 `~/.xcode/projects/<project-key>/sessions/<uuid>.jsonl`。
- 轻量用户输入历史写入 `~/.xcode/history.jsonl`。
- runtime status 写入 `~/.xcode/sessions/<pid>.json`，进程退出时删除。
- `/compact` 和自动 context compression 会写入 `message(system)` + `compaction_checkpoint`。
- `/resume` 使用最新 checkpoint summary + checkpoint 之后的 recent tail 恢复 `_history`；无 checkpoint 时使用 tail-only fallback。
- 恢复时按 token budget 裁剪，并保护 assistant `tool_calls` / tool result pair。

当前不做 CLI `--resume <session_id>`、`xcode chat --resume <session_id>` 和 `--continue`。这些入口保留为后续如有明确需求再设计。

### 目标

让用户退出 CLI 后可以恢复指定历史会话，并继续一个在 token 预算内可推理的上下文。

推荐入口：

```text
/compact
/resume
```

CLI `--resume <session_id>` 和 `xcode chat --resume <session_id>` 暂不作为当前收口目标，可留到后续如果确有命令行启动恢复需求时再设计；`--continue` 也暂不做。

### 已解决的问题

旧版 `SessionStore` 只写简化 user / assistant 文本：

```json
{"role": "user|assistant", "content": "...", "ts": "..."}
```

但 `_run_llm_loop()` 内部真正需要继续推理的是完整 `history`，其中可能包含 assistant `tool_calls`、tool result、system compression summary 等结构。当前实现已改为结构化 transcript event，并在 context compression 发生时持久化可恢复 checkpoint。

另一个关键问题是大 transcript：恢复时不能把整个 JSONL 全量塞回 `_history`，否则会直接超过 token 预算。当前实现通过 `SessionResumeBuilder` 使用 checkpoint + recent tail 或 tail-only fallback 构造预算内 history。

### 已采用的实现模型

分两步做：

1. **Step 1：Session persistence foundation**
   - 使用 UUID session id 和 project-key。
   - 完整 transcript 写入 `~/.xcode/projects/<project-key>/sessions/<uuid>.jsonl`。
   - `~/.xcode/history.jsonl` 只存轻量用户输入历史。
   - `~/.xcode/sessions/<pid>.json` 只表示当前活跃进程，退出时删除。
   - `/resume` 先跑通当前项目 session 列表和小 transcript 恢复。

2. **Step 2：Compaction checkpoint + budgeted resume**
   - context compression 或用户手动 `/compact` 发生时写入 `compaction_checkpoint` event。
   - checkpoint summary 必须是累积摘要，避免多次压缩后早期上下文丢失。
   - `/compact` 压缩“上次 checkpoint 之后到当前”的增量消息，但新 checkpoint summary 必须合并旧 summary。
   - `/resume` 优先恢复最新 checkpoint summary + checkpoint 之后的 recent tail。
   - 无 checkpoint 时按 token budget 只恢复 recent tail，并给出清晰提示。
   - 恢复后 `_history` 必须保持 OpenAI-compatible message 顺序，特别是 tool_calls / tool result pair。

### 已修改文件

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/session.py` | UUID session、project-key、transcript event、history.jsonl、session listing |
| `src/xcode_cli/core/runtime_status.py` | 管理 `<pid>.json` 的 create/update/delete |
| `src/xcode_cli/core/session_resume.py` | 负责 checkpoint + token budget 的恢复构造 |
| `src/xcode_cli/core/context.py` | compression 结果暴露 summary/checkpoint 信息 |
| `src/xcode_cli/core/agent.py` | 接入 transcript 写入、runtime status、`/resume`、`self._session_id` |
| `src/xcode_cli/main.py` | 当前不改 CLI resume；后续如有明确需求再设计 |
| `tests/` | 增加 session、runtime status、resume builder、tool_calls、大 transcript 测试 |

### 基础验收标准

- `pytest` 覆盖 session 读取、runtime status、checkpoint 和 budgeted resume。
- 手工创建 session JSONL 后，`/resume` 能把可继续工作的历史注入 `_history`。
- 大 transcript 不会被全量加载到 `_history`。
- 有 checkpoint 时优先恢复 checkpoint summary + recent tail。
- 无 checkpoint 时恢复 recent tail，并提示没有压缩 checkpoint。
- 恢复失败时给出可读错误，不崩溃。

### 后续增强

- `/compact` 调用 LLM 压缩时显示进度或动态状态，避免用户干等。
- `/resume` 从数字输入改为方向键上下选择 + Enter 确认，并保留非 TTY fallback。
- 如后续确有命令行恢复需求，再设计 CLI `--resume <session_id>` / `xcode chat --resume <session_id>`。

## 4. P1：对话回退和分叉

### 目标

支持用户回到某一轮对话继续，但不破坏原始 session 日志。

推荐模型：fork-based rollback。

```text
原 session 保持 append-only
选择 turn N
创建新 session_id
复制 turn N 之前的可恢复 history
后续对话写入新 session
```

### 推荐命令

```text
/session history
/session fork <turn>
/session rollback <turn>
```

其中 `/session rollback <turn>` 可以作为 `/session fork <turn>` 的用户友好别名，内部仍创建新 session。

### 关键设计问题

- turn 的定义建议先采用 user/assistant pair，不按每条 tool message 暴露给用户。
- 若当前只实现文本级恢复，则 rollback 只保证普通聊天上下文。
- 结构化 tool history 恢复应等 Batch B session schema 完成后再做。

## 5. P1：`/context` cost 估算

### 目标

在 `/context` 中展示当前上下文近似费用，而不是只展示 token。

### 推荐设计

在 `Config` 中加入可选价格字段，保留默认模型价格表：

```python
pricing_model: str = ""
input_cost_per_1m: float | None = None
output_cost_per_1m: float | None = None
```

短期更保守的方案：不持久化价格配置，只在 `context.py` 或新模块中维护一个小型价格表，并在未知模型时展示 `cost: unknown`。

### 建议修改文件

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/context.py` | 增加 cost 估算 helper |
| `src/xcode_cli/core/config.py` | 如需要，增加 pricing 配置 |
| `src/xcode_cli/core/agent.py` | `/context` table 增加 cost 行 |
| `tests/test_context.py` | 覆盖已知模型、未知模型、非 ASCII token 估算 |

### 验收标准

- 未知模型不报错。
- 已知模型显示 input/output/total 近似费用。
- 文案明确是 estimate，避免被用户理解为账单。

## 6. P0：原生 Windows E2E 验收

### 目标

在 cmd.exe 或 PowerShell 中跑一次真实 `xcode chat`，验证 prompt_toolkit、审批菜单、diff preview、streaming/rendering、slash command 都能工作。

### 验收清单

- 启动 `xcode chat` 不出现 `NoConsoleScreenBufferError`。
- `/help`、`/context`、`/env show` 可用。
- 触发 `write_file` 或 `edit_file` 时 diff 在审批期间保持可见。
- 方向键上下 + Enter 可选择审批项。
- `y/n/a` 快捷键仍可用。
- 拒绝工具调用不会让主循环崩溃。
- `Yes, for this conversation` 只影响当前会话。

### 记录位置

验收结果写入：

- `docs/current/PROGRESS.md`
- `docs/current/DEVNOTES.md`
- 如涉及 Phase 4，可同步 `PHASE4_ACCEPTANCE.md`

## 7. P1：工具调用 UI 折叠与展开

### 背景

当前 `_render_tool_call()` 会把每个工具调用的 name 和完整 args 持续向下打印。连续读取、搜索和编辑时，终端会快速被工具调用详情刷屏，用户真正需要看的 assistant 输出、diff 和审批信息会被推远。

期望体验接近 Claude Code：

```text
3 tools: read_file, grep, glob
```

默认只显示一行摘要。用户按 `Ctrl+O` 后，再展开看到每个工具的完整参数：

```text
## tool.read_file
  path: D:\Xcode\src\xcode_cli\core\agent.py
  limit: 25
  offset: 550

## tool.grep
  pattern: _render_tool_call
  path: D:\Xcode\src
```

### 推荐设计

引入“工具调用显示状态”：

- 默认折叠连续工具调用，只展示数量和工具名摘要。
- `Ctrl+O` 在当前会话内切换 collapsed / expanded。
- expanded 时保留当前详细参数格式。
- diff preview、审批菜单、工具结果摘要不应被折叠掉。
- 如果一次工具调用包含危险操作，例如 `write_file`、`edit_file`、`run_shell`，摘要必须显式标出危险工具名。

### 建议修改文件

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/agent.py` | 重构 `_render_tool_call()`，增加 tool-call display state 和 `Ctrl+O` key binding |
| `src/xcode_cli/ui/renderer.py` | 如有必要，增加工具摘要/详情渲染 helper |
| `tests/` | 增加工具调用摘要格式和展开状态的单元测试 |

### 验收标准

- 连续 3 个只读工具调用默认只产生一行摘要。
- 按 `Ctrl+O` 后，同样的工具调用可以展示完整参数。
- `write_file` / `edit_file` 的 diff preview 和审批 UI 不被折叠隐藏。
- 非 TTY 环境下有稳定 fallback，不因快捷键能力缺失崩溃。
- 原生 PowerShell/cmd.exe 下验证 `Ctrl+O` 不影响 prompt 输入和审批菜单。

## 8. P1：工具调用轮次不中断

### 背景

实际使用中观察到 Xcode 可能因为工具调用轮次停下来：模型发起 tool_calls 后，工具结果没有顺畅推动下一轮 LLM 推理，或者 UI/状态让用户误以为 Agent 卡住。

这类问题优先级高于纯 UI 美化，因为它会直接中断 Agent 完成任务的能力。

### 调查方向

重点检查 `_run_llm_loop()`：

- tool_calls 是否都被合并为一条 assistant message。
- 每个 tool result 是否都带正确 `tool_call_id`。
- 多轮 tool_calls 后是否继续调用 `llm.complete()`。
- 被拒绝、权限 denied、工具异常时，是否仍向模型返回可理解的 tool result。
- `KeyboardInterrupt`、streaming final render、context compression 是否可能提前 `return final_text`。
- 是否存在最大工具轮次限制、空 content、空 tool_calls 等边界没有清楚提示。

### 推荐修复方向

- 给 `_run_llm_loop()` 增加明确的 tool round counter 和 debug/status 提示。
- 对每轮 tool call 都记录：round number、tool count、执行结果数量、是否继续下一轮。
- 当模型返回空文本且无 tool_calls 时，输出可读 fallback，而不是静默停住。
- 如果达到最大工具轮次，明确告诉用户并保留 history，不要像卡死一样停在中间。

### 验收标准

- 构造一个两轮工具调用的 fake LLM 测试，验证第二轮会继续执行。
- 工具被拒绝时，模型能收到拒绝结果并继续生成最终回复。
- 工具异常时，主循环不崩溃，并能继续下一轮或给出最终说明。
- 真实运行中连续 read/grep/read 后不会无提示停住。

## 9. P2：项目级配置合并

### 目标

让项目 `.xcode/settings.json` 不只服务权限规则，也能覆盖部分 Config 字段。

### 当前状态

`PermissionManager` 已读取 project/global settings 的 permissions。`ConfigStore.load()` 仍主要读取 `~/.xcode/config.json`，没有通用项目级 merge。

### 推荐边界

允许项目级覆盖：

- `model`
- `base_url`
- `max_tokens`
- `syntax_theme`
- `response_render_mode`

不建议项目级覆盖：

- `api_key`
- 用户级隐私偏好

## 10. P2：渲染模式完善

### 当前状态

`Config.response_render_mode` 支持：

- `streaming_plus_final_render`
- `buffer_then_render`

默认值和历史配置兼容逻辑仍需进一步整理和文档化。

### 目标

明确三类体验：

| 模式 | 目标 |
|------|------|
| streaming plain | 最快反馈 |
| streaming + final render | 兼顾即时反馈和最终 Markdown |
| buffer then render | 最稳定美观 |

当前代码只覆盖后两者，是否补第一种应根据实际体验决定。

## 11. Phase 5：生态扩展候选

Phase 5 当前冻结。后续如果解冻，建议逐项设计和验收，不一次性铺开。

候选能力：

| Task | 能力 | 备注 |
|------|------|------|
| 5.1 | WebFetch | 需考虑网络权限、安全和缓存 |
| 5.2 | WebSearch | 需考虑 provider 抽象和引用展示 |
| 5.3 | Cron/automation | 应先明确本地线程、系统计划任务还是外部调度 |
| 5.4 | Git tools | 需强权限边界，避免误操作 |
| 5.5 | Hooks | 需定义触发点、失败策略和用户可见性 |
| 5.6 | Project config | 可先完成 P2 配置合并 |
