from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import time

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
    filename: str = ""
    truncated: bool = False
    byte_count: int = 0
    line_count: int = 0


@dataclass(frozen=True)
class RelevantMemoryAudit:
    selected_count: int = 0
    surfaced_count: int = 0
    skipped_reason: str = ""
    warnings_count: int = 0
    selector_model: str = ""
    elapsed_ms: int = 0
    late_or_consumed: str = ""

    def summary(self) -> str:
        parts = [
            f"selected={self.selected_count}",
            f"surfaced={self.surfaced_count}",
            f"skipped={self.skipped_reason or '-'}",
            f"warnings={self.warnings_count}",
            f"elapsed_ms={self.elapsed_ms}",
        ]
        if self.late_or_consumed:
            parts.append(f"status={self.late_or_consumed}")
        if self.selector_model:
            parts.append(f"selector_model={self.selector_model}")
        return " ".join(parts)


@dataclass
class RelevantMemoryState:
    surfaced_paths: set[str] = field(default_factory=set)
    touched_paths: set[str] = field(default_factory=set)
    surfaced_bytes: int = 0
    late_prefetch_count: int = 0
    warnings: list[str] = field(default_factory=list)
    last_result: str = ""

    def snapshot(self) -> "RelevantMemoryState":
        return RelevantMemoryState(
            surfaced_paths=set(self.surfaced_paths),
            touched_paths=set(self.touched_paths),
            surfaced_bytes=self.surfaced_bytes,
            late_prefetch_count=self.late_prefetch_count,
            warnings=list(self.warnings),
            last_result=self.last_result,
        )


@dataclass(frozen=True)
class RelevantMemoryResult:
    memories: list[SurfacedMemory] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    audit: RelevantMemoryAudit = field(default_factory=RelevantMemoryAudit)

    def audit_summary(self) -> str:
        return self.audit.summary()

    def render_system_reminder(self) -> str:
        if not self.memories:
            return ""
        chunks = ["<system-reminder>"]
        for memory in self.memories:
            chunks.append(_render_age_warning(memory.mtime_ms))
            chunks.append(
                "Memories are point-in-time observations, not live state. "
                "Claims about code behavior, file paths, file:line citations, dependency versions, "
                "schedules or current project status may be outdated. "
                "Verify against current code or current docs before asserting them as fact."
            )
            chunks.append(f"Memory: {memory.path}:")
            chunks.append(memory.content)
        chunks.append("</system-reminder>")
        return "\n\n".join(chunks).strip()


class MemoryRecallService:
    def __init__(self, *, llm) -> None:
        self.llm = llm

    def prefetch(
        self,
        query: str,
        manifest: list[MemoryManifestEntry],
        state: RelevantMemoryState,
        *,
        recent_successful_tools: list[str] | None = None,
    ) -> RelevantMemoryResult:
        start = time.monotonic()

        def build_result(
            *,
            memories: list[SurfacedMemory] | None = None,
            warnings: list[str] | None = None,
            selected_count: int = 0,
            skipped_reason: str = "",
        ) -> RelevantMemoryResult:
            actual_memories = memories or []
            actual_warnings = warnings or []
            audit = RelevantMemoryAudit(
                selected_count=selected_count,
                surfaced_count=len(actual_memories),
                skipped_reason=skipped_reason,
                warnings_count=len(actual_warnings),
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )
            result = RelevantMemoryResult(memories=actual_memories, warnings=actual_warnings, audit=audit)
            state.last_result = result.audit_summary()
            if actual_warnings:
                state.warnings.extend(actual_warnings)
            return result

        if not query.strip() or state.surfaced_bytes >= MAX_SESSION_SURFACED_BYTES:
            reason = "empty_query" if not query.strip() else "session_cap"
            return build_result(skipped_reason=reason)
        candidates = manifest[:200]
        if not candidates:
            return build_result(skipped_reason="no_manifest")

        try:
            response = self.llm.complete(
                system_prompt=_SELECTOR_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _render_selector_input(
                            query,
                            candidates,
                            recent_successful_tools=recent_successful_tools,
                        ),
                    }
                ],
                tool_schemas=[],
            )
            payload = json.loads(response.content or "")
        except Exception as exc:
            return build_result(warnings=[str(exc)], skipped_reason="selector_error")

        selected = _validated_selection(payload, candidates)
        if not selected:
            return build_result(selected_count=0, skipped_reason="no_selection")
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
                bounded = _read_bounded(entry.file_path)
            except Exception as exc:
                warnings.append(f"{entry.filename}: {exc}")
                continue
            memories.append(
                SurfacedMemory(
                    path=entry.file_path,
                    mtime_ms=entry.mtime_ms,
                    content=bounded.content,
                    filename=entry.filename,
                    truncated=bounded.truncated,
                    byte_count=bounded.byte_count,
                    line_count=bounded.line_count,
                )
            )
            state.surfaced_paths.add(resolved)
            state.surfaced_bytes += len(bounded.content.encode("utf-8", errors="replace"))
        skipped_reason = ""
        if not memories:
            skipped_reason = "read_failed" if warnings else "filtered"
        return build_result(
            memories=memories[:MAX_RECALL_FILES],
            warnings=warnings,
            selected_count=len(selected),
            skipped_reason=skipped_reason,
        )


