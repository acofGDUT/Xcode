from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.agent import AgentRuntime
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult


def _make_agent(tmp_path: Path, monkeypatch) -> AgentRuntime:
    import xcode_cli.paths
    import xcode_cli.core.agent as agent_mod

    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    xcode_dir = tmp_path / ".xcode"
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(json.dumps({"auto_memory": True, "model": "test"}), encoding="utf-8")
    for subdir in ("sessions", "skills", "bin"):
        (xcode_dir / subdir).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)
    agent = AgentRuntime()
    agent._session_id = "session-1"
    return agent


def _event(text: str) -> AfterTurnSuccessEvent:
    return AfterTurnSuccessEvent(
        session_id="session-1",
        cwd="D:/Xcode",
        user_display_content=text,
        user_model_content=text,
        assistant_text="Done.",
        recent_history=[{"role": "user", "content": text}, {"role": "assistant", "content": "Done."}],
        wrote_memory_this_turn=False,
    )


class RecordingRunner:
    def __init__(self) -> None:
        self.submissions = []
        self.shutdown_calls = []

    def submit(self, event, *, auto_memory_enabled: bool) -> None:
        self.submissions.append((event, auto_memory_enabled))

    def latest_result(self):
        return MemoryExtractionResult(action="skipped", reason="test")

    def shutdown(self, wait: bool = False) -> None:
        self.shutdown_calls.append(wait)


def test_agent_after_turn_submits_to_memory_runner(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    runner = RecordingRunner()
    agent.memory_extraction_runner = runner

    agent._run_memory_extraction_hook(_event("remember review preference"))

    assert len(runner.submissions) == 1
    assert runner.submissions[0][1] is True


def test_agent_memory_hook_submit_exception_is_swallowed(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)

    class BrokenRunner:
        def submit(self, event, *, auto_memory_enabled: bool) -> None:
            raise RuntimeError("boom")

    agent.memory_extraction_runner = BrokenRunner()

    agent._run_memory_extraction_hook(_event("remember this"))


def test_run_chat_shutdowns_memory_runner(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    runner = RecordingRunner()
    agent.memory_extraction_runner = runner
    monkeypatch.setattr(agent.prompt, "prompt", lambda *args, **kwargs: "/exit")

    agent.run_chat()

    assert runner.shutdown_calls == [False]
