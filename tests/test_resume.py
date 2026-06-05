from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xcode_cli.core.context import ContextManager
from xcode_cli.core.conversation.resume import ResumeCommandService
from xcode_cli.core.session import SessionStore
from xcode_cli.core.session_resume import SessionResumeBuilder


class TestResumeTTY:
    """测试 TTY 环境下的方向键选择"""

    def test_tty_renders_session_list(self, capsys):
        """TTY 环境下列表渲染正确"""
        mock_sessions = MagicMock()
        mock_sessions.list_sessions.return_value = [
            MagicMock(
                session_id="test1234-5678",
                updated_at=1717000000,
                last_user_input="hello world",
                has_checkpoint=False,
                path="/tmp/test"
            )
        ]

        mock_context = MagicMock()
        mock_context.max_tokens = 128000
        mock_console = MagicMock()
        mock_prompt = MagicMock()

        service = ResumeCommandService(mock_sessions, mock_context, mock_console, mock_prompt)

        # 模拟 TTY 环境
        with patch('sys.stdin.isatty', return_value=True):
            with patch('xcode_cli.core.conversation.resume.read_key', side_effect=['enter']):
                with patch.object(service, '_render_session_list') as mock_render:
                    with patch.object(service, '_refresh_session_list') as mock_refresh:
                        # 模拟 SessionResumeBuilder
                        with patch('xcode_cli.core.conversation.resume.SessionResumeBuilder') as mock_builder_cls:
                            mock_builder = MagicMock()
                            mock_builder.build.return_value = MagicMock(
                                history=[{"role": "user", "content": "hello"}],
                                restored_from_checkpoint=False,
                                message_count=1,
                                estimated_tokens=100
                            )
                            mock_builder_cls.return_value = mock_builder

                            result = service.run()

                            # 验证渲染被调用
                            mock_render.assert_called_once()
                            assert result is not None

    def test_tty_escape_cancels(self):
        """TTY 环境下 Esc 取消"""
        mock_sessions = MagicMock()
        mock_sessions.list_sessions.return_value = [
            MagicMock(
                session_id="test1234-5678",
                updated_at=1717000000,
                last_user_input="hello",
                has_checkpoint=False,
                path="/tmp/test"
            )
        ]

        mock_context = MagicMock()
        mock_context.max_tokens = 128000
        mock_console = MagicMock()
        mock_prompt = MagicMock()

        service = ResumeCommandService(mock_sessions, mock_context, mock_console, mock_prompt)

        with patch('sys.stdin.isatty', return_value=True):
            with patch('xcode_cli.core.conversation.resume.read_key', return_value='escape'):
                result = service.run()

                assert result is None
                mock_console.print.assert_any_call("Cancelled.")

    def test_tty_arrow_keys_navigate(self):
        """TTY 环境下方向键导航"""
        mock_sessions = MagicMock()
        mock_sessions.list_sessions.return_value = [
            MagicMock(
                session_id=f"test{i}234-5678",
                updated_at=1717000000 + i,
                last_user_input=f"message {i}",
                has_checkpoint=False,
                path=f"/tmp/test{i}"
            )
            for i in range(3)
        ]

        mock_context = MagicMock()
        mock_context.max_tokens = 128000
        mock_console = MagicMock()
        mock_prompt = MagicMock()

        service = ResumeCommandService(mock_sessions, mock_context, mock_console, mock_prompt)

        # 模拟：按两次下箭头，然后回车
        with patch('sys.stdin.isatty', return_value=True):
            with patch('xcode_cli.core.conversation.resume.read_key', side_effect=['down', 'down', 'enter']):
                with patch.object(service, '_render_session_list'):
                    with patch.object(service, '_refresh_session_list') as mock_refresh:
                        with patch('xcode_cli.core.conversation.resume.SessionResumeBuilder') as mock_builder_cls:
                            mock_builder = MagicMock()
                            mock_builder.build.return_value = MagicMock(
                                history=[{"role": "user", "content": "test"}],
                                restored_from_checkpoint=False,
                                message_count=1,
                                estimated_tokens=100
                            )
                            mock_builder_cls.return_value = mock_builder

                            result = service.run()

                            # 验证刷新被调用了两次（两次方向键）
                            assert mock_refresh.call_count == 2
                            assert result is not None


class TestResumeNonTTY:
    """测试非 TTY 环境下的数字输入"""

    def test_non_tty_uses_number_input(self):
        """非 TTY 环境保持数字输入"""
        mock_sessions = MagicMock()
        mock_sessions.list_sessions.return_value = [
            MagicMock(
                session_id="test1234-5678",
                updated_at=1717000000,
                last_user_input="hello",
                has_checkpoint=False,
                path="/tmp/test"
            )
        ]

        mock_context = MagicMock()
        mock_context.max_tokens = 128000
        mock_console = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.prompt.return_value = "1"

        service = ResumeCommandService(mock_sessions, mock_context, mock_console, mock_prompt)

        with patch('sys.stdin.isatty', return_value=False):
            with patch('xcode_cli.core.conversation.resume.SessionResumeBuilder') as mock_builder_cls:
                mock_builder = MagicMock()
                mock_builder.build.return_value = MagicMock(
                    history=[{"role": "user", "content": "hello"}],
                    restored_from_checkpoint=False,
                    message_count=1,
                    estimated_tokens=100
                )
                mock_builder_cls.return_value = mock_builder

                result = service.run()

                # 验证 prompt 被调用（数字输入方式）
                mock_prompt.prompt.assert_called_once()
                assert result is not None


class TestReadKeyFunction:
    """测试 read_key 函数"""

    def test_read_key_importable(self):
        """read_key 函数可导入"""
        from xcode_cli.core.tooling.approval import read_key
        assert callable(read_key)


class TestResumeSkillInvocation:
    def test_resume_uses_skill_model_content_from_metadata(self, tmp_path: Path, monkeypatch) -> None:
        import xcode_cli.paths

        xcode_dir = tmp_path / ".xcode"
        monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
        for subdir in ("sessions", "skills", "bin"):
            (xcode_dir / subdir).mkdir(parents=True, exist_ok=True)

        store = SessionStore(cwd=str(tmp_path / "project"))
        session_id = store.new_session_id()
        store.append_message(
            session_id,
            {
                "role": "user",
                "content": "/review src/foo.py",
                "metadata": {
                    "kind": "skill_invocation",
                    "skill": "review",
                    "model_content": "Review this: src/foo.py",
                    "skill_source_hash": "sha256:test",
                },
            },
        )
        store.append_message(session_id, {"role": "assistant", "content": "ok"})

        result = SessionResumeBuilder(ContextManager(max_tokens=128000), token_budget=100000).build(
            store.transcript_path(session_id)
        )

        assert result.history[0] == {"role": "user", "content": "Review this: src/foo.py"}
        assert result.history[1] == {"role": "assistant", "content": "ok"}

    def test_resume_preserves_skill_tool_message_for_model_history(self, tmp_path):
        from xcode_cli.core.session_resume import build_model_history_from_events

        events = [
            {"type": "message", "role": "user", "content": "please review src/foo.py"},
            {
                "type": "message",
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "skill", "arguments": "{\"skill\":\"review\"}"},
                    }
                ],
            },
            {
                "type": "message",
                "role": "tool",
                "tool_call_id": "call_1",
                "content": (
                    "<xcode_loaded_skill name=\"review\" source=\"model\">\n"
                    "Review src/foo.py\n"
                    "</xcode_loaded_skill>"
                ),
            },
        ]

        history = build_model_history_from_events(events)

        assert any("<xcode_loaded_skill name=\"review\"" in str(message) for message in history)