_SELECTOR_PROMPT = """You are selecting memories that will be useful to Xcode as it processes the user's current query.
You will be given the user's query and a list of available memory files with their types, filenames, timestamps, sources, names, and descriptions.
Return JSON only: {"selected_memories":["filename.md"]}.
Choose up to 5 memories that are clearly useful for processing the query. Be selective and discerning. If you are unsure whether a memory will help, do not include it. If no memory is clearly useful, return an empty list.
If a list of recently successful tools is provided, do not select ordinary usage reference or API documentation memories for those tools because Xcode is already exercising them. Still select memories that contain warnings, gotchas, known issues, user preferences or project constraints about those tools.
Do not invent filenames. Do not include paths. Do not explain.
"""


def _render_selector_input(
    query: str,
    entries: list[MemoryManifestEntry],
    *,
    recent_successful_tools: list[str] | None = None,
) -> str:
    lines = [f"Query: {query}", "", "Available memories:"]
    for entry in entries:
        name = f"name={entry.name}; " if entry.name else ""
        lines.append(
            f"- [{entry.type}] {entry.filename} ({name}mtime={entry.mtime_ms}; "
            f"source={entry.source}): {entry.description}"
        )
    tools = _bounded_distinct_tool_names(recent_successful_tools or [])
    if tools:
        lines.extend(["", "Recently successful tools:"])
        lines.extend(f"- {tool}" for tool in tools)
    return "\n".join(lines)


def _bounded_distinct_tool_names(tool_names: list[str]) -> list[str]:
    result: list[str] = []
    for raw_name in tool_names:
        name = str(raw_name).strip()
        if not name or name in result:
            continue
        result.append(name)
        if len(result) >= 10:
            break
    return result


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


@dataclass(frozen=True)
class _BoundedMemoryRead:
    content: str
    truncated: bool
    byte_count: int
    line_count: int


def _read_bounded(path: Path) -> _BoundedMemoryRead:
    raw_all = path.read_bytes()
    truncated_by_bytes = len(raw_all) > MAX_MEMORY_BYTES
    raw = raw_all[:MAX_MEMORY_BYTES]
    text = raw.decode("utf-8", errors="replace")
    all_lines = text.splitlines()
    truncated_by_lines = len(all_lines) > MAX_MEMORY_LINES
    lines = all_lines[:MAX_MEMORY_LINES]
    body = "\n".join(lines).strip()
    truncated = truncated_by_bytes or truncated_by_lines
    byte_count = len(body.encode("utf-8", errors="replace"))
    if truncated:
        body = (
            body
            + "\n\n> This memory file was truncated (4096 byte limit). "
            + f"Use read_file to view the complete file at: {path.resolve(strict=False)}"
        ).strip()
    return _BoundedMemoryRead(
        content=body,
        truncated=truncated,
        byte_count=byte_count,
        line_count=len(lines),
    )


def _render_age_warning(mtime_ms: int) -> str:
    age_seconds = max(0, time.time() - (mtime_ms / 1000))
    age_days = int(age_seconds // 86400)
    if age_days <= 0:
        return "This memory was saved recently."
    day_label = "day" if age_days == 1 else "days"
    return f"This memory is {age_days} {day_label} old."
