from __future__ import annotations

from pathlib import Path

from xcode_cli.core.config import Config
from xcode_cli.core.context import ContextManager


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
    """With max_tokens=128000, threshold is 102400. A few short messages should NOT trigger."""
    cm = ContextManager(max_tokens=128000)
    short = [{"role": "user", "content": "hello"}] * 5
    tokens = cm.estimate_tokens(short)
    assert tokens < 10000  # sanity: short messages
    assert cm.should_compress(short) is False


def test_should_compress_above_threshold_triggers() -> None:
    """With a tiny max_tokens, compression should trigger easily."""
    cm = ContextManager(max_tokens=2000)
    # Each message: content + 12 overhead, so 100 messages should easily exceed 1600
    many = [{"role": "user", "content": "a" * 100}] * 100
    assert cm.should_compress(many) is True


def test_should_compress_small_max_tokens() -> None:
    cm = ContextManager(max_tokens=1000)
    long_content = [{"role": "user", "content": "x" * 3000}]
    tokens = cm.estimate_tokens(long_content)
    assert cm.should_compress(long_content) is (tokens >= int(1000 * 0.8))


def test_compress_short_history_returns_unchanged() -> None:
    """Messages <= 20 should not be compressed."""
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient()
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
    result = cm.compress(msgs, llm)
    assert len(result) == len(msgs)
    assert llm.calls == []  # LLM was never called


def test_compress_uses_english_prompts() -> None:
    """Verify the compress() method sends English prompts to LLM."""
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient(response_text="a concise summary")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    result = cm.compress(msgs, llm)

    assert len(llm.calls) >= 1
    call = llm.calls[0]

    # system prompt is English
    assert "You are a conversation summarization assistant" in call["system_prompt"]

    # user prompt is English
    user_content = call["messages"][0]["content"]
    assert "Summarize the following conversation" in user_content
    assert "preserve key" in user_content.lower()

    # compressed result includes English system message
    system_msgs = [m for m in result if m.get("role") == "system"]
    assert len(system_msgs) >= 1
    summary_msg = system_msgs[0]["content"]
    assert "Conversation summary:" in summary_msg
    assert "a concise summary" in summary_msg


def test_compress_preserves_first_user_message() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("summary")
    first = {"role": "user", "content": "first message"}
    msgs = [first] + [{"role": "user", "content": f"msg {i}"} for i in range(25)]
    result = cm.compress(msgs, llm)
    assert result[0]["content"] == "first message"
    assert result[0]["role"] == "user"


def test_compress_preserves_tail_messages() -> None:
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient("summary")
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    tail = msgs[-8:]
    result = cm.compress(msgs, llm)
    assert result[-8:] == tail


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


def test_compress_empty_middle_returns_unchanged() -> None:
    """If there's nothing between first user and tail, don't compress.

    With first_user at idx 0 and tail_count=8, 9 messages total means middle is empty."""
    cm = ContextManager(max_tokens=128000)
    llm = _FakeLLMClient()
    msgs = [{"role": "user", "content": "hi"}] + [{"role": "assistant", "content": "hey"}] * 8
    result = cm.compress(msgs, llm)
    assert isinstance(result, list)
    # middle was empty, so result should be the original messages
    assert len(result) == len(msgs)
