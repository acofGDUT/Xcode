from __future__ import annotations

from typing import Any


class ContextManager:
    """Manage chat history token usage with lightweight compression strategy."""

    MAX_TOKENS = 200000

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            ascii_chars = sum(1 for ch in content if ord(ch) < 128)
            non_ascii_chars = len(content) - ascii_chars
            total += int(ascii_chars / 4 + non_ascii_chars / 1.5) + 12
        return total

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        return self.estimate_tokens(messages) >= int(self.MAX_TOKENS * 0.8)

    def compress(self, messages: list[dict[str, Any]], llm_client) -> list[dict[str, Any]]:
        if len(messages) <= 20:
            return messages

        first_user_idx = next((i for i, m in enumerate(messages) if m.get("role") == "user"), None)
        first_user = messages[first_user_idx] if first_user_idx is not None else None

        tail_count = 8
        tail = messages[-tail_count:]
        middle_start = (first_user_idx + 1) if first_user_idx is not None else 0
        middle_end = max(len(messages) - tail_count, middle_start)
        middle = messages[middle_start:middle_end]

        if not middle:
            return messages

        summary_prompt = (
            "请将以下对话压缩为 200 字以内摘要，保留关键需求、已完成操作、未完成事项、约束条件。"
        )
        middle_text = "\n".join(f"[{m.get('role','unknown')}] {m.get('content','')}" for m in middle)
        summary_resp = llm_client.complete(
            system_prompt="你是对话摘要助手。",
            messages=[{"role": "user", "content": f"{summary_prompt}\n\n{middle_text}"}],
            tool_schemas=[],
        )
        summary = summary_resp.content.strip() or "（中间对话已压缩）"

        compressed: list[dict[str, Any]] = []
        if first_user:
            compressed.append(first_user)
        compressed.append({"role": "system", "content": f"历史摘要：{summary}"})
        compressed.extend(tail)
        return compressed
