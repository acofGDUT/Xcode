from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from xcode_cli.core.message_history import sanitize_model_messages


MICROCOMPACT_MIN_AGE_MESSAGES = 12
MICROCOMPACT_RESULT_CHARS = 12000


@dataclass
class CompressionResult:
    messages: list[dict[str, Any]]
    summary: str
    checkpoint_message: dict[str, Any]
    boundary_message: dict[str, Any] = field(default_factory=dict)
    protected_tail_messages: int = 0
    micro_compacted_tool_results: int = 0


class ContextManager:
    """Manage chat history token usage with lightweight compression strategy."""

    def __init__(
        self,
        max_tokens: int = 128000,
        max_summary_chars: int | None = 6000,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_summary_chars = max_summary_chars

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            parts = [str(msg.get("content", ""))]
            reasoning_content = msg.get("reasoning_content")
            if reasoning_content:
                parts.append(str(reasoning_content))
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                try:
                    parts.append(json.dumps(tool_calls, ensure_ascii=False))
                except Exception:
                    parts.append(str(tool_calls))
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id:
                parts.append(str(tool_call_id))
            content = "\n".join(part for part in parts if part)
            ascii_chars = sum(1 for ch in content if ord(ch) < 128)
            non_ascii_chars = len(content) - ascii_chars
            total += int(ascii_chars / 4 + non_ascii_chars / 1.5) + 12
        return total

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        return self.estimate_tokens(messages) >= int(self.max_tokens * 0.8)

    def compress(
        self,
        messages: list[dict[str, Any]],
        llm_client,
        previous_summary: str = "",
    ) -> CompressionResult:
        if len(messages) <= 20:
            return CompressionResult(
                messages=messages,
                summary="",
                checkpoint_message={},
            )

        tail_count = 8
        protected_tail_start = max(0, len(messages) - tail_count)
        working_messages, micro_compacted_tool_results = microcompact_tool_results(
            messages,
            protected_tail_start=protected_tail_start,
        )
        working_messages = sanitize_model_messages(working_messages)

        first_user_idx = next((i for i, m in enumerate(working_messages) if m.get("role") == "user"), None)
        first_user = working_messages[first_user_idx] if first_user_idx is not None else None

        tail = build_pair_safe_tail(working_messages, max_messages=tail_count)
        middle_start = (first_user_idx + 1) if first_user_idx is not None else 0
        middle_end = max(len(working_messages) - tail_count, middle_start)
        middle = working_messages[middle_start:middle_end]

        if previous_summary:
            middle = [
                m for m in middle
                if not (
                    m.get("role") == "system"
                    and "Conversation summary checkpoint:" in str(m.get("content", ""))
                )
            ]

        if not middle:
            return CompressionResult(
                messages=messages,
                summary="",
                checkpoint_message={},
            )

        char_limit = f" under {self.max_summary_chars} characters" if self.max_summary_chars else ""
        structured_format = (
            "Summary:\n"
            "- User intent and active task\n"
            "- Decisions and constraints\n"
            "- Files and code changes\n"
            "- Tool results and errors\n"
            "- Pending tasks\n"
            "- Current state\n"
            "- Next steps\n"
            "- Recent user messages"
        )
        format_instruction = (
            "Use this exact structured format:\n"
            f"{structured_format}\n\n"
            "Output summary text only: no tool calls, no XML tool tags, "
            f"no JSON tool invocation payloads,{char_limit}."
        )
        if previous_summary:
            summary_prompt = (
                "Below is a previous conversation summary and new conversation content since that summary. "
                "Produce an updated cumulative summary that merges old and new information. "
                "The new summary must preserve key decisions, constraints, file changes, errors, "
                "user preferences, pending items, current work, and next steps from BOTH the old summary "
                "and the new content. "
                f"{format_instruction}"
            )
            middle_text = (
                f"Previous summary:\n{previous_summary}\n\n"
                f"New content:\n"
                + "\n".join(f"[{m.get('role','unknown')}] {m.get('content','')}" for m in middle)
            )
        else:
            summary_prompt = (
                "Summarize the following conversation. Preserve key requirements, "
                "completed actions, pending items, constraints, file changes, errors, "
                "user preferences, current work, and next steps. "
                f"{format_instruction}"
            )
            middle_text = "\n".join(f"[{m.get('role','unknown')}] {m.get('content','')}" for m in middle)

        summary_resp = llm_client.complete(
            system_prompt="You are a conversation summarization assistant.",
            messages=[{"role": "user", "content": f"{summary_prompt}\n\n{middle_text}"}],
            tool_schemas=[],
        )
        source_token_estimate = self.estimate_tokens(middle)
        summary = validate_compact_summary(
            summary_resp.content,
            source_token_estimate=source_token_estimate,
        )
        if summary is None:
            return CompressionResult(
                messages=messages,
                summary="",
                checkpoint_message={},
            )

        if self.max_summary_chars and self.max_summary_chars > 0 and len(summary) > self.max_summary_chars:
            summary = summary[:self.max_summary_chars] + "...[summary truncated]"

        compressed: list[dict[str, Any]] = []
        if first_user:
            compressed.append(first_user)
        boundary_message: dict[str, Any] = {
            "role": "system",
            "content": (
                "Compact boundary: earlier conversation has been summarized below. "
                "Do not treat omitted tool results as pending tool calls."
            ),
        }
        checkpoint_message: dict[str, Any] = {
            "role": "system",
            "content": f"Conversation summary checkpoint:\n{summary}",
        }
        compressed.append(boundary_message)
        compressed.append(checkpoint_message)
        protected_tail = [message for message in tail if message is not first_user]
        compressed.extend(protected_tail)

        return CompressionResult(
            messages=compressed,
            summary=summary,
            checkpoint_message=checkpoint_message,
            boundary_message=boundary_message,
            protected_tail_messages=len(protected_tail),
            micro_compacted_tool_results=micro_compacted_tool_results,
        )


def validate_compact_summary(summary: str, *, source_token_estimate: int) -> str | None:
    normalized = summary.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    if "<tool_call>" in lowered:
        return None
    if normalized == "(middle conversation compressed)":
        return None
    if "tool_calls" in lowered or "function_call" in lowered:
        return None
    if source_token_estimate > 10000 and len(normalized) < 80:
        return None
    if _looks_like_tool_invocation_json(normalized):
        return None
    return normalized


def build_pair_safe_tail(messages: list[dict[str, Any]], *, max_messages: int = 8) -> list[dict[str, Any]]:
    if max_messages <= 0:
        return []

    start = max(0, len(messages) - max_messages)
    keep_indices = set(range(start, len(messages)))
    latest_user_idx = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
        None,
    )
    if latest_user_idx is not None:
        keep_indices.add(latest_user_idx)

    assistant_by_tool_id = _assistant_indices_by_tool_id(messages)
    tool_indices_by_id = _tool_indices_by_id(messages)

    changed = True
    while changed:
        changed = False
        for index in list(keep_indices):
            message = messages[index]
            if message.get("role") == "tool":
                assistant_idx = assistant_by_tool_id.get(str(message.get("tool_call_id", "")))
                if assistant_idx is not None and assistant_idx not in keep_indices:
                    keep_indices.add(assistant_idx)
                    changed = True

            if message.get("role") == "assistant" and message.get("tool_calls"):
                for tool_call in message.get("tool_calls", []):
                    tool_id = str(tool_call.get("id", ""))
                    tool_idx = tool_indices_by_id.get(tool_id)
                    if tool_idx is not None and tool_idx not in keep_indices:
                        keep_indices.add(tool_idx)
                        changed = True

    keep_indices = _remove_incomplete_tool_pairs(messages, keep_indices, tool_indices_by_id)
    return [messages[index] for index in sorted(keep_indices)]


