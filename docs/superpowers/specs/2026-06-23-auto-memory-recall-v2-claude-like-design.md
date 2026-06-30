# Auto Memory Recall v2 Claude-like Design

> 状态：设计已创建；代码实现、自动化回归和 PowerShell/cmd.exe 原生 PTY 手工交互验收均未执行。
> 日期：2026-06-23

## Background

Auto memory v1 已经具备两层召回：

1. `MEMORY.md` 索引常驻注入 prompt。
2. `MemoryRecallService` 基于 manifest 做 no-tool selector side query，选择最多 5 个 topic 正文，以 bounded system reminder 注入当前 turn。

该机制可用，但仍偏轻量：selector prompt 很薄，只看 `description`，不理解 v2 顶层 `type` 和 `Evidence:`；注入 reminder 也缺少“point-in-time observation，需要按当前代码验证”的明确提醒。用户提供的 Claude Code 召回链路显示，召回准确率主要来自两条并行路径：

- `MEMORY.md` 作为每轮都可见的短索引，让主 agent 知道有哪些记忆可读。
- 后台 relevant memory prefetch 使用 manifest selector 只挑确定有用的 topic，再 bounded 读取正文并作为 reminder 注入。

本设计只描述 recall v2。它排在 `2026-06-23-auto-memory-extraction-v2-claude-like-design.md` 之后实施，因为 recall v2 依赖 v2 topic frontmatter、manifest 和主 prompt 格式先稳定。

## Goals

- 把 v1 relevant recall 升级为 Claude-like 双路径召回：常驻 `MEMORY.md` 索引 + 后台相关 topic prefetch。
- 让 recall v2 默认消费 v2 frontmatter：`name`、`description`、顶层 `type`，并把 `description` 视为 selector 的主要检索摘要。
- 保持 prefetch 不阻塞主模型流式回复和工具执行。
- 默认使用与主 agent 相同的 LLM client/model 做 selector side query；暂不强制引入 Sonnet 或固定外部模型。
- 保留后续可选 `memory_recall_model` 配置位，但本阶段不要求实现。
- 在 reminder 注入中明确 memory 是 point-in-time observation，涉及代码行为、路径、行号或当前状态时必须按当前代码验证。
- 增加工具使用上下文：selector 可看到最近成功使用的工具，并避免召回普通 usage/API reference；但 warning、gotcha、known issue 类记忆仍可召回。
- 继续执行 session 级 surfaced/touched 去重、每文件读取上限、每轮文件数上限和 session 累计字节上限。

## Non-goals

- 本阶段不实现代码；只建立 recall v2 升级合同。
- 不引入 embedding、vector DB、全文索引服务或长期 daemon。
- 不要求使用 Sonnet；如未来需要独立 selector 模型，另行加配置和成本说明。
- 不新增公开 `memory_search` / `memory_get` / `memory_list` 工具。
- 不把 topic memory 正文常驻塞进 base system prompt。
- 不让 QQchat、MCP、sub-agent 或 external/headless turn 共享本地 REPL 的 recall state。
- 不在 recall v2 中兼容旧 `metadata.type` 作为验收要求；旧 topic 迁移应跟随 extraction v2 或单独 migration/cleanup。
- 不实现 agent-specific memory 目录隔离，除非后续 Xcode 明确引入可 @-mention 的 agent memory scope。

## Current v1 Behavior

当前 Xcode v1 的召回路径如下：

1. `MemoryManager.get_context_for_prompt()` 读取 `Project XCODE.md`、`User XCODE.md` 和 auto memory `MEMORY.md` 索引。
2. 本地 REPL 每轮 user turn 开始时调用 `_start_memory_prefetch()`。
3. 若 `auto_memory=false`，或用户说“不要记住 / 不使用记忆 / ignore memory”，本轮不启动 recall。
4. `MemoryManifestScanner` 扫 stable 和 legacy memory dir 的直接 `.md` 子文件，排除 `MEMORY.md`，每个文件只读前 30 行或 16 KiB frontmatter，最多 200 个候选。
5. `MemoryRecallService` 用 `tool_schemas=[]` no-tool selector 选择最多 5 个 filename。
6. selector 输出必须来自 manifest，不能包含路径分隔符，重复和不存在文件会被过滤。
7. 选中文件最多读取 4096 bytes / 200 行。
8. 若 prefetch 在主 LLM 请求前或工具轮后的安全点完成，则追加一条 `Relevant auto memories:` system reminder。
9. 同一 session 已 surfaced 的 memory，以及主模型已经读写过的 memory 文件，不再重复注入。
10. selector 失败、JSON 非法或文件读取失败不影响主回复。

v2 保留这些安全边界，但升级 manifest 格式、selector 输入、注入语义和调度细节。

## Architecture

### 1. Always-loaded Memory Index

`MEMORY.md` 仍是常驻短索引。它应在每轮主 prompt 中可见，但只能包含短标题、相对链接和一行 hook，不包含 topic 正文。

