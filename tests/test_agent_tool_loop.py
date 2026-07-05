from __future__ import annotations

import json
from pathlib import Path

from xcode_cli.core.agent import AgentRuntime
from xcode_cli.core.external_turn import ToolScope
from xcode_cli.core.llm import LLMResponse, ToolCall


def _setup_tmp_xcode_home(tmp_path: Path, monkeypatch) -> Path:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(
        json.dumps({"model": "test", "auto_memory": True}),
        encoding="utf-8",
    )
    for sub in ("sessions", "skills", "bin"):
        (xcode_dir / sub).mkdir(parents=True, exist_ok=True)
    return xcode_dir


def _make_agent(tmp_path: Path, monkeypatch) -> AgentRuntime:
    import xcode_cli.core.agent as agent_mod
    from unittest.mock import MagicMock

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    _setup_tmp_xcode_home(tmp_path, monkeypatch)
    monkeypatch.setattr(
        agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True,
    )
    monkeypatch.setattr(
        agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True,
    )
    monkeypatch.setattr(
        agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True,
    )
    agent = AgentRuntime()
    agent._session_id = "test-session"
    return agent


# ---------------------------------------------------------------------------
# multi-round tool call regression (Batch 0 safety net)
# ---------------------------------------------------------------------------

def test_llm_loop_continues_across_multiple_tool_rounds(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "README.md"})],
            )
        if calls[0] == 2:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_2", name="grep", args={"pattern": "Xcode", "path": "."})],
            )
        return LLMResponse(content="final answer", tool_calls=[])

    executed: list[str] = []
    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: executed.append("read_file") or "read result"
    agent.tools._tools["grep"].execute = lambda **kwargs: executed.append("grep") or "grep result"

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "final answer"
    assert calls[0] == 3
    assert executed == ["read_file", "grep"]
    assert [m["role"] for m in history] == ["assistant", "tool", "assistant", "tool"]
    assert agent.work_state.snapshot().active_file.endswith("README.md")


def test_llm_loop_handles_tool_error_and_continues(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_err", name="read_file", args={"path": "missing.txt"})],
            )
        return LLMResponse(content="recovered after error", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: (_ for _ in ()).throw(OSError("disk error"))

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "recovered after error"
    assert calls[0] == 2
    assert len(history) == 2
    assert history[0]["role"] == "assistant"
    assert history[1]["role"] == "tool"
    assert "Tool error" in history[1]["content"]


def test_llm_loop_allows_more_than_ten_tool_rounds(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] <= 12:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id=f"call_{calls[0]}", name="read_file", args={"path": "x"})],
            )
        return LLMResponse(content="final after many tools", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: "ok"

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "final after many tools"
    assert calls[0] == 13
    assert len([m for m in history if m.get("role") == "tool"]) == 12


def test_llm_loop_interrupts_after_user_denies_tool(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"})],
            )
        raise AssertionError("LLM should not be called again after local user denial")

    agent.llm.complete = fake_complete
    monkeypatch.setattr(agent.approval, "prompt", lambda tool_name, scope: "no")

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "User denied tool: run_shell"
    assert calls[0] == 1
    assert [m["role"] for m in history] == ["assistant", "tool", "system"]
    assert history[1]["content"] == "User denied tool: run_shell"
    assert history[2]["content"] == "[Request interrupted by user for tool use]"


def test_user_denial_skips_later_sibling_tool_calls(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]
    executed: list[str] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"}),
                    ToolCall(id="call_read", name="read_file", args={"path": "README.md"}),
                ],
            )
        raise AssertionError("LLM should not be called again after local user denial")

    agent.llm.complete = fake_complete
    agent.tools._tools["run_shell"].execute = lambda **kwargs: executed.append("run_shell") or "shell result"
    agent.tools._tools["read_file"].execute = lambda **kwargs: executed.append("read_file") or "read result"
    monkeypatch.setattr(agent.approval, "prompt", lambda tool_name, scope: "no")

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "User denied tool: run_shell"
    assert calls[0] == 1
    assert executed == []
    assert [m["role"] for m in history] == ["assistant", "tool", "system"]
    assert history[0]["tool_calls"] == [
        {
            "id": "call_shell",
            "type": "function",
            "function": {"name": "run_shell", "arguments": json.dumps({"command": "echo hi"})},
        }
    ]
    assert history[1]["tool_call_id"] == "call_shell"
    assert history[2]["content"] == "[Request interrupted by user for tool use]"


