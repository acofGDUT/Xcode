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


def test_relevant_memory_state_snapshot_copies_mutable_audit_fields() -> None:
    state = RelevantMemoryState(
        surfaced_paths={"a.md"},
        touched_paths={"b.md"},
        surfaced_bytes=42,
        late_prefetch_count=2,
        warnings=["old warning"],
        last_result="selected=1 surfaced=0",
    )

    snapshot = state.snapshot()
    state.surfaced_paths.add("new.md")
    state.touched_paths.add("new-touch.md")
    state.warnings.append("new warning")

    assert snapshot.surfaced_paths == {"a.md"}
    assert snapshot.touched_paths == {"b.md"}
    assert snapshot.surfaced_bytes == 42
    assert snapshot.late_prefetch_count == 2
    assert snapshot.warnings == ["old warning"]
    assert snapshot.last_result == "selected=1 surfaced=0"
