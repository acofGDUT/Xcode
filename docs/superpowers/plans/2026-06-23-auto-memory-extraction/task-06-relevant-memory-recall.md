# Task 06: Relevant Memory Recall

**Risk layer:** P1

## Goal

Add Claude-style relevant memory recall: keep `MEMORY.md` as常驻索引, scan topic manifest, use no-tool selector side query, read at most 5 bounded topic files, and inject relevant memory reminders without blocking the main loop.

## Suggested Files

- Create: `src/xcode_cli/core/memory_recall.py`
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `src/xcode_cli/core/tooling/execution.py` if read/write/edit memory path tracking needs a public result
- Test: `tests/test_memory_recall.py`
- Test: `tests/test_agent_tool_loop.py`
- Test: `tests/test_prompting_memory.py`

## Constraints

- No embedding or vector DB.
- Selector side query must use `tool_schemas=[]`.
- Selector output is strictly validated against manifest filenames.
- Per file read limit: 200 lines or 4096 bytes.
- Per session surfaced memory total cap: 60 KiB.
- Same session and already-read/write/edit memory files are deduped.
- Prefetch must not block main LLM loop.

## Steps

- [x] **Step 1: Write recall service tests**

Create `tests/test_memory_recall.py`:

```python
from __future__ import annotations

from pathlib import Path

from xcode_cli.core.llm import LLMResponse
from xcode_cli.core.memory_manifest import MemoryManifestEntry
from xcode_cli.core.memory_recall import MemoryRecallService, RelevantMemoryState


class FakeRecallLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(content=self.content, tool_calls=[])


def _entry(path: Path, filename: str, description: str = "Useful memory") -> MemoryManifestEntry:
    return MemoryManifestEntry(
        filename=filename,
        file_path=path / filename,
        mtime_ms=123,
        description=description,
        type="feedback",
        source="stable",
    )


def test_recall_selects_existing_files_and_renders_bounded_content(tmp_path: Path) -> None:
    memory_file = tmp_path / "foo.md"
    memory_file.write_text("---\nname: foo\ndescription: useful\nmetadata:\n  type: feedback\n---\nBody\n", encoding="utf-8")
    llm = FakeRecallLLM('{"selected_memories":["foo.md","missing.md","foo.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please use my review preference", [_entry(tmp_path, "foo.md")], RelevantMemoryState())

    assert len(result.memories) == 1
    assert "Body" in result.render_system_reminder()
    assert llm.calls[0]["tool_schemas"] == []


def test_recall_skips_invalid_json(tmp_path: Path) -> None:
    llm = FakeRecallLLM("not json")
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("query", [], RelevantMemoryState())

    assert result.memories == []


def test_recall_respects_session_surface_cap(tmp_path: Path) -> None:
    memory_file = tmp_path / "foo.md"
    memory_file.write_text("x" * 5000, encoding="utf-8")
    state = RelevantMemoryState(surfaced_bytes=60 * 1024)
    service = MemoryRecallService(llm=FakeRecallLLM('{"selected_memories":["foo.md"]}'))

    result = service.prefetch("query", [_entry(tmp_path, "foo.md")], state)

    assert result.memories == []


def test_recall_dedupes_surfaced_and_read_files(tmp_path: Path) -> None:
    memory_file = tmp_path / "foo.md"
    memory_file.write_text("Body\n", encoding="utf-8")
    state = RelevantMemoryState(surfaced_paths={str(memory_file.resolve())}, touched_paths=set())
    service = MemoryRecallService(llm=FakeRecallLLM('{"selected_memories":["foo.md"]}'))

    result = service.prefetch("query", [_entry(tmp_path, "foo.md")], state)

    assert result.memories == []
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_recall.py -q
```

Expected:

- Import fails because `memory_recall.py` does not exist.

- [x] **Step 3: Implement recall service**

