# Auto Memory Recall v2 设计解读

> 本文用于解释 auto memory recall v2 为什么这样升级、每个升级点解决什么问题，以及升级后的实际效果。当前实现细节仍以 `docs/current/ARCHITECTURE.md` 为准，完成证据见 `docs/current/PROGRESS.md`。

## 1. 一句话总结

Auto memory recall v2 把记忆召回从“能把相关 memory 塞进上下文”升级为“索引常驻、正文按需、后台召回、当前 turn 安全注入、失败不影响主流程、过程可审计”。

核心目标不是让 Agent 记得更多，而是让它在正确时机看到更相关、更有边界的历史信息。

## 2. 为什么要升级

v1 的 recall 已经能工作，但存在几个长期风险：

- selector 输入偏薄，主要依赖 `description`，不容易区分用户偏好、项目约束、反馈和普通参考资料。
- 相关 topic 正文如果注入得太随意，容易挤占上下文预算。
- 旧记忆可能被模型当成当前事实，尤其是代码路径、行号、依赖版本和项目状态。
- 后台 prefetch 如果迟到，可能污染下一轮不相关输入。
- 出问题时不容易判断是没有候选、selector 没选、被去重过滤、文件读取失败，还是 prefetch 迟到。

v2 的升级方向是把 recall 做成一个低风险辅助通道：它可以帮主 Agent 补上下文，但不能阻塞主回复、不能越权读文件、不能破坏 tool loop，也不能把 debug 信息泄漏给用户对话。

## 3. 双路径召回模型

v2 采用两条路径：

1. `MEMORY.md` 短索引常驻主 prompt。
2. 后台 relevant prefetch 按需读取少量 topic 正文，并以 point-in-time reminder 注入当前本地 REPL turn。

这样做的效果是：

- 主 Agent 每轮都知道“有哪些记忆可能存在”。
- topic 正文不会常驻进入 base system prompt。
- 只有 selector 判断明确相关的 topic 才会被 bounded 读取。
- 如果 selector 没赶上当前 turn，主回复仍然继续，不会为了 memory 等待。

## 4. 每个升级点有什么用

### 4.1 `MEMORY.md` 短索引常驻

用处：让主 Agent 每轮都能看到 memory 的目录。

`MEMORY.md` 只放标题、相对链接和短 hook，不放正文。这样主 Agent 可以知道某类记忆存在，需要时再显式 `read_file`，但不会让长正文反复占用上下文。

效果：

- 保留跨会话记忆的可发现性。
- 避免旧 topic 正文常驻污染当前判断。
- 保持 base prompt 体积稳定。

### 4.2 后台 relevant prefetch

用处：让召回不阻塞主回复。

本地 REPL 收到 user turn 后，`AgentRuntime` 只做轻量 gate 和 manifest scan，然后把 selector 工作提交到后台线程。主 LLM 请求、streaming 和工具执行不等待 recall。

效果：

- 用户不会因为 memory selector 变慢而卡住。
- recall 成功时可以在安全点补充上下文。
- recall 失败或迟到时不会影响主回答。

### 4.3 trigger gates

用处：只在值得召回时启动 prefetch。

v2 会跳过这些情况：

- `auto_memory=false`。
- 用户明确说忽略记忆、不使用记忆。
- query 为空或过短。
- session 已注入 relevant memory bytes 达到上限。
- manifest 没有可用候选。

效果：

- 减少无意义 selector 请求。
- 降低成本和延迟风险。
- 避免在用户明确要求不使用记忆时违反意图。

### 4.4 v2 manifest selector

用处：让 selector 有更好的判断材料。

selector 不只看文件名和描述，还能看到：

- `name`
- `description`
- 顶层 `type`
- `mtime`
- `source`
- `filename`

效果：

- 更容易区分用户偏好、项目约束、反馈和参考资料。
- 可以结合更新时间判断记忆新旧。
- 不再把 legacy `metadata.type` topic 当作有效 v2 topic。

### 4.5 no-tool side query

用处：让 selector 只能“选记忆”，不能做别的事。

selector 调用 `LLMClient.complete(..., tool_schemas=[])`，不会拿到工具 schema，也不会执行文件、shell、MCP 或写入操作。

效果：

- recall 是低风险旁路。
- selector 失败不会破坏主 tool loop。
- 不引入新的公开 memory CRUD tool。

### 4.6 recent successful tools

用处：减少普通工具说明类 memory 的误召回。

Agent 会记录本地 REPL 最近成功执行的工具名，最多 10 个 distinct names。selector 可以据此降低普通 usage/API reference memory 的优先级。

例子：

- 最近已经成功用了 `read_file`，就不需要召回“如何使用 read_file”的普通参考。
- 但“这个项目里 read_file 某路径有编码坑”这种 warning/gotcha 仍然可以召回。

效果：

- 减少噪声 memory。
- 保留真正有价值的警告、偏好和项目约束。
- 不泄漏工具参数、路径、shell command、输出或 secret。

### 4.7 selector 输出严格过滤

用处：防止 selector 幻觉文件名或越权路径。

v2 只接受 manifest 中真实存在的 `.md` 文件名，并过滤：

- 重复项。
- 不存在文件。
- `../foo.md`。
- `dir/foo.md`。
- `dir\foo.md`。
- 非 JSON 或非预期结构。

