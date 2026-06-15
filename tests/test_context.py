from __future__ import annotations

from pathlib import Path

import pytest

from xcode_cli.core.config import Config
from xcode_cli.core.context import CompressionResult, ContextManager, microcompact_tool_results


class _FakeLLMClient:
    """Returns a canned English summary so we can verify compress()."""

    def __init__(self, response_text: str = "test summary") -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def complete(self, system_prompt: str, messages: list[dict], tool_schemas: list) -> object:
        self.calls.append({
            "system_prompt": system_prompt,
            "messages": messages,
        })
        return _FakeResponse(self.response_text)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


def test_context_manager_uses_configured_max_tokens() -> None:
    cm = ContextManager(max_tokens=64000)
    assert cm.max_tokens == 64000


def test_default_max_tokens_is_128000() -> None:
    cm = ContextManager()
    assert cm.max_tokens == 128000


def test_should_compress_below_threshold() -> None:
    cm = ContextManager(max_tokens=128000)
    short = [{"role": "user", "content": "hello"}] * 5
    tokens = cm.estimate_tokens(short)
    assert tokens < 10000
    assert cm.should_compress(short) is False


def test_should_compress_above_threshold_triggers() -> None:
    cm = ContextManager(max_tokens=2000)
    many = [{"role": "user", "content": "a" * 100}] * 100
    assert cm.should_compress(many) is True


def test_should_compress_small_max_tokens() -> None:
    cm = ContextManager(max_tokens=1000)
    long_content = [{"role": "user", "content": "x" * 3000}]
    tokens = cm.estimate_tokens(long_content)
    assert cm.should_compress(long_content) is (tokens >= int(1000 * 0.8))


def test_auto_compress_short_history_can_checkpoint_when_called() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("short summary")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
    result = cm.compress(msgs, llm)
    assert result.summary == "short summary"
    assert result.checkpoint_message
    assert llm.calls


def test_compress_uses_english_prompts() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient(response_text="a concise summary")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm)

    assert len(llm.calls) >= 1
    call = llm.calls[0]
    assert "You are a conversation summarization assistant" in call["system_prompt"]
    user_content = call["messages"][0]["content"]
    assert "Summarize the following conversation" in user_content
    assert "preserve key" in user_content.lower()

    system_msgs = [m for m in result.messages if m.get("role") == "system"]
    assert len(system_msgs) >= 1
    summary_msg = next(m["content"] for m in system_msgs if "Conversation summary checkpoint:" in m["content"])
    assert "Conversation summary checkpoint:" in summary_msg
    assert "a concise summary" in summary_msg


def test_compress_with_previous_summary_uses_cumulative_prompt() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient(response_text="cumulative summary")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm, previous_summary="old summary text")

    call = llm.calls[0]
    user_content = call["messages"][0]["content"]
    assert "Previous summary" in user_content
    assert "old summary text" in user_content
    assert "cumulative" in user_content.lower() or "Cumulative" in user_content


def test_compress_no_longer_preserves_first_user_message_when_it_is_not_latest() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("summary")
    first = {"role": "user", "content": "first message"}
    msgs = [first] + [{"role": "user", "content": f"msg {i}"} for i in range(25)]
    result = cm.compress(msgs, llm)
    assert first not in result.messages
    assert result.messages[0]["role"] == "system"
    assert result.messages[0]["content"].startswith("Compact boundary:")


def test_compress_preserves_tail_messages() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("summary")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    tail = msgs[-8:]
    result = cm.compress(msgs, llm)
    assert result.messages[-8:] == tail


def test_compress_result_has_checkpoint_message() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("checkpoint test")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm)
    assert result.checkpoint_message["role"] == "system"
    assert "Conversation summary checkpoint:" in result.checkpoint_message["content"]
    assert "checkpoint test" in result.summary


def test_compress_result_has_boundary_before_checkpoint() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: continue")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]

    result = cm.compress(msgs, llm)

    system_messages = [message for message in result.messages if message.get("role") == "system"]
    assert system_messages[0]["content"].startswith("Compact boundary:")
    assert "<tool_call" not in system_messages[0]["content"].lower()
    assert "Conversation summary checkpoint:" in system_messages[1]["content"]
    assert result.boundary_message == system_messages[0]