def test_explicit_permission_deny_still_allows_model_followup(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    settings_dir = Path(agent.cwd) / ".xcode"
    settings_dir.mkdir(exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"run_shell": "deny"}}),
        encoding="utf-8",
    )
    calls = [0]
    executed: list[str] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"})],
            )
        assert any(
            m.get("role") == "tool" and "Permission denied for tool: run_shell" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="continued after config deny", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["run_shell"].execute = lambda **kwargs: executed.append("run_shell") or "shell result"

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "continued after config deny"
    assert calls[0] == 2
    assert executed == []


def test_next_user_turn_sees_prior_tool_denial_and_interruption_marker(
    tmp_path: Path, monkeypatch
) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "_start_memory_prefetch", lambda query: None)
    monkeypatch.setattr(agent.approval, "prompt", lambda tool_name, scope: "no")
    calls = [0]
    second_turn_messages: list[dict] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"})],
            )
        second_turn_messages.extend(kwargs["messages"])
        return LLMResponse(content="second turn answer", tool_calls=[])

    agent.llm.complete = fake_complete

    agent._run_user_turn("please run this")
    agent._run_user_turn("now continue")

    assert calls[0] == 2
    assert [message["role"] for message in second_turn_messages] == [
        "user",
        "assistant",
        "tool",
        "system",
        "user",
    ]
    assert second_turn_messages[2]["content"] == "User denied tool: run_shell"
    assert second_turn_messages[3]["content"] == "[Request interrupted by user for tool use]"
    assert second_turn_messages[4]["content"] == "now continue"


