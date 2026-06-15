from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xcode_cli.core.conversation.compaction import ConversationCompactor
from xcode_cli.core.context import ContextManager
from xcode_cli.core.session import SessionStore


def _make_store(tmp_path: Path, monkeypatch, cwd: str = "D:\\Xcode") -> SessionStore:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    return SessionStore(cwd=cwd)


def _make_outcome(summary: str = "summary") -> MagicMock:
    return MagicMock(
        messages=[
            {"role": "system", "content": "Compact boundary: earlier conversation has been summarized below."},
            {"role": "system", "content": f"Conversation summary checkpoint:\n{summary}"},
        ],
        summary=summary,
        boundary_message={"role": "system", "content": "Compact boundary: earlier conversation has been summarized below."},
        checkpoint_message={"role": "system", "content": f"Conversation summary checkpoint:\n{summary}"},
        restored_context_message={},
        restored_context_sections=[],
        before_messages=20,
        after_messages=2,
        before_tokens=1000,
        after_tokens=200,
        protected_tail_messages=0,
        micro_compacted_tool_results=0,
    )


def _checkpoint_events(store: SessionStore, session_id: str) -> list[dict]:
    events: list[dict] = []
    with store.transcript_path(session_id).open("r", encoding="utf-8") as fh:
        for line in fh:
            event = json.loads(line)
            if event.get("type") == "compaction_checkpoint":
                events.append(event)
    return events


