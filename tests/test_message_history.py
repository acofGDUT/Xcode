from __future__ import annotations

from xcode_cli.core.message_history import sanitize_model_messages


def test_sanitize_drops_tool_call_when_matching_result_precedes_assistant() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "call-1", "content": "early result"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
    ]

    assert sanitize_model_messages(messages) == []


def test_sanitize_keeps_valid_consecutive_tool_batch() -> None:
    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }
        ],
    }
    tool_result = {"role": "tool", "tool_call_id": "call-1", "content": "file content"}

    assert sanitize_model_messages([assistant, tool_result]) == [assistant, tool_result]
