# Task 04: Extraction Subagent Loop

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P0/P1

## Goal

Replace v1's no-tool JSON extraction path with a memory-only subagent loop that inherits the main v2 memory prompt, appends a dedicated extraction user message, runs for at most 5 model turns, and records saved topic paths and skip reasons.

## Suggested Files

- Create: `src/xcode_cli/core/memory_extraction_subagent.py`
- Modify: `src/xcode_cli/core/memory_extraction.py`
- Modify: `tests/test_memory_extraction_subagent.py`
- Modify: `tests/test_memory_extraction.py`

## Constraints

- Subagent must use the restricted tool registry from Task 03.
- It must not call `LLMClient.complete(tool_schemas=[])`; v2 extraction needs memory tools.
- Turn budget is 5 model turns.
- Manifest is injected as text only; topic bodies require `read_file`.
- Single run saves at most 3 topic files.
- Assistant task summaries, generic memories, and missing `Evidence:` writes must be rejected by post-run validation.

## Steps

- [x] **Step 1: Add subagent loop tests**

Append to `tests/test_memory_extraction_subagent.py`:

```python
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.llm import LLMResponse, ToolCall
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionSubagent
from xcode_cli.core.permissions import PermissionManager


def _event(text: str) -> AfterTurnSuccessEvent:
    return AfterTurnSuccessEvent(
        session_id="session-1",
        cwd="D:/Xcode",
        user_display_content=text,
        user_model_content=text,
        assistant_text="Done.",
        recent_history=[{"role": "user", "content": text}, {"role": "assistant", "content": "Done."}],
        wrote_memory_this_turn=False,
    )


class FakeToolLLM:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else LLMResponse(content="Done", tool_calls=[])


def test_subagent_injects_manifest_and_v2_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    llm = FakeToolLLM([LLMResponse(content="Nothing durable.", tool_calls=[])])
    subagent = MemoryExtractionSubagent(memory=memory, permissions=PermissionManager(cwd=str(tmp_path)), llm=llm)

    result = subagent.run(event=_event("hook should skip generic memory"), auto_memory_enabled=True)

    assert result.action == "skipped"
    assert "memory extraction subagent" in llm.calls[0]["messages"][-1]["content"]
    assert "Existing memory manifest:" in llm.calls[0]["messages"][-1]["content"]
    assert "type: <user|feedback|project|reference>" in llm.calls[0]["system_prompt"]


def test_subagent_executes_memory_tool_and_records_topic_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    topic = memory.memory_dir_path() / "generic-feedback.md"
    content = "---\nname: generic-feedback\ndescription: User says memory is too generic.\ntype: feedback\n---\n\nRule: Avoid generic memory.\nEvidence: \"User said hook memory was too generic.\"\nHow to apply: Save specific feedback only.\n"
    llm = FakeToolLLM([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="1", name="write_file", args={"path": str(topic), "content": content})],
        ),
        LLMResponse(content="Saved.", tool_calls=[]),
    ])
    subagent = MemoryExtractionSubagent(memory=memory, permissions=PermissionManager(cwd=str(tmp_path)), llm=llm)

    result = subagent.run(event=_event("hook should save specific memory"), auto_memory_enabled=True)

    assert result.action == "saved"
    assert result.saved_paths == [topic]
    assert topic.exists()


def test_subagent_caps_saved_topics_at_three(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    calls = []
    for index in range(4):
        path = memory.memory_dir_path() / f"m{index}.md"
        calls.append(ToolCall(id=str(index), name="write_file", args={"path": str(path), "content": "---\nname: m\ndescription: d\ntype: feedback\n---\n\nEvidence: \"x\"\n"}))
    llm = FakeToolLLM([LLMResponse(content="", tool_calls=calls), LLMResponse(content="Done", tool_calls=[])])
    subagent = MemoryExtractionSubagent(memory=memory, permissions=PermissionManager(cwd=str(tmp_path)), llm=llm)

    result = subagent.run(event=_event("save several"), auto_memory_enabled=True)

    assert result.action == "failed"
    assert result.reason == "too many topics"
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_extraction_subagent.py -q
```

Expected:

- Import fails because `memory_extraction_subagent.py` does not exist.

- [x] **Step 3: Implement result model and prompt builder**

Create `src/xcode_cli/core/memory_extraction_subagent.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xcode_cli.core.config import ConfigStore
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_manifest import MemoryManifestScanner
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
    def __init__(self, *, memory: MemoryManager, permissions: PermissionManager, llm) -> None:
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
        history.append({"role": "user", "content": _render_extraction_user_message(event, manifest.entries, manifest.warnings)})

        for _turn in range(MAX_EXTRACTION_TURNS):
            response = self.llm.complete(
                system_prompt=system_prompt,
                messages=history,
                tool_schemas=tools.get_openai_schemas(),
            )
            if not response.tool_calls:
                break
            tool_messages = []
            for tool_call in response.tool_calls:
                output = tools.execute(tool_call.name, tool_call.args)
                tool_messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output.content})
            history.append(_assistant_message_from_response(response))
            history.extend(tool_messages)

        saved_paths = list(audit.saved_topic_paths)
        if len(saved_paths) > MAX_SAVED_TOPICS:
            return MemoryExtractionResult(action="failed", reason="too many topics", saved_paths=saved_paths[:MAX_SAVED_TOPICS])
        if saved_paths:
            return MemoryExtractionResult(action="saved", saved_paths=saved_paths, warnings=manifest.warnings + audit.warnings)
        return MemoryExtractionResult(action="skipped", reason="no durable memory", warnings=manifest.warnings + audit.warnings)
```

- [x] **Step 4: Implement extraction user message helpers**

Add:

```python
import json


def _assistant_message_from_response(response) -> dict[str, object]:
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


def _render_extraction_user_message(event, entries, warnings: list[str]) -> str:
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
```

Move `_user_disabled_memory()` from `memory_extraction.py` or share it from a small helper to avoid duplicate phrase drift.

- [x] **Step 5: Run focused tests**

Run:

```text
pytest tests/test_memory_extraction_subagent.py tests/test_memory_extraction.py -q
```

Expected:

- Subagent tests pass.
- v1 service tests that depend on JSON side query are either updated to facade behavior or moved to v2 subagent assertions.

- [x] **Step 6: Stop for review**

Review before continuing:

- Tool schemas are non-empty and memory-only.
- User message says no code/git/tests/build investigation.
- `MEMORY.md` is not counted in `saved_paths`.
- Turn loop cannot exceed 5 LLM calls.

If committing is requested:

```text
git add src/xcode_cli/core/memory_extraction_subagent.py src/xcode_cli/core/memory_extraction.py tests/test_memory_extraction_subagent.py tests/test_memory_extraction.py
git commit -m "feat: add memory extraction subagent"
```
