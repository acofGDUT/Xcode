from __future__ import annotations

import json
from typing import Any


def sanitize_model_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return OpenAI-compatible messages with malformed tool-call pairs removed."""
    sanitized: list[dict[str, Any]] = []
    index = 0

    while index < len(messages):
        message = messages[index]
        role = message.get("role")
        if role == "assistant":
            assistant_message, next_index = _sanitize_assistant_at(messages, index)
            if assistant_message is not None:
                sanitized.append(assistant_message)
            for tool_message in messages[index + 1:next_index]:
                tool_call_id = str(tool_message.get("tool_call_id", ""))
                expected_ids = {
                    str(tool_call.get("id", ""))
                    for tool_call in assistant_message.get("tool_calls", [])
                } if assistant_message else set()
                if tool_call_id in expected_ids:
                    sanitized.append(dict(tool_message))
            index = next_index
            continue

        if role == "tool":
            index += 1
            continue

        sanitized.append(dict(message))
        index += 1

    return sanitized


def _sanitize_assistant_at(
    messages: list[dict[str, Any]],
    index: int,
) -> tuple[dict[str, Any] | None, int]:
    message = messages[index]
    tool_calls = message.get("tool_calls")
    if not tool_calls:
        return dict(message), index + 1

    normalized_tool_calls: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        normalized = _normalize_tool_call(tool_call)
        if normalized is None:
            next_index = _next_after_consecutive_tools(messages, index + 1)
            return _assistant_without_tool_calls(message), next_index
        normalized_tool_calls.append(normalized)

    expected_ids = {str(tool_call["id"]) for tool_call in normalized_tool_calls}
    next_index = _next_after_consecutive_tools(messages, index + 1)
    result_ids = {
        str(tool_message.get("tool_call_id", ""))
        for tool_message in messages[index + 1:next_index]
        if tool_message.get("role") == "tool"
    }
    if not expected_ids <= result_ids:
        return _assistant_without_tool_calls(message), next_index

    sanitized = dict(message)
    sanitized["tool_calls"] = normalized_tool_calls
    return sanitized, next_index


def _next_after_consecutive_tools(messages: list[dict[str, Any]], index: int) -> int:
    while index < len(messages) and messages[index].get("role") == "tool":
        index += 1
    return index


def _assistant_without_tool_calls(message: dict[str, Any]) -> dict[str, Any] | None:
    sanitized = dict(message)
    sanitized.pop("tool_calls", None)
    content = sanitized.get("content")
    if isinstance(content, str) and content:
        return sanitized
    if sanitized.get("reasoning_content"):
        return sanitized
    return None


def _normalize_tool_call(tool_call: object) -> dict[str, Any] | None:
    if not isinstance(tool_call, dict):
        return None
    tool_id = str(tool_call.get("id", "")).strip()
    if not tool_id:
        return None
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    arguments = function.get("arguments", "{}")
    if not isinstance(arguments, str):
        try:
            arguments = json.dumps(arguments, ensure_ascii=False)
        except Exception:
            arguments = "{}"
    return {
        "id": tool_id,
        "type": "function",
        "function": {
            "name": name.strip(),
            "arguments": arguments,
        },
    }
