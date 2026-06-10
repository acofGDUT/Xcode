# Xcode 路线图

> 本文只记录未来计划、未完成能力和仍需验收的风险。已完成实现只保留状态索引；具体实现见 `ARCHITECTURE.md`，历史过程和验证证据见 `PROGRESS.md`，坑点和设计取舍见 `DEVNOTES.md`。

最后更新：2026-06-09

## 1. 当前状态

Xcode v0.1.0 已完成 Phase 1-4、Phase 4.5 稳定化、AgentRuntime 两轮重构、Skills Phase 1-2、QQchat 第一版代码实现和 review 加固，以及 MCP Phase 1 stdio tools 安全接入代码实现。MCP 自动化回归已覆盖 trust gate、默认非只读、schema/result 防御、failed 状态、timeout cancellation cleanup 和 shutdown；真实 PowerShell/cmd.exe 交互验收用户反馈已基本完成，待补具体记录。MCP Phase 2 设计已完成，范围限定为 stdio tools 的管理面、动态工具刷新和可观测性，尚未实现。

当前近期工作不应继续堆新大功能，而应优先收口：

- 原生 Windows cmd.exe / PowerShell 端到端交互验收。
- `/QQchat` 配置初始化、热部署 reload、真实 QQ 平台验收和文档最终验证。
- `/resume` 恢复后最近对话渲染：已写 spec/plan，待实现。
- `/context` cost 估算。
- MCP Phase 1 stdio tools 原生 Windows 手工验收：代码和自动化已完成，用户反馈 fake stdio server、审批 UI 和 `/exit` 子进程退出基本验收完成，仍需补具体记录。
- MCP Phase 2 管理面与动态工具刷新：已写 spec/plan/task，未实现。

Phase 5 生态扩展整体继续冻结；MCP 只按已写 spec 小步解冻。当前 Phase 2 仍限制在 stdio tools 管理面，不包含 HTTP/OAuth/resources/prompts/MCP Apps。

## 2. 近期优先级

| 优先级 | 能力 | 状态 | 下一步 |
|--------|------|------|--------|
| P0 | 原生 Windows E2E 验收 | 未完成 | 在 cmd.exe/PowerShell 覆盖审批菜单、diff preview、工具摘要折叠、多轮 tool call、`/resume` 长列表刷新、`/compact`、`/QQchat start` |
| P1 | QQchat Task 7 文档和最终验证 | 待执行 | 收口 `ARCHITECTURE/DEVNOTES/PROGRESS/ROADMAP` 与验证证据；未做真实 QQ 验收前不得声称完整接入 |
| P1 | QQchat Task 8：`/QQchat init` + reload | 已写 spec/plan，未实现 | 实现配置骨架初始化和热部署 reload，按 TDD 补测试 |
| P1 | `/resume` 长列表重复渲染 | 代码实现和自动化通过；Windows 手工验收待补 | 在原生 PowerShell/cmd.exe 中补长列表、窄窗口、中文预览连续滚动记录 |
| P1 | runtime status stale cleanup | 代码实现和自动化通过 | 后续 dashboard/list 如读取 runtime status 目录，应复用 `RuntimeStatusStore.prune_stale()` |
| P1 | `/resume` 恢复后最近对话渲染 | 已写 spec/plan，未实现 | 恢复成功后渲染最新 checkpoint 后的 user/assistant 对话，不展示 tool result 或 hidden prompt |
| P0 | MCP Phase 1：stdio tools 安全接入 | 代码实现和自动化通过；Windows 手工验收待补记录 | 补 PowerShell/cmd.exe fake stdio server、审批 UI 和 `/exit` shutdown 的具体验收记录 |
| P0/P1 | MCP Phase 2：管理面与动态工具刷新 | 已写 spec/plan/task，未实现 | 按 `2026-06-09-mcp-phase2-plan.md` 从 state store 开始实现 |
| P1 | `/context` cost 估算 | 未实现 | 在 token 统计外展示近似费用，未知模型显示 unknown |
| P1 | 工具调用 UI 展开 | 基础完成，展开未做 | 设计并验证 `Ctrl+O` 展开摘要，重点看原生 Windows 热键兼容 |
| P1 | task 面板持久展示 | 基础完成，待迭代 | 当前为瞬时渲染；后续评估底部驻留或 prompt_toolkit toolbar |
| P1 | 对话回退 / 分叉 | 未实现 | 设计 fork-based rollback，避免破坏原 session |
| P1 | 渲染模式完善 | 部分实现 | 明确 streaming、buffer、可替换区域式 final render 的边界 |
| P2 | skills 后续生态 | 冻结候选 | fork skill runtime、hooks、paths 自动激活、remote skills、skill search 暂不进入近期默认开发 |

