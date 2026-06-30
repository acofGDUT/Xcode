from __future__ import annotations

from xcode_cli.core.memory_extraction_policy import validate_v2_memory
from xcode_cli.core.memory_writer import ExtractedMemory


def _memory(**overrides) -> ExtractedMemory:
    data = {
        "type": "feedback",
        "slug": "review-findings-first",
        "title": "Review findings first",
        "description": "User prefers review output to lead with findings.",
        "body": (
            "Rule: Lead with findings.\n"
            'Evidence: "review output should lead with issues"\n'
            "How to apply: Put findings before summary."
        ),
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
            body='Rule: Task 04 completed.\nEvidence: "pytest -q passed"\nHow to apply: Continue.',
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
