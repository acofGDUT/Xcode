# Task 05: Memory Extraction Service

**Risk layer:** P0/P1

## Goal

Use the internal after-turn hook to run local REPL-only no-tool memory extraction and write safe auto memory files when the model identifies durable information.

## Suggested Files

- Create: `src/xcode_cli/core/memory_extraction.py`
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `src/xcode_cli/core/llm.py` only if no-tool handling regresses
- Test: `tests/test_memory_extraction.py`
- Test: `tests/test_agent_memory_hooks.py`
- Test: `tests/test_llm.py`

## Constraints

- Runs only for local REPL after-turn success.
- Skips when `auto_memory=false`.
- Skips when user asks not to remember.
- Skips when the main model already wrote memory this turn.
- Uses no-tool side query and controlled JSON.
- Extraction failure does not affect main reply.

## Steps

- [x] **Step 1: Add extraction service tests**

Append to `tests/test_memory_extraction.py`:

```python
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.llm import LLMResponse
from xcode_cli.core.memory_extraction import MemoryExtractionService


class FakeExtractionLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(content=self.content, tool_calls=[])


def _event(text: str = "I prefer findings first.") -> AfterTurnSuccessEvent:
    return AfterTurnSuccessEvent(
        session_id="session-1",
        cwd="D:/Xcode",
        user_display_content=text,
        user_model_content=text,
        assistant_text="Noted.",
        recent_history=[{"role": "user", "content": text}, {"role": "assistant", "content": "Noted."}],
        wrote_memory_this_turn=False,
    )


def test_extraction_service_writes_memory_from_json(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    permissions = PermissionManager(cwd=str(project))
    llm = FakeExtractionLLM(
        '{"action":"save","type":"feedback","slug":"findings-first","title":"Findings first",'
        '"description":"User prefers review findings first.",'
        '"body":"Rule: Lead reviews with findings. Why: Faster triage. How to apply: Put issues first."}'
    )
    service = MemoryExtractionService(memory=memory, permissions=permissions, llm=llm)

    result = service.after_turn(_event())

    assert result.action == "saved"
    assert (memory.memory_dir_path() / "findings-first.md").exists()
    assert llm.calls[0]["tool_schemas"] == []


def test_extraction_service_skips_when_auto_memory_off(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    llm = FakeExtractionLLM('{"action":"save","type":"feedback","slug":"x","title":"X","description":"X","body":"X"}')
    service = MemoryExtractionService(memory=memory, permissions=PermissionManager(cwd=str(project)), llm=llm)

    result = service.after_turn(_event(), auto_memory_enabled=False)

    assert result.action == "skipped"
    assert llm.calls == []


def test_extraction_service_skips_when_user_says_do_not_remember(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    llm = FakeExtractionLLM('{"action":"save","type":"feedback","slug":"x","title":"X","description":"X","body":"X"}')
    service = MemoryExtractionService(memory=memory, permissions=PermissionManager(cwd=str(project)), llm=llm)

    result = service.after_turn(_event("不要记住这件事"))

    assert result.action == "skipped"
    assert llm.calls == []


def test_extraction_service_ignores_invalid_json(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    service = MemoryExtractionService(
        memory=memory,
        permissions=PermissionManager(cwd=str(project)),
        llm=FakeExtractionLLM("not json"),
    )

    result = service.after_turn(_event())

    assert result.action == "failed"
    assert not list(memory.memory_dir_path().glob("*.md"))
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_extraction.py -q
```

Expected:

- Import fails because `memory_extraction.py` does not exist.

- [x] **Step 3: Implement extraction service**