def test_estimate_tokens_includes_tool_calls() -> None:
    cm = ContextManager()
    plain = [{"role": "user", "content": "x"}]
    with_tool_calls = [{
        "role": "assistant",
        "content": "x",
        "tool_calls": [{"id": "1", "type": "function", "function": {"name": "read", "arguments": '{"path":"f.py"}'}}],
    }]
    assert cm.estimate_tokens(with_tool_calls) > cm.estimate_tokens(plain)


def test_estimate_tokens_includes_reasoning() -> None:
    cm = ContextManager()
    without = [{"role": "assistant", "content": "x"}]
    with_reasoning = [{"role": "assistant", "content": "x", "reasoning_content": "Let me think about this carefully."}]
    assert cm.estimate_tokens(with_reasoning) > cm.estimate_tokens(without)


def test_manual_compress_uses_full_history_when_pair_safe_middle_is_empty() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("manual short checkpoint")
    msgs = [{"role": "user", "content": "hi"}] + [{"role": "assistant", "content": "hey"}] * 8
    result = cm.compress(msgs, llm, trigger="manual")
    assert result.checkpoint_message
    assert result.summary == "manual short checkpoint"
    assert "hi" in llm.calls[0]["messages"][0]["content"]


def test_summary_truncated_when_too_long() -> None:
    cm = ContextManager(max_tokens=128000, max_summary_chars=6000)
    long_summary = "x" * 9000
    llm = _FakeLLMClient(response_text=long_summary)
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm)

    assert len(result.summary) <= 6000 + len("...[summary truncated]")
    assert "...[summary truncated]" in result.summary
    assert result.summary in result.checkpoint_message["content"]


def test_summary_not_truncated_when_disabled() -> None:
    cm = ContextManager(max_tokens=128000, max_summary_chars=None)
    long_summary = "x" * 9000
    llm = _FakeLLMClient(response_text=long_summary)
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm)

    assert result.summary == long_summary
    assert "...[summary truncated]" not in result.summary


def test_summary_not_truncated_when_zero() -> None:
    cm = ContextManager(max_tokens=128000, max_summary_chars=0)
    long_summary = "x" * 9000
    llm = _FakeLLMClient(response_text=long_summary)
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm)

    assert result.summary == long_summary
    assert "...[summary truncated]" not in result.summary


def test_previous_summary_filters_old_checkpoint_messages() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("new cumulative summary")
    msgs = [{"role": "user", "content": "first"}] + [
        {"role": "system", "content": "Conversation summary checkpoint:\nold summary text"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ] + [{"role": "user", "content": f"extra {i}"} for i in range(20)]

    cm.compress(msgs, llm, previous_summary="old summary text")

    call = llm.calls[0]
    user_content = call["messages"][0]["content"]
    assert "New content:" in user_content
    new_content_section = user_content.split("New content:\n", 1)[-1]
    assert "Conversation summary checkpoint:" not in new_content_section


def test_empty_history_returns_no_input_status() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient()
    msgs: list[dict] = []
    result = cm.compress(msgs, llm)
    assert result.checkpoint_message == {}
    assert result.summary == ""
    assert result.status == "no_input"
    assert llm.calls == []


@pytest.mark.parametrize(
    "bad_summary",
    [
        "",
        "   \n\t  ",
    ],
)
def test_rejects_empty_summary_without_replacing_messages(bad_summary: str) -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient(response_text=bad_summary)
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]

    result = cm.compress(msgs, llm)

    assert result.messages == msgs
    assert result.summary == ""
    assert result.checkpoint_message == {}
    assert result.status == "empty_summary"


@pytest.mark.parametrize(
    "summary",
    [
        "short",
        "(middle conversation compressed)",
        "<tool_call>{\"name\":\"read_file\",\"arguments\":{}}</tool_call>",
        "{\"tool_calls\":[{\"function\":{\"name\":\"read_file\",\"arguments\":\"{}\"}}]}",
        "{\"name\":\"read_file\",\"arguments\":{\"path\":\"README.md\"}}",
    ],
)
def test_compact_summary_quality_gate_allows_non_empty_text(summary: str) -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient(response_text=summary)
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]

    result = cm.compress(msgs, llm)

    assert result.summary == summary
    assert result.checkpoint_message


