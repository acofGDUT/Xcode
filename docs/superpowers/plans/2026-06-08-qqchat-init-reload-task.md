# Task: `/QQchat init` 与热部署 reload

> Parent spec: [2026-06-08-qqchat-init-reload-design.md](../specs/2026-06-08-qqchat-init-reload-design.md)
> Related spec: [2026-06-05-qq-chat-integration-design.md](../specs/2026-06-05-qq-chat-integration-design.md)

**Risk layer:** P1。`/QQchat init` 和 `/QQchat reload` 是用户可见命令；secret 不覆盖、不泄露和 reload 异常不崩主循环按 P0 检查。

**Goal:** 增加两个 side-effect command：`/QQchat init` 幂等创建 QQchat 配置文件骨架；`/QQchat reload` 在不重启 Xcode REPL 的情况下重新加载配置，并在 service 运行中时重建连接。

## 涉及文件

优先修改：

- `src/xcode_cli/qqchat/config.py` 或新增 `src/xcode_cli/qqchat/config_init.py`
- `src/xcode_cli/core/agent.py`
- `src/xcode_cli/core/commands/slash.py`

优先补测试：

- `tests/test_qqchat_config.py` 或新增 `tests/test_qqchat_config_init.py`
- `tests/test_agent_user_turn.py`
- `tests/test_slash_dispatcher.py` 如 completion/dispatch 行为需要覆盖

文档收口：

- `docs/current/ARCHITECTURE.md`
- `docs/current/DEVNOTES.md`
- `docs/current/PROGRESS.md`
- 如 roadmap 状态变化，再更新 `docs/current/ROADMAP.md`

## 约束

- 不引入 `asyncio`。
- `/QQchat init` 和 `/QQchat reload` 都必须是 side-effect command，不进入普通 LLM turn，不写 session history。
- 项目级路径使用 `<project>/.xcode/config.json`，不要创建 `.xocde`，也不要创建无扩展名 `.xcode/config`。
- 项目级 config 不允许写入 `client_secret`、AccessToken 或 Authorization header。
- init 不覆盖用户已有配置；损坏 JSON 只报错，不自动重写。
- reload 捕获所有配置和 service 重建错误，不让主 REPL 崩溃。

## Step 1: 写失败测试

新增或扩展配置初始化测试：

```python
def test_init_qqchat_config_creates_project_and_user_files(tmp_path):
    from xcode_cli.qqchat.config_init import init_qqchat_config

    user_config = tmp_path / "home" / ".xcode" / "qqchat.json"
    result = init_qqchat_config(project_root=tmp_path / "project", user_config_path=user_config)

    project_config = tmp_path / "project" / ".xcode" / "config.json"
    assert project_config.exists()
    assert user_config.exists()
    assert "client_secret" not in project_config.read_text(encoding="utf-8")
    assert result.errors == ()
```

```python
def test_init_qqchat_config_is_idempotent_and_does_not_overwrite_secret(tmp_path):
    from xcode_cli.qqchat.config_init import init_qqchat_config

    project = tmp_path / "project"
    user_config = tmp_path / "home" / ".xcode" / "qqchat.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('{"app_id":"real-app","client_secret":"real-secret"}', encoding="utf-8")

    init_qqchat_config(project_root=project, user_config_path=user_config)
    init_qqchat_config(project_root=project, user_config_path=user_config)

    assert "real-secret" in user_config.read_text(encoding="utf-8")
```

```python
def test_init_qqchat_config_adds_missing_qqchat_section_without_overwriting_existing_keys(tmp_path):
    from xcode_cli.qqchat.config_init import init_qqchat_config

    project_config = tmp_path / "project" / ".xcode" / "config.json"
    project_config.parent.mkdir(parents=True)
    project_config.write_text('{"model":"test-model"}', encoding="utf-8")

    init_qqchat_config(project_root=tmp_path / "project", user_config_path=tmp_path / "qqchat.json")

    data = json.loads(project_config.read_text(encoding="utf-8"))
    assert data["model"] == "test-model"
    assert data["qqchat"]["enable_c2c"] is True
```

```python
def test_init_qqchat_config_reports_malformed_project_config_without_overwrite(tmp_path):
    from xcode_cli.qqchat.config_init import init_qqchat_config

    project_config = tmp_path / "project" / ".xcode" / "config.json"
    project_config.parent.mkdir(parents=True)
    project_config.write_text("{bad json", encoding="utf-8")

    result = init_qqchat_config(project_root=tmp_path / "project", user_config_path=tmp_path / "qqchat.json")

    assert result.errors
    assert project_config.read_text(encoding="utf-8") == "{bad json"
```

扩展 AgentRuntime 行为测试：

```python
def test_qqchat_init_command_does_not_enter_llm_turn(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    agent._run_user_turn = MagicMock()

    agent._handle_slash_command("/QQchat init")

    agent._run_user_turn.assert_not_called()
    assert (Path(agent.cwd) / ".xcode" / "config.json").exists()
```

```python
def test_qqchat_reload_recreates_service_without_starting_when_stopped(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    old_service = MagicMock()
    old_service.status.return_value = {"state": "stopped"}
    new_service = MagicMock()
    new_service.status.return_value = {"state": "stopped"}
    agent.qqchat_service = old_service
    agent._create_qqchat_service = MagicMock(return_value=new_service)

    agent._handle_qqchat_command(["/QQchat", "reload"])

    old_service.stop.assert_not_called()
    new_service.start.assert_not_called()
    assert agent.qqchat_service is new_service
```

