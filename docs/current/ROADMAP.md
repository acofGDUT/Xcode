# Xcode 路线图

> 本文只记录未来计划、未完成能力和仍需验收的风险。已完成实现请看 `PROGRESS.md`，当前实现细节请看 `ARCHITECTURE.md`，坑点和设计取舍请看 `DEVNOTES.md`。

最后更新：2026-06-30

## 1. 当前焦点

Xcode v0.1.0 的核心 CLI、session/resume、compact v2 可靠性、Skills Phase 1-2、MCP Phase 1/2、本地主会话 `dispatch_agent` 免审和 auto memory extraction v2 已经收口。compact v3 现场恢复代码和自动化回归已落地，但原生 Windows/QQchat 手工验收仍未收口。后续 roadmap 不再展开已完成项，只保留仍需实现或仍需真实平台验收的工作。

近期优先级：

- 完成 `/QQchat init`、`/QQchat reload` 和真实 QQ 单聊/群聊平台验收。
- 按 `docs/superpowers/plans/2026-06-30-approval-denial-interrupts-turn-plan.md` 实现本地审批拒绝后中断当前 turn，等待用户下一次输入。
- 补齐 relevant memory recall v2 的 PowerShell/cmd.exe 原生 PTY 手工交互验收记录。
- 为 `/context` 增加费用估算，而不只是 token 统计。
- 补齐 compact v3 现场恢复与 `xcode.v3` checkpoint 链路的 PowerShell/cmd.exe 原生 PTY 和 QQchat 平台手工验收。
- 继续收口工具调用展开、task 面板持久展示、对话回退/分叉和渲染模式。

Phase 5 生态扩展整体继续冻结。MCP 目前只完成 stdio tools 的安全接入和管理面；HTTP/SSE/OAuth/resources/prompts/MCP Apps、WebFetch、WebSearch、hooks、remote skills 等仍不得无 spec 铺开。

## 2. 近期优先级

| 优先级 | 能力 | 状态 | 下一步 |
|--------|------|------|--------|
| P0 | QQchat 原生 Windows/真实平台 E2E | 未完成 | 在 PowerShell/cmd.exe 验证 `/QQchat start|stop|status` 与 prompt_toolkit 共存，并完成真实 QQ 单聊和群聊 @ 回复验收 |
| P0 | 本地审批拒绝中断当前 turn | 已写 spec/plan，待实现 | 从 `docs/superpowers/plans/2026-06-30-approval-denial-interrupts-turn/task-01-distinguish-interactive-approval-denial.md` 开始，实现审批 `No` 后写入拒绝记录并停止本轮 LLM loop |
| P0/P1 | compact 现场恢复与 checkpoint 链路 | 代码实现和自动化回归已完成；手工验收未执行/未记录 | 在 PowerShell/cmd.exe 验证 restored-context `/compact` 和 v3 `/resume`，并完成 QQchat same-conversation continuation/isolation 平台验收 |
| P1 | `/QQchat init` + reload | 已写 spec/plan，未实现 | 实现配置骨架初始化和热部署 reload，项目级配置不能写 secret |
| P1 | Auto memory recall v2 手工验收 | 代码实现和自动化回归已完成；手工验收未执行/未记录 | 在 PowerShell/cmd.exe 验证 non-blocking prefetch、安全点注入、late 丢弃和 memory 目录 bounded read；QQchat/external/headless 隔离目前只有自动化覆盖 |
| P1 | `/context` cost 估算 | 未实现 | 在 token 统计外展示近似费用，未知模型显示 `unknown` |
| P1 | 工具调用 UI 展开 | 默认摘要已完成，展开未做 | 设计并验证 `Ctrl+O` 展开摘要，重点看原生 Windows 热键兼容 |
| P1 | task 面板持久展示 | 瞬时面板已完成，持久展示未做 | 评估 bottom toolbar 或固定区域，并验证与 Rich Live、streaming、审批菜单共存 |
| P1 | 对话回退 / 分叉 | 未实现 | 设计 fork-based rollback，避免破坏原 session |
| P1 | 渲染模式完善 | 部分实现 | 明确 streaming、buffer、可替换区域式 final render 的边界 |
| P2 | skills 后续生态 | 冻结候选 | fork skill runtime、hooks、paths 自动激活、remote skills、skill search 暂不进入近期默认开发 |

## 3. 当前阻塞和遗留

本表是当前 backlog 的单一入口。`PROGRESS.md` 只保留历史和验收证据，不再维护另一份遗留清单。