效果：

- recall 不会变成任意文件读取入口。
- selector 幻觉不会影响主流程。
- 非法输出 fail closed。

### 4.8 bounded topic read

用处：控制每轮注入体积。

读取规则：

- 每轮最多 5 个 topic。
- 每个 topic 最多 4096 bytes。
- 每个 topic 最多 200 行。
- session surfaced bytes 默认上限 60 KiB。

效果：

- 避免 memory 正文挤占主任务上下文。
- 长 topic 不会一次性塞满 prompt。
- 长会话中 recall 注入量有总体边界。

### 4.9 截断提示

用处：告诉模型“这不是全文”。

如果 topic 被截断，正文末尾会提示可以用 `read_file` 查看完整文件。

效果：

- 模型不会误以为截断内容就是全部事实。
- 需要完整上下文时仍有明确下一步。
- 提示路径限制在 auto memory scope 内。

### 4.10 point-in-time reminder

用处：防止旧记忆被当作当前事实。

reminder 明确说明 memory 是历史观察，不是 live state。涉及代码行为、文件路径、行号、依赖版本、日程或当前项目状态时，必须按当前代码或当前文档验证。

效果：

- 降低旧记忆误导模型的风险。
- 鼓励模型先验证再下结论。
- 适合代码库持续变化的场景。

### 4.11 safe-point 注入

用处：避免破坏 LLM/tool 协议消息顺序。

relevant memory reminder 只在安全点注入，例如主请求前或工具轮后。它不会插在 assistant tool_calls 和 tool result 中间。

效果：

- 保持 OpenAI-compatible assistant/tool message 配对正确。
- 不破坏多轮 tool loop。
- 不影响工具执行和 transcript 结构。

### 4.12 late/stale 丢弃

用处：防止迟到的 prefetch 污染下一轮。

如果 prefetch 在当前 turn 可注入时机之后才完成，它只会被标记为 late，不会塞进下一轮 unrelated turn。

效果：

- 每个 prefetch 都是 turn-local。
- 上一轮的记忆不会误注入下一轮问题。
- debug 时仍能看到 late 计数。

### 4.13 surfaced/touched 去重

用处：避免重复注入和重复解释。

v2 有两层过滤：

- 已 surfaced 的 memory，本 session 不重复注入。
- 本轮主模型已经通过 `read_file` / `write_file` / `edit_file` 触碰过的 auto memory 文件，注入前再次过滤。

效果：

- 减少上下文重复。
- 避免模型刚读过的文件又以 reminder 形式出现。
- 降低同一 memory 多次影响当前判断的风险。

### 4.14 QQchat/external/headless 隔离

用处：避免外部入口污染本地 REPL recall state。

v2 recall 只服务本地 REPL state。QQchat、external、headless turn 不共享本地 recall state，也不触发本地 relevant reminder 注入。

效果：

- 远程输入不会影响本地开发上下文。
- 本地 recent tools 不被 QQchat/external 工具调用污染。
- 后续如果要支持外部入口 recall，需要单独设计 owner、权限和隔离策略。

### 4.15 audit/debug summary

用处：知道“为什么没有召回”，但不污染普通对话。

v2 记录本地 runtime audit summary，例如：

```text
selected=2 surfaced=1 skipped=late warnings=0 elapsed_ms=12 status=late
```

`/memory` 可以展示这个摘要，但不会输出：

- selector prompt。
- manifest 全量列表。
- 工具参数。
- 工具输出。
- memory 正文。
- secret。

效果：

- 方便定位 recall 问题。
- 不把 debug 噪声写进普通回复。
- 不把敏感上下文泄漏到 transcript。

## 5. 升级后的整体效果

v2 带来的效果可以概括为五点：

| 维度 | v2 效果 |
|------|---------|
| 准确性 | selector 使用 v2 manifest、recent tools 和更强筛选规则，召回更相关 |
| 性能 | 后台 prefetch 不阻塞主回复和工具执行 |
| 安全 | no-tool selector、严格文件名过滤、bounded read、防路径越界 |
| 上下文健康 | topic 正文不常驻，注入量有每轮和 session 上限 |
| 可审计 | `/memory` 可看到最近 recall 摘要，失败路径 fail closed |

## 6. 仍然保留的边界

这些事情 v2 仍然不做：

- 不引入 embedding、vector DB、全文索引 daemon。
- 不新增公开 `memory_search` / `memory_get` / `memory_list` 工具。
- 不实现独立 `memory_recall_model` 配置。
- 不把 topic 正文常驻 base system prompt。
- 不让 QQchat/external/headless turn 共享本地 REPL recall state。
- 不把 recall failure 写入普通 assistant 回复或 session transcript。

## 7. 如何判断 v2 是否工作正常

理想行为是：

- 普通本地 REPL turn 不等待 memory selector。
- 相关 topic 如果及时完成，会在当前 turn 的安全点作为 reminder 注入。
- 迟到 prefetch 不进入下一轮。
- 已 surfaced 或本轮 touched 的 memory 不重复注入。
- `/memory` 能看到最近 recall 摘要。
- `MEMORY.md` 索引仍在 prompt 中可见，但 topic 正文不会常驻。

当前已完成自动化回归；PowerShell/cmd.exe 原生 PTY 手工交互验收和真实 QQ/external 平台验收仍需另行记录。