def test_summary_prompt_requests_structured_text_without_tool_payloads() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient(response_text="Summary:\n- User intent and active task: continue")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]

    cm.compress(msgs, llm)

    user_content = llm.calls[0]["messages"][0]["content"]
    for heading in (
        "Summary:",
        "- User intent and active task",
        "- Decisions and constraints",
        "- Files and code changes",
        "- Tool results and errors",
        "- Pending tasks",
        "- Current state",
        "- Next steps",
        "- Recent user messages",
    ):
        assert heading in user_content
    assert "no tool calls" in user_content.lower()
    assert "no xml tool tags" in user_content.lower()
    assert "no json tool invocation payloads" in user_content.lower()


def _assert_no_orphan_tool_messages(messages: list[dict]) -> None:
    declared_ids = {
        tc["id"]
        for message in messages
        if message.get("role") == "assistant"
        for tc in message.get("tool_calls", [])
    }
    for message in messages:
        if message.get("role") == "tool":
            assert message.get("tool_call_id") in declared_ids


def _assert_no_incomplete_tool_call_assistants(messages: list[dict]) -> None:
    result_ids = {
        message.get("tool_call_id")
        for message in messages
        if message.get("role") == "tool"
    }
    for message in messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            expected_ids = {tc["id"] for tc in message["tool_calls"]}
            assert expected_ids <= result_ids


def test_compress_tail_expands_to_keep_tool_pair_together() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: read file")
    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ],
    }
    tool_result = {"role": "tool", "tool_call_id": "call-1", "content": "file content"}
    msgs = (
        [{"role": "user", "content": "first"}]
        + [{"role": "assistant", "content": f"old {index}"} for index in range(20)]
        + [assistant, tool_result]
        + [{"role": "assistant", "content": f"tail {index}"} for index in range(7)]
    )

    result = cm.compress(msgs, llm)

    assert assistant in result.messages
    assert tool_result in result.messages
    _assert_no_orphan_tool_messages(result.messages)
    _assert_no_incomplete_tool_call_assistants(result.messages)


def test_compress_tail_drops_incomplete_assistant_tool_calls() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: inspect files")
    incomplete_assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
            {"id": "call-2", "type": "function", "function": {"name": "grep", "arguments": "{}"}},
        ],
    }
    only_one_result = {"role": "tool", "tool_call_id": "call-1", "content": "file content"}
    msgs = (
        [{"role": "user", "content": "first"}]
        + [{"role": "assistant", "content": f"old {index}"} for index in range(20)]
        + [incomplete_assistant, only_one_result]
        + [{"role": "assistant", "content": f"tail {index}"} for index in range(6)]
    )

    result = cm.compress(msgs, llm)

    assert incomplete_assistant not in result.messages
    assert only_one_result not in result.messages
    _assert_no_orphan_tool_messages(result.messages)
    _assert_no_incomplete_tool_call_assistants(result.messages)


def test_compress_tail_drops_tool_calls_missing_function_name() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: inspect files")
    malformed_assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": "", "arguments": "{}"}},
        ],
    }
    malformed_result = {"role": "tool", "tool_call_id": "call-1", "content": "file content"}
    msgs = (
        [{"role": "user", "content": "first"}]
        + [{"role": "assistant", "content": f"old {index}"} for index in range(20)]
        + [malformed_assistant, malformed_result]
        + [{"role": "assistant", "content": f"tail {index}"} for index in range(7)]
    )

    result = cm.compress(msgs, llm)

    assert malformed_assistant not in result.messages
    assert malformed_result not in result.messages
    assert not any(message.get("tool_calls") for message in result.messages if message is malformed_assistant)


def test_compress_tail_retains_latest_user_before_tool_block() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: answer latest user")
    latest_user = {"role": "user", "content": "latest user intent"}
    tool_block = []
    for index in range(4):
        call_id = f"call-{index}"
        tool_block.extend([
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": call_id, "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": call_id, "content": f"result {index}"},
        ])
    msgs = (
        [{"role": "user", "content": "first"}]
        + [{"role": "assistant", "content": f"old {index}"} for index in range(20)]
        + [latest_user]
        + tool_block
    )

    result = cm.compress(msgs, llm)

    assert latest_user in result.messages
    _assert_no_orphan_tool_messages(result.messages)
    _assert_no_incomplete_tool_call_assistants(result.messages)


def test_compress_tail_does_not_duplicate_first_user_when_it_is_latest_user() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: continue")
    first_user = {"role": "user", "content": "first and latest user"}
    msgs = [first_user] + [{"role": "assistant", "content": f"assistant {index}"} for index in range(25)]

    result = cm.compress(msgs, llm)

    assert result.messages.count(first_user) == 1