```python
def test_qqchat_reload_restarts_when_running(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    old_service = MagicMock()
    old_service.status.return_value = {"state": "running"}
    new_service = MagicMock()
    new_service.status.return_value = {"state": "running"}
    agent.qqchat_service = old_service
    agent._create_qqchat_service = MagicMock(return_value=new_service)

    agent._handle_qqchat_command(["/QQchat", "reload"])

    old_service.stop.assert_called_once()
    new_service.start.assert_called_once()
    assert agent.qqchat_service is new_service
```

先运行：

```powershell
pytest tests/test_qqchat_config.py tests/test_agent_user_turn.py tests/test_slash_dispatcher.py -q
```

预期：失败，提示初始化 helper 或 reload 命令尚不存在。

## Step 2: 实现配置初始化 helper

推荐新增 `src/xcode_cli/qqchat/config_init.py`，实现：

```python
@dataclass(frozen=True)
class QQChatInitResult:
    project_config_path: Path
    user_config_path: Path
    created: tuple[Path, ...] = ()
    updated: tuple[Path, ...] = ()
    unchanged: tuple[Path, ...] = ()
    errors: tuple[str, ...] = ()

def init_qqchat_config(*, project_root: str | Path, user_config_path: str | Path | None = None) -> QQChatInitResult:
    ...
```

实现要求：

- 创建 `<project>/.xcode/config.json` 时使用 UTF-8 和 `indent=2`。
- 默认 `qqchat` object 与 spec 中模板一致，可复用 `default_tool_scope()`。
- 已有 project config 只补缺失 `qqchat` 字段；如果已有 `qqchat` object，可只补缺失 top-level 字段，不覆盖已有值。
- 创建 `~/.xcode/qqchat.json` 时只写 `app_id` 和 `client_secret` 空字符串。
- 捕获 `OSError` 和 `json.JSONDecodeError`，放入 `errors`，不抛到 REPL。

## Step 3: 注册命令和补全

修改 `src/xcode_cli/core/commands/slash.py`：

- `/QQchat` 描述更新为 `Start, stop, status, init, or reload QQ chat bridge`。
- completion 支持 `init` 和 `reload`。

如果 `SlashCommandDispatcher` 已经把 `/QQchat *` 全量交给 handler，不需要改 dispatcher；只在现有测试缺口下补一条 `/QQchat init` dispatch 测试即可。

## Step 4: 接入 AgentRuntime

修改 `_handle_qqchat_command(parts)`：

- action 允许集合改为 `{"init", "reload", "start", "stop", "status"}`。
- usage 改为 `Usage: /QQchat init|reload|start|stop|status`。
- `init`：
  - 调用 `init_qqchat_config(project_root=self.cwd)`。
  - 打印 created / updated / unchanged / errors 摘要。
  - 不要求当前 `qqchat_service` 可用。
- `reload`：
  - 判断旧 service 是否 running。
  - running 时先 `stop()`。
  - 调用 `_create_qqchat_service()` 重建。
  - 成功后清空 `_qqchat_init_error`。
  - 如果旧 service running，则对新 service 调 `start()`。
  - 任意异常写入 `_qqchat_init_error` 并打印可读错误。
- `start|stop|status` 保持现有行为，但 usage 和 status 输出要兼容 reload 后的新 service。

建议新增私有 helper，降低 `_handle_qqchat_command()` 膨胀：

```python
def _handle_qqchat_init_command(self) -> None: ...
def _handle_qqchat_reload_command(self) -> None: ...
def _qqchat_is_running(self) -> bool: ...
```

## Step 5: 验证

运行聚焦自动化：

```powershell
python -m py_compile src\xcode_cli\core\agent.py src\xcode_cli\core\commands\slash.py src\xcode_cli\qqchat\config.py src\xcode_cli\qqchat\config_init.py
pytest tests\test_qqchat_config.py tests\test_agent_user_turn.py tests\test_slash_dispatcher.py -q
git diff --check
```

如果新增独立测试文件，把命令中的测试文件替换为实际文件名。

手工验收记录需要包含：

```text
PowerShell:
  xcode chat
  /QQchat init
  /QQchat status
  /QQchat reload

cmd.exe:
  xcode chat
  /QQchat init
```

验收结论必须明确：未连接真实 QQ 平台时，只能说配置初始化和 reload 命令通过本地验收，不能说 QQ 真实接入完成。

## Review 检查点

- `/QQchat init` 是否会误写 `.xocde` 或 `.xcode/config`。
- 项目级 config 是否绝不包含 secret。
- 已有用户级 `qqchat.json` 是否绝不被覆盖。
- 损坏 JSON 是否保留原样。
- `/QQchat reload` 是否处理 running/stopped 两种状态。
- reload 失败是否不会让 REPL 崩溃。
- completion/help 是否包含新命令。

## 建议提交信息

```powershell
git add src/xcode_cli/qqchat/config_init.py src/xcode_cli/core/agent.py src/xcode_cli/core/commands/slash.py tests/test_qqchat_config.py tests/test_agent_user_turn.py tests/test_slash_dispatcher.py
git commit -m "feat: add qqchat init and reload commands"
```
