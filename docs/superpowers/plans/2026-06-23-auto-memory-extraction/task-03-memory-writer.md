# Task 03: Safe Memory Writer

**Risk layer:** P0

## Goal

Create a memory-scoped writer used by background extraction. It must write only auto memory files, update `MEMORY.md`, redact secrets, sanitize slugs, and respect explicit `deny write_file`.

## Suggested Files

- Create: `src/xcode_cli/core/memory_writer.py`
- Modify: `src/xcode_cli/core/memory.py`
- Test: `tests/test_memory_extraction.py`
- Test: `tests/test_agent_memory_permissions.py`

## Constraints

- No public memory CRUD tool is introduced.
- Writer must not write outside `MemoryManager` auto memory directory.
- Explicit `deny write_file` blocks background writes.
- `MEMORY.md` index uses relative filename only.
- Do not write secret-like text into topic body, description, or index hook.

## Steps

- [x] **Step 1: Write failing writer tests**

Create `tests/test_memory_extraction.py` with initial writer coverage:

```python
from __future__ import annotations

import json
from pathlib import Path

from xcode_cli.core.config import Config
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_writer import ExtractedMemory, MemoryWriter
from xcode_cli.core.permissions import PermissionManager


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
            body="Rule: Lead reviews with findings.\nWhy: Easier triage.\nHow to apply: Put issues first.",
        )
    )

    topic = memory.memory_dir_path() / "review-findings-first.md"
    assert result.written is True
    assert topic.exists()
    assert "metadata:\n  type: feedback" in topic.read_text(encoding="utf-8")
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
            body="Authorization: Bearer abc123\nclient_secret: very-secret\nsafe line",
        )
    )

    content = (memory.memory_dir_path() / "secret-ref.md").read_text(encoding="utf-8")
    assert "abc123" not in content
    assert "very-secret" not in content
    assert "[REDACTED]" in content
    assert "safe line" in content
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_extraction.py::test_memory_writer_creates_topic_and_index tests/test_memory_extraction.py::test_memory_writer_respects_explicit_deny tests/test_memory_extraction.py::test_memory_writer_redacts_secret_like_values -q
```

Expected:

- Import fails because `memory_writer.py` does not exist.

- [x] **Step 3: Implement writer dataclasses and redaction**

Create `src/xcode_cli/core/memory_writer.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.permissions import PermissionManager


VALID_MEMORY_TYPES = {"user", "feedback", "project", "reference"}


@dataclass(frozen=True)
class ExtractedMemory:
    type: str
    slug: str
    title: str
    description: str
    body: str


@dataclass(frozen=True)
class MemoryWriteResult:
    written: bool
    path: Path | None = None
    reason: str = ""


class MemoryWriter:
    def __init__(self, memory: MemoryManager, permissions: PermissionManager) -> None:
        self.memory = memory
        self.permissions = permissions

    def write_topic(self, entry: ExtractedMemory) -> MemoryWriteResult:
        if self.permissions.check("write_file", is_read_only=False) == "deny":
            return MemoryWriteResult(written=False, reason="permission denied")
        slug = sanitize_slug(entry.slug)
        if not slug:
            return MemoryWriteResult(written=False, reason="invalid slug")
        memory_type = entry.type if entry.type in VALID_MEMORY_TYPES else "project"
        title = _single_line(_redact(entry.title)).strip() or slug
        description = _single_line(_redact(entry.description)).strip()
        body = _redact(entry.body).strip()
        if not description or not body:
            return MemoryWriteResult(written=False, reason="empty memory")
        topic_path = self.memory.memory_dir_path() / f"{slug}.md"
        if not self.memory.is_memory_write_target(topic_path):
            return MemoryWriteResult(written=False, reason="path outside memory")
        topic_path.parent.mkdir(parents=True, exist_ok=True)
        topic_path.write_text(_render_topic(slug, description, memory_type, body), encoding="utf-8")
        _upsert_index_line(self.memory.memory_index_path(), title, f"{slug}.md", description)
        return MemoryWriteResult(written=True, path=topic_path)


def sanitize_slug(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered[:80].strip("-")


def _render_topic(slug: str, description: str, memory_type: str, body: str) -> str:
    return (
        "---\n"
        f"name: {slug}\n"
        f"description: {description}\n"
        "metadata:\n"
        f"  type: {memory_type}\n"
        "---\n\n"
        f"{body}\n"
    )


def _upsert_index_line(index_path: Path, title: str, filename: str, hook: str) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"- [{title}]({filename}) - {hook[:150]}"
    existing = index_path.read_text(encoding="utf-8").splitlines() if index_path.exists() else []
    prefix = f"- [{title}]({filename})"
    updated = [line if item.startswith(prefix) else item for item in existing]
    if all(not item.startswith(prefix) for item in existing):
        updated.append(line)
    index_path.write_text("\n".join(updated).strip() + "\n", encoding="utf-8")


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _redact(value: str) -> str:
    patterns = [
        r"Authorization:\s*(Bearer|Basic)\s+[^\s]+",
        r"(?i)(access_token|client_secret|api_key|app_secret|QQ_BOT_CLIENT_SECRET)\s*[:=]\s*[^,\s]+",
        r"(?i)(--token|--secret|--password)\s+\S+",
    ]
    result = value
    for pattern in patterns:
        result = re.sub(pattern, lambda match: match.group(0).split()[0] + " [REDACTED]", result)
    return result
```

- [x] **Step 4: Run focused writer tests**

Run:

```text
pytest tests/test_memory_extraction.py::test_memory_writer_creates_topic_and_index tests/test_memory_extraction.py::test_memory_writer_respects_explicit_deny tests/test_memory_extraction.py::test_memory_writer_redacts_secret_like_values -q
```

Expected:

- All three tests pass.

- [x] **Step 5: Run permission regression tests**

Run:

```text
pytest tests/test_agent_memory_permissions.py tests/test_memory_extraction.py -q
```

Expected:

- Existing memory auto-allow behavior remains unchanged.
- Writer tests pass.

- [x] **Step 6: Stop for review**

If committing is requested:

```text
git add src/xcode_cli/core/memory_writer.py tests/test_memory_extraction.py tests/test_agent_memory_permissions.py
git commit -m "feat: add safe memory writer"
```

