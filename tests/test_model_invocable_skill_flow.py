from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.llm import LLMResponse, ToolCall


def make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=None):
    import xcode_cli.core.agent as agent_mod
    import xcode_cli.paths
    from xcode_cli.core.agent import AgentRuntime

    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".xcode" / "skills" / "review"
    skill_dir.mkdir(parents=True)
    allowed_tools_block = ""
    if allowed_tools is not None:
        allowed_tools_block = "allowed-tools:\n" + "".join(f"  - {name}\n" for name in allowed_tools)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Review code changes\n"
        f"{allowed_tools_block}"
        "---\n"
        "Review $ARGUMENTS\n",
        encoding="utf-8",
    )
    xcode_dir = tmp_path / ".xcode-home"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)

    runtime = AgentRuntime()
    return runtime


def test_skill_tool_loads_prompt_and_narrows_followup_tool_schemas(tmp_path, monkeypatch):
    runtime = make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=["read"])
    runtime._session_id = runtime.sessions.new_session_id()

    seen_schemas = []
    seen_messages = []

    def fake_complete(system_prompt, messages, tool_schemas, on_text_token=None, on_reasoning_token=None):
        seen_schemas.append([schema["function"]["name"] for schema in tool_schemas])
        seen_messages.append(messages.copy())
        if len(seen_schemas) == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="skill", args={"skill": "review", "args": "src/foo.py"})],
            )
        return LLMResponse(content="review complete", tool_calls=[])

    runtime.llm.complete = fake_complete

    runtime._run_user_turn("review src/foo.py")

    assert "skill" in seen_schemas[0]
    assert seen_schemas[1] == ["read_file"]
    assert any('<xcode_loaded_skill name="review"' in str(msg) for msg in seen_messages[1])


def test_skill_tool_is_removed_after_loading_even_without_allowed_tools(tmp_path, monkeypatch):
    runtime = make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=None)
    runtime._session_id = runtime.sessions.new_session_id()
    seen_schemas = []

    def fake_complete(system_prompt, messages, tool_schemas, on_text_token=None, on_reasoning_token=None):
        seen_schemas.append([schema["function"]["name"] for schema in tool_schemas])
        if len(seen_schemas) == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="skill", args={"skill": "review", "args": "src/foo.py"})],
            )
        return LLMResponse(content="review complete", tool_calls=[])

    runtime.llm.complete = fake_complete

    runtime._run_user_turn("review src/foo.py")

    assert "skill" in seen_schemas[0]
    assert "skill" not in seen_schemas[1]
    assert "read_file" in seen_schemas[1]
