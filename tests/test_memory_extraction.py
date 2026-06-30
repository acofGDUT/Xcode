from __future__ import annotations

import json
from pathlib import Path

from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_writer import ExtractedMemory, MemoryWriter
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.llm import LLMResponse, ToolCall
from xcode_cli.core.memory_extraction import MemoryExtractionService


def _setup_xcode_home(tmp_path: Path, monkeypatch) -> Path:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(json.dumps({"auto_memory": True}), encoding="utf-8")
    return xcode_dir


def test_memory_writer_creates_topic_and_index(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    permissions = PermissionManager(cwd=str(project))
    writer = MemoryWriter(memory, permissions)

    result = writer.write_topic(
        ExtractedMemory(
            type="feedback",
            slug="Review Findings First!",
            title="Review findings first",
            description="User wants review findings first.",
            body=(
                "Rule: Lead reviews with findings.\n"
                'Evidence: "review output should lead with issues"\n'
                "How to apply: Put issues first."
            ),
        )
    )

    topic = memory.memory_dir_path() / "review-findings-first.md"
    assert result.written is True
    assert topic.exists()
    content = topic.read_text(encoding="utf-8")
    assert "metadata:\n  type:" not in content
    assert "type: feedback" in content
    assert "[Review findings first](review-findings-first.md)" in memory.memory_index_path().read_text(encoding="utf-8")


def test_memory_writer_respects_explicit_deny(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    permissions = PermissionManager(cwd=str(project))
    permissions.set_session_rule("write_file", "deny")
    writer = MemoryWriter(memory, permissions)

    result = writer.write_topic(
        ExtractedMemory(
            type="feedback",
            slug="blocked",
            title="Blocked",
            description="Should not write.",
            body="This should not be written.",
        )
    )

    assert result.written is False
    assert result.reason == "permission denied"
    assert not (memory.memory_dir_path() / "blocked.md").exists()


def test_memory_writer_redacts_secret_like_values(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    writer = MemoryWriter(memory, PermissionManager(cwd=str(project)))

    writer.write_topic(
        ExtractedMemory(
            type="reference",
            slug="secret-ref",
            title="Secret ref",
            description="Token access_token=abc123 should be redacted.",
            body=(
                "Rule: Keep token references redacted.\n"
                'Evidence: "Authorization: Bearer abc123"\n'
                "How to apply: Record only that a secret reference exists.\n"
                "client_secret: very-secret\nsafe line"
            ),
        )
    )

    content = (memory.memory_dir_path() / "secret-ref.md").read_text(encoding="utf-8")
    assert "abc123" not in content
    assert "very-secret" not in content
    assert "[REDACTED]" in content
    assert "safe line" in content


class FakeExtractionLLM:
    def __init__(self, responses: str | list[LLMResponse]):
        self.responses = (
            list(responses)
            if isinstance(responses, list)
            else [LLMResponse(content=responses, tool_calls=[])]
        )
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if self.responses else LLMResponse(content="Done", tool_calls=[])


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


def _event_with_memory_written(text: str = "I prefer findings first.") -> AfterTurnSuccessEvent:
    event = _event(text)
    return AfterTurnSuccessEvent(
        session_id=event.session_id,
        cwd=event.cwd,
        user_display_content=event.user_display_content,
        user_model_content=event.user_model_content,
        assistant_text=event.assistant_text,
        recent_history=event.recent_history,
        wrote_memory_this_turn=True,
    )


def test_extraction_service_delegates_to_memory_tool_subagent(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    permissions = PermissionManager(cwd=str(project))
    topic = memory.memory_dir_path() / "findings-first.md"
    content = (
        "---\n"
        "name: findings-first\n"
        "description: User prefers review findings first.\n"
        "type: feedback\n"
        "---\n\n"
        "Rule: Lead reviews with findings.\n"
        'Evidence: "review output should lead with issues"\n'
        "How to apply: Put issues first.\n"
    )
    llm = FakeExtractionLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="1", name="write_file", args={"path": str(topic), "content": content})],
            ),
            LLMResponse(content="Saved.", tool_calls=[]),
        ]
    )
    service = MemoryExtractionService(memory=memory, permissions=permissions, llm=llm)

    result = service.after_turn(_event())

    assert result.action == "saved"
    assert topic.exists()
    assert llm.calls[0]["tool_schemas"]


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


def test_extraction_service_skips_when_memory_already_written(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    llm = FakeExtractionLLM('{"action":"save","type":"feedback","slug":"x","title":"X","description":"X","body":"X"}')
    service = MemoryExtractionService(memory=memory, permissions=PermissionManager(cwd=str(project)), llm=llm)

    result = service.after_turn(_event_with_memory_written())

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


def test_extraction_service_skips_when_subagent_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    _setup_xcode_home(tmp_path, monkeypatch)
    project = tmp_path / "repo"
    project.mkdir()
    memory = MemoryManager(cwd=str(project))
    service = MemoryExtractionService(
        memory=memory,
        permissions=PermissionManager(cwd=str(project)),
        llm=FakeExtractionLLM("Nothing durable."),
    )

    result = service.after_turn(_event())

    assert result.action == "skipped"
    assert result.reason == "no durable memory"
    assert not list(memory.memory_dir_path().glob("*.md"))