def test_llm_loop_empty_response_returns_readable_fallback(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent.llm.complete = lambda **kwargs: LLMResponse(content="", tool_calls=[])

    result = agent._run_llm_loop([], "system")

    assert result == "No response."


def test_llm_loop_converts_unexpected_llm_exception_to_error_text(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)

    def fail_complete(**kwargs):
        raise RuntimeError("transport exploded")

    agent.llm.complete = fail_complete

    result = agent._run_llm_loop([], "system")

    assert result.startswith("[v0] LLM request failed:")
    assert "transport exploded" in result


def test_llm_loop_buffer_then_render_prints_final_answer(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    cfg = agent.config_store.load()
    cfg.response_render_mode = "buffer_then_render"
    agent.config_store.save(cfg)
    agent.llm.complete = lambda **kwargs: LLMResponse(content="buffered final answer", tool_calls=[])

    printed: list[str] = []
    monkeypatch.setattr(agent.shell_ui, "print_assistant_bubble", lambda text: printed.append(text))
    monkeypatch.setattr(agent.shell_ui, "render_assistant_prefix", lambda: None)

    result = agent._run_llm_loop([], "system")

    assert result == "buffered final answer"
    assert printed == ["buffered final answer"]


def test_llm_loop_filters_tool_schemas_for_entry_tool_scope(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    seen_tool_names: list[list[str]] = []

    def fake_complete(**kwargs):
        seen_tool_names.append(
            [schema["function"]["name"] for schema in kwargs["tool_schemas"]]
        )
        return LLMResponse(content="scoped answer", tool_calls=[])

    agent.llm.complete = fake_complete
    scope = ToolScope(
        source="qqchat",
        visible_tools=("read_file", "grep"),
        execution_allowlist=("read_file", "grep"),
        remote_approval=False,
    )

    result = agent._run_llm_loop([], "system", tool_scope=scope)

    assert result == "scoped answer"
    assert "read_file" in seen_tool_names[0]
    assert "grep" in seen_tool_names[0]
    assert "write_file" not in seen_tool_names[0]
    assert "run_shell" not in seen_tool_names[0]


def test_llm_loop_blocks_tool_calls_outside_execution_scope(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]
    scope = ToolScope(
        source="qqchat",
        visible_tools=("read_file",),
        execution_allowlist=("read_file",),
        remote_approval=False,
    )

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"})],
            )
        assert any(
            m.get("role") == "tool" and "blocked by entry tool scope" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="continued safely", tool_calls=[])

    agent.llm.complete = fake_complete

    result = agent._run_llm_loop([], "system", tool_scope=scope)

    assert result == "continued safely"
    assert calls[0] == 2


def test_external_llm_loop_does_not_render_to_terminal(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    printed: list[object] = []

    cfg = agent.config_store.load()
    cfg.response_render_mode = "buffer_then_render"
    agent.config_store.save(cfg)

    agent.llm.complete = lambda **kwargs: LLMResponse(content="external final", tool_calls=[])
    monkeypatch.setattr(agent.console, "print", lambda *args, **kwargs: printed.append(args))
    monkeypatch.setattr(agent.shell_ui, "print_assistant_bubble", lambda text: printed.append(("bubble", text)))
    monkeypatch.setattr(agent.shell_ui, "render_assistant_prefix", lambda: printed.append(("prefix",)))

    result = agent._run_external_llm_loop(
        history=[],
        system_prompt="system",
        tool_scope=ToolScope(
            source="qqchat",
            visible_tools=("read_file",),
            execution_allowlist=("read_file",),
            remote_approval=False,
        ),
        session_id="external-session",
    )

    assert result == "external final"
    assert printed == []


def test_external_llm_loop_does_not_update_local_tool_stats(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]
    agent._tool_call_count = 5

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_read", name="read_file", args={"path": "missing.txt"})],
            )
        return LLMResponse(content="external done", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(agent.console, "print", lambda *args, **kwargs: None)

    result = agent._run_external_llm_loop(
        history=[],
        system_prompt="system",
        tool_scope=ToolScope(
            source="qqchat",
            visible_tools=("read_file",),
            execution_allowlist=("read_file",),
            remote_approval=False,
        ),
        session_id="external-session",
    )

    assert result == "external done"
    assert agent._tool_call_count == 5


def test_external_llm_loop_uses_supplied_work_state_instead_of_local_state(tmp_path: Path, monkeypatch) -> None:
    from xcode_cli.core.work_state import WorkStateTracker

    agent = _make_agent(tmp_path, monkeypatch)
    external_state = WorkStateTracker(cwd=agent.cwd)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_read", name="read_file", args={"path": "README.md"})],
            )
        return LLMResponse(content="external done", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: "external read"
    monkeypatch.setattr(agent.console, "print", lambda *args, **kwargs: None)

    result = agent._run_external_llm_loop(
        history=[],
        system_prompt="system",
        tool_scope=ToolScope(
            source="qqchat",
            visible_tools=("read_file",),
            execution_allowlist=("read_file",),
            remote_approval=False,
        ),
        session_id="external-session",
        work_state=external_state,
    )

    assert result == "external done"
    assert external_state.snapshot().active_file.endswith("README.md")
    assert agent.work_state.snapshot().active_file == ""


def test_qq_tool_scope_rejects_non_read_only_allowlisted_tools(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]
    scope = ToolScope(
        source="qqchat",
        visible_tools=("task_create",),
        execution_allowlist=("task_create",),
        remote_approval=False,
    )

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_task",
                        name="task_create",
                        args={"subject": "remote task", "description": "from qq"},
                    )
                ],
            )
        assert any(
            m.get("role") == "tool" and "not read-only" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="blocked", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(agent.console, "print", lambda *args, **kwargs: None)

    result = agent._run_llm_loop([], "system", tool_scope=scope)

    assert result == "blocked"
    assert agent.task_tracker.list_all() == []


def test_dispatch_agent_default_allow_skips_approval_prompt(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]
    approvals: list[str] = []
    executed: list[dict] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_dispatch",
                        name="dispatch_agent",
                        args={"agent_type": "explore", "prompt": "Inspect README.md"},
                    )
                ],
            )
        return LLMResponse(content="continued after dispatch", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(
        agent.approval,
        "prompt",
        lambda tool_name, scope: approvals.append(f"{tool_name}:{scope}") or "no",
    )
    agent.tools._tools["dispatch_agent"].execute = (
        lambda **kwargs: executed.append(kwargs) or "sub-agent result"
    )

    result = agent._run_llm_loop([], "system")

    assert result == "continued after dispatch"
    assert approvals == []
    assert executed == [{"agent_type": "explore", "prompt": "Inspect README.md"}]


def test_dispatch_agent_explicit_deny_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    settings_dir = Path(agent.cwd) / ".xcode"
    settings_dir.mkdir(exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"dispatch_agent": "deny"}}),
        encoding="utf-8",
    )
    calls = [0]
    executed: list[dict] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_dispatch",
                        name="dispatch_agent",
                        args={"agent_type": "explore", "prompt": "Inspect README.md"},
                    )
                ],
            )
        assert any(
            m.get("role") == "tool"
            and "Permission denied for tool: dispatch_agent" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="continued without dispatch", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["dispatch_agent"].execute = (
        lambda **kwargs: executed.append(kwargs) or "sub-agent result"
    )

    result = agent._run_llm_loop([], "system")

    assert result == "continued without dispatch"
    assert executed == []


def test_dispatch_agent_explicit_ask_prompts_and_user_denial_interrupts(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    settings_dir = Path(agent.cwd) / ".xcode"
    settings_dir.mkdir(exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"dispatch_agent": "ask"}}),
        encoding="utf-8",
    )
    calls = [0]
    approvals: list[str] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_dispatch",
                        name="dispatch_agent",
                        args={"agent_type": "explore", "prompt": "Inspect README.md"},
                    )
                ],
            )
        raise AssertionError("LLM should not be called again after local user denial")

    agent.llm.complete = fake_complete
    monkeypatch.setattr(
        agent.approval,
        "prompt",
        lambda tool_name, scope: approvals.append(f"{tool_name}:{scope}") or "no",
    )

    result = agent._run_llm_loop([], "system")

    assert result == "User denied tool: dispatch_agent"
    assert approvals == ["dispatch_agent:dispatch_agent"]
    assert calls[0] == 1
