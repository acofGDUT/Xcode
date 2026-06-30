# Auto Memory Extraction Design

> 状态：v1 代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工交互验收未执行/未记录。v2 升级要求已抽离到独立文档：`2026-06-23-auto-memory-extraction-v2-claude-like-design.md`。
> 日期：2026-06-23

## Background

Xcode 当前已经有文件驱动 memory 模型：`XCODE.md` 保存用户和项目级长期约定，auto memory 目录保存主题 `.md` 文件，`MEMORY.md` 作为常驻上下文索引。系统提示会指导主模型在需要记忆时通过 `write_file` / `edit_file` 写入 memory 文件，`ToolCallExecutor` 也已经支持 memory-scoped 写入免审，并保持显式 `deny` 优先。

问题是当前模型依赖主模型在当轮主动意识到“这值得记住”。如果用户在普通工作流中透露了长期偏好、稳定反馈、项目背景或外部资源，Xcode 可能完成任务后就丢失这类信息。用户希望 Xcode 能像 Claude 的记忆系统一样，在每轮结束后自动抽取长期有价值的信息，但仍保持本项目已有的文件模型、安全边界和同步主循环。

本设计按三阶段推进：先稳定 auto memory 路径和 manifest 扫描，再接入受控 after-turn 内部 hook 做自动沉淀，最后基于 manifest 做相关记忆召回。第一版已经交付“本地 REPL 自动沉淀长期记忆”。

2026-06-23 后续 review 发现 v1 extraction 仍偏宽；v2 Claude-like 受限 extraction subagent 的升级要求不再耦合在本文，见独立 spec：`2026-06-23-auto-memory-extraction-v2-claude-like-design.md`。

## Goals

- auto memory 路径使用与 `SessionStore.project_key()` 等价的稳定 project key，避免同名目录项目共享记忆。
- 增加 memory manifest 扫描能力，读取主题 memory 文件 frontmatter 中的 `description` 和 `metadata.type`，排除 `MEMORY.md`，并限制读取行数和字节数。
- 增加受控的 `after_turn_success` 内部 hook，只在本地 REPL assistant 成功落盘后触发。
- 新增 `MemoryExtractionService`，根据最近一轮本地 REPL 对话判断是否值得长期保存，并写入 auto memory 主题文件和 `MEMORY.md` 索引。
- 所有后台抽取异常都必须被捕获并记录为 audit/status，不得影响主循环、用户可见 assistant 回复、`_history` 或 session transcript 的正常写入。
- 保持当前 memory 安全边界：auto memory off 时不写，显式 `deny` 仍优先，不新增通用 memory CRUD 工具。
- 为后续相关记忆召回保留 manifest 数据契约和注入边界。

## Non-goals

- 不实现通用用户脚本 hooks，不执行 skill frontmatter 的 `hooks` 字段。
- 不引入 embedding、vector DB、后台索引服务或长期 daemon。
- 不新增公开 `memory_save` / `memory_list` / `memory_get` / `memory_delete` 工具。
- 第一版不让 QQchat、MCP、sub-agent 或其他 external/headless turn 自动写长期 memory。
- 第一版不做跨项目全局 memory 检索；User `XCODE.md` 仍按现有机制注入。
- 第一版不把主题 memory 文件正文全量常驻注入 system prompt。
- 不把代码模式、git 历史、临时任务状态、完整 shell 输出、完整文件内容或 secret 写入 auto memory。

## Current Constraints

- Xcode 主循环是同步架构；v1 不把 `AgentRuntime`、`LLMClient.complete()` 或 `_run_llm_loop()` 改成全局 `asyncio`。
- `src/xcode_cli/core/memory.py` 当前是单文件模块；已有计划曾提醒不要未经设计把它直接改成同名包。若需要拆分，应使用新模块名，或在 plan 中单独设计包迁移。
- `MemoryManager` 当前使用 `cwd.name` 生成 auto memory 目录，和 `SessionStore.project_key()` 的项目隔离规则不一致。
- `BASE_SYSTEM_PROMPT` 已经定义 auto memory 文件格式和写入规则；实现必须保持 prompt、文档和代码契约一致。
- `ToolCallExecutor` 已有 memory-scoped approval bypass；自动抽取不能绕过 `PermissionManager` 的显式 `deny`。
- QQchat/external turn 当前默认只允许只读工具，并且远程用户不能批准危险工具；自动 memory 写入不能破坏这个边界。
- 已有 `WorkStateTracker` 只负责 compact restored context 的短期现场恢复，不应被扩展为长期记忆存储。