Create `src/xcode_cli/core/memory_recall.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from xcode_cli.core.memory_manifest import MemoryManifestEntry


MAX_RECALL_FILES = 5
MAX_MEMORY_LINES = 200
MAX_MEMORY_BYTES = 4096
MAX_SESSION_SURFACED_BYTES = 60 * 1024


@dataclass(frozen=True)
class SurfacedMemory:
    path: Path
    mtime_ms: int
    content: str


@dataclass
class RelevantMemoryState:
    surfaced_paths: set[str] = field(default_factory=set)
    touched_paths: set[str] = field(default_factory=set)
    surfaced_bytes: int = 0

    def snapshot(self) -> "RelevantMemoryState":
        return RelevantMemoryState(
            surfaced_paths=set(self.surfaced_paths),
            touched_paths=set(self.touched_paths),
            surfaced_bytes=self.surfaced_bytes,
        )


@dataclass(frozen=True)
class RelevantMemoryResult:
    memories: list[SurfacedMemory] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render_system_reminder(self) -> str:
        if not self.memories:
            return ""
        chunks = ["Relevant auto memories:"]
        for memory in self.memories:
            chunks.append(f"Memory (saved {memory.mtime_ms}): {memory.path}:")
            chunks.append(memory.content)
        return "\n\n".join(chunks).strip()


class MemoryRecallService:
    def __init__(self, *, llm) -> None:
        self.llm = llm

    def prefetch(
        self,
        query: str,
        manifest: list[MemoryManifestEntry],
        state: RelevantMemoryState,
    ) -> RelevantMemoryResult:
        # The caller may pass a snapshot when running in a background prefetch
        # thread. Do not rely on mutating this object to update shared runtime state.
        if not query.strip() or state.surfaced_bytes >= MAX_SESSION_SURFACED_BYTES:
            return RelevantMemoryResult()
        candidates = manifest[:200]
        if not candidates:
            return RelevantMemoryResult()
        try:
            response = self.llm.complete(
                system_prompt=_SELECTOR_PROMPT,
                messages=[{"role": "user", "content": _render_selector_input(query, candidates)}],
                tool_schemas=[],
            )
            payload = json.loads(response.content or "")
        except Exception as exc:
            return RelevantMemoryResult(warnings=[str(exc)])
        selected = _validated_selection(payload, candidates)
        memories: list[SurfacedMemory] = []
        warnings: list[str] = []
        by_name = {entry.filename: entry for entry in candidates}
        for filename in selected:
            entry = by_name[filename]
            resolved = str(entry.file_path.resolve(strict=False))
            if resolved in state.surfaced_paths or resolved in state.touched_paths:
                continue
            if state.surfaced_bytes >= MAX_SESSION_SURFACED_BYTES:
                break
            try:
                content = _read_bounded(entry.file_path)
            except Exception as exc:
                warnings.append(f"{entry.filename}: {exc}")
                continue
            memories.append(SurfacedMemory(path=entry.file_path, mtime_ms=entry.mtime_ms, content=content))
            state.surfaced_paths.add(resolved)
            state.surfaced_bytes += len(content.encode("utf-8", errors="replace"))
        return RelevantMemoryResult(memories=memories[:MAX_RECALL_FILES], warnings=warnings)


_SELECTOR_PROMPT = """Select relevant memories for the user's current query.
Choose only memories that are clearly useful. Select at most 5.
Return JSON only: {"selected_memories":["filename.md"]}.
Do not invent filenames.
"""


def _render_selector_input(query: str, entries: list[MemoryManifestEntry]) -> str:
    lines = [f"Query: {query}", "", "Available memories:"]
    for entry in entries:
        lines.append(f"- [{entry.type}] {entry.filename} (mtime={entry.mtime_ms}): {entry.description}")
    return "\n".join(lines)


def _validated_selection(payload: object, entries: list[MemoryManifestEntry]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("selected_memories")
    if not isinstance(raw, list):
        return []
    valid = {entry.filename for entry in entries}
    result: list[str] = []
    for item in raw:
        filename = str(item)
        if filename in valid and filename.endswith(".md") and "/" not in filename and "\\" not in filename:
            if filename not in result:
                result.append(filename)
    return result[:MAX_RECALL_FILES]


def _read_bounded(path: Path) -> str:
    raw = path.read_bytes()[:MAX_MEMORY_BYTES]
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()[:MAX_MEMORY_LINES]
    return "\n".join(lines).strip()
```

