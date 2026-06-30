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
        from xcode_cli.core.memory_extraction_policy import validate_v2_memory

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

        sanitized_entry = ExtractedMemory(
            type=memory_type,
            slug=slug,
            title=title,
            description=description,
            body=body,
        )
        policy = validate_v2_memory(sanitized_entry)
        if not policy.accepted:
            return MemoryWriteResult(written=False, reason=policy.reason)

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
        f"type: {memory_type}\n"
        "---\n\n"
        f"{body}\n"
    )


def _upsert_index_line(index_path: Path, title: str, filename: str, hook: str) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"- [{title}]({filename}) - {hook[:150]}"
    existing = index_path.read_text(encoding="utf-8").splitlines() if index_path.exists() else []
    updated = [line if f"]({filename})" in item else item for item in existing]
    if all(f"]({filename})" not in item for item in existing):
        updated.append(line)
    index_path.write_text("\n".join(updated).strip() + "\n", encoding="utf-8")


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _redact(value: str) -> str:
    result = re.sub(
        r"(?i)Authorization:\s*(Bearer|Basic)\s+[^\s]+",
        lambda match: f"Authorization: {match.group(1)} [REDACTED]",
        value,
    )
    result = re.sub(
        r"(?i)\b(access_token|client_secret|api_key|app_secret|QQ_BOT_CLIENT_SECRET)\s*([:=])\s*[^,\s]+",
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        result,
    )
    result = re.sub(
        r"(?i)(--token|--secret|--password)\s+\S+",
        lambda match: f"{match.group(1)} [REDACTED]",
        result,
    )
    return result