## User-visible Behavior

本地 REPL 中，用户完成一次普通对话后，Xcode 可以在后台尝试抽取长期记忆。成功或失败默认不打断用户，也不要求用户审批 memory 文件写入；如需要可在 debug/audit 日志或 `/memory` 状态中看到最近抽取结果。

当 `auto_memory=false` 时，Xcode 不执行自动抽取，也不召回主题 memory 文件正文。现有 `Project Memory`、`User Memory` 和 `/memory auto on|off` 行为保持不变。

当用户明确说“不要记住”“不要使用记忆”“忽略 memory”时，本轮不执行自动抽取；后续如果做召回，本轮也不读取主题 memory 正文。

如果后台抽取失败，用户看到的主回复不改变。失败只记录为可审计事件，例如 summary request failed、memory write denied、bad frontmatter skipped、duplicate memory skipped。

第一版 QQchat 消息不会自动写入长期 memory。QQchat 仍可使用当前 system prompt 中已有的 memory context，但外部输入不会触发 after-turn memory extraction。

## Design

### 1. Path and Manifest Baseline

新增一个共享 helper，例如 `project_key_for_path(cwd: str) -> str`，其输出与 `SessionStore.project_key()` 保持一致。`SessionStore.project_key()` 和 `MemoryManager` 都应使用同一实现，避免路径规则分叉。

`MemoryManager.memory_dir_path()` 从：

```text
~/.xcode/projects/<cwd.name>/memory/
```

迁移为：

```text
~/.xcode/projects/<project_key>/memory/
```

为了兼容旧数据，`MemoryManager` 应知道 legacy memory dir：`~/.xcode/projects/<cwd.name>/memory/`。第一版兼容策略：

- 新写入只写 stable project key 目录。
- 读取 `MEMORY.md` 时优先读取 stable 目录；如果 stable index 不存在而 legacy index 存在，则读取 legacy index。
- manifest 扫描可同时扫描 stable 和 legacy 目录，但相同 slug 以 stable 目录为准。
- `/memory` 状态展示 stable 目录，并在发现 legacy 目录时提示 legacy exists。
- 不自动迁移或删除 legacy 文件，避免无授权移动用户数据。

新增 `MemoryManifestScanner`，建议放在 `src/xcode_cli/core/memory_manifest.py`，避免立即包化 `core/memory.py`。v1 baseline 扫描规则：

- 输入：stable memory dir、可选 legacy memory dir。
- 只扫描目录直接子文件或受控递归深度。第一版建议只扫直接子文件，避免意外读取深层目录。
- 只处理 `.md` 文件，排除大小写精确的 `MEMORY.md`。
- 每个文件最多读取前 30 行和 16 KiB，超过即截断。
- 解析 YAML-like frontmatter，只读取：
  - `name`
  - `description`
  - `metadata.type`
- `type` 只接受 `user|feedback|project|reference`，未知时记为 `unknown`。
- 坏 frontmatter、编码错误、读取错误跳过文件并产生 warning，不抛出到主循环。

Manifest entry 数据契约：

```python
@dataclass(frozen=True)
class MemoryManifestEntry:
    slug: str
    title: str
    path: Path
    description: str
    type: str
    source: Literal["stable", "legacy"]
```

### 2. Controlled After-turn Hook

新增受控内部 hook runner，例如 `AfterTurnHookRunner`。它不是用户脚本系统，只接受代码注册的内部 hook。

事件：

```python
@dataclass(frozen=True)
class AfterTurnSuccessEvent:
    session_id: str
    cwd: str
    user_display_content: str
    user_model_content: str
    assistant_text: str
    recent_history: list[dict[str, Any]]
    wrote_memory_this_turn: bool
```

触发点位于本地 REPL `_run_user_turn()` 中 assistant 成功写入 session 和 `_history` 之后。不能在 LLM 错误、missing API key、用户中断或 `No response.` 路径触发。

`_run_llm_loop()` / `ToolCallExecutor` 应能返回或记录本轮是否执行过 memory-scoped 写入。若主模型已经写过 memory 文件，`MemoryExtractionService` 跳过，避免同一轮重复沉淀。

Hook runner 失败策略：