- [x] **Step 4: Wire recall prefetch into AgentRuntime**

In `src/xcode_cli/core/agent.py`, initialize:

```python
from concurrent.futures import Future, ThreadPoolExecutor
from xcode_cli.core.memory_manifest import MemoryManifestScanner
from xcode_cli.core.memory_recall import MemoryRecallService, RelevantMemoryState
```

In `__init__`:

```python
        self.memory_recall = MemoryRecallService(llm=self.llm)
        self._memory_recall_state = RelevantMemoryState()
        self._memory_prefetch_executor = ThreadPoolExecutor(max_workers=1)
```

At the beginning of `_run_user_turn()`, after `turn = coerce_user_turn_input(user_input)`:

```python
        memory_prefetch = self._start_memory_prefetch(turn.model_content)
```

Add helper:

```python
    def _start_memory_prefetch(self, query: str) -> Future | None:
        cfg = self.config_store.load()
        if not cfg.auto_memory or self._memory_disabled_for_turn(query):
            return None
        stable, legacy = self.memory.manifest_dirs()
        scanner = MemoryManifestScanner(stable, legacy)
        state_snapshot = self._memory_recall_state.snapshot()
        return self._memory_prefetch_executor.submit(
            lambda: self.memory_recall.prefetch(query, scanner.scan().entries, state_snapshot)
        )

    def _memory_disabled_for_turn(self, query: str) -> bool:
        lowered = query.lower()
        return any(
            phrase in lowered
            for phrase in (
                "do not remember",
                "don't remember",
                "不要记住",
                "别记住",
                "不要保存到记忆",
            )
        )
```

Before first LLM request and after each tool-result append, check:

```python
    def _maybe_inject_relevant_memories(self, history: list[dict[str, Any]], future: Future | None) -> None:
        if future is None or not future.done():
            return
        try:
            result = future.result()
        except Exception:
            return
        reminder = result.render_system_reminder()
        if reminder:
            history.append({"role": "system", "content": reminder})
            self._mark_relevant_memories_surfaced(result)

    def _mark_relevant_memories_surfaced(self, result) -> None:
        for memory in result.memories:
            resolved = str(memory.path.resolve(strict=False))
            if resolved in self._memory_recall_state.surfaced_paths:
                continue
            self._memory_recall_state.surfaced_paths.add(resolved)
            self._memory_recall_state.surfaced_bytes += len(memory.content.encode("utf-8", errors="replace"))
```

Pass `memory_prefetch` into `_run_llm_loop()` with a new optional argument, and call `_maybe_inject_relevant_memories()` at safe points before `self.llm.complete()`.

- [x] **Step 5: Track touched memory paths**

When `ToolCallExecutor` sees `read_file`, `write_file`, or `edit_file` with a path that `MemoryManager.is_memory_write_target()` accepts or belongs to manifest dirs, add the resolved path to `RelevantMemoryState.touched_paths`. Implement this in `AgentRuntime` if easier by reading tool args from `response.tool_calls` after execution.

- [x] **Step 6: Run focused recall tests**

Run:

```text
pytest tests/test_memory_recall.py tests/test_agent_tool_loop.py tests/test_prompting_memory.py -q
```

Expected:

- Recall service tests pass.
- Tool loop tests still pass.
- Prompting memory tests still show `MEMORY.md` index is injected and topic bodies are not常驻 injected.

- [x] **Step 7: Stop for review**

If committing is requested:

```text
git add src/xcode_cli/core/memory_recall.py src/xcode_cli/core/agent.py src/xcode_cli/core/tooling/execution.py tests/test_memory_recall.py tests/test_agent_tool_loop.py tests/test_prompting_memory.py
git commit -m "feat: recall relevant auto memories"
```

