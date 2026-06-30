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