def microcompact_tool_results(
    messages: list[dict[str, Any]],
    *,
    protected_tail_start: int,
) -> tuple[list[dict[str, Any]], int]:
    tool_metadata = _tool_call_metadata_by_id(messages)
    compacted = list(messages)
    count = 0
    for index, message in enumerate(messages):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str) or len(content) <= MICROCOMPACT_RESULT_CHARS:
            continue
        if index >= protected_tail_start:
            continue
        if len(messages) - index < MICROCOMPACT_MIN_AGE_MESSAGES:
            continue

        tool_call_id = str(message.get("tool_call_id", ""))
        tool_name, tool_args = tool_metadata.get(tool_call_id, ("unknown_tool", {}))
        replacement = dict(message)
        replacement["content"] = _microcompact_placeholder(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call_id,
            original_chars=len(content),
        )
        compacted[index] = replacement
        count += 1
    return compacted, count


def _tool_call_metadata_by_id(messages: list[dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    metadata: dict[str, tuple[str, dict[str, Any]]] = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls", []) or []:
            tool_id = str(tool_call.get("id", ""))
            function = tool_call.get("function") or {}
            tool_name = str(function.get("name") or "unknown_tool")
            args = _parse_tool_arguments(function.get("arguments"))
            if tool_id:
                metadata[tool_id] = (tool_name, args)
    return metadata


def _parse_tool_arguments(raw_args: object) -> dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if not isinstance(raw_args, str) or not raw_args.strip():
        return {}
    try:
        parsed = json.loads(raw_args)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _microcompact_placeholder(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_call_id: str,
    original_chars: int,
) -> str:
    detail = _tool_placeholder_detail(tool_args)
    detail_text = f" {detail}" if detail else ""
    return (
        f"[Old tool result content cleared: {tool_name}{detail_text}, "
        f"tool_call_id={tool_call_id}, original ~{original_chars} chars]"
    )


def _tool_placeholder_detail(tool_args: dict[str, Any]) -> str:
    for key in ("path", "pattern", "command", "query"):
        value = tool_args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return ""


def _assistant_indices_by_tool_id(messages: list[dict[str, Any]]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, message in enumerate(messages):
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        for tool_call in message.get("tool_calls", []):
            tool_id = str(tool_call.get("id", ""))
            if tool_id:
                indices[tool_id] = index
    return indices


def _tool_indices_by_id(messages: list[dict[str, Any]]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, message in enumerate(messages):
        if message.get("role") == "tool" and message.get("tool_call_id"):
            indices[str(message["tool_call_id"])] = index
    return indices


def _remove_incomplete_tool_pairs(
    messages: list[dict[str, Any]],
    keep_indices: set[int],
    tool_indices_by_id: dict[str, int],
) -> set[int]:
    result = set(keep_indices)

    for index in sorted(keep_indices):
        message = messages[index]
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        tool_ids = {str(tool_call.get("id", "")) for tool_call in message.get("tool_calls", [])}
        tool_ids.discard("")
        kept_tool_ids = {
            str(messages[tool_idx].get("tool_call_id", ""))
            for tool_idx in result
            if messages[tool_idx].get("role") == "tool"
        }
        if not tool_ids or not tool_ids <= kept_tool_ids:
            result.discard(index)
            for tool_id in tool_ids:
                tool_idx = tool_indices_by_id.get(tool_id)
                if tool_idx is not None:
                    result.discard(tool_idx)

    declared_ids = {
        str(tool_call.get("id", ""))
        for index in result
        if messages[index].get("role") == "assistant"
        for tool_call in messages[index].get("tool_calls", [])
    }
    declared_ids.discard("")
    for index in list(result):
        message = messages[index]
        if message.get("role") == "tool" and str(message.get("tool_call_id", "")) not in declared_ids:
            result.discard(index)

    return result


def _looks_like_tool_invocation_json(summary: str) -> bool:
    stripped = summary.strip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        payload = json.loads(stripped)
    except Exception:
        return False
    return _contains_tool_protocol_key(payload)


def _contains_tool_protocol_key(value: Any) -> bool:
    if isinstance(value, dict):
        if "name" in value and "arguments" in value:
            return True
        for key, item in value.items():
            if str(key) in {"tool_calls", "function_call"}:
                return True
            if _contains_tool_protocol_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_tool_protocol_key(item) for item in value)
    return False
