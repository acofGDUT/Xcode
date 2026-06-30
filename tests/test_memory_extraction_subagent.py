from __future__ import annotations

from pathlib import Path

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.llm import LLMResponse, ToolCall
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionSubagent
from xcode_cli.core.memory_tools import create_memory_extraction_tools
from xcode_cli.core.permissions import PermissionManager


def _memory(tmp_path: Path, monkeypatch) -> MemoryManager:
    import xcode_cli.paths

    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", tmp_path / ".xcode", raising=True)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return MemoryManager(cwd=str(project))


def test_memory_tools_reject_project_file_reads(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    tools, audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    outside = tmp_path / "project" / "README.md"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("project", encoding="utf-8")

    result = tools.execute("read_file", {"path": str(outside)})

    assert "outside auto memory" in result.content
    assert audit.saved_topic_paths == []


def test_memory_tools_write_topic_and_ignore_index_as_saved_path(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    tools, audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    topic = memory.memory_dir_path() / "review.md"
    index = memory.memory_index_path()
    content = (
        "---\n"
        "name: review\n"
        "description: Review preference.\n"
        "type: feedback\n"
        "---\n\n"
        "Rule: Lead with findings.\n"
        'Evidence: "review output should lead with issues"\n'
        "How to apply: Put findings first.\n"
    )

    topic_result = tools.execute("write_file", {"path": str(topic), "content": content})
    index_result = tools.execute("write_file", {"path": str(index), "content": "- [Review](review.md) - hook\n"})

    assert not topic_result.content.startswith("Error:")
    assert not index_result.content.startswith("Error:")
    assert audit.saved_topic_paths == [topic]


def test_memory_tools_reject_invalid_v2_topic_before_write(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    tools, audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    topic = memory.memory_dir_path() / "task-summary.md"

    result = tools.execute(
        "write_file",
        {
            "path": str(topic),
            "content": "---\nname: task-summary\ndescription: tests passed\ntype: feedback\n---\n\npytest -q passed\n",
        },
    )

    assert "policy rejected" in result.content
    assert not topic.exists()
    assert audit.saved_topic_paths == []


def test_memory_tools_edit_requires_prior_read(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    tools, _audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    topic = memory.memory_dir_path() / "review.md"
    topic.parent.mkdir(parents=True, exist_ok=True)
    topic.write_text("old", encoding="utf-8")

    result = tools.execute("edit_file", {"path": str(topic), "old_string": "old", "new_string": "new"})

    assert "requires prior read_file" in result.content


def test_memory_tools_do_not_register_run_shell_or_dispatch_agent(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    tools, _audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))

    assert "run_shell" not in tools.list_names()
    assert "dispatch_agent" not in tools.list_names()


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


def test_subagent_injects_manifest_and_v2_prompt(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    llm = FakeToolLLM([LLMResponse(content="Nothing durable.", tool_calls=[])])
    subagent = MemoryExtractionSubagent(memory=memory, permissions=PermissionManager(cwd=str(tmp_path)), llm=llm)

    result = subagent.run(event=_event("memory feedback is too generic"), auto_memory_enabled=True)

    assert result.action == "skipped"
    assert "memory extraction subagent" in llm.calls[0]["messages"][-1]["content"]
    assert "Existing memory manifest:" in llm.calls[0]["messages"][-1]["content"]
    assert "type: <user|feedback|project|reference>" in llm.calls[0]["system_prompt"]


def test_subagent_executes_memory_tool_and_records_topic_path(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    topic = memory.memory_dir_path() / "specific-feedback.md"
    content = (
        "---\n"
        "name: specific-feedback\n"
        "description: User says memory is too generic.\n"
        "type: feedback\n"
        "---\n\n"
        "Rule: Avoid generic memory.\n"
        'Evidence: "memory feedback is too generic"\n'
        "How to apply: Save specific feedback only.\n"
    )
    llm = FakeToolLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="1", name="write_file", args={"path": str(topic), "content": content})],
            ),
            LLMResponse(content="Saved.", tool_calls=[]),
        ]
    )
    subagent = MemoryExtractionSubagent(memory=memory, permissions=PermissionManager(cwd=str(tmp_path)), llm=llm)

    result = subagent.run(event=_event("memory feedback is too generic"), auto_memory_enabled=True)

    assert result.action == "saved"
    assert result.saved_paths == [topic]
    assert topic.exists()


def test_subagent_caps_saved_topics_at_three(tmp_path: Path, monkeypatch) -> None:
    memory = _memory(tmp_path, monkeypatch)
    calls = []
    for index in range(4):
        path = memory.memory_dir_path() / f"m{index}.md"
        calls.append(
            ToolCall(
                id=str(index),
                name="write_file",
                args={
                    "path": str(path),
                    "content": (
                        f"---\nname: m{index}\ndescription: memory {index}\ntype: feedback\n---\n\n"
                        f"Rule: Specific memory {index}.\n"
                        f'Evidence: "quote {index}"\n'
                        "How to apply: Use when relevant.\n"
                    ),
                },
            )
        )
    llm = FakeToolLLM([LLMResponse(content="", tool_calls=calls), LLMResponse(content="Done", tool_calls=[])])
    subagent = MemoryExtractionSubagent(memory=memory, permissions=PermissionManager(cwd=str(tmp_path)), llm=llm)

    result = subagent.run(event=_event("save several"), auto_memory_enabled=True)

    assert result.action == "failed"
    assert result.reason == "too many topics"
    assert sorted(path.name for path in memory.memory_dir_path().glob("m*.md")) == ["m0.md", "m1.md", "m2.md"]
