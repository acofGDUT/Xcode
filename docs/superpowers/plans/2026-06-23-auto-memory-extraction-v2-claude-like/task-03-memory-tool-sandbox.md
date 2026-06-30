# Task 03: Memory Tool Sandbox

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P0

## Goal

Create a restricted tool surface for the extraction subagent that can only read/write/edit auto memory files and optionally list/search inside the auto memory directory.

## Suggested Files

- Create: `src/xcode_cli/core/memory_tools.py`
- Test: `tests/test_memory_extraction_subagent.py`
- Test: `tests/test_memory_extraction_policy.py`

## Constraints

- Do not expose MCP tools, `dispatch_agent`, project file reads, unrestricted `grep`, unrestricted `glob`, or `run_shell`.
- `write_file` and `edit_file` must respect `PermissionManager.check("write_file") == "deny"`.
- `edit_file` requires the path to have been read earlier by this sandbox instance.
- `MEMORY.md` updates are allowed but do not count as saved topic paths.
- All new tools must set `is_read_only` correctly.

## Steps

- [x] **Step 1: Add sandbox tests**

Append to `tests/test_memory_extraction_subagent.py`:

```python
from __future__ import annotations

from pathlib import Path

from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_tools import create_memory_extraction_tools
from xcode_cli.core.permissions import PermissionManager


def test_memory_tools_reject_project_file_reads(tmp_path: Path) -> None:
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    tools, audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    outside = tmp_path / "project" / "README.md"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("project", encoding="utf-8")

    result = tools.execute("read_file", {"path": str(outside)})

    assert "outside auto memory" in result.content
    assert audit.saved_topic_paths == []


def test_memory_tools_write_topic_and_ignore_index_as_saved_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    tools, audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    topic = memory.memory_dir_path() / "review.md"
    index = memory.memory_index_path()
    content = "---\nname: review\ndescription: Review preference.\ntype: feedback\n---\n\nRule: Lead with findings.\nEvidence: \"User said review output should lead with findings.\"\nHow to apply: Put findings first.\n"

    topic_result = tools.execute("write_file", {"path": str(topic), "content": content})
    index_result = tools.execute("write_file", {"path": str(index), "content": "- [Review](review.md) - hook\n"})

    assert not topic_result.content.startswith("Error:")
    assert not index_result.content.startswith("Error:")
    assert audit.saved_topic_paths == [topic]


def test_memory_tools_reject_invalid_v2_topic_before_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    memory = MemoryManager(cwd=str(tmp_path / "project"))
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
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    tools, _audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))
    topic = memory.memory_dir_path() / "review.md"
    topic.parent.mkdir(parents=True, exist_ok=True)
    topic.write_text("old", encoding="utf-8")

    result = tools.execute("edit_file", {"path": str(topic), "old_string": "old", "new_string": "new"})

    assert "requires prior read_file" in result.content


def test_memory_tools_do_not_register_run_shell_or_dispatch_agent(tmp_path: Path) -> None:
    memory = MemoryManager(cwd=str(tmp_path / "project"))
    tools, _audit = create_memory_extraction_tools(memory, PermissionManager(cwd=str(tmp_path)))

    assert "run_shell" not in tools.list_names()
    assert "dispatch_agent" not in tools.list_names()
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_extraction_subagent.py -q
```

Expected:

- Import fails because `memory_tools.py` does not exist.

- [x] **Step 3: Implement sandbox audit and tool registry**

Create `src/xcode_cli/core/memory_tools.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_extraction_policy import validate_v2_topic_text
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.tool_registry import ToolDef, ToolOutput, ToolRegistry


@dataclass
class MemoryToolAudit:
    read_paths: set[Path] = field(default_factory=set)
    saved_topic_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def create_memory_extraction_tools(
    memory: MemoryManager,
    permissions: PermissionManager,
) -> tuple[ToolRegistry, MemoryToolAudit]:
    audit = MemoryToolAudit()
    tools = ToolRegistry()

    def read_file(path: str) -> ToolOutput:
        resolved = _resolve_memory_path(memory, path)
        if resolved is None:
            return ToolOutput(content="Error: path outside auto memory")
        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolOutput(content=f"Error: {exc}")
        audit.read_paths.add(resolved)
        return ToolOutput(content=content)

    def write_file(path: str, content: str) -> ToolOutput:
        resolved = _resolve_memory_path(memory, path)
        if resolved is None:
            return ToolOutput(content="Error: path outside auto memory")
        if permissions.check("write_file", is_read_only=False) == "deny":
            return ToolOutput(content="Error: permission denied")
        if resolved.name != "MEMORY.md":
            policy = validate_v2_topic_text(content)
            if not policy.accepted:
                return ToolOutput(content=f"Error: policy rejected: {policy.reason}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        _record_saved_topic(memory, audit, resolved)
        return ToolOutput(content=f"Wrote {resolved}")

    def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> ToolOutput:
        resolved = _resolve_memory_path(memory, path)
        if resolved is None:
            return ToolOutput(content="Error: path outside auto memory")
        if resolved not in audit.read_paths:
            return ToolOutput(content="Error: edit_file requires prior read_file")
        if permissions.check("write_file", is_read_only=False) == "deny":
            return ToolOutput(content="Error: permission denied")
        text = resolved.read_text(encoding="utf-8")
        count = -1 if replace_all else 1
        if old_string not in text:
            return ToolOutput(content="Error: old_string not found")
        new_text = text.replace(old_string, new_string, count)
        if resolved.name != "MEMORY.md":
            policy = validate_v2_topic_text(new_text)
            if not policy.accepted:
                return ToolOutput(content=f"Error: policy rejected: {policy.reason}")
        resolved.write_text(new_text, encoding="utf-8")
        _record_saved_topic(memory, audit, resolved)
        return ToolOutput(content=f"Edited {resolved}")

    def glob(pattern: str = "*.md") -> ToolOutput:
        root = memory.memory_dir_path()
        files = sorted(path.name for path in root.glob(pattern) if _resolve_memory_path(memory, str(path)) is not None)
        return ToolOutput(content="\n".join(files))

    tools.register(ToolDef("read_file", "Read an auto memory file.", {"path": {"type": "string"}}, ["path"], read_file, True))
    tools.register(ToolDef("write_file", "Write an auto memory file.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], write_file, False))
    tools.register(ToolDef("edit_file", "Edit an already-read auto memory file.", {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}}, ["path", "old_string", "new_string"], edit_file, False))
    tools.register(ToolDef("glob", "List auto memory files.", {"pattern": {"type": "string"}}, [], glob, True))
    return tools, audit


def _resolve_memory_path(memory: MemoryManager, path: str) -> Path | None:
    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except Exception:
        return None
    if memory.is_memory_write_target(resolved):
        return resolved
    return None


def _record_saved_topic(memory: MemoryManager, audit: MemoryToolAudit, path: Path) -> None:
    if path.name == "MEMORY.md":
        return
    if path.suffix.lower() == ".md" and path not in audit.saved_topic_paths:
        audit.saved_topic_paths.append(path)
```

- [x] **Step 4: Run focused tests**

Run:

```text
pytest tests/test_memory_extraction_subagent.py -q
```

Expected:

- Sandbox tests pass.
- Tool registry contains only memory extraction tools.

- [x] **Step 5: Stop for review**

Review before continuing:

- No project path can be read through sandbox tools.
- No shell or agent tool is registered.
- `is_read_only=False` is set for write/edit tools.

If committing is requested:

```text
git add src/xcode_cli/core/memory_tools.py tests/test_memory_extraction_subagent.py
git commit -m "feat: restrict memory extraction tools"
```