| 项目 | 状态 | 说明 |
|------|------|------|
| CLI `--resume` / `--continue` | 延后 | 当前只做交互内 `/resume`，CLI 恢复入口后续如有明确需求再设计 |
| 本地审批拒绝中断当前 turn | 已写 spec/plan，待实现 | 用户在本地 REPL 审批菜单选择 `No` 后应立即停止当前 turn，保留 assistant/tool 拒绝记录和中断标记，等待下一次用户输入；设计见 `docs/superpowers/specs/2026-06-30-approval-denial-interrupts-turn-design.md`，实施入口见 `docs/superpowers/plans/2026-06-30-approval-denial-interrupts-turn-plan.md` |
| `/context` cost | 未实现 | 当前只有 token 估算，没有价格估算 |
| compact 现场恢复与 checkpoint 链路 | 代码实现和自动化回归已完成；手工验收未执行/未记录 | `xcode.v3` restored context、checkpoint lineage metadata、v3 resume 和 external work-state isolation 已有自动化覆盖；仍需原生 Windows/QQchat 手工验收 |
| `/QQchat init` + reload | 已写 spec/plan，未实现 | 需要实现配置文件骨架初始化和热部署 reload；项目级 config 不能写 secret |
| Auto memory recall v2 | 代码实现和自动化回归已完成；手工验收未执行/未记录 | Claude-like `MEMORY.md` 短索引 + relevant topic prefetch 已实现；仍需 PowerShell/cmd.exe 原生 PTY 验证 non-blocking prefetch、安全点注入、late 丢弃、memory 目录 bounded read；QQchat/external/headless 隔离目前只有自动化覆盖 |
| `/QQchat` 最终验证 | 未完成 | 需要记录真实 QQ/Windows 验收；自动化通过不能替代真实平台接入完成 |
| QQ 真实平台验收 | 未完成 | 单聊被动回复、群聊 @ 被动回复、危险工具真实 QQ 场景均未验收 |
| 工具调用 `Ctrl+O` 展开 | 未实现 | 默认摘要已完成；展开热键和原生 Windows 热键验收仍未做 |
| 可替换区域式 streaming | 未实现 | 结构化内容去重已基础收口；长期更稳的 streaming + final render 仍需设计 |
| task 面板持久展示 | 待后续迭代 | `task_create/update` auto-allow + 瞬时面板已完成；持久底部驻留展示未做 |
| `/resume` last_user_input 不稳定 | 仅记录 | 同一 session 的预览文案随时间变化，用户难识别；后续可考虑首条输入或固定摘要 |
| 原生 Windows E2E | 核心 CLI 完成；QQchat 待验收 | `/resume`、`/compact`、多轮 tool call 和 MCP 已通过；`/QQchat start` 与真实 QQ 平台仍待验收 |
| Phase 5 | 整体冻结，MCP 小步例外 | 不全面扩展生态；MCP 仅允许按已写 spec/plan 小步推进 |

## 4. P0/P1：QQchat 收口

QQchat 第一版代码已实现 `/QQchat start|stop|status`，并已完成自动化和 review 加固；仍不能标记为完整完成，因为真实 QQ 平台和原生 Windows 手工验收尚未完成。

近期只做：

- `/QQchat init`
- `/QQchat reload`
- 真实 QQ 单聊被动回复验收
- 真实 QQ 群聊 @ 被动回复验收
- 原生 PowerShell/cmd.exe 中 `/QQchat start|stop|status` 与 prompt_toolkit 并存验收

暂不做：

- Webhook
- 富媒体
- 频道消息
- 主动推送
- 远程危险工具审批
- 多 IM connector 抽象

核心安全边界保持不变：

- QQ 消息是外部不可信输入。
- QQ turn 使用独立 session/history，不复用本地 REPL `_history`。
- QQ turn 默认只读 `ToolScope`。
- 远程 QQ 用户不能审批危险工具。
- AppSecret、AccessToken、Authorization header 不得进入项目配置、session transcript、audit event、错误输出或测试快照。

## 5. P0/P1：compact 现场恢复与 checkpoint 链路

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY restored-context `/compact`、v3 `/resume` 和 QQchat 平台手工验收未执行/未记录。

文档：

- `docs/superpowers/specs/2026-06-12-compact-state-restoration-design.md`
- `docs/superpowers/plans/2026-06-12-compact-state-restoration-plan.md`

目标是在现有 compact v2 可靠性基线之上继续增强两件事：

1. compact 后注入 bounded `Compact restored context` system message，恢复 active file、最近读过的文件 excerpt/hash、latest diagnostics、latest build/test、current plan 和 invoked skill metadata。
2. checkpoint 从 `xcode.v2` 演进到兼容的 `xcode.v3` lineage metadata，记录 `checkpoint_id`、`parent_checkpoint_id`、summary/restored-context hash、累计序号和可选 message range。

已落地范围：