- 每个 hook 独立 try/except。
- 捕获 `Exception`，不捕获并吞掉 `KeyboardInterrupt` 以外的用户主动中断语义；若实现选择捕获 `BaseException`，必须明确不隐藏进程退出信号。
- hook 结果只写 audit/status，不修改本轮 assistant 回复。
- hook 不允许调用普通 `run_shell`、`edit_file` 等工具链；第一版 memory extraction 使用受控文件写入服务或受限工具 adapter。

### 3. Memory Extraction Service

`MemoryExtractionService` 是第一版唯一 after-turn consumer。它负责判断最近一轮是否产生长期记忆，并写入 auto memory。

输入：

- `AfterTurnSuccessEvent`
- 当前 `Config`
- `MemoryManager`
- `MemoryManifestScanner`
- `LLMClient` 或一个可测试的 extraction client adapter

执行条件：

- `config.auto_memory` 为 true。
- turn 来源是本地 REPL，而不是 QQchat/external runner。
- 用户本轮没有明确禁止记忆。
- 主模型本轮没有已经写 memory。

推荐第一版使用 no-tool LLM side query 做抽取，而不是简单规则。原因是“什么值得长期保存”需要理解语义；但请求必须明确 `tool_schemas=[]`，并且结果必须是受控 JSON 或纯文本 schema。若 no-tool request 失败，服务直接放弃本轮抽取。

Extraction prompt 必须强调：

- 只保存长期稳定且不可从代码/git/docs 推导的信息。
- 优先保存用户偏好、用户反馈、项目背景、长期约束、外部资源引用。
- 不保存临时任务状态、代码实现细节、git 历史、完整文件内容、secret、token、凭证、完整 shell 输出。
- 如果没有值得保存的信息，返回 `{"action":"skip","reason":"..."}`。

建议 extraction 输出：

```json
{
  "action": "save",
  "type": "feedback",
  "slug": "review-findings-first",
  "title": "Review findings first",
  "description": "User prefers code reviews to lead with concrete findings.",
  "body": "Rule: ...\nWhy: ...\nHow to apply: ..."
}
```

写入策略：

- slug 只允许小写字母、数字和短横线；超出时 sanitize。
- 如果 manifest 中已有相同 slug，优先更新已有文件；第一版也可以选择 skip duplicate，但必须记录原因。
- 创建主题文件时使用既有 frontmatter 格式。
- 更新 `MEMORY.md` 时新增或修正一行：

```md
- [Title](slug.md) - one-line hook
```

- index 行必须使用相对文件名，不写绝对路径。
- 写入前后不读取或写入非 memory-scoped 路径。

安全上，`MemoryExtractionService` 不应直接享有任意文件写权限。建议通过 `MemoryWriter` 封装：

```python
class MemoryWriter:
    def write_topic(entry: ExtractedMemory) -> MemoryWriteResult
```

`MemoryWriter` 内部调用 `MemoryManager.is_memory_write_target()` 校验目标路径，并显式检查 `PermissionManager.check("write_file") != "deny"`。这样保持“显式 deny 优先”的用户承诺。

### 4. Relevant Memory Recall

相关召回采用两层模型：

1. `MEMORY.md` 继续作为常驻短索引进入 system prompt，帮助主模型知道有哪些主题记忆。
2. 主题 `.md` 文件按需召回，只在当前用户 query 明确相关时注入 bounded 正文。

第一版相关召回不使用 embedding、vector DB 或全文搜索索引，而是使用：

```text
用户 query
  -> 扫描 auto memory 目录的主题文件 frontmatter
  -> 生成 bounded manifest
  -> no-tool side query 从 manifest 中选择最多 5 个文件
  -> 校验 selector 输出必须来自候选列表
  -> 读取主题文件前 200 行或 4096 bytes
  -> 作为 relevant memory system reminder 注入主对话
```

#### 4.1 Prefetch timing

在每个本地 REPL user turn 开始时启动 memory prefetch。由于 Xcode 主循环保持同步外观，不引入全局 async 化，建议用 `ThreadPoolExecutor`、专用 background future 或受控 async runner 执行 prefetch。

Prefetch 不应阻塞首个主 LLM 请求。`_run_llm_loop()` 在安全点检查 prefetch 是否完成：

- 第一次构建 LLM request 前可做一次极短非阻塞检查，完成则注入。
- 每轮 tool call 执行后、下一次 LLM request 前再次检查，完成则注入。
- 如果主模型没有工具调用且 prefetch 尚未完成，本 turn 可以不注入；相关记忆仍会在后续 turn 或用户显式读取时可用。
- future 异常只记录 warning/audit，不影响主 LLM loop。