推荐 prompt 形态保持现有系统 prompt context，或渲染为内部 reminder；无论实现形态如何，都必须满足：

- `MEMORY.md` 内容每轮可见。
- `MEMORY.md` 不超过既有 prompt context 上限。
- 索引只包含相对链接，不包含绝对路径、secret 或长正文。
- 主 agent 可基于索引显式 `read_file` 某个 topic，但 topic 正文不常驻。

### 2. Relevant Memory Prefetch Trigger

本地 REPL user turn 接收后启动后台 prefetch。触发条件：

- `auto_memory=true`。
- 当前 turn 没有用户级“不要使用/忽略记忆”语义。
- 存在非空的最后一条 user `model_content`。
- query 不是过短输入；建议跳过单字、单词或无空白的极短 prompt，除非后续有明确上下文增强。
- session 已注入 relevant memory 字节数低于 `MAX_SESSION_SURFACED_BYTES`，默认 60 KiB。
- 当前 turn 属于本地 REPL；QQchat/external/headless turn 不共享本地 recall state。

Prefetch 必须不阻塞：

- 不等待 selector 才发起主 LLM 请求。
- 不等待 memory 文件读取才开始流式输出。
- 只在主模型请求前或工具轮次后的安全点，如果 prefetch 已完成，才注入 reminder。
- 当前 turn 已结束仍未完成的 prefetch 不得把 stale memory 注入后续 unrelated turn；可记录 skipped/late 状态用于审计。

### 3. Manifest Scan

Manifest scanner v2 默认只接受 v2 frontmatter：

```md
---
name: review-findings-first
description: User prefers code reviews to lead with concrete findings.
type: feedback
---
```

扫描规则：

- 扫描 stable auto memory dir；legacy dir 仅在 migration/compat 策略明确允许时参与。
- 排除 `MEMORY.md`。
- 每个文件只读取前 30 行或 16 KiB frontmatter。
- 提取 `filename`、`name`、`description`、`type`、`mtime`、`source`。
- `type` 只允许 `user|feedback|project|reference`。
- 缺少 `description`、缺少顶层 `type`、坏 frontmatter、旧 `metadata.type` 默认跳过并记录 warning。
- 按修改时间降序，最多 200 个候选。

Manifest 不读取正文；正文只在 selector 选中后 bounded 读取。

### 4. Selector Side Query

Recall selector 是一个 no-tool side query：

- `tool_schemas=[]`。
- `max_tokens` 建议 256。
- 输出必须是 JSON：`{"selected_memories":["filename.md"]}`。
- 最多 5 个文件名。
- 文件名必须来自 manifest 候选。
- 默认使用当前主 agent 配置的同一个 LLM client/model，不固定 Sonnet。
- 后续可以增加 `memory_recall_model` 配置，但本 spec 不要求。

推荐 selector system prompt：

```text
You are selecting memories that will be useful to Xcode as it processes the
user's current query.

You will be given the user's query and a list of available memory files with
their types, filenames, timestamps and descriptions.

Return JSON only: {"selected_memories":["filename.md"]}.

Choose up to 5 memories that are clearly useful for processing the query. Be
selective and discerning. If you are unsure whether a memory will help, do not
include it. If no memory is clearly useful, return an empty list.

If a list of recently successful tools is provided, do not select ordinary
usage reference or API documentation memories for those tools because Xcode is
already exercising them. Still select memories that contain warnings, gotchas,
known issues, user preferences or project constraints about those tools.

Do not invent filenames. Do not include paths. Do not explain.
```

Selector user input format：

```text
Query: <current user model_content>

Available memories:
- [feedback] review-findings-first.md (2026-06-23T10:00:00Z): User prefers code reviews to lead with concrete findings.
- [project] qqchat-constraints.md (2026-06-23T10:02:00Z): QQchat remote turns are read-only by default.

Recently successful tools:
- read_file
- edit_file
```

如果没有最近成功工具，可省略该段。

### 5. Recent Tool Context

Recall v2 应从当前 conversation/tool state 提供一个 bounded recent tool summary：

- 只包含工具名，不包含工具参数、路径、输出或 secret。
- 只统计成功执行的工具。
- 上限建议最近 10 个 distinct tool names。
- selector 用它抑制普通 usage/reference memory，避免模型正在熟练使用某工具时又被注入“如何使用该工具”的说明。
- warning、gotcha、known issue、用户偏好、项目约束不应被抑制。

### 6. Reading Selected Memories

读取规则：

- 每轮最多读取 5 个 topic。
- 每个 topic 最多 4096 bytes 或 200 行。
- 单轮自然上限约 20 KiB。
- session 累计 surfaced 上限默认 60 KiB。
- 读取失败只记录 warning，不影响主回复。
- 若发生截断，正文末尾附加短提示：

```text
> This memory file was truncated (4096 byte limit). Use read_file to view the complete file at: <path>
```

该提示中的 `<path>` 可以是 resolved path，但必须只指向 auto memory scope 内文件。

### 7. Reminder Injection

