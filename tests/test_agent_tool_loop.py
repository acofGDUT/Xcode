from __future__ import annotations

import json
from pathlib import Path

from xcode_cli.core.agent import AgentRuntime
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


def test_llm_loop_continues_after_user_denies_tool(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"})],
            )
        assert any(
            m.get("role") == "tool" and "User denied tool" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="I will continue without shell.", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(agent.approval, "prompt", lambda tool_name, scope: "no")

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "I will continue without shell."
    assert calls[0] == 2


def test_llm_loop_empty_response_returns_readable_fallback(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent.llm.complete = lambda **kwargs: LLMResponse(content="", tool_calls=[])

    result = agent._run_llm_loop([], "system")

    assert result == "No response."


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
