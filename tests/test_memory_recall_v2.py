from __future__ import annotations

import time
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


class RaisingRecallLLM:
    def complete(self, **kwargs):
        raise RuntimeError("selector exploded")


def _entry(path: Path, filename: str, index: int = 0) -> MemoryManifestEntry:
    file_path = path / filename
    file_path.write_text(
        f"---\nname: Review Preference {index}\ndescription: Useful memory {index}.\ntype: feedback\n---\nBody {index}\n",
        encoding="utf-8",
    )
    return MemoryManifestEntry(
        filename=filename,
        file_path=file_path,
        mtime_ms=1000 + index,
        description=f"Useful memory {index}.",
        type="feedback",
        source="stable",
        name=f"Review Preference {index}",
    )


def test_selector_request_uses_no_tools_and_v2_prompt_input(tmp_path: Path) -> None:
    entries = [_entry(tmp_path, f"memory-{idx}.md", idx) for idx in range(205)]
    llm = FakeRecallLLM('{"selected_memories":[]}')
    service = MemoryRecallService(llm=llm)

    service.prefetch(
        "please apply review preferences",
        entries,
        RelevantMemoryState(),
        recent_successful_tools=["read_file"],
    )

    call = llm.calls[0]
    assert call["tool_schemas"] == []
    assert "Return JSON only" in call["system_prompt"]
    assert "Do not invent filenames" in call["system_prompt"]
    assert "recently successful tools" in call["system_prompt"].lower()
    selector_input = call["messages"][0]["content"]
    assert "Query: please apply review preferences" in selector_input
    assert selector_input.count("- [feedback]") == 200
    assert "[feedback] memory-0.md" in selector_input
    assert "Review Preference 0" in selector_input
    assert "source=stable" in selector_input


def test_recent_tools_are_distinct_bounded_and_names_only(tmp_path: Path) -> None:
    llm = FakeRecallLLM('{"selected_memories":[]}')
    service = MemoryRecallService(llm=llm)
    tools = [
        "read_file",
        "edit_file",
        "read_file",
        "run_shell",
        "grep",
        "glob",
        "task_list",
        "task_create",
        "skill",
        "write_file",
        "dispatch_agent",
        "mcp__server__tool",
    ]

    service.prefetch("please apply review preferences", [_entry(tmp_path, "memory.md")], RelevantMemoryState(), recent_successful_tools=tools)

    selector_input = llm.calls[0]["messages"][0]["content"]
    recent_section = selector_input.split("Recently successful tools:", 1)[1]
    rendered_tools = [line.strip()[2:] for line in recent_section.splitlines() if line.strip().startswith("- ")]
    assert rendered_tools == [
        "read_file",
        "edit_file",
        "run_shell",
        "grep",
        "glob",
        "task_list",
        "task_create",
        "skill",
        "write_file",
        "dispatch_agent",
    ]
    assert "secret" not in selector_input
    assert "path" not in recent_section.lower()
    assert "output" not in recent_section.lower()
    assert "command" not in recent_section.lower()


def test_recent_tools_section_is_omitted_when_empty(tmp_path: Path) -> None:
    llm = FakeRecallLLM('{"selected_memories":[]}')
    service = MemoryRecallService(llm=llm)

    service.prefetch("please apply review preferences", [_entry(tmp_path, "memory.md")], RelevantMemoryState())

    assert "Recently successful tools:" not in llm.calls[0]["messages"][0]["content"]


def test_selector_selection_filters_invalid_paths_duplicates_and_overflow(tmp_path: Path) -> None:
    entries = [_entry(tmp_path, f"memory-{idx}.md", idx) for idx in range(6)]
    llm = FakeRecallLLM(
        '{"selected_memories":["memory-0.md","../secret.md","dir/foo.md","dir\\\\foo.md",'
        '"memory-0.md","missing.md","memory-1.md","memory-2.md","memory-3.md","memory-4.md","memory-5.md"]}'
    )
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", entries, RelevantMemoryState())

    assert [memory.path.name for memory in result.memories] == [
        "memory-0.md",
        "memory-1.md",
        "memory-2.md",
        "memory-3.md",
        "memory-4.md",
    ]


def test_selector_invalid_payloads_fail_closed(tmp_path: Path) -> None:
    for content in ("[]", '{"other":[]}', "not json"):
        llm = FakeRecallLLM(content)
        service = MemoryRecallService(llm=llm)

        result = service.prefetch("please apply review preferences", [_entry(tmp_path, "memory.md")], RelevantMemoryState())

        assert result.memories == []


