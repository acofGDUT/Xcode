# Task 01: V2 Format, Policy, And Prompt

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P0

## Goal

Make v2 memory format the only new-write format for both the main agent and background extraction path: top-level `type`, required `Evidence:`, atomic topic body, and explicit rejection of generic/task-summary/secret-like memory.

## Suggested Files

- Modify: `src/xcode_cli/core/prompting.py`
- Modify: `src/xcode_cli/core/memory_writer.py`
- Create: `src/xcode_cli/core/memory_extraction_policy.py`
- Test: `tests/test_prompting_memory_v2.py`
- Test: `tests/test_memory_extraction_policy.py`
- Modify: `tests/test_memory_extraction.py`
- Modify: `tests/test_prompting_memory.py`

## Constraints

- New topic writes must not use old `metadata.type`.
- `MEMORY.md` still uses short relative links only.
- Explicit `deny write_file` remains stronger than memory auto-allow.
- Writer-level validation must reject unsafe content before touching disk.
- Do not update `ARCHITECTURE.md` in this task; v2 is not fully implemented yet.

## Steps

- [x] **Step 1: Add prompt tests for v2 memory format**

Create `tests/test_prompting_memory_v2.py`:

```python
from __future__ import annotations

from xcode_cli.core.config import Config
from xcode_cli.core.prompting import build_system_prompt


def test_auto_memory_prompt_uses_v2_frontmatter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    prompt = build_system_prompt(Config(auto_memory=True), str(tmp_path))

    assert "metadata:\n  type:" not in prompt
    assert "type: <user|feedback|project|reference>" in prompt
    assert "Evidence:" in prompt
    assert "MEMORY.md" in prompt


def test_auto_memory_prompt_rejects_task_summaries_and_generic_topics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XCODE_DIR", str(tmp_path / ".xcode"))
    prompt = build_system_prompt(Config(auto_memory=True), str(tmp_path))

    assert "Do NOT save task progress" in prompt
    assert "Do NOT save implementation details" in prompt
    assert "generic slugs" in prompt
```

- [x] **Step 2: Add policy tests**

Create `tests/test_memory_extraction_policy.py`:

```python
from __future__ import annotations

from xcode_cli.core.memory_extraction_policy import validate_v2_memory
from xcode_cli.core.memory_writer import ExtractedMemory


def _memory(**overrides) -> ExtractedMemory:
    data = {
        "type": "feedback",
        "slug": "review-findings-first",
        "title": "Review findings first",
        "description": "User prefers review output to lead with findings.",
        "body": 'Rule: Lead with findings.\nEvidence: "User said review output should lead with findings."\nHow to apply: Put findings before summary.',
    }
    data.update(overrides)
    return ExtractedMemory(**data)


def test_validate_v2_memory_accepts_specific_evidence_backed_memory() -> None:
    result = validate_v2_memory(_memory())

    assert result.accepted
    assert result.reason == ""


def test_validate_v2_memory_rejects_missing_evidence() -> None:
    result = validate_v2_memory(_memory(body="Rule: Lead with findings."))

    assert not result.accepted
    assert result.reason == "missing evidence"


def test_validate_v2_memory_rejects_generic_slug() -> None:
    result = validate_v2_memory(_memory(slug="user-feedback"))

    assert not result.accepted
    assert result.reason == "generic memory"


def test_validate_v2_memory_rejects_task_progress_summary() -> None:
    result = validate_v2_memory(
        _memory(
            slug="task-completed",
            body="Rule: Task 04 completed.\nEvidence: \"pytest -q passed\"\nHow to apply: Continue.",
        )
    )

    assert not result.accepted
    assert result.reason == "task summary"


def test_validate_v2_memory_rejects_secret_like_value() -> None:
    result = validate_v2_memory(
        _memory(body='Rule: Token is Authorization: Bearer abc.\nEvidence: "Authorization: Bearer abc"')
    )

    assert not result.accepted
    assert result.reason == "secret-like content"
```

- [x] **Step 3: Run tests to verify failure**

Run:

```text
pytest tests/test_prompting_memory_v2.py tests/test_memory_extraction_policy.py -q
```

Expected:

- Prompt tests fail because v1 prompt still shows `metadata.type`.
- Policy import fails because `memory_extraction_policy.py` does not exist.

- [x] **Step 4: Implement policy helpers**