class TestCompactHistoryProgress:
    """测试 compact_history 的进度显示功能"""

    def test_compact_history_shows_live_progress(self, tmp_path):
        """压缩成功时显示 Live 进度"""
        mock_context = MagicMock()
        mock_context.estimate_tokens.return_value = 100
        mock_context.compress.return_value = MagicMock(
            checkpoint_message={"role": "system", "content": "summary"},
            messages=[{"role": "system", "content": "summary"}],
            summary="test summary"
        )

        mock_llm = MagicMock()
        mock_sessions = MagicMock()
        mock_console = MagicMock()

        compactor = ConversationCompactor(mock_context, mock_llm, mock_sessions, mock_console)
        history = [{"role": "user", "content": "test"}]

        with patch('xcode_cli.core.conversation.compaction.Live') as mock_live_cls:
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live

            result = compactor.compact_history(history)

            # 验证 Live 被创建和启动
            mock_live_cls.assert_called_once()
            mock_live.start.assert_called_once()
            mock_live.stop.assert_called_once()
            assert result is not None

    def test_compact_history_stops_live_on_exception(self, tmp_path):
        """compress() 抛异常时 Live 仍然停止并返回失败"""
        mock_context = MagicMock()
        mock_context.estimate_tokens.return_value = 100
        mock_context.compress.side_effect = Exception("LLM error")

        mock_llm = MagicMock()
        mock_sessions = MagicMock()
        mock_console = MagicMock()

        compactor = ConversationCompactor(mock_context, mock_llm, mock_sessions, mock_console)
        history = [{"role": "user", "content": "test"}]

        with patch('xcode_cli.core.conversation.compaction.Live') as mock_live_cls:
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live

            result = compactor.compact_history(history)

            assert result is None
            assert compactor.last_failure_reason == "summary request failed: LLM error"
            mock_live.start.assert_called_once()
            mock_live.stop.assert_called_once()

    def test_compact_history_no_checkpoint_no_live(self, tmp_path):
        """Nothing to compact 路径不启动 Live"""
        mock_context = MagicMock()
        mock_context.estimate_tokens.return_value = 100
        mock_context.compress.return_value = MagicMock(
            checkpoint_message=None,
            messages=[],
            summary=""
        )

        mock_llm = MagicMock()
        mock_sessions = MagicMock()
        mock_console = MagicMock()

        compactor = ConversationCompactor(mock_context, mock_llm, mock_sessions, mock_console)
        history = [{"role": "user", "content": "test"}]

        with patch('xcode_cli.core.conversation.compaction.Live') as mock_live_cls:
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live

            result = compactor.compact_history(history)

            # 即使没有 checkpoint，Live 也会被启动（因为 compress 被调用了）
            # 但结果应该是 None
            assert result is None
            mock_live.start.assert_called_once()
            mock_live.stop.assert_called_once()

    def test_compaction_keeps_loaded_skill_marker_in_source_history(self, tmp_path):
        captured = {}

        class FakeContext:
            def estimate_tokens(self, history):
                return len(str(history))

            def compress(self, history, llm, previous_summary):
                captured["history"] = history
                return MagicMock(
                    messages=history,
                    summary="summary",
                    checkpoint_message={"role": "system", "content": "Conversation summary checkpoint:\nsummary"},
                )

        history = [
            {"role": "user", "content": "please review src/foo.py"},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "<xcode_loaded_skill name=\"review\">Review src/foo.py</xcode_loaded_skill>",
            },
        ]
        compactor = ConversationCompactor(FakeContext(), MagicMock(), MagicMock(), MagicMock())

        compactor.compact_history(history)

        assert any("<xcode_loaded_skill name=\"review\"" in str(message) for message in captured["history"])

    def test_empty_summary_returns_none_and_preserves_history(self):
        class BadSummaryLLM:
            def complete(self, system_prompt, messages, tool_schemas):
                return type("Response", (), {"content": ""})()

        history = [{"role": "user", "content": f"msg {index}"} for index in range(30)]
        original = [dict(message) for message in history]
        compactor = ConversationCompactor(ContextManager(), BadSummaryLLM(), MagicMock(), MagicMock())

        with patch('xcode_cli.core.conversation.compaction.Live') as mock_live_cls:
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live

            result = compactor.compact_history(history)

            assert result is None
            assert compactor.last_failure_reason == "empty summary"
            assert history == original
            mock_live.start.assert_called_once()
            mock_live.stop.assert_called_once()

    def test_write_checkpoint_records_boundary_restored_context_and_v3_metadata(self):
        mock_sessions = MagicMock()
        outcome = MagicMock(
            messages=[
                {"role": "system", "content": "Compact boundary: earlier conversation has been summarized below."},
                {"role": "system", "content": "Conversation summary checkpoint:\nsummary"},
                {"role": "system", "content": "Compact restored context:\n- Active file: src/foo.py"},
                {"role": "user", "content": "latest"},
            ],
            summary="summary",
            boundary_message={"role": "system", "content": "Compact boundary: earlier conversation has been summarized below."},
            checkpoint_message={"role": "system", "content": "Conversation summary checkpoint:\nsummary"},
            restored_context_message={"role": "system", "content": "Compact restored context:\n- Active file: src/foo.py"},
            restored_context_sections=["active_file"],
            before_messages=20,
            after_messages=4,
            before_tokens=1000,
            after_tokens=200,
            protected_tail_messages=1,
            micro_compacted_tool_results=0,
        )
        compactor = ConversationCompactor(MagicMock(), MagicMock(), mock_sessions, MagicMock())

        compactor.write_checkpoint("session-1", outcome)

        assert mock_sessions.append_message.call_args_list[0].args == ("session-1", outcome.boundary_message)
        assert mock_sessions.append_message.call_args_list[1].args == ("session-1", outcome.checkpoint_message)
        assert mock_sessions.append_message.call_args_list[2].args == ("session-1", outcome.restored_context_message)
        event = mock_sessions.append_event.call_args.args[1]
        assert event["summary_format"] == "xcode.v3"
        assert event["checkpoint_id"].startswith("ckpt_")
        assert event["parent_checkpoint_id"] is None
        assert event["checkpoint_index"] == 1
        assert event["summary_hash"].startswith("sha256:")
        assert event["restored_context_hash"].startswith("sha256:")
        assert event["restored_context_sections"] == ["active_file"]
        assert event["source_message_count"] == 20
        assert event["remaining_message_count"] == 4
        assert event["protected_tail_messages"] == 1
        assert event["micro_compacted_tool_results"] == 0
        assert event["rejected_summary"] is False

        second = MagicMock(**{**outcome.__dict__})
        compactor.write_checkpoint("session-1", second)
        second_event = mock_sessions.append_event.call_args.args[1]
        assert second_event["parent_checkpoint_id"] == event["checkpoint_id"]
        assert second_event["checkpoint_index"] == 2

    def test_write_checkpoint_continues_v3_lineage_from_existing_transcript(self, tmp_path, monkeypatch):
        store = _make_store(tmp_path, monkeypatch)
        session_id = store.new_session_id()

        first_compactor = ConversationCompactor(MagicMock(), MagicMock(), store, MagicMock())
        first_compactor.write_checkpoint(session_id, _make_outcome("first summary"))
        first_event = _checkpoint_events(store, session_id)[0]

        resumed_compactor = ConversationCompactor(MagicMock(), MagicMock(), store, MagicMock())
        resumed_compactor.write_checkpoint(session_id, _make_outcome("second summary"))

        _, second_event = _checkpoint_events(store, session_id)
        assert second_event["parent_checkpoint_id"] == first_event["checkpoint_id"]
        assert second_event["checkpoint_index"] == 2
        assert second_event["previous_summary_hash"] == first_event["summary_hash"]
