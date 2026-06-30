from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.agent import AgentRuntime
from xcode_cli.core.llm import LLMResponse, ToolCall


def _make_agent(tmp_path: Path, monkeypatch) -> AgentRuntime:
    import xcode_cli.paths
    import xcode_cli.core.agent as agent_mod

    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(json.dumps({"model": "test", "auto_memory": True}), encoding="utf-8")
    for sub in ("sessions", "skills", "bin"):
        (xcode_dir / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)
    agent = AgentRuntime()
    agent._session_id = "session-1"
    return agent


def _single_memory_write_then_reply(memory_path: Path):
    calls = [0]

    def complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_memory",
                        name="write_file",
                        args={"path": str(memory_path), "content": "memory body"},
                    )
                ],
            )
        return LLMResponse(content="assistant reply", tool_calls=[])

    return complete


def test_after_turn_hook_runs_after_successful_local_repl_turn(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    events = []
    agent.after_turn_hooks.register(lambda event: events.append(event))
    agent._run_llm_loop = MagicMock(return_value="assistant reply")

    agent._run_user_turn("remember my preference")

    assert len(events) == 1
    assert events[0].session_id == "session-1"
    assert events[0].user_display_content == "remember my preference"
    assert events[0].assistant_text == "assistant reply"
    assert agent._history[-1] == {"role": "assistant", "content": "assistant reply"}


def test_after_turn_hook_exception_does_not_break_reply(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent.after_turn_hooks.register(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    agent._run_llm_loop = MagicMock(return_value="assistant reply")

    agent._run_user_turn("hello")

    assert agent._history[-1] == {"role": "assistant", "content": "assistant reply"}


def test_after_turn_hook_does_not_run_on_llm_error(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    events = []
    agent.after_turn_hooks.register(lambda event: events.append(event))
    agent._run_llm_loop = MagicMock(return_value="[v0] LLM request failed: timeout")

    agent._run_user_turn("hello")

    assert events == []


def test_after_turn_hook_does_not_run_on_no_response(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    events = []
    agent.after_turn_hooks.register(lambda event: events.append(event))
    agent._run_llm_loop = MagicMock(return_value="No response.")

    agent._run_user_turn("hello")

    assert events == []


def test_after_turn_hook_reports_memory_written_this_turn(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    events = []
    agent.after_turn_hooks.register(lambda event: events.append(event))
    memory_path = agent.memory.memory_dir_path() / "preference.md"
    agent.llm.complete = _single_memory_write_then_reply(memory_path)

    agent._run_user_turn("remember this")

    assert events
    assert events[0].wrote_memory_this_turn is True