## 3. P0：原生 Windows E2E 验收

目标是在真实 cmd.exe / PowerShell 中验证关键交互，而不是只依赖 pytest 或 Git Bash。

必须覆盖：

- prompt_toolkit 主输入循环。
- 审批方向键菜单：↑/↓、Enter、Esc、`y/n/a`。
- diff preview + 审批菜单共存。
- `/resume`：
  - 普通短列表选择。
  - 长列表连续方向键滚动。
  - 窄窗口和中文预览。
  - Esc 取消不污染 `_history`。
- `/compact` Rich Live 进度。
- 多轮 tool call 不被 UI 状态打断。
- `/QQchat status/start/stop` 与 prompt_toolkit 共存。
- QQchat reload / init 完成后，还要补 `/QQchat init|reload`。

验收记录应写入 `PROGRESS.md` 或对应 task closeout。没有原生 Windows 证据时，不应声称终端交互“完成”。

## 4. P1：QQchat 收口

QQchat 第一版代码已实现 `/QQchat start|stop|status`，并在 2026-06-08 做过 review 加固。当前仍不能标记为完整完成，因为真实 QQ 平台和原生 Windows 手工验收尚未执行。

### 4.1 Task 7：文档和最终验证

目标：

- 同步 `ARCHITECTURE.md`、`DEVNOTES.md`、`PROGRESS.md`、`ROADMAP.md`。
- 跑 QQchat 聚焦测试、`py_compile` 和 `git diff --check`。
- 明确记录未执行的真实 QQ 验收，不把自动化通过写成真实平台接入完成。

建议验证：

```powershell
python -m py_compile src\xcode_cli\core\agent.py src\xcode_cli\core\external_turn.py src\xcode_cli\core\commands\dispatcher.py src\xcode_cli\core\commands\slash.py src\xcode_cli\qqchat\config.py src\xcode_cli\qqchat\auth.py src\xcode_cli\qqchat\message_client.py src\xcode_cli\qqchat\events.py src\xcode_cli\qqchat\dedupe.py src\xcode_cli\qqchat\gateway.py src\xcode_cli\qqchat\service.py
pytest tests\test_qqchat_config.py tests\test_qqchat_auth.py tests\test_qqchat_events.py tests\test_qqchat_message_client.py tests\test_qqchat_gateway.py tests\test_qqchat_service.py tests\test_external_turn.py tests\test_slash_dispatcher.py tests\test_agent_tool_loop.py -q
git diff --check
```

### 4.2 Task 8：`/QQchat init` 与热部署 reload

目标：

- `/QQchat init` 幂等创建：
  - `<project>/.xcode/config.json`
  - `~/.xcode/qqchat.json`
- 项目级 config 只写非敏感字段；`client_secret` 只允许用户级配置或环境变量。
- `/QQchat reload` 重新加载配置；service 已运行时 stop 旧实例、重建、再 start。
- reload 失败不崩主 REPL，不泄露 secret。

文档：

- `docs/superpowers/specs/2026-06-08-qqchat-init-reload-design.md`
- `docs/superpowers/plans/2026-06-08-qqchat-init-reload-task.md`

## 5. P1：`/resume` 长列表重复渲染

状态：代码实现和自动化验证已通过；原生 PowerShell/cmd.exe 手工验收仍需补记录。

当前实现：

- `/resume` TTY 菜单改为固定高度窗口，每次最多显示 9 条 session。
- header 显示 `current/total`。
- 每条预览先单行化，并按显示宽度截断；窄窗口下 checkpoint 标记使用短标记。
- refresh 固定清理 `header + visible rows + footer` 行，不再按 `len(sessions) + 1` 清理。

文档：

- `docs/superpowers/specs/2026-06-08-resume-menu-rendering-fix-design.md`
- `docs/superpowers/plans/2026-06-08-resume-menu-rendering-fix-plan.md`

已验证：

- `python -m py_compile src\xcode_cli\core\conversation\resume.py src\xcode_cli\core\runtime_status.py src\xcode_cli\core\agent.py`
- `pytest tests\test_agent_resume_command.py tests\test_resume.py tests\test_runtime_status.py -q`：44 passed

