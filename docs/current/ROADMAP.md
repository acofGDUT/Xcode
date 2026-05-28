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
| P1 | 工具调用 UI 折叠 | 基础完成 | 默认已合并为工具摘要；后续补 `Ctrl+O` 展开和原生 Windows 热键验收 |
| P1 | 工具调用轮次不中断 | 基础完成 | 已支持多轮 tool loop 和关键回归测试；后续补真实终端验收与可选 round 状态提示 |
| P1 | memory 自管理权限 | 完成 | Xcode 管理 resolved memory 文件时不再频繁要求用户审核，普通文件仍保留审批 |
| P1 | 流式输出去重 | 基础收口完成 | 已避免结构化内容 raw + Rich 双重完整输出；后续再评估可替换区域式 streaming |
| P1 | AgentRuntime 重构 | 第一轮完成 | 已抽出 commands/slash、conversation、tooling、ui 基础模块；后续继续拆 command handlers |
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

## 6. P1：memory 自管理权限

### 目标

让 Xcode 在维护自己的 memory 文件时，不必每次都走和普通代码文件完全一样的用户审核流程。

### 设计边界

- 只针对 resolved memory 路径和明确标记的 memory 文件生效。
- 不影响普通项目文件、代码文件、配置文件的审批。
- 仍保留审计记录，避免“无声写入”。
- 不能依赖模型自己判断路径是否属于 memory，必须由代码侧校验。

### 当前实现

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/memory.py` | `is_memory_write_target()` 判断 resolved memory 写入目标 |
| `src/xcode_cli/core/agent.py` | 对 memory-scoped `write_file` / `edit_file` 跳过用户审批 |
| `tests/test_memory.py` | 覆盖 memory path membership |
| `tests/test_agent_memory_permissions.py` | 覆盖 memory 写入免审、普通文件仍审批、非法 memory-like path 不放行 |

### 验收标准

- 写 memory 文件时不再像普通代码文件那样频繁询问用户。
- 非 memory 文件仍保持现有审批行为。
- 路径拼错时不会误放行。

### 后续补充

- 建议补 explicit `deny` + memory path 回归测试，防止未来重排审批分支时误放行。

## 7. P0：原生 Windows E2E 验收

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

## 8. P1：流式输出去重

### 背景

当前基础问题已经收口：结构化内容场景不再出现完整 raw + 完整 Rich 的双重输出。但渲染模式的长期边界仍未完全定型，尤其是“即时反馈”和“最终美观渲染”的取舍。

### 目标

继续把当前的“基础可用”推进到“模式边界清晰、终端体验稳定”。

### 后续方向

- 对 `streaming_plus_final_render` 明确设计可替换区域，而不是普通逐行追加。
- 评估是否把 `buffer_then_render` 作为更稳的默认模式。
- 对代码块、表格、长列表和中断场景做更真实的终端验收，避免“去重后又静默”。

### 建议修改文件

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/agent.py` | 继续收口 streaming / final render orchestration |
| `src/xcode_cli/core/ui/streaming.py` | 如需要，承载可替换区域式 streaming 状态 |
| `src/xcode_cli/ui/renderer.py` | 如有必要增加可替换渲染 helper |

### 验收标准

- 同一轮 assistant 输出在真实终端里不再出现明显重复占屏。
- 流式输出与最终渲染的边界对用户是可解释的。
- Markdown / code block / table 不出现半成品和重复成品同时占屏。

## 9. P1：工具调用 UI 折叠与展开

### 背景

基础折叠已经完成，但还没有热键展开和原生 TTY 验收。

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

### 后续方向

- `Ctrl+O` 在当前会话内切换 collapsed / expanded。
- expanded 时保留当前详细参数格式。
- diff preview、审批菜单、工具结果摘要继续保持不被折叠。
- 原生 Windows 控制台下补热键和审批菜单并存验收。

