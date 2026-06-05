# Task 6: 权限、审计和 Windows 回归

> Parent plan: [2026-06-05-qq-chat-integration-plan.md](../2026-06-05-qq-chat-integration-plan.md)
> Spec: [2026-06-05-qq-chat-integration-design.md](../../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P0。该 task 锁定 QQ 外部入口的安全边界：危险工具不可达、secret 不泄露、session 不串线、Windows 终端不被后台线程破坏。

**Files:**
- Modify: `src/xcode_cli/core/external_turn.py`
- Modify: `src/xcode_cli/qqchat/service.py`
- Modify: `src/xcode_cli/qqchat/config.py`
- Modify: `src/xcode_cli/qqchat/auth.py`
- Modify: `src/xcode_cli/qqchat/message_client.py`
- Test: `tests/test_external_turn.py`
- Test: `tests/test_qqchat_service.py`
- Test: `tests/test_qqchat_config.py`
- Test: `tests/test_qqchat_auth.py`
- Test: `tests/test_qqchat_message_client.py`

## Goal

在基础功能接入后专门做安全和交互回归，不把这些检查分散在前面任务里靠“顺手”。该 task 完成后，QQ 外部入口应满足 AGENTS 中 P0 安全与状态要求。

## Step 1: 补 secret 脱敏回归

在相关测试中补这些断言：

```python
def test_status_and_errors_do_not_include_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("QQ_BOT_APP_ID", "app")
    monkeypatch.setenv("QQ_BOT_CLIENT_SECRET", "super-secret")
    cfg = load_qqchat_config(project_root=tmp_path, user_config_path=tmp_path / "missing.json")

    rendered = str(cfg.safe_summary())

    assert "super-secret" not in rendered
    assert "<set>" in rendered
```

对 `QQAuthClient` 和 `QQMessageClient` 的错误测试也要断言：

- 不包含 `client_secret`
- 不包含 `access_token`
- 不包含 `Authorization`

Run:

```powershell
pytest tests/test_qqchat_config.py tests/test_qqchat_auth.py tests/test_qqchat_message_client.py -q
```

Expected: PASS。

## Step 2: 补危险工具不可达测试

在 `tests/test_external_turn.py` 中增加：

```python
def test_qq_turn_never_allows_dangerous_tools_even_if_config_attempts_to_add_them():
    sessions = FakeSessionStore()
    loop = FakeLoop()
    runner = ExternalTurnRunner(
        session_store=sessions,
        run_llm_loop=loop,
        build_system_prompt=lambda: "system",
        default_tool_scope=ToolScope(
            source="qqchat",
            visible_tools=("read_file", "grep", "glob", "task_list", "run_shell"),
            execution_allowlist=("read_file", "grep", "glob", "task_list", "run_shell"),
            remote_approval=True,
        ),
    )

    runner.run("qq:c2c:user-a", UserTurnInput("QQ: run command", "run command"))

    tool_scope = loop.calls[0][2]
    assert tool_scope.visible_tools == ("read_file", "grep", "glob", "task_list")
    assert tool_scope.execution_allowlist == ("read_file", "grep", "glob", "task_list")
    assert tool_scope.remote_approval is False
```

实现要求：

- ExternalTurnRunner 内部维护 `SAFE_QQ_TOOLS = ("read_file", "grep", "glob", "task_list")`。
- 对配置传入的 `ToolScope.visible_tools` 和 `ToolScope.execution_allowlist` 做交集过滤。
- 第一版无论配置如何传入，都强制 `remote_approval=False`。
- 如果过滤后为空，使用安全默认列表。

Run:

```powershell
pytest tests/test_external_turn.py -q
```

Expected: PASS。

## Step 3: 补 execution 层白名单回归

如果当前 `ToolCallExecutor` 已经检查 turn 级工具范围，新增测试证明 QQ `ToolScope` 同样会到执行层；如果没有覆盖，补测试并修复。

测试目标：

- 模型尝试调用 `run_shell`。
- 当前 turn `ToolScope.execution_allowlist` 只有 `read_file`。
- executor 返回 `Tool error` 或拒绝消息。
- 不执行 `run_shell` 的 execute function。

Run:

```powershell
pytest tests/test_agent_tool_loop.py tests/test_external_turn.py -q
```

Expected: PASS。

## Step 4: 补 session 串线回归

在 `tests/test_external_turn.py` 中确认：

- `qq:c2c:user-a` 与 `qq:c2c:user-b` 不共享 history。
- `qq:group:group-a:member:user-a` 与 `qq:group:group-a:member:user-b` 不共享 history。
- group shared mode 未显式开启时不使用 `qq:group:{group_openid}`。

Run:

```powershell
pytest tests/test_external_turn.py tests/test_qqchat_events.py -q
```

Expected: PASS。

## Step 5: 补 Windows/终端手工验收记录模板

在 `docs/reference/qq-bot-integration-guide.md` 的验收章节加入实现后必须填写的记录模板：

```markdown
### Windows 手工验收记录

- 日期：
- 终端：PowerShell / cmd.exe
- 命令：`xcode chat` -> `/QQchat status` -> `/QQchat start`
- 结果：
- 是否出现 prompt_toolkit 输入错乱：
- 是否出现后台线程抢屏：
- QQ 单聊被动回复结果：
- QQ 群聊 @ 被动回复结果：
- 危险工具请求结果：
```

该模板只有在真实验收后填写结果；没有真实 QQ 验收时保留为空或写“未执行”，不得写“通过”。

## Step 6: 运行聚焦测试

Run:

```powershell
pytest tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_config.py tests/test_qqchat_auth.py tests/test_qqchat_message_client.py tests/test_agent_tool_loop.py -q
```

Expected: PASS。

## Step 7: Review 检查点

Codex review 时重点检查：

- 是否有任何 secret/token 出现在错误字符串、status、transcript metadata 或测试 expected 文案中。
- QQ `ToolScope` 是否只是收窄能力，不提权。
- 是否没有把 skill `allowed-tools` 作为 QQ 外部入口安全字段。
- 执行层是否防止模型调用未暴露工具。
- session 隔离是否覆盖单聊和群聊。
- Windows 手工验收模板是否没有伪造结果。

## Step 8: 提交建议

```powershell
git add src/xcode_cli/core/external_turn.py src/xcode_cli/qqchat/service.py src/xcode_cli/qqchat/config.py src/xcode_cli/qqchat/auth.py src/xcode_cli/qqchat/message_client.py tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_config.py tests/test_qqchat_auth.py tests/test_qqchat_message_client.py docs/reference/qq-bot-integration-guide.md
git commit -m "test: harden qq chat security boundaries"
```