def test_relevant_memory_result_exposes_audit_summary(tmp_path: Path) -> None:
    entries = [_entry(tmp_path, "memory.md")]
    llm = FakeRecallLLM('{"selected_memories":["memory.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", entries, RelevantMemoryState())

    assert result.audit.selected_count == 1
    assert result.audit.surfaced_count == 1
    assert result.audit.skipped_reason == ""
    assert result.audit.elapsed_ms >= 0
    assert "selected=1 surfaced=1" in result.audit_summary()


def test_selector_failures_are_audited_fail_closed(tmp_path: Path) -> None:
    service = MemoryRecallService(llm=RaisingRecallLLM())

    result = service.prefetch("please apply review preferences", [_entry(tmp_path, "memory.md")], RelevantMemoryState())

    assert result.memories == []
    assert result.audit.selected_count == 0
    assert result.audit.surfaced_count == 0
    assert result.audit.skipped_reason == "selector_error"
    assert result.warnings == ["selector exploded"]
    assert "selector exploded" not in result.audit_summary()


def test_no_manifest_is_audited_without_selector_call() -> None:
    llm = FakeRecallLLM('{"selected_memories":["memory.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", [], RelevantMemoryState())

    assert result.memories == []
    assert result.audit.skipped_reason == "no_manifest"
    assert llm.calls == []


def test_bounded_read_truncates_by_bytes_with_read_file_hint(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "large.md")
    entry.file_path.write_text("x" * 5000, encoding="utf-8")
    llm = FakeRecallLLM('{"selected_memories":["large.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", [entry], RelevantMemoryState())

    assert len(result.memories) == 1
    memory = result.memories[0]
    assert memory.truncated is True
    assert memory.byte_count <= 4096
    assert "This memory file was truncated (4096 byte limit)" in memory.content
    assert "Use read_file to view the complete file at:" in memory.content
    assert str(entry.file_path.resolve(strict=False)) in memory.content


def test_bounded_read_truncates_by_lines(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "many-lines.md")
    entry.file_path.write_text("\n".join(f"line {idx}" for idx in range(250)), encoding="utf-8")
    llm = FakeRecallLLM('{"selected_memories":["many-lines.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", [entry], RelevantMemoryState())

    memory = result.memories[0]
    assert memory.truncated is True
    assert memory.line_count == 200
    assert "line 199" in memory.content
    assert "line 200" not in memory.content


def test_read_failure_records_warning_and_keeps_other_memories(tmp_path: Path) -> None:
    missing = _entry(tmp_path, "missing.md")
    missing.file_path.unlink()
    present = _entry(tmp_path, "present.md")
    llm = FakeRecallLLM('{"selected_memories":["missing.md","present.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", [missing, present], RelevantMemoryState())

    assert [memory.path.name for memory in result.memories] == ["present.md"]
    assert any("missing.md" in warning for warning in result.warnings)


def test_system_reminder_contains_age_and_point_in_time_warning(tmp_path: Path) -> None:
    recent = _entry(tmp_path, "recent.md")
    old = _entry(tmp_path, "old.md", 1)
    recent_mtime = int(time.time() * 1000)
    old_mtime = recent_mtime - (3 * 24 * 60 * 60 * 1000)
    entries = [
        MemoryManifestEntry(**{**recent.__dict__, "mtime_ms": recent_mtime}),
        MemoryManifestEntry(**{**old.__dict__, "mtime_ms": old_mtime}),
    ]
    llm = FakeRecallLLM('{"selected_memories":["recent.md","old.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", entries, RelevantMemoryState())
    reminder = result.render_system_reminder()

    assert reminder.startswith("<system-reminder>")
    assert reminder.endswith("</system-reminder>")
    assert "saved recently" in reminder
    assert "3 days old" in reminder
    assert "point-in-time observations, not live state" in reminder
    assert "Verify against current code or current docs" in reminder
    assert f"Memory: {recent.file_path}:" in reminder
    assert f"Memory: {old.file_path}:" in reminder


def test_prefetch_filters_touched_and_counts_utf8_bytes(tmp_path: Path) -> None:
    touched = _entry(tmp_path, "touched.md")
    selected = _entry(tmp_path, "selected.md")
    selected.file_path.write_text("记忆", encoding="utf-8")
    state = RelevantMemoryState(touched_paths={str(touched.file_path.resolve(strict=False))})
    llm = FakeRecallLLM('{"selected_memories":["touched.md","selected.md"]}')
    service = MemoryRecallService(llm=llm)

    result = service.prefetch("please apply review preferences", [touched, selected], state)

    assert [memory.path.name for memory in result.memories] == ["selected.md"]
    assert result.memories[0].byte_count == len("记忆".encode("utf-8"))
    assert state.surfaced_bytes == len("记忆".encode("utf-8"))
