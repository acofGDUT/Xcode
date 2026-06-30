from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.agent import AgentRuntime
from xcode_cli.core.llm import LLMResponse, ToolCall
from xcode_cli.core.memory_recall import MAX_SESSION_SURFACED_BYTES, RelevantMemoryResult, SurfacedMemory


def _setup_tmp_xcode_home(tmp_path: Path, monkeypatch, *, auto_memory: bool = True) -> None:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(
        json.dumps({"model": "test", "api_key": "test-key", "auto_memory": auto_memory}),
        encoding="utf-8",
    )
    for subdir in ("sessions", "skills", "bin"):
        (xcode_dir / subdir).mkdir(parents=True, exist_ok=True)


def _write_memory(path: Path, name: str = "review") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: Useful recall topic.\ntype: feedback\n---\nBody\n",
        encoding="utf-8",
    )


def _make_agent(tmp_path: Path, monkeypatch, *, auto_memory: bool = True) -> AgentRuntime:
    import xcode_cli.core.agent as agent_mod

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    _setup_tmp_xcode_home(tmp_path, monkeypatch, auto_memory=auto_memory)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)
    agent = AgentRuntime()
    agent._session_id = "test-session"
    return agent


def test_start_memory_prefetch_skips_when_auto_memory_off(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch, auto_memory=False)

    assert agent._start_memory_prefetch("please remember my review preference") is None


def test_start_memory_prefetch_skips_ignore_memory_phrases(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)

    assert agent._start_memory_prefetch("ignore memory for this turn") is None
    assert agent._start_memory_prefetch("这轮不使用记忆") is None


