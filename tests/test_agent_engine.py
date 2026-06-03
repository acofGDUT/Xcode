"""Tests for AgentEngine."""
import pytest
from unittest.mock import MagicMock

from xcode_cli.core.llm import LLMClient, LLMResponse, ToolCall
from xcode_cli.core.runtime.agent_engine import AgentEngine
from xcode_cli.core.runtime.cancellation import CancellationToken


class FakeLLMClient:
    """Fake LLM client for testing AgentEngine."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses = responses or []
        self.call_count = 0
        self.complete_calls: list[dict] = []

    def complete(self, system_prompt, messages, tool_schemas,
                 on_text_token=None, on_reasoning_token=None) -> LLMResponse:
        self.complete_calls.append({
            "system_prompt": system_prompt,
            "messages": messages,
            "tool_schemas": tool_schemas,
        })
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            # Simulate streaming
            if resp.content and on_text_token:
                for char in resp.content:
                    on_text_token(char)
            return resp
        # Default: empty response
        return LLMResponse(content="No response.", tool_calls=[])


class TestAgentEngine:
    """Tests for AgentEngine."""

    def test_simple_text_response(self):
        """Test simple text response without tool calls."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(content="Hello, world!", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        tokens: list[str] = []
        final_text = engine.run_turn(
            history=[{"role": "user", "content": "hi"}],
            system_prompt="You are helpful.",
            tool_schemas=[],
            on_text_token=lambda t: tokens.append(t),
        )

        assert final_text == "Hello, world!"
        assert "".join(tokens) == "Hello, world!"

    def test_multiple_turns_with_tools(self):
        """Test multi-turn loop where LLM returns tools then text."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "/f.txt"})],
            ),
            LLMResponse(content="File contents shown.", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        tool_calls_received: list[str] = []
        tool_outputs_received: list[tuple] = []

        def fake_execute_tools(tool_calls, turn_id, cancellation):
            results = []
            for tc in tool_calls:
                tool_calls_received.append(tc.name)
                results.append((tc, "file content"))
            return results

        final_text = engine.run_turn(
            history=[{"role": "user", "content": "read file"}],
            system_prompt="You are helpful.",
            tool_schemas=[{"type": "function", "function": {"name": "read_file"}}],
            on_text_token=lambda t: None,
            on_tool_call_started=lambda tc_id, name, args: tool_calls_received.append(name),
            execute_tools=fake_execute_tools,
        )

        assert "read_file" in tool_calls_received
        assert final_text == "File contents shown."
        assert fake_llm.call_count == 2

    def test_cancellation_stops_loop(self):
        """Test that cancellation stops the loop."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "/f.txt"})],
            ),
            LLMResponse(content="Should not reach.", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)
        cancellation = CancellationToken()

        def fake_execute_tools(tool_calls, turn_id, cancellation_token):
            # Cancel during tool execution
            cancellation.cancel()
            return [(tool_calls[0], "cancelled")]

        final_text = engine.run_turn(
            history=[{"role": "user", "content": "read file"}],
            system_prompt="You are helpful.",
            tool_schemas=[{"type": "function", "function": {"name": "read_file"}}],
            on_text_token=lambda t: None,
            execute_tools=fake_execute_tools,
            cancellation=cancellation,
        )

        assert final_text == "Cancelled."

    def test_no_tool_executor_returns_text(self):
        """Test that missing tool executor returns current content."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content="Here's text",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "/f.txt"})],
            ),
            LLMResponse(content="No response.", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        # Without execute_tools, agent returns current content when tool_calls present
        final_text = engine.run_turn(
            history=[{"role": "user", "content": "read file"}],
            system_prompt="You are helpful.",
            tool_schemas=[{"type": "function", "function": {"name": "read_file"}}],
            on_text_token=lambda t: None,
        )

        assert final_text == "Here's text"

    def test_tool_error_is_handled(self):
        """Test that tool errors don't crash the loop."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="bad_tool", args={})],
            ),
            LLMResponse(content="Recovered.", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        tool_errors: list[str] = []

        def fake_execute_tools(tool_calls, turn_id, cancellation):
            results = []
            for tc in tool_calls:
                results.append((tc, "Error: tool failed"))
            return results

        final_text = engine.run_turn(
            history=[{"role": "user", "content": "use bad tool"}],
            system_prompt="You are helpful.",
            tool_schemas=[{"type": "function", "function": {"name": "bad_tool"}}],
            on_text_token=lambda t: None,
            on_tool_error=lambda tc_id, name, err: tool_errors.append(err),
            execute_tools=fake_execute_tools,
        )

        assert len(tool_errors) == 1
        assert "Error" in tool_errors[0]
        assert final_text == "Recovered."

    def test_history_is_appended(self):
        """Test that history is appended with assistant and tool messages."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content="Let me read",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "/f.txt"})],
            ),
            LLMResponse(content="Done.", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        history: list[dict] = [{"role": "user", "content": "read file"}]

        def fake_execute_tools(tool_calls, turn_id, cancellation):
            return [(t, "content") for t in tool_calls]

        engine.run_turn(
            history=history,
            system_prompt="You are helpful.",
            tool_schemas=[{"type": "function", "function": {"name": "read_file"}}],
            on_text_token=lambda t: None,
            execute_tools=fake_execute_tools,
        )

        # Should have: user, assistant (tool_calls), tool, assistant (final)
        assert len(history) >= 3
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert "tool_calls" in history[1]

    def test_llm_error_response(self):
        """Test that LLM error responses are returned immediately."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(content="[v0] LLM request failed: 请求超时", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        final_text = engine.run_turn(
            history=[{"role": "user", "content": "hi"}],
            system_prompt="You are helpful.",
            tool_schemas=[],
            on_text_token=lambda t: None,
        )

        assert final_text.startswith("[v0]")

    def test_token_streaming_callback(self):
        """Test that text tokens are streamed character by character."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(content="ABC", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        tokens: list[str] = []
        engine.run_turn(
            history=[{"role": "user", "content": "hi"}],
            system_prompt="You are helpful.",
            tool_schemas=[],
            on_text_token=lambda t: tokens.append(t),
        )

        assert tokens == ["A", "B", "C"]

    def test_tool_call_callbacks(self):
        """Test that tool call start/finish callbacks fire."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "/f.txt"})],
            ),
            LLMResponse(content="OK", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        started: list[str] = []
        finished: list[str] = []

        def fake_execute_tools(tool_calls, turn_id, cancellation):
            return [(tc, "ok") for tc in tool_calls]

        engine.run_turn(
            history=[{"role": "user", "content": "hi"}],
            system_prompt="You are helpful.",
            tool_schemas=[{"type": "function", "function": {"name": "read_file"}}],
            on_text_token=lambda t: None,
            on_tool_call_started=lambda tc_id, name, args: started.append(name),
            on_tool_call_finished=lambda tc_id, name, success: finished.append(name),
            execute_tools=fake_execute_tools,
        )

        assert started == ["read_file"]
        assert finished == ["read_file"]

    def test_agent_engine_with_empty_response(self):
        """Test empty response handling."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(content="", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)

        final_text = engine.run_turn(
            history=[{"role": "user", "content": "hi"}],
            system_prompt="You are helpful.",
            tool_schemas=[],
            on_text_token=lambda t: None,
        )

        assert final_text == ""

    def test_final_assistant_message_is_appended_to_history(self):
        """Test that a simple assistant reply is appended to history."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(content="hello back", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)
        history = [{"role": "user", "content": "hello"}]

        final_text = engine.run_turn(
            history=history,
            system_prompt="",
            tool_schemas=[],
            on_text_token=lambda delta: None,
        )

        assert final_text == "hello back"
        assert history[-1] == {"role": "assistant", "content": "hello back"}

    def test_tool_turn_appends_tool_messages_and_final_assistant_message(self):
        """Test tool-call turn appends assistant(tool_calls), tool result, and final assistant."""
        fake_llm = FakeLLMClient(responses=[
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "README.md"})],
            ),
            LLMResponse(content="I read it.", tool_calls=[]),
        ])
        engine = AgentEngine(llm_client=fake_llm)
        history = [{"role": "user", "content": "read README"}]

        def fake_execute_tools(tool_calls, turn_id, cancellation):
            return [(tc, "file content") for tc in tool_calls]

        final_text = engine.run_turn(
            history=history,
            system_prompt="",
            tool_schemas=[],
            on_text_token=lambda delta: None,
            execute_tools=fake_execute_tools,
        )

        assert final_text == "I read it."
        assert history[1]["role"] == "assistant"
        assert history[1]["tool_calls"][0]["id"] == "call_1"
        assert history[2] == {"role": "tool", "tool_call_id": "call_1", "content": "file content"}
        assert history[3] == {"role": "assistant", "content": "I read it."}