Recall v2 注入为 system reminder，格式应比 v1 更明确：

```text
<system-reminder>
This memory is 47 days old. Memories are point-in-time observations, not live
state. Claims about code behavior, file paths, file:line citations, dependency
versions, schedules or current project status may be outdated. Verify against
current code or current docs before asserting them as fact.

Memory: <path>:

---
name: review-findings-first
description: User prefers code reviews to lead with concrete findings.
type: feedback
---

Rule: Lead code reviews with concrete findings.
Evidence: "review 输出应以问题为主"
How to apply: Put findings before summaries.
</system-reminder>
```

要求：

- 每个 surfaced memory 都带 age warning。
- `mtime` 转换为天数；不足一天可写 `saved recently`。
- reminder 不应泄漏 selector prompt、manifest 全量列表或工具参数。
- 多个 memory 可以合并到一条 system message，也可以多条 system reminder；实现必须可测试且 bounded。
- 注入只能发生一次；同一 turn 已消费的 prefetch 不得重复注入。

### 8. Duplicate Filtering

必须有两层去重：

- selector 前：从候选 manifest 中过滤当前 session 已 surfaced 的 memory。
- 注入前：再次过滤主模型已经通过 `read_file` / `write_file` / `edit_file` 触碰过的 auto memory 文件。

State 至少包括：

- `surfaced_paths`
- `touched_paths`
- `surfaced_bytes`
- 可选 `late_prefetch_count`
- 可选 `warnings`

`surfaced_paths` 可以从当前 session state 维护；如后续支持 resume 后继续 recall，应考虑从已有 messages 中扫描已注入 reminder 的 `Memory: <path>:` 行重建 surfaced set。

### 9. Failure And Audit

Recall v2 是辅助上下文，不是主流程依赖。以下情况都必须 fail closed：

- manifest scan 失败。
- selector LLM 报错、超时或返回非法 JSON。
- selector 编造文件名。
- 文件读取失败或超过限制。
- prefetch 晚于当前 turn 可注入时机完成。

审计字段建议：

- `selected_count`
- `surfaced_count`
- `skipped_reason`
- `warnings`
- `selector_model`
- `elapsed_ms`
- `late_or_consumed`

默认不在普通对话中打印这些字段；后续 `/memory` 或 debug 日志可以展示最近一次 recall 状态。

## Implementation Order

Recall v2 必须在 extraction v2 之后实施：

1. 先完成 extraction v2：主 prompt、writer、manifest、topic 文件全部迁移到 v2 frontmatter。
2. 再实现 recall v2 scanner/selector/reminder。
3. 最后更新 current architecture/docs，移除 v1 `metadata.type` recall 说明。

原因：召回准确率依赖 `description` 和 `type` 质量；如果 extraction 仍在写旧格式或泛化 topic，recall v2 会把不稳定输入放大。

## Compatibility

- v2 recall 默认不兼容旧 `metadata.type` topic。
- 旧 topic 不自动删除。
- 如需保留旧记忆，先执行 migration/cleanup，把旧 topic 转成 v2 frontmatter。
- `Project XCODE.md` 和 `User XCODE.md` 召回语义不变。
- `MEMORY.md` 索引继续是短索引；索引行格式不要求破坏性迁移。

## Acceptance Criteria

- `MEMORY.md` 短索引仍每轮可见，topic 正文不常驻。
- 本地 REPL user turn 后启动 non-blocking recall prefetch；主 LLM 请求和 streaming 不等待 prefetch。
- `auto_memory=false`、用户要求忽略/不使用记忆、过短 query、session surfaced bytes 达上限时不启动 recall。
- Manifest scanner 默认读取 v2 frontmatter：`name`、`description`、顶层 `type`。
- 旧 `metadata.type` topic 默认跳过并记录 warning。
- Selector 使用 `tool_schemas=[]`，默认复用主模型 LLM，不固定 Sonnet。
- Selector 输入包含 query、最多 200 条 manifest，以及 bounded recent successful tool names。
- Selector 输出最多 5 个 filename，且必须来自 manifest；非法、重复、带路径分隔符的输出被过滤。
- 最近成功工具可抑制普通 usage/API reference memory，但 warning/gotcha/known issue 不被抑制。
- 选中 topic 每文件最多读取 4096 bytes / 200 行；截断时附加 read_file 提示。
- Reminder 注入包含 point-in-time/verify-current-state 警告和 memory age。
- 同一 session 已 surfaced 或本轮已 touched 的 memory 不重复注入。
- Prefetch 失败、超时、迟到、selector 非法或文件读取失败不影响主回复。
- QQchat/external/headless turn 不共享本地 REPL recall state。

## Suggested Verification

- `pytest tests/test_memory_manifest_v2.py -q`
- `pytest tests/test_memory_recall_v2.py -q`
- `pytest tests/test_agent_memory_recall_v2.py -q`
- `pytest tests/test_prompting_memory_v2.py -q`
- `python -m compileall -q src`
- `pytest -q`

实现完成前不得把以上命令写成已通过。