### 建议修改文件

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/agent.py` | 如需要，接入 `Ctrl+O` key binding |
| `src/xcode_cli/core/tooling/display.py` | 继续增强摘要 / 展开状态 |
| `tests/` | 增加热键切换和终端行为回归测试 |

### 验收标准

- 连续只读工具调用默认保持一行摘要。
- 按 `Ctrl+O` 后，同样的工具调用可以展示完整参数。
- `write_file` / `edit_file` 的 diff preview 和审批 UI 不被折叠隐藏。
- 非 TTY 环境下有稳定 fallback，不因快捷键能力缺失崩溃。
- 原生 PowerShell/cmd.exe 下验证 `Ctrl+O` 不影响 prompt 输入和审批菜单。

## 10. P1：工具调用轮次不中断

### 背景

核心逻辑问题已经收口，但还缺少真实终端层面的补充验收与可视化状态反馈。

### 当前状态

- `_run_llm_loop()` 已改为 `while True`。
- 已补超过 10 轮、拒绝后继续、空响应 fallback、最终渲染补洞等回归测试。
- 重点回归测试已通过。

### 后续方向

- 评估是否给 `_run_llm_loop()` 增加可选 round/status 提示。
- 在原生 Windows 终端里做真实多轮工具链路验收。
- 继续覆盖 streaming、context compression、KeyboardInterrupt 等边界交互。

### 验收标准

- 真实运行中连续 read/grep/read 后不会无提示停住。
- 工具被拒绝或工具异常时，主循环仍能继续完成当前 turn。
- 原生终端场景下不会因为 streaming / UI 状态让用户误以为卡死。

## 11. P1：AgentRuntime 重构

### 目标

把现在过于集中的 `src/xcode_cli/core/agent.py` 拆成更容易 review 和维护的模块。

### 当前状态

第一轮已完成并推送：`fb18243 refactor: modularize agent runtime`。

已完成：

- `core/commands/slash.py`：slash command 列表和补全。
- `core/ui/shell.py`：welcome、命令建议、bottom toolbar、用户/助手基础输出。
- `core/conversation/resume.py`：`/resume` 命令编排。
- `core/conversation/compaction.py`：`/compact` 和自动 compression checkpoint 编排。
- `core/tooling/approval.py`：审批 scope、方向键菜单、TTY / non-TTY fallback。
- `core/tooling/execution.py`：tool call 执行、diff preview、memory auto-allow、工具结果摘要。
- 测试补齐：多轮 tool call、审批 controller、explicit `deny` + memory path。

未完成：

- `/env`、`/memory`、`/context`、`/plan` 等具体 command handlers 仍在 `agent.py`，后续可以继续拆到 `core/commands/`。
- `_run_llm_loop()` 的 streaming/render orchestration 仍在 `agent.py`，但状态判断已收口到 `core/ui/streaming.py`。
- 工具调用 UI 折叠已完成，`Ctrl+O` 展开未纳入当前交付。

### 推荐拆分方向

- slash command 解析和分发。
- session / resume / compaction 编排。
- tool call 执行与审批流程。
- streaming / render 状态。
- 主循环 orchestration。

### 约束

- 重构优先保持行为不变。
- 先保留测试，再做结构搬迁。
- 不要因为重构顺手改产品语义。

### 建议修改文件

| 文件 | 修改方向 |
|------|----------|
| `src/xcode_cli/core/agent.py` | 继续收缩 command handler glue |
| `src/xcode_cli/core/commands/*` | 继续迁移 `/env`、`/memory`、`/context`、`/plan` 等 handler |
| `src/xcode_cli/core/ui/streaming.py` | 继续承载 Thinking/token/final render 状态的后续增强 |
| `tests/` | 补重构回归测试 |

### 验收标准

- `agent.py` 体积明显下降，职责更清晰。
- `/resume`、`/compact`、审批、tool call、streaming 的回归测试继续通过。
- command handlers 迁移后不改变 slash command 用户可见行为。
- streaming 抽离必须和重复渲染问题一起验收，不能只搬代码。

## 12. P2：项目级配置合并

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

## 13. P2：渲染模式完善

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

## 14. Phase 5：生态扩展候选

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

## 15. Phase 6：外部聊天入口候选

Phase 6 只是远期方向记录，当前不进入设计和实现。

可能方向：Xcode 后续可以向类似 OpenClaw 的外部聊天 Agent 形态发展，让 Xcode 不只运行在 CLI 内，也能接入外部 IM 用户进行对话，例如 QQ 用户入口。

初步设想：

- 外部消息适配层：把 QQ 等 IM 消息转换为 Xcode 内部 user message。
- 会话映射：每个外部用户或群聊映射到独立 session，避免上下文串线。
- 权限边界：外部入口默认不能直接执行高风险工具，尤其是 `write_file`、`edit_file`、`run_shell`。
- 人类确认：危险操作仍需要本机 owner 确认，不能只由远程聊天用户批准。
- 审计日志：记录外部用户、消息、工具调用、审批结果和 session id。
- 部署边界：先明确是本地 bot、网关服务，还是插件化 connector。

开放问题：

- QQ 接入采用哪个协议或适配器，是否需要独立进程。
- 外部用户身份如何认证和授权。
- 群聊场景下如何避免 prompt 注入和多人上下文污染。
- 是否允许外部用户触发 coding 任务，还是只允许咨询和只读探索。