def _read_file_tool_pair(tool_call_id: str, content: str) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": "{\"path\":\"D:\\\\Xcode\\\\src\\\\foo.py\"}",
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": tool_call_id, "content": content},
    ]


def test_microcompact_old_large_tool_result_replaces_content_and_keeps_id() -> None:
    large_content = "x" * 13000
    messages = (
        [{"role": "user", "content": "first"}]
        + _read_file_tool_pair("call-large", large_content)
        + [{"role": "assistant", "content": f"tail {index}"} for index in range(15)]
    )

    compacted, count = microcompact_tool_results(messages, protected_tail_start=len(messages) - 8)

    assert count == 1
    tool_message = compacted[2]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-large"
    assert tool_message["content"].startswith("[Old tool result content cleared:")
    assert "read_file" in tool_message["content"]
    assert "D:\\Xcode\\src\\foo.py" in tool_message["content"]
    assert "original ~13000 chars" in tool_message["content"]
    assert len(tool_message["content"]) < 300
    assert messages[2]["content"] == large_content


def test_microcompact_does_not_touch_recent_protected_tail_tool_result() -> None:
    large_content = "y" * 13000
    messages = (
        [{"role": "user", "content": "first"}]
        + [{"role": "assistant", "content": f"old {index}"} for index in range(15)]
        + _read_file_tool_pair("call-recent", large_content)
    )

    compacted, count = microcompact_tool_results(messages, protected_tail_start=len(messages) - 8)

    assert count == 0
    assert compacted[-1]["tool_call_id"] == "call-recent"
    assert compacted[-1]["content"] == large_content


def test_microcompact_decreases_token_estimate() -> None:
    cm = ContextManager()
    large_content = "z" * 13000
    messages = (
        [{"role": "user", "content": "first"}]
        + _read_file_tool_pair("call-token", large_content)
        + [{"role": "assistant", "content": f"tail {index}"} for index in range(15)]
    )

    compacted, count = microcompact_tool_results(messages, protected_tail_start=len(messages) - 8)

    assert count == 1
    assert cm.estimate_tokens(compacted) < cm.estimate_tokens(messages)


def test_compress_metadata_reports_microcompacted_tool_results() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: continue")
    messages = (
        [{"role": "user", "content": "first"}]
        + _read_file_tool_pair("call-compact", "q" * 13000)
        + [{"role": "assistant", "content": f"tail {index}"} for index in range(25)]
    )

    result = cm.compress(messages, llm)

    assert result.micro_compacted_tool_results == 1


def test_compress_inserts_restored_context_after_summary_before_tail() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("Summary:\n- User intent and active task: continue")
    tail_user = {"role": "user", "content": "latest user"}
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(25)] + [tail_user]

    result = cm.compress(
        msgs,
        llm,
        restored_context="Compact restored context:\n- Active file: src/foo.py",
    )

    contents = [message.get("content", "") for message in result.messages]
    restored_index = contents.index("Compact restored context:\n- Active file: src/foo.py")
    summary_index = contents.index(result.checkpoint_message["content"])
    tail_index = result.messages.index(tail_user)
    assert summary_index < restored_index < tail_index
    assert result.restored_context_message["content"].startswith("Compact restored context:")


def test_previous_summary_filters_old_restored_context_messages() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("new cumulative summary")
    msgs = [
        {"role": "system", "content": "Conversation summary checkpoint:\nold summary text"},
        {"role": "system", "content": "Compact restored context:\n- Active file: old.py"},
        {"role": "user", "content": "new work"},
        {"role": "assistant", "content": "new answer"},
    ] + [{"role": "user", "content": f"extra {i}"} for i in range(20)]

    cm.compress(msgs, llm, previous_summary="old summary text")

    new_content_section = llm.calls[0]["messages"][0]["content"].split("New content:\n", 1)[-1]
    assert "Conversation summary checkpoint:" not in new_content_section
    assert "Compact restored context:" not in new_content_section


def test_summary_request_exception_returns_failure_status_without_replacing_messages() -> None:
    class BrokenLLM:
        def complete(self, **kwargs):
            raise RuntimeError("provider down")

    cm = ContextManager(max_tokens=128000)
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]

    result = cm.compress(msgs, BrokenLLM())

    assert result.messages == msgs
    assert result.checkpoint_message == {}
    assert result.status == "summary_request_failed"
    assert "provider down" in result.failure_reason