Create `src/xcode_cli/core/memory_extraction.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_writer import ExtractedMemory, MemoryWriter
from xcode_cli.core.permissions import PermissionManager


@dataclass(frozen=True)
class MemoryExtractionResult:
    action: str
    reason: str = ""


class MemoryExtractionService:
    def __init__(self, *, memory: MemoryManager, permissions: PermissionManager, llm) -> None:
        self.memory = memory
        self.permissions = permissions
        self.llm = llm
        self.last_result = MemoryExtractionResult(action="skipped", reason="not run")

    def after_turn(self, event: AfterTurnSuccessEvent, *, auto_memory_enabled: bool = True) -> MemoryExtractionResult:
        if not auto_memory_enabled:
            return self._set(MemoryExtractionResult(action="skipped", reason="auto memory off"))
        if event.wrote_memory_this_turn:
            return self._set(MemoryExtractionResult(action="skipped", reason="memory already written"))
        if _user_disabled_memory(event.user_display_content):
            return self._set(MemoryExtractionResult(action="skipped", reason="user disabled memory"))
        try:
            response = self.llm.complete(
                system_prompt=_EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _render_extraction_input(event)}],
                tool_schemas=[],
            )
            payload = json.loads(response.content or "")
        except Exception as exc:
            return self._set(MemoryExtractionResult(action="failed", reason=str(exc)))
        if payload.get("action") != "save":
            return self._set(MemoryExtractionResult(action="skipped", reason=str(payload.get("reason") or "selector skipped")))
        entry = ExtractedMemory(
            type=str(payload.get("type") or "project"),
            slug=str(payload.get("slug") or ""),
            title=str(payload.get("title") or ""),
            description=str(payload.get("description") or ""),
            body=str(payload.get("body") or ""),
        )
        write_result = MemoryWriter(self.memory, self.permissions).write_topic(entry)
        if not write_result.written:
            return self._set(MemoryExtractionResult(action="failed", reason=write_result.reason))
        return self._set(MemoryExtractionResult(action="saved", reason=str(write_result.path or "")))

    def _set(self, result: MemoryExtractionResult) -> MemoryExtractionResult:
        self.last_result = result
        return result


_EXTRACTION_SYSTEM_PROMPT = """You extract durable memory for a coding agent.
Return JSON only.
Save only long-term stable information not derivable from code, git, or docs.
Prefer user preferences, user feedback, project background, durable constraints, and external resource references.
Do not save temporary task state, implementation details, full file contents, secrets, tokens, credentials, or full shell output.
If nothing is worth saving, return {"action":"skip","reason":"..."}.
For saved memory return {"action":"save","type":"feedback|user|project|reference","slug":"kebab-case","title":"...","description":"...","body":"..."}.
"""


def _render_extraction_input(event: AfterTurnSuccessEvent) -> str:
    history = "\n".join(f"[{msg.get('role', 'unknown')}] {msg.get('content', '')}" for msg in event.recent_history[-8:])
    return f"User turn:\n{event.user_model_content}\n\nAssistant reply:\n{event.assistant_text}\n\nRecent history:\n{history}"


def _user_disabled_memory(text: str) -> bool:
    lowered = text.lower()
    phrases = ("不要记住", "别记住", "不要保存记忆", "不使用记忆", "ignore memory", "do not remember", "don't remember")
    return any(phrase in lowered for phrase in phrases)
```

- [x] **Step 4: Register extraction hook in AgentRuntime**

Modify `src/xcode_cli/core/agent.py` imports:

```python
from xcode_cli.core.memory_extraction import MemoryExtractionService
```

In `AgentRuntime.__init__`, after `self.memory` and `self.permissions` exist:

```python
        self.memory_extraction = MemoryExtractionService(
            memory=self.memory,
            permissions=self.permissions,
            llm=self.llm,
        )
        self.after_turn_hooks.register(self._run_memory_extraction_hook)
```

Add method:

```python
    def _run_memory_extraction_hook(self, event) -> None:
        cfg = self.config_store.load()
        self.memory_extraction.after_turn(event, auto_memory_enabled=cfg.auto_memory)
```

- [x] **Step 5: Run focused tests**

Run:

```text
pytest tests/test_memory_extraction.py tests/test_agent_memory_hooks.py tests/test_llm.py -q
```

Expected:

- Extraction tests pass.
- Hook tests pass.
- Existing no-tool `LLMClient.complete(tool_schemas=[])` behavior remains correct.

- [x] **Step 6: Stop for review**

If committing is requested:

```text
git add src/xcode_cli/core/memory_extraction.py src/xcode_cli/core/agent.py tests/test_memory_extraction.py tests/test_agent_memory_hooks.py tests/test_llm.py
git commit -m "feat: extract auto memory after turns"
```