仍需手工验收：

- PowerShell 和 cmd.exe 中构造 30 条以上 session，连续按 ↑/↓ 不残留旧行。
- 窄窗口和中文长预览不换行污染菜单。

## 6. P1：runtime status stale cleanup

状态：代码实现和自动化验证已通过。

当前模型：

- `RuntimeStatusStore` 写入 `~/.xcode/sessions/<pid>.json`。
- 正常退出时 `AgentRuntime.run_chat()` 的 `finally` 会调用 `delete()`。
- 强杀进程、断电、native crash、`os._exit()` 等意外退出不会执行 `finally`，会留下 stale status 文件。

当前实现：

- `RuntimeStatusStore.create()` 写入当前状态前调用 `prune_stale()` 扫描 `~/.xcode/sessions/*.json`。
- 保留仍存活 pid，删除已死亡 pid。
- 无法可靠判断 liveness 时使用 24 小时 TTL 兜底。
- 损坏 JSON、权限错误、删除失败都不会影响主 REPL 启动。

已验证：

- dead pid 文件删除、alive pid 文件保留、未知 liveness 的 TTL 兜底、损坏 JSON 不崩溃。
- `create/update/update_session_id/delete` 生命周期仍通过。

## 7. P1：`/context` cost 估算

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

## 8. P1：工具调用 UI 和渲染体验

### 8.1 工具调用展开

当前默认已折叠为工具摘要，但 `Ctrl+O` 展开尚未实现和验收。

后续方向：

- 保持默认摘要紧凑。
- `Ctrl+O` 展开当前或最近工具调用的完整参数和结果。
- diff preview 和审批菜单不能被折叠隐藏。
- 原生 Windows 中验证热键不干扰 prompt 输入。

### 8.2 渲染模式完善

当前已支持：

- `streaming_plus_final_render`
- `buffer_then_render`

后续需要明确：

- 纯流式模式是否保留。
- 结构化内容何时停止 raw streaming。
- 是否采用可替换区域式 streaming + final render，彻底避免重复输出。

## 9. P1：对话回退和分叉

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

## 10. P1：task 面板持久展示

当前 task 面板已经能在工具执行后瞬时渲染，但不会像 Claude Code 一样持续驻留底部。

后续方向：

- 评估 prompt_toolkit bottom toolbar 或固定区域。
- 验证与 Rich Live、streaming、审批菜单共存。
- 原生 Windows 验收优先于视觉增强。

## 11. 已完成归档

下列能力已完成或基础收口，未来 roadmap 不再保留详细实现设计。需要实现细节请看 `ARCHITECTURE.md`，需要过程和证据请看 `PROGRESS.md`。

| 能力 | 状态 |
|------|------|
| Phase 1-4 基础 agent、工具协议、权限、上下文 | 完成 |
| Phase 4.5 memory/path/context 稳定化 | 完成 |
| session resume 基础：UUID transcript、checkpoint + recent tail、`/compact`、`/resume` | 完成；CLI resume 延后 |
| `/compact` Rich Live 进度 | 完成 |
| `/resume` 方向键菜单基础版 | 完成；长列表渲染另列 bugfix |
| `/init` prompt command | 完成 |
| memory 自管理权限 | 完成 |
| 项目级 `.xcode/config.json` merge 和 `/env` TUI | 完成 |
| AgentRuntime Refactor Round 1-2 | 完成；`_run_llm_loop()` 仍暂不大动 |
| Skills As Prompt Commands | 完成 |
| Model-Invocable Skills / `SkillTool` | 完成；fork/hooks/remote/search 未包含 |
| Task 工具免审和瞬时 task 面板 | 基础完成 |
| 工具调用多轮不中断 | 核心完成；真实终端验收仍需补 |
| 流式输出重复显示 | 基础收口；可替换区域式 streaming 未实现 |
| QQchat 第一版代码和 review 加固 | 自动化通过；真实 QQ 和 Windows 手工验收未完成 |

## 12. Phase 5：生态扩展候选

Phase 5 整体仍冻结。MCP 是当前唯一按 spec 小步解冻的生态方向；它不是完整生态扩展，而是从 stdio tool provider 的安全接入逐步推进到管理面和动态刷新。

### 12.1 MCP Phase 1：stdio tools 安全接入

状态：代码实现和自动化回归已完成；真实 PowerShell/cmd.exe 手工验收用户反馈已基本完成，待补具体记录。

