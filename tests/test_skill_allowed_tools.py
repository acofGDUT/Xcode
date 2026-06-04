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


def test_disallowed_tool_call_is_returned_as_tool_error(tmp_path, monkeypatch):
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
    agent._current_allowed_tools = ["read_file"]
    executed = []
    agent.tools._tools["grep"].execute = lambda **kwargs: executed.append(kwargs) or "matched"

    calls = [0]

    def complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_disallowed_grep", name="grep", args={"pattern": "x", "path": "."})],
            )
        assert any(
            m.get("role") == "tool" and "not allowed by the current skill" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="done", tool_calls=[])

    agent.llm.complete = complete

    result = agent._run_llm_loop([], "system")

    assert result == "done"
    assert executed == []
