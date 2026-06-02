"""AgentEngine for UI-free turn loop.

Runs the LLM loop without Rich/prompt_toolkit console output.
Uses callbacks for streaming text, tool calls, and permission.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from xcode_cli.core.llm import LLMClient, LLMResponse, ToolCall
from xcode_cli.core.runtime.cancellation import CancellationToken


class AgentEngine:
    """UI-free agent turn loop.

    Runs the LLM loop with streaming callbacks. Tools are executed
    through a pluggable `execute_tools` callback that handles
    permission, execution, and result formatting.

    This class has zero console/terminal dependencies.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def run_turn(
        self,
        history: list[dict[str, Any]],
        system_prompt: str,
        tool_schemas: list[dict[str, Any]],
        *,
        on_text_token: Callable[[str], None],
        on_reasoning_token: Callable[[str], None] | None = None,
        on_tool_call_started: Callable[[str, str, dict[str, Any]], None] | None = None,
        on_tool_call_finished: Callable[[str, str, bool], None] | None = None,
        on_tool_output: Callable[[str, str, str, str], None] | None = None,
        on_tool_error: Callable[[str, str, str], None] | None = None,
        execute_tools: Callable[
            [list[ToolCall], str, CancellationToken],
            list[tuple[ToolCall, str]],
        ]
        | None = None,
        cancellation: CancellationToken | None = None,
    ) -> str:
        """Run one agent turn.

        Args:
            history: Chat history (list of role/content dicts).
            system_prompt: System prompt.
            tool_schemas: OpenAI tool schemas.
            on_text_token: Called for each text token delta.
            on_reasoning_token: Called for each reasoning token delta.
            on_tool_call_started: Called when a tool call starts.
            on_tool_call_finished: Called when a tool call finishes.
            on_tool_output: Called with tool output.
            on_tool_error: Called when a tool call errors.
            execute_tools: Callback to execute tool calls.
            cancellation: Cancellation token.

        Returns:
            Final assistant text content.
        """
        while True:
            if cancellation and cancellation.is_cancelled:
                return "Cancelled."

            response = self._llm.complete(
                system_prompt=system_prompt,
                messages=history,
                tool_schemas=tool_schemas,
                on_text_token=on_text_token,
                on_reasoning_token=on_reasoning_token,
            )

            if cancellation and cancellation.is_cancelled:
                return "Cancelled."

            # Check for errors
            if response.content and response.content.startswith("[v0]"):
                return response.content

            # No tool calls - turn complete
            if not response.tool_calls:
                return response.content or ""

            # Execute tools
            if execute_tools is None:
                return response.content or ""

            # Notify tool calls started
            for tc in response.tool_calls:
                if on_tool_call_started:
                    on_tool_call_started(tc.id, tc.name, tc.args)

            # Execute tools (blocks for permission if needed)
            results = execute_tools(response.tool_calls, "turn", cancellation or CancellationToken())

            # Build assistant message
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                    }
                    for tc in response.tool_calls
                ],
            }
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content

            history.append(assistant_msg)

            # Process results and build tool messages
            tool_messages: list[dict[str, Any]] = []
            for tc, result_str in results:
                tool_messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

                is_error = result_str.startswith("Error:") or result_str.startswith("Tool error:")
                is_denied = "denied" in result_str.lower()
                success = not is_error and not is_denied

                if on_tool_call_finished:
                    on_tool_call_finished(tc.id, tc.name, success)

                if is_error:
                    if on_tool_error:
                        on_tool_error(tc.id, tc.name, result_str)
                elif on_tool_output:
                    output_type = "rejected" if is_denied else "result"
                    on_tool_output(tc.id, tc.name, output_type, result_str)

            history.extend(tool_messages)

    def _default_execute_tools(
        self,
        tool_calls: list[ToolCall],
        turn_id: str,
        cancellation: CancellationToken,
    ) -> list[tuple[ToolCall, str]]:
        """Default no-op tool executor (always returns error)."""
        return [(tc, "Error: no tool executor configured") for tc in tool_calls]