Create `src/xcode_cli/core/memory_extraction_policy.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from typing import Any

from xcode_cli.core.memory_writer import sanitize_slug


GENERIC_SLUGS = {
    "project-update",
    "memory-improvement",
    "user-feedback",
    "coding-preferences",
    "task-completed",
    "implementation-summary",
}

TASK_SUMMARY_PATTERNS = (
    r"\btask\s+\d+\s+(completed|done|passed)\b",
    r"\bpytest\b.*\bpassed\b",
    r"\bmodified files?\b",
    r"\bimplemented\b.*\btests?\b",
    r"(?i)\bcompleted\b.*\btests?\b",
    r"(?i)\btask\b.*\bfinished\b",
)

SECRET_PATTERNS = (
    r"(?i)Authorization:\s*(Bearer|Basic)\s+\S+",
    r"(?i)\b(access_token|client_secret|api_key|app_secret|QQ_BOT_CLIENT_SECRET)\s*[:=]\s*\S+",
    r"(?i)(--token|--secret|--password)\s+\S+",
    r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
)


@dataclass(frozen=True)
class PolicyResult:
    accepted: bool
    reason: str = ""


def validate_v2_memory(entry: Any) -> PolicyResult:
    slug = sanitize_slug(entry.slug)
    text = "\n".join([entry.title, entry.description, entry.body])
    lowered = text.lower()
    if not slug or slug in GENERIC_SLUGS:
        return PolicyResult(False, "generic memory")
    if "evidence:" not in lowered:
        return PolicyResult(False, "missing evidence")
    if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
        return PolicyResult(False, "secret-like content")
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in TASK_SUMMARY_PATTERNS):
        return PolicyResult(False, "task summary")
    return PolicyResult(True)


def validate_v2_topic_text(content: str) -> PolicyResult:
    frontmatter, body = _split_frontmatter(content)
    if frontmatter is None:
        return PolicyResult(False, "missing frontmatter")
    if "metadata:" in frontmatter:
        return PolicyResult(False, "legacy-format skipped")
    if not re.search(r"(?m)^name:\s*\S+", frontmatter):
        return PolicyResult(False, "missing name")
    if not re.search(r"(?m)^description:\s*\S+", frontmatter):
        return PolicyResult(False, "missing description")
    match = re.search(r"(?m)^type:\s*(\S+)\s*$", frontmatter)
    if not match or match.group(1) not in {"user", "feedback", "project", "reference"}:
        return PolicyResult(False, "missing type")
    text = f"{frontmatter}\n{body}"
    if "evidence:" not in body.lower():
        return PolicyResult(False, "missing evidence")
    if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
        return PolicyResult(False, "secret-like content")
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in TASK_SUMMARY_PATTERNS):
        return PolicyResult(False, "task summary")
    return PolicyResult(True)


def _split_frontmatter(content: str) -> tuple[str | None, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, content
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])
    return None, content
```

- [x] **Step 5: Upgrade writer to v2 format**

In `src/xcode_cli/core/memory_writer.py`, make `write_topic()` call `validate_v2_memory()` after redaction/sanitization and render:

```python
def _render_topic(slug: str, description: str, memory_type: str, body: str) -> str:
    return (
        "---\n"
        f"name: {slug}\n"
        f"description: {description}\n"
        f"type: {memory_type}\n"
        "---\n\n"
        f"{body}\n"
    )
```

Keep `MemoryWriteResult(written=False, reason=<policy reason>)` when policy rejects.

- [x] **Step 6: Upgrade main agent memory prompt**

In `src/xcode_cli/core/prompting.py`, change the auto memory format section to:

```text
---
name: kebab-case-slug
description: one-line summary used to decide relevance in future conversations
type: <user|feedback|project|reference>
---

Rule: one atomic durable rule, fact, decision, or reference.
Evidence: "short user quote or explicit external reference from the current conversation"
How to apply: when future Xcode should use this memory.
```

Also add explicit wording:

```text
Do NOT save task progress, implementation summaries, file modification lists,
test results, git history, code patterns, or generic slugs such as
project-update, memory-improvement, user-feedback, coding-preferences.
```

- [x] **Step 7: Update v1 tests that assert old frontmatter**

Change tests that assert `"metadata:\n  type:"` to assert top-level `"type: feedback"` or move legacy-format expectations into v2 migration/recall specs.

- [x] **Step 8: Run focused tests**

Run:

```text
pytest tests/test_prompting_memory_v2.py tests/test_memory_extraction_policy.py tests/test_memory_extraction.py tests/test_prompting_memory.py -q
```

Expected:

- Prompt and writer tests pass.
- Existing memory write permission tests still pass.
- Old `metadata.type` new-write assertions are gone.

- [x] **Step 9: Stop for review**

Review before continuing:

- No new topic write path emits `metadata.type`.
- Policy rejection happens before disk write.
- `MEMORY.md` index remains relative-link only.

If committing is requested:

```text
git add src/xcode_cli/core/prompting.py src/xcode_cli/core/memory_writer.py src/xcode_cli/core/memory_extraction_policy.py tests/test_prompting_memory_v2.py tests/test_memory_extraction_policy.py tests/test_memory_extraction.py tests/test_prompting_memory.py
git commit -m "feat: enforce v2 auto memory format"
```
