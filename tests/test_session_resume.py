from __future__ import annotations

import json
from pathlib import Path

import pytest

from xcode_cli.core.context import ContextManager
from xcode_cli.core.session import SessionStore
from xcode_cli.core.session_resume import SessionResumeBuilder


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path, monkeypatch, cwd: str = "D:\\Xcode") -> SessionStore:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    for sub in ("sessions", "skills", "bin"):
        (xcode_dir / sub).mkdir(parents=True, exist_ok=True)
    return SessionStore(cwd=cwd)


def _write_messages(store: SessionStore, session_id: str, messages: list[dict]) -> None:
    for msg in messages:
        store.append_message(session_id, msg)


def _write_checkpoint(store: SessionStore, session_id: str, summary: str) -> None:
    store.append_event(session_id, {
        "type": "compaction_checkpoint",
        "summary": summary,
        "summary_format": "xcode.v1",
        "source_message_count": 10,
        "source_token_estimate": 5000,
        "remaining_message_count": 5,
    })


# ---------------------------------------------------------------------------
# SessionResumeBuilder
# ---------------------------------------------------------------------------

class TestResumeBuilderCheckpoint:
    def test_restores_from_checkpoint(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        _write_messages(store, sid, [
            {"role": "user", "content": "initial question"},
            {"role": "assistant", "content": "initial answer"},
        ])
        _write_checkpoint(store, sid, "Discussed initial setup and project structure.")
        _write_messages(store, sid, [
            {"role": "user", "content": "follow-up"},
            {"role": "assistant", "content": "follow-up answer"},
        ])

        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=100000)
        result = builder.build(store.transcript_path(sid))

        assert result.restored_from_checkpoint is True
        assert result.checkpoint_summary_chars > 0
        assert len(result.history) >= 3
        assert result.history[0]["role"] == "system"
        assert "Conversation summary checkpoint:" in result.history[0]["content"]
        assert "initial setup" in result.history[0]["content"]
        assert any(m.get("content") == "follow-up" for m in result.history)
        assert any(m.get("content") == "follow-up answer" for m in result.history)

    def test_checkpoint_result_metadata(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        _write_messages(store, sid, [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ])
        _write_checkpoint(store, sid, "summary")

        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=100000)
        result = builder.build(store.transcript_path(sid))

        assert result.restored_from_checkpoint is True
        assert result.message_count == len(result.history)
        assert result.estimated_tokens > 0
        assert result.estimated_tokens <= 100000

    def test_uses_last_checkpoint_only(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        _write_messages(store, sid, [{"role": "user", "content": "q1"}])
        _write_checkpoint(store, sid, "first summary")
        _write_messages(store, sid, [{"role": "assistant", "content": "a1"}])
        _write_checkpoint(store, sid, "second summary - final")
        _write_messages(store, sid, [{"role": "user", "content": "q2"}])

        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=100000)
        result = builder.build(store.transcript_path(sid))

        assert "second summary" in result.history[0]["content"]
        assert "first summary" not in result.history[0]["content"]
        assert any(m.get("content") == "q2" for m in result.history)
        assert not any(m.get("content") == "q1" for m in result.history)


class TestResumeBuilderNoCheckpoint:
    def test_tail_only_fallback(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        _write_messages(store, sid, [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ])

        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=100000)
        result = builder.build(store.transcript_path(sid))

        assert result.restored_from_checkpoint is False
        assert result.checkpoint_summary_chars == 0
        assert len(result.history) == 3

    def test_missing_file_returns_empty(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=100000)
        result = builder.build(store.transcript_path("nonexistent"))
        assert result.history == []
        assert result.message_count == 0


class TestResumeBuilderBudget:
    def test_large_transcript_stays_within_budget(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        messages = []
        for i in range(500):
            messages.append({"role": "user", "content": f"message {i} " + "x" * 50})
            messages.append({"role": "assistant", "content": f"response {i} " + "y" * 100})
        _write_messages(store, sid, messages)

        ctx = ContextManager(max_tokens=128000)
        budget = 20000
        builder = SessionResumeBuilder(ctx, token_budget=budget)
        result = builder.build(store.transcript_path(sid))

        assert result.estimated_tokens <= budget
        assert len(result.history) < 1000
        assert result.restored_from_checkpoint is False

    def test_checkpoint_resume_stays_within_budget(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        _write_messages(store, sid, [{"role": "user", "content": "early"}])
        _write_checkpoint(store, sid, "early work summary")
        for i in range(300):
            _write_messages(store, sid, [
                {"role": "user", "content": f"msg {i} " + "x" * 40},
                {"role": "assistant", "content": f"resp {i} " + "y" * 80},
            ])

        ctx = ContextManager(max_tokens=128000)
        budget = 15000
        builder = SessionResumeBuilder(ctx, token_budget=budget)
        result = builder.build(store.transcript_path(sid))

        assert result.restored_from_checkpoint is True
        assert result.estimated_tokens <= budget
        assert any("checkpoint" in m.get("content", "") for m in result.history)


class TestToolPairProtection:
    def test_orphaned_tool_message_removed(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        _write_messages(store, sid, [
            {"role": "user", "content": "read file"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "content"},
            {"role": "assistant", "content": "done"},
        ])

        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=100)  # very tight budget
        result = builder.build(store.transcript_path(sid))

        for msg in result.history:
            if msg.get("role") == "tool":
                tool_id = msg.get("tool_call_id")
                found = False
                for m2 in result.history:
                    if m2.get("role") == "assistant" and m2.get("tool_calls"):
                        for tc in m2["tool_calls"]:
                            if tc["id"] == tool_id:
                                found = True
                assert found, f"Orphaned tool message with id {tool_id}"

    def test_tool_calls_pair_kept_together(self, tmp_path: Path, monkeypatch) -> None:
        store = _make_store(tmp_path, monkeypatch)
        sid = store.new_session_id()
        messages = [{"role": "user", "content": "x" * 100}] * 50
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "tc1", "type": "function", "function": {"name": "glob", "arguments": "{}"}},
            ],
        })
        messages.append({"role": "tool", "tool_call_id": "tc1", "content": "result" * 50})
        _write_messages(store, sid, messages)

        ctx = ContextManager(max_tokens=128000)
        builder = SessionResumeBuilder(ctx, token_budget=3000)
        result = builder.build(store.transcript_path(sid))

        assistant_msgs = [m for m in result.history if m.get("role") == "assistant" and m.get("tool_calls")]
        tool_msgs = [m for m in result.history if m.get("role") == "tool"]
        assert len(tool_msgs) == len(assistant_msgs)
        if tool_msgs:
            for tm in tool_msgs:
                matching = any(
                    any(tc["id"] == tm["tool_call_id"] for tc in am.get("tool_calls", []))
                    for am in assistant_msgs
                )
                assert matching, f"No matching assistant for tool {tm['tool_call_id']}"