注入形式建议使用 history 中的 system reminder，而不是重写 base system prompt：

```text
Relevant auto memories:
Memory (saved <mtime>): <path>:

<bounded memory content>
```

这样可以保留“本轮动态附件”的语义，也更容易在 session 内去重。

#### 4.2 Candidate manifest

Manifest 由 `MemoryManifestScanner` 提供：

- 扫描 stable auto memory dir 和可选 legacy memory dir。
- 排除 `MEMORY.md`。
- 每个主题文件只读前 30 行或 16 KiB frontmatter。
- 读取 `filename`、`filePath`、`mtimeMs`、`description`、`type`。
- 最多保留最近修改的 200 个候选文件。
- 坏 frontmatter、读取错误、编码错误跳过并记录 warning。

传给 selector 的候选文本使用紧凑格式：

```text
Query: <user query>

Available memories:
- [feedback] foo.md (mtime=...): description
- [project] bar.md (mtime=...): description
```

#### 4.3 Side-query selector

新增 `MemoryRecallService`，使用 no-tool side query 选择相关主题文件。请求必须满足：

- `tool_schemas=[]`，不得发送 `tools` 或 `tool_choice=auto`。
- 只选择“明确有用”的记忆，不为了凑数选择。
- 最多返回 5 个文件名。
- 输出 JSON：

```json
{
  "selected_memories": ["foo.md", "bar.md"]
}
```

实现必须校验 selector 输出：

- 只能接受 manifest 候选中存在的文件名。
- 重复文件去重。
- 不存在、路径穿越、绝对路径、非 `.md` 文件全部丢弃。
- selector JSON 解析失败时不注入相关记忆。

模型选择第一版可复用当前 configured model，后续如需要再增加 `memory_recall_model` 配置；不要在本 spec 中新增价格表或模型切换复杂度。

#### 4.4 Reading and surfacing

选中文件后读取正文：

- 每个主题文件最多 200 行或 4096 bytes。
- 单 turn 最多 5 个文件，约 20 KiB 原始上限。
- 同一 session 中 relevant memory 累计注入超过 60 KiB 后停止继续注入。
- 读取失败跳过并记录 warning。
- 注入内容不展开 linked memory，不递归读取。

注入前执行两层去重：

- session 级 surfaced memory set：同一 session 已注入过的 memory path 不重复注入。
- tool state 去重：如果本轮或当前 session 中模型已经通过 `read_file` / `write_file` / `edit_file` 读写过该 memory 文件，则不再作为 relevant memory 注入。Xcode 可复用 `WorkStateTracker` 或新增轻量 `ReadFileState` 来记录这些路径。

当用户明确要求“不使用记忆”“忽略 memory”时，本 turn 不启动 prefetch，也不注入 relevant memory。

## Security and Reliability

- 外部输入不可信。QQchat/external turn 第一版不触发自动 memory extraction。
- Auto memory 写入范围必须由 `MemoryManager.is_memory_write_target()` 判定，不能用字符串前缀手写判断。
- 显式 `deny write_file` 或等价权限规则必须阻止后台自动写入 memory。
- extraction LLM 不允许工具调用。`tool_schemas=[]` 时 `LLMClient` 不应继续发送 `tools` 或 `tool_choice=auto`。
- Memory 文件不能保存 secret。Extraction prompt 和 `MemoryWriter` 都应做基础 secret redaction，至少覆盖 Authorization、Bearer、Basic、access_token、client_secret、api_key、app_secret、QQ_BOT_CLIENT_SECRET、常见 `--token/--secret/--password` 参数。
- Hook 异常不影响主循环，不改变 `_history`，不写坏 transcript。
- Manifest 扫描和召回必须有读取上限，避免超大文件拖慢 REPL 或污染上下文。
- Memory recall prefetch 不得创建无界线程或无限等待；每个本地 REPL turn 最多一个 pending future，turn 结束后未使用的 future 要么可被安全丢弃，要么只记录结果不再注入旧 turn。
- 后台抽取不应在每轮输出额外噪音；可通过 debug/audit 或 `/memory` 扩展查看最近状态。

## Compatibility and Migration

路径迁移必须兼容旧的 `<cwd.name>` auto memory 目录。第一版不自动移动旧文件，仅在读取和扫描时兼容 legacy 目录，并在 `/memory` 中提示。

