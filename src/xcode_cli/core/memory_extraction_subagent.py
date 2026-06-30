from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xcode_cli.core.config import ConfigStore
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_manifest import MemoryManifestEntry, MemoryManifestScanner
from xcode_cli.core.memory_tools import create_memory_extraction_tools
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.prompting import build_system_prompt


MAX_EXTRACTION_TURNS = 5
MAX_SAVED_TOPICS = 3


@dataclass(frozen=True)
class MemoryExtractionResult:
    action: str
    reason: str = ""
    saved_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class MemoryExtractionSubagent:
    def __init__(self, *, memory: MemoryManager, permissions: PermissionManager, llm: Any) -> None:
        self.memory = memory
        self.permissions = permissions
        self.llm = llm

    def run(self, event: AfterTurnSuccessEvent, *, auto_memory_enabled: bool = True) -> MemoryExtractionResult:
        if not auto_memory_enabled:
            return MemoryExtractionResult(action="skipped", reason="auto memory off")
        if event.wrote_memory_this_turn:
            return MemoryExtractionResult(action="skipped", reason="memory already written")
        if _user_disabled_memory(event.user_display_content) or _user_disabled_memory(event.user_model_content):
            return MemoryExtractionResult(action="skipped", reason="user disabled memory")

        tools, audit = create_memory_extraction_tools(self.memory, self.permissions)
        manifest = MemoryManifestScanner(self.memory.memory_dir_path()).scan()
        system_prompt = build_system_prompt(ConfigStore().load(), event.cwd)
        history = list(event.recent_history[-12:])
        history.append(
            {
                "role": "user",
                "content": _render_extraction_user_message(event, manifest.entries, manifest.warnings),
            }
        )
        too_many_topics = False

        for _turn in range(MAX_EXTRACTION_TURNS):
            response = self.llm.complete(
                system_prompt=system_prompt,
                messages=history,
                tool_schemas=tools.get_openai_schemas(),
            )
            if not response.tool_calls:
                break
            history.append(_assistant_message_from_response(response))
            for tool_call in response.tool_calls:
                if _would_exceed_topic_cap(self.memory, audit.saved_topic_paths, tool_call):
                    too_many_topics = True
                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Error: policy rejected: too many topics",
                        }
                    )
                    continue
                output = tools.execute(tool_call.name, tool_call.args)
                history.append({"role": "tool", "tool_call_id": tool_call.id, "content": output.content})

        saved_paths = list(audit.saved_topic_paths)
        warnings = manifest.warnings + audit.warnings
        if too_many_topics or len(saved_paths) > MAX_SAVED_TOPICS:
            return MemoryExtractionResult(
                action="failed",
                reason="too many topics",
                saved_paths=saved_paths[:MAX_SAVED_TOPICS],
                warnings=warnings,
            )
        if saved_paths:
            return MemoryExtractionResult(action="saved", saved_paths=saved_paths, warnings=warnings)
        return MemoryExtractionResult(action="skipped", reason="no durable memory", warnings=warnings)


def _assistant_message_from_response(response: Any) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": response.content or None}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {"name": tool_call.name, "arguments": json.dumps(tool_call.args)},
            }
            for tool_call in response.tool_calls
        ]
    return message


def _render_extraction_user_message(
    event: AfterTurnSuccessEvent,
    entries: list[MemoryManifestEntry],
    warnings: list[str],
) -> str:
    lines = [
        "You are now acting as the memory extraction subagent.",
        "Analyze only the most recent ~12 messages above and use them to update persistent auto memory.",
        "Do not investigate further: no source reads, no git, no tests, no builds, no project search.",
        "You have a limited turn budget of 5 model turns.",
        "Efficient strategy: first read every existing memory file you may update, then write or edit.",
        "Saving is two-step: write a v2 topic file, then add or update MEMORY.md.",
        "If nothing durable should be saved, do not write anything.",
        "",
        "Existing memory manifest:",
    ]
    if entries:
        for entry in entries:
            lines.append(f"- [{entry.type}] {entry.filename} ({entry.mtime_ms}): {entry.description}")
    else:
        lines.append("- none")
    if warnings:
        lines.append("")
        lines.append("Manifest warnings:")
        lines.extend(f"- {warning}" for warning in warnings[:20])
    lines.append("")
    lines.append(f"Current user turn: {event.user_model_content}")
    lines.append(f"Assistant reply: {event.assistant_text}")
    return "\n".join(lines)


def _would_exceed_topic_cap(memory: MemoryManager, saved_paths: list[Path], tool_call: Any) -> bool:
    if tool_call.name not in {"write_file", "edit_file"}:
        return False
    raw_path = tool_call.args.get("path")
    if not raw_path:
        return False
    try:
        path = Path(raw_path).expanduser().resolve(strict=False)
    except Exception:
        return False
    if path.name == "MEMORY.md":
        return False
    memory_root = memory.memory_dir_path().resolve(strict=False)
    try:
        if not path.is_relative_to(memory_root):
            return False
    except ValueError:
        return False
    if path in saved_paths:
        return False
    return len(saved_paths) >= MAX_SAVED_TOPICS


def _user_disabled_memory(text: str) -> bool:
    lowered = text.lower()
    phrases = (
        "不要记住",
        "别记住",
        "不要保存记忆",
        "不要保存到记忆",
        "不使用记忆",
        "忽略记忆",
        "ignore memory",
        "do not remember",
        "don't remember",
    )
    return any(phrase in lowered for phrase in phrases)