- `WorkStateTracker` 记录 bounded active/recent files、shell diagnostics、search summary 和 skill metadata，并在 tool loop 中 best-effort 更新。
- compact 成功后插入 `Compact restored context` system message；summary rejection 时不写 restored context。
- compact 运行时 `_history` 不再固定保留第一条 user message；第一条用户意图和约束由累计 summary 承担，latest user 仍由 pair-safe tail 保护。
- restored context 的 secret redaction 已扩展到 QQBot/Basic/Token Authorization、JSON/YAML/冒号/等号形式 token、CLI secret 参数和 `QQ_BOT_CLIENT_SECRET` 等常见形态；`xcodebuild test`/`swift test`/JS test 命令归入 latest tests，plan-mode 会写入 current plan。
- checkpoint metadata 使用兼容的 `summary_format=xcode.v3`，记录 checkpoint id、parent id、summary/restored-context hash、checkpoint index 和 restored-context sections。
- `/resume` 对 v3 checkpoint 恢复 boundary + summary + restored context；旧 v1/v2 checkpoint 继续兼容。
- 本地 REPL 和 QQchat/external conversation 的 work state 使用独立 tracker。

下一步：补齐 PowerShell/cmd.exe 原生 PTY `/compact` with restored context、v3 `/resume`、QQchat same-conversation continuation 和 conversation isolation 手工验收；真实 QQ 平台验收未完成前，本项仍保留在 ROADMAP。

约束：

- 不引入 asyncio、embedding、vector DB 或后台索引服务。
- 不把完整文件、完整 shell 输出、secret、skill body 或 MCP secret 写入 restored context。
- 本地 REPL 和 QQchat/external conversation 的 work state 必须隔离。
- summary rejection 仍然不能写 checkpoint、不能改写 `_history`、不能插入 restored context。

## 6. P1：`/context` cost 估算

目标是在 `/context` 中展示近似费用，而不只是 token 数。

推荐设计：

- 短期维护小型价格表，未知模型显示 `cost: unknown`。
- 或在 `Config` 中增加可选价格字段：

```python
pricing_model: str = ""
input_cost_per_1m: float | None = None
output_cost_per_1m: float | None = None
```

验收：

- 未知模型不报错。
- 已知模型显示 input/output/total 估算。
- 文案明确是 estimate，不是账单。

## 7. P1：工具调用 UI 和渲染体验

### 7.1 工具调用展开

当前默认已折叠为工具摘要，但 `Ctrl+O` 展开尚未实现和验收。

后续方向：

- 保持默认摘要紧凑。
- `Ctrl+O` 展开当前或最近工具调用的完整参数和结果。
- diff preview 和审批菜单不能被折叠隐藏。
- 原生 Windows 中验证热键不干扰 prompt 输入。

### 7.2 渲染模式完善

当前已支持：

- `streaming_plus_final_render`
- `buffer_then_render`

后续需要明确：

- 纯流式模式是否保留。
- 结构化内容何时停止 raw streaming。
- 是否采用可替换区域式 streaming + final render，彻底避免重复输出。

## 8. P1：对话回退和分叉

目标：支持用户回到某一轮对话继续，但不破坏原始 session。

推荐模型：fork-based rollback。

```text
原 session 保持 append-only
选择 turn N
创建新 session_id
复制 turn N 之前的可恢复 history
后续对话写入新 session
```

建议命令：

```text
/session history
/session fork <turn>
/session rollback <turn>
```

关键边界：

- turn 优先按 user/assistant pair 展示，不把每条 tool message 暴露给用户。
- 普通文本恢复可以先做；结构化 tool history fork 要依赖现有 transcript schema，小步验证。

## 9. P1：task 面板持久展示

当前 task 面板已经能在工具执行后瞬时渲染，但不会像 Claude Code 一样持续驻留底部。

后续方向：

- 评估 prompt_toolkit bottom toolbar 或固定区域。
- 验证与 Rich Live、streaming、审批菜单共存。
- 原生 Windows 验收优先于视觉增强。

## 10. Phase 5：生态扩展候选

Phase 5 整体仍冻结。MCP 只允许在已完成的 stdio tools 基线之上按 spec 小步推进；不得把已完成的 MCP Phase 1/2 当作继续扩张到 HTTP/OAuth/resources/prompts 的默认许可。

候选能力：

| 能力 | 备注 |
|------|------|
| WebFetch | 需要网络权限、安全边界和缓存策略 |
| WebSearch | 需要 provider 抽象和引用展示 |
| Cron / automation | 先明确本地线程、系统计划任务还是外部调度 |
| Git tools | 需要强权限边界，避免误操作 |
| Hooks | 需要定义触发点、失败策略和用户可见性 |
| Remote skills / skill search | 需要信任模型、签名、安装和禁用策略 |
| MCP HTTP/SSE/OAuth/resources/prompts/MCP Apps | 需要独立 spec、trust model、secret 边界和原生 Windows 验收 |
