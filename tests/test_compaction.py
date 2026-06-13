from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from xcode_cli.core.conversation.compaction import ConversationCompactor
from xcode_cli.core.context import ContextManager


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
        """compress() 抛异常时 Live 仍然停止"""
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

            with pytest.raises(Exception, match="LLM error"):
                compactor.compact_history(history)

            # 即使异常，Live 也应该停止
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

    def test_rejected_summary_returns_none_and_preserves_history(self):
        class BadSummaryLLM:
            def complete(self, system_prompt, messages, tool_schemas):
                return type("Response", (), {"content": "<tool_call>{}</tool_call>"})()

        history = [{"role": "user", "content": f"msg {index}"} for index in range(30)]
        original = [dict(message) for message in history]
        compactor = ConversationCompactor(ContextManager(), BadSummaryLLM(), MagicMock(), MagicMock())

        with patch('xcode_cli.core.conversation.compaction.Live') as mock_live_cls:
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live

            result = compactor.compact_history(history)

            assert result is None
            assert history == original
            mock_live.start.assert_called_once()
            mock_live.stop.assert_called_once()

    def test_write_checkpoint_records_boundary_and_v2_metadata(self):
        mock_sessions = MagicMock()
        outcome = MagicMock(
            messages=[
                {"role": "user", "content": "first"},
                {"role": "system", "content": "Compact boundary: earlier conversation has been summarized below."},
                {"role": "system", "content": "Conversation summary checkpoint:\nsummary"},
                {"role": "user", "content": "latest"},
            ],
            summary="summary",
            boundary_message={"role": "system", "content": "Compact boundary: earlier conversation has been summarized below."},
            checkpoint_message={"role": "system", "content": "Conversation summary checkpoint:\nsummary"},
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
        event = mock_sessions.append_event.call_args.args[1]
        assert event["summary_format"] == "xcode.v2"
        assert event["source_message_count"] == 20
        assert event["remaining_message_count"] == 4
        assert event["protected_tail_messages"] == 1
        assert event["micro_compacted_tool_results"] == 0
        assert event["rejected_summary"] is False
