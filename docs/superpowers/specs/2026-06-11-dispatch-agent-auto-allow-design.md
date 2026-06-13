# dispatch_agent 免审优化设计

> 本文只描述本轮优化设计和交付要求，不直接修改功能代码。

## 背景

当前 `dispatch_agent` 由主 Agent 作为工具调用，用于把探索、规划或局部分析任务交给子 Agent。它在 `src/xcode_cli/core/tools/agent_tool.py` 中注册为 `is_read_only=False`，因此默认权限会落到 `PermissionManager._default_level()` 的兜底 `ask`，触发用户审批。

这个行为在体验上偏重：`dispatch_agent` 本身不直接写文件、不运行 shell，也不会把危险工具暴露给 EXPLORE / PLAN 子 Agent。它更接近本地编排能力，而不是外部副作用工具。长任务中频繁分派子 Agent 时，每次审批会打断主循环，也削弱“强 Agent / 架构 Agent”拆任务的流畅度。

## 目标

- 模型在本地 REPL 主会话中调用 `dispatch_agent` 时默认不需要用户审批。
- 免审只覆盖 `dispatch_agent` 这一层本地分派行为，不扩大子 Agent 工具权限。
- 保持 explicit `deny` 最高优先级：如果用户、项目或全局权限配置明确拒绝 `dispatch_agent`，仍必须拒绝执行。
- 保持 QQchat 等外部入口安全边界：远程 QQ turn 仍不能调用 `dispatch_agent`。
- 用聚焦测试锁住权限行为，避免未来把免审扩散到危险工具。

## 非目标

- 不让子 Agent 获得写文件、shell 或再次派发子 Agent 的能力。
- 不改变 `write_file`、`edit_file`、`run_shell`、MCP 非只读工具的审批策略。
- 不新增远程用户审批能力。
- 不解决子 Agent 长任务自动压缩、checkpoint 或 resume 问题；那是独立设计。
- 不把所有本地 orchestration 工具都默认免审，本轮只处理 `dispatch_agent`。

## 当前行为

现有链路：

1. `AgentRuntime` 注册 `dispatch_agent` 工具。
2. LLM 返回 `dispatch_agent` tool call。
3. `ToolCallExecutor.execute()` 调用 `permissions.check(tc.name, is_read_only=self.tools.is_read_only(tc.name))`。
4. 因 `dispatch_agent.is_read_only=False` 且没有默认 allow 规则，`PermissionManager` 返回 `ask`。
5. `ToolApprovalController.prompt()` 弹出审批菜单。

QQchat 入口另有保护：

- `ExternalTurnRunner.sanitize_tool_scope()` 会把 `dispatch_agent` 放在 forbidden tool 列表中。
- 即使配置尝试加入，QQchat 的 visible / execution allowlist 也会过滤掉该工具。

## 推荐方案

在 `PermissionManager._default_level()` 中把 `dispatch_agent` 加入默认 allow 列表，类似当前 `task_create` / `task_update` 的默认免审处理。

推荐理由：

- 改动范围最小，只调整权限默认值，不需要把 `dispatch_agent` 伪装成 read-only。
- explicit `deny`、project/global/session override 的优先级天然保持不变。
- `ToolCallExecutor` 的远程入口拦截、QQchat forbidden scope、子 Agent 工具白名单都不需要改变。
- 行为语义清晰：`dispatch_agent` 不是只读工具，而是“默认允许的本地编排工具”。

不推荐把 `dispatch_agent.is_read_only` 改成 `True`。虽然也能免审，但语义不准：子 Agent 会消耗 LLM 调用、读取项目内容，并可能产生较长推理结果；它不是纯读取工具。用权限默认 allow 更符合项目已有模式。

## 安全边界

- `dispatch_agent` 默认免审只适用于没有显式权限规则时。
- 如果 `.xcode/settings.json` 或 `~/.xcode/settings.json` 中配置：

```json
{
  "permissions": {
    "dispatch_agent": "deny"
  }
}
```

则工具必须被拒绝，不能弹审批、不能执行。

- 如果显式配置为 `ask`，应尊重配置并继续弹审批。
- QQchat 入口仍必须过滤 `dispatch_agent`，且测试应证明远程 turn 无法通过配置把它加回来。
- EXPLORE / PLAN 子 Agent 仍只注册 `read_file`、`grep`、`glob`；子 Agent 不注册 `dispatch_agent`，避免递归分派。

## 实现建议

优先修改：

- `src/xcode_cli/core/permissions.py`

建议把默认 allow 规则改成：

```python
if tool_name in {"task_create", "task_update", "dispatch_agent"}:
    return "allow"
```

如担心 `task_create` / `task_update` 与 `dispatch_agent` 语义混在一起，也可以拆成两个集合：

```python
DEFAULT_ALLOWED_TOOLS = {"task_create", "task_update", "dispatch_agent"}
```

但本轮不必为了一个新增项做过度抽象。

不建议修改：

- `src/xcode_cli/core/tools/agent_tool.py` 中的 `is_read_only=False`
- `src/xcode_cli/core/external_turn.py` 中的 `FORBIDDEN_EXTERNAL_TOOLS`
- `src/xcode_cli/core/sub_agent.py` 的只读工具白名单

## 测试要求

本轮属于 P0/P1 交界：权限行为属于 P0 安全路径，用户可见审批体验属于 P1。

必须新增或扩展测试：

- `tests/test_task_permissions.py` 或新增 `tests/test_dispatch_agent_permissions.py`
  - `PermissionManager.check("dispatch_agent") == "allow"`
  - project explicit `deny` 覆盖默认 allow
  - explicit `ask` 覆盖默认 allow
- `tests/test_agent_tool_loop.py`
  - LLM 调用 `dispatch_agent` 时不调用 `approval.prompt()`
  - 显式 deny 时不执行 `dispatch_agent`
- `tests/test_external_turn.py`
  - QQchat tool scope 继续过滤 `dispatch_agent`
  - 即使配置 visible / execution allowlist 包含 `dispatch_agent`，sanitize 后也不存在

建议验证命令：

```powershell
python -m py_compile src\xcode_cli\core\permissions.py src\xcode_cli\core\tools\agent_tool.py src\xcode_cli\core\external_turn.py src\xcode_cli\core\sub_agent.py
pytest tests\test_task_permissions.py tests\test_agent_tool_loop.py tests\test_external_turn.py -q
git diff --check
```

## 验收标准

- 本地 REPL 中模型调用 `dispatch_agent` 不再弹审批菜单。
- 用户显式配置 `dispatch_agent: deny` 时，工具调用返回权限拒绝结果。
- 用户显式配置 `dispatch_agent: ask` 时，仍走审批菜单。
- QQchat 远程入口仍看不到、也执行不了 `dispatch_agent`。
- 子 Agent 仍不能递归调用 `dispatch_agent`。
- 自动化测试和 `py_compile` 先通过，再更新完成结论。

## 文档收口

实现完成后同步：

- `docs/current/ARCHITECTURE.md`：权限默认行为中补充 `dispatch_agent` 默认 allow。
- `docs/current/DEVNOTES.md`：记录免审边界和 explicit deny 优先级。
- `docs/current/PROGRESS.md`：记录验证命令和结果。

如果实现只改权限默认值且测试通过，`ROADMAP.md` 不一定需要更新；除非后续把子 Agent 长任务压缩 / resume 一并纳入近期计划。