设计文档：

- `docs/superpowers/specs/2026-06-08-mcp-integration-design.md`
- `docs/superpowers/plans/2026-06-08-mcp-integration-plan.md`
- `docs/superpowers/plans/2026-06-08-mcp-integration/`

Phase 1 范围：

- 只做 `.xcode/mcp.json` 中的 stdio servers。
- trust gate 必须先于 server 启动；trust 绑定配置 hash，写入 `~/.xcode/mcp_trust.json`。
- MCP tool 命名为 `mcp__<server>__<tool>`，sanitize 后防冲突。
- MCP tool 默认 `is_read_only=False`，继续走 `PermissionManager` 和审批 UI。
- `MCPConnectionManager` 内部允许 async event loop/thread；`AgentRuntime` Phase 1 保持同步 wrapper，后续再逐步 async 化。
- `tools/list` schema 不兼容时跳过 tool 并记录 warning，不打崩 Agent。
- `tools/call` 结果进入 `_history` 前按 `max_mcp_output_chars` 截断。
- `/mcp status` 显示 connected/failed/untrusted/disabled、tool count 和 error summary。

Phase 1 不做：

- resources/prompts/HTTP/SSE/OAuth/list_changed。
- MCP prompts 转 slash commands。
- 自动下载/安装 MCP server 或 marketplace。
- tool search / lazy schema loading。
- 子 Agent 独立 MCP scope。

验收重点不是“能跑 filesystem server”，而是证明 Xcode 能安全、可审计、可失败恢复地把 trusted MCP stdio server 变成外部工具来源。

后续如果解冻其他 Phase 5 能力，必须逐项设计、逐项验收，不一次性铺开。

### 12.2 MCP Phase 2：管理面与动态工具刷新

状态：设计完成，待实现。

设计文档：

- `docs/superpowers/specs/2026-06-09-mcp-phase2-design.md`
- `docs/superpowers/plans/2026-06-09-mcp-phase2-plan.md`
- `docs/superpowers/plans/2026-06-09-mcp-phase2/`

Phase 2 范围：

- project-scoped 本机 `mcp_state.json`，保存 server/tool enable-disable 和 per-tool output limit，不写项目仓库。
- `/mcp status --verbose`、`/mcp tools`、`/mcp enable|disable`、`/mcp tool enable|disable`、`/mcp refresh`、`/mcp reconnect`、`/mcp events`。
- `notifications/tools/list_changed` 或等价 pending refresh event，在 AgentRuntime safe point 重建 MCP ToolDefs。
- ToolRegistry mutation 只在主线程 safe point，background MCP thread 不直接改 schema。
- lifecycle event ring buffer 和可观测 status，不泄露 env values。

Phase 2 不做：

- HTTP / Streamable HTTP / SSE。
- OAuth、dynamic headers、token refresh。
- resources、prompts、MCP Apps。
- marketplace、registry、企业 policy。
- 子 Agent 独立 MCP scope。
- model-driven tool search / lazy schema loading。

候选能力：

| Task | 能力 | 备注 |
|------|------|------|
| 5.1 | MCP stdio tools | 代码实现和自动化通过；P0 安全接入，不含 resources/prompts/HTTP/SSE/OAuth；Windows 手工验收待补记录 |
| 5.2 | MCP management + dynamic refresh | 已写设计和 task；只覆盖 stdio tools 管理面 |
| 5.3 | WebFetch | 需要网络权限、安全边界和缓存策略 |
| 5.4 | WebSearch | 需要 provider 抽象和引用展示 |
| 5.5 | Cron / automation | 先明确本地线程、系统计划任务还是外部调度 |
| 5.6 | Git tools | 需要强权限边界，避免误操作 |
| 5.7 | Hooks | 需要定义触发点、失败策略和用户可见性 |
| 5.8 | Remote skills / skill search | 需要信任模型、签名、安装和禁用策略 |

## 13. Phase 6：外部聊天入口

Phase 6 当前只围绕 QQchat 第一版收口，不扩大到更多 IM 或 Webhook。

近期只做：

- `/QQchat init`
- `/QQchat reload`
- QQchat Task 7 文档和最终验证
- 真实 QQ 单聊被动回复验收
- 真实 QQ 群聊 @ 被动回复验收
- 原生 PowerShell/cmd.exe 中 `/QQchat start` 与 prompt_toolkit 并存验收

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