def test_start_memory_prefetch_skips_tiny_queries(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    stable, _legacy = agent.memory.manifest_dirs()
    _write_memory(stable / "review.md")

    assert agent._start_memory_prefetch("x") is None
    assert agent._start_memory_prefetch("status") is None
    assert agent._start_memory_prefetch("看看") is None


def test_start_memory_prefetch_skips_when_session_surface_cap_reached(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    stable, _legacy = agent.memory.manifest_dirs()
    _write_memory(stable / "review.md")
    agent._memory_recall_state.surfaced_bytes = MAX_SESSION_SURFACED_BYTES

    assert agent._start_memory_prefetch("please use my review preference in this task") is None


def test_start_memory_prefetch_submits_without_waiting_for_selector(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    stable, _legacy = agent.memory.manifest_dirs()
    _write_memory(stable / "review.md")
    submit_calls = []

    class FakeExecutor:
        def submit(self, fn):
            submit_calls.append(fn)
            return "future"

    agent._memory_prefetch_executor = FakeExecutor()

    result = agent._start_memory_prefetch("please use my review preference in this implementation")

    assert result == "future"
    assert len(submit_calls) == 1


def test_external_llm_loop_does_not_share_local_memory_prefetch(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent._start_memory_prefetch = MagicMock()
    agent._run_llm_loop = MagicMock(return_value="external reply")

    result = agent._run_external_llm_loop(
        history=[],
        system_prompt="system",
        tool_scope=None,
        session_id="external-session",
    )

    assert result == "external reply"
    agent._start_memory_prefetch.assert_not_called()
    assert "memory_prefetch" not in agent._run_llm_loop.call_args.kwargs


def test_start_memory_prefetch_passes_recent_successful_tool_names(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    stable, _legacy = agent.memory.manifest_dirs()
    _write_memory(stable / "review.md")
    agent._recent_successful_tool_names = ["read_file", "edit_file"]
    seen = {}

    class FakeExecutor:
        def submit(self, fn):
            result = fn()
            seen["result"] = result
            return "future"

    class FakeRecall:
        def prefetch(self, query, manifest, state, *, recent_successful_tools=None):
            seen["recent_successful_tools"] = recent_successful_tools
            return "result"

    agent._memory_prefetch_executor = FakeExecutor()
    agent.memory_recall = FakeRecall()

    assert agent._start_memory_prefetch("please use my review preference in this implementation") == "future"
    assert seen["recent_successful_tools"] == ["read_file", "edit_file"]


def test_llm_loop_records_recent_successful_local_tool_names_only(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(id="call_read", name="read_file", args={"path": "README.md"}),
                    ToolCall(id="call_error", name="grep", args={"pattern": "x", "path": "."}),
                ],
            )
        if calls[0] == 2:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(id="call_glob", name="glob", args={"pattern": "*.md"}),
                    ToolCall(id="call_read2", name="read_file", args={"path": "README.md"}),
                ],
            )
        return LLMResponse(content="done", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: "read ok"
    agent.tools._tools["grep"].execute = lambda **kwargs: "Error: grep failed"
    agent.tools._tools["glob"].execute = lambda **kwargs: "README.md"

    assert agent._run_llm_loop([], "system") == "done"

    assert agent._recent_successful_tool_names == ["glob", "read_file"]


class SequencedMemoryFuture:
    def __init__(self, done_values, result):
        self.done_values = list(done_values)
        self._result = result
        self.result_called = 0

    def done(self):
        if self.done_values:
            return self.done_values.pop(0)
        return False

    def result(self):
        self.result_called += 1
        return self._result


class RaisingMemoryFuture:
    def done(self):
        return True

    def result(self):
        raise RuntimeError("future exploded")


def _memory_result(path: Path, content: str = "memory body") -> RelevantMemoryResult:
    return RelevantMemoryResult(
        memories=[
            SurfacedMemory(
                path=path,
                mtime_ms=123,
                content=content,
                filename=path.name,
                byte_count=len(content.encode("utf-8")),
                line_count=1,
            )
        ]
    )


def test_llm_loop_does_not_wait_for_unfinished_prefetch_before_first_request(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    memory_file = tmp_path / "memory.md"
    future = SequencedMemoryFuture([False], _memory_result(memory_file))
    seen_messages = []

    def fake_complete(**kwargs):
        seen_messages.append(list(kwargs["messages"]))
        return LLMResponse(content="done", tool_calls=[])

    agent.llm.complete = fake_complete

    assert agent._run_llm_loop([], "system", memory_prefetch=future) == "done"
    assert future.result_called == 0
    assert seen_messages == [[]]


def test_llm_loop_injects_prefetch_once_at_tool_safe_point(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    memory_file = tmp_path / "memory.md"
    future = SequencedMemoryFuture([False, True], _memory_result(memory_file, "safe point memory"))
    seen_messages = []
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        seen_messages.append(list(kwargs["messages"]))
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_read", name="read_file", args={"path": "README.md"})],
            )
        return LLMResponse(content="done", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: "read ok"

    assert agent._run_llm_loop([], "system", memory_prefetch=future) == "done"

    assert future.result_called == 1
    assert "safe point memory" not in str(seen_messages[0])
    assert any(
        message["role"] == "system" and "safe point memory" in message["content"]
        for message in seen_messages[1]
    )
    assert sum(1 for message in seen_messages[1] if message.get("role") == "system") == 1


def test_unfinished_prefetch_is_marked_late_and_not_consumed_by_next_turn(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    memory_file = tmp_path / "memory.md"
    future = SequencedMemoryFuture([False], _memory_result(memory_file, "late memory"))
    seen_messages = []

    agent.llm.complete = lambda **kwargs: seen_messages.append(list(kwargs["messages"])) or LLMResponse(content="done", tool_calls=[])

    assert agent._run_llm_loop([], "system", memory_prefetch=future) == "done"
    assert future.result_called == 0
    assert agent._memory_recall_state.late_prefetch_count == 1

    assert agent._run_llm_loop([], "system") == "done"
    assert "late memory" not in str(seen_messages)


def test_touched_memory_is_filtered_before_safe_point_injection(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    stable, _legacy = agent.memory.manifest_dirs()
    memory_file = stable / "review.md"
    _write_memory(memory_file)
    future = SequencedMemoryFuture([False, True], _memory_result(memory_file, "should not inject"))
    seen_messages = []
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        seen_messages.append(list(kwargs["messages"]))
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_read", name="read_file", args={"path": str(memory_file)})],
            )
        return LLMResponse(content="done", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: "memory body"

    assert agent._run_llm_loop([], "system", memory_prefetch=future) == "done"

    assert future.result_called == 1
    assert "should not inject" not in str(seen_messages[1])


def test_prefetch_future_failure_is_audited_without_polluting_reply(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    seen_messages = []

    agent.llm.complete = lambda **kwargs: seen_messages.append(list(kwargs["messages"])) or LLMResponse(content="done", tool_calls=[])

    assert agent._run_llm_loop([], "system", memory_prefetch=RaisingMemoryFuture()) == "done"

    assert agent._last_memory_recall_result is not None
    assert agent._last_memory_recall_result.audit.skipped_reason == "future_error"
    assert "future exploded" not in str(seen_messages)