如果 stable 和 legacy 中存在同名 slug，stable 版本优先。新写入总是写 stable 目录，避免继续扩大旧路径。

已有 `MEMORY.md` 索引格式保持兼容。新的 scanner 不依赖 index 解析主题文件列表，而是以磁盘 `.md` 文件为准；index 继续作为模型常驻短索引。

`Project XCODE.md` 和 `User XCODE.md` 语义不变。自动抽取默认写 auto memory，不主动写用户全局 `XCODE.md` 或项目仓库内 `XCODE.md`。

## Alternatives

- **只加强 prompt，不做 after-turn hook。** 实现最小，但仍依赖主模型主动记忆，无法解决用户的主要目标。
- **新增公开 memory CRUD 工具。** 更容易测试，但违背当前项目“memory 不是 CRUD 工具模型”的架构决策，会增加 schema 面和权限维护成本。
- **执行 skill hooks 或用户脚本 hooks。** 看似通用，但信任边界过大，且当前 skills 文档明确规定 hooks 只解析保存、不执行。memory 第一版不需要这个风险。
- **直接引入 vector DB/embedding。** 可能提升召回，但增加依赖、索引一致性、隐私和迁移成本，不符合当前路线。
- **让 QQchat 也自动写 memory。** 远程输入不可信，且 QQ 场景默认只读工具。后续如需要，应单独设计 owner-only、明确 opt-in 的外部 memory 策略。

## Acceptance Criteria

- `MemoryManager` 的 auto memory stable 目录与 `SessionStore.project_key()` 对同一 cwd 生成的项目 key 一致。
- 两个同名目录、不同绝对路径的项目不会共享 stable auto memory 目录。
- legacy `<cwd.name>/memory` 中已有 `MEMORY.md` 时，在 stable index 缺失情况下仍可读取；新写入只进入 stable 目录。
- Manifest scanner 排除 `MEMORY.md`，只读取 `.md` 主题文件的 bounded frontmatter，坏文件不抛异常。
- `auto_memory=false` 时，不执行 after-turn extraction，也不注入 relevant auto memory 正文。
- 本地 REPL assistant 成功回复后会触发 `after_turn_success`，LLM 错误、missing API key、用户中断、`No response.` 不触发。
- QQchat/external turn 不触发 after-turn memory extraction。
- 主模型本轮已经写入 memory 文件时，后台 extraction 跳过。
- extraction side query 使用 no-tool request；如果 extraction 失败，主回复、`_history` 和 session transcript 不受影响。
- 显式 `deny write_file` 时，后台 extraction 不能写入 memory 文件。
- 写入的主题文件包含 `name`、`description`、`metadata.type` frontmatter，`MEMORY.md` 只新增相对链接索引行。
- secret-like 文本不会进入新 memory 文件或 audit metadata。
- 相关召回阶段从 manifest 通过 no-tool side query 选择最多 5 个主题文件；selector 编造、不存在、重复或越界文件名会被过滤。
- 相关召回读取每个主题文件最多 200 行或 4096 bytes；同一 session 的 relevant memory 累计注入超过 60 KiB 后停止继续注入。
- 同一 session 已 surfaced 的 memory 文件不会重复注入；模型已经读过、写过或编辑过的 memory 文件不会再作为 relevant memory 注入。
- memory prefetch 未完成时不阻塞主 LLM loop；失败或超时不影响主回复。

## Suggested Verification

- `pytest tests/test_memory.py tests/test_prompting_memory.py -q`
- `pytest tests/test_memory_manifest.py -q`
- `pytest tests/test_memory_extraction.py -q`
- `pytest tests/test_memory_recall.py -q`
- `pytest tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q`
- `pytest tests/test_external_turn.py tests/test_qqchat_service.py -q`
- `python -m compileall -q src`
- `pytest -q`

实现完成前不得把以上命令写成已通过。若只完成 spec/plan，不运行测试。

## Open Questions

- `/memory` 是否需要展示最近一次 extraction 状态：本轮未扩展 `/memory` 状态展示；`MemoryExtractionService.last_result` 保留为内部状态。
- Duplicate slug 第一版应更新已有 memory，还是保守跳过并记录 duplicate：本轮选择由 `MemoryWriter` 按 slug 覆盖同名 topic 文件，并按相对 filename upsert `MEMORY.md` 索引行。
- Relevant memory recall 第一版是否随 extraction 同批实现：已同批实现，采用 manifest + no-tool selector + bounded system reminder，不引入 embedding 或 vector DB。

