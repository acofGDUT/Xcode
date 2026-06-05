# Task 6: 实现 allowed-tools 当前 turn 白名单

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Modify: `src/xcode_cli/core/tool_registry.py`
- Modify: `src/xcode_cli/core/tooling/execution.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_skill_allowed_tools.py`

- [ ] **Step 1: 写 tool schema 过滤测试**

创建 `tests/test_skill_allowed_tools.py`：

```python
from xcode_cli.core.tool_registry import ToolDef, ToolRegistry


def _tool(name):
    return ToolDef(
        name=name,
        description=name,
        parameters={},
        required=[],
        execute=lambda: "ok",
        is_read_only=True,
    )


def test_get_openai_schemas_filters_allowed_tools():
    registry = ToolRegistry()
    registry.register(_tool("read_file"))
    registry.register(_tool("edit_file"))

    schemas = registry.get_openai_schemas(allowed_tools=["read_file"])

    names = [s["function"]["name"] for s in schemas]
    assert names == ["read_file"]


def test_allowed_tools_do_not_override_permission_denies(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    import xcode_cli.core.agent as agent_mod
    import xcode_cli.paths
    from xcode_cli.core.agent import AgentRuntime
    from xcode_cli.core.llm import LLMResponse, ToolCall

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True)
    (xcode_dir / "config.json").write_text("{}", encoding="utf-8")
    for sub in ("sessions", "skills", "bin"):
        (xcode_dir / sub).mkdir(parents=True, exist_ok=True)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)

    agent = AgentRuntime()
    agent._session_id = "test-session"
    agent._current_allowed_tools = ["edit_file"]
    agent.permissions.set_session_rule("edit_file", "deny")
    executed = []
    agent.tools._tools["edit_file"].execute = lambda **kwargs: executed.append(kwargs) or "edited"

    calls = [0]

    def complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_denied_edit",
                        name="edit_file",
                        args={"path": str(project_dir / "app.py"), "old_string": "a", "new_string": "b"},
                    )
                ],
            )
        return LLMResponse(content="done", tool_calls=[])

    agent.llm.complete = complete

    result = agent._run_llm_loop([], "system")

    assert result == "done"
    assert executed == []
```

- [ ] **Step 2: 修改 ToolRegistry**

`get_openai_schemas()` 支持：

```python
def get_openai_schemas(self, allowed_tools: list[str] | None = None) -> list[dict]:
    allowed = set(allowed_tools) if allowed_tools else None
    schemas = []
    for tool in self._tools.values():
        if allowed is not None and tool.name not in allowed:
            continue
        schemas.append(tool.to_openai_schema())
    return schemas
```

- [ ] **Step 3: 执行层兜底**

`ToolCallExecutor.execute()` 增加参数：

```python
def execute(self, response, allowed_tools: list[str] | None = None):
```

当 `allowed_tools` 非空且 tool name 不在集合中，生成 tool result：

```text
Tool error: tool '<name>' is not allowed by the current skill.
```

不要抛异常，不要打断主循环。

`allowed-tools` 只收窄当前 turn 的工具集合，不自动提升权限。危险工具仍必须走 `PermissionManager` 的 allow/ask/deny，显式 deny 永远优先。不要因为 skill 声明了 `write_file`、`edit_file` 或 `run_shell` 就跳过审批。

- [ ] **Step 4: AgentRuntime 传递当前 turn allowed-tools**

`_run_user_turn()` 保存当前 turn allowed-tools：

```python
self._current_allowed_tools = turn.allowed_tools
```

`_run_llm_loop()` 调用：

```python
self.tools.get_openai_schemas(allowed_tools=self._current_allowed_tools)
self.tool_executor.execute(response, allowed_tools=self._current_allowed_tools)
```

普通 turn 使用 `None`，行为不变。

- [ ] **Step 5: 运行测试**

Run:

```powershell
pytest tests/test_skill_allowed_tools.py tests/test_agent_tool_loop.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/xcode_cli/core/tool_registry.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/agent.py tests/test_skill_allowed_tools.py tests/test_agent_tool_loop.py
git commit -m "feat: scope tools for skill turns"
```
