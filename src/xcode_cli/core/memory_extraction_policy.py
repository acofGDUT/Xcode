from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from xcode_cli.core.memory_writer import sanitize_slug


VALID_V2_TYPES = {"user", "feedback", "project", "reference"}

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
    r"本轮实现",
    r"自动化回归",
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
    slug = sanitize_slug(str(entry.slug))
    text = "\n".join([str(entry.title), str(entry.description), str(entry.body)])
    secret_text = _remove_redacted_secret_placeholders(text)
    lowered = text.lower()
    if "evidence:" not in lowered:
        return PolicyResult(False, "missing evidence")
    if any(re.search(pattern, secret_text) for pattern in SECRET_PATTERNS):
        return PolicyResult(False, "secret-like content")
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in TASK_SUMMARY_PATTERNS):
        return PolicyResult(False, "task summary")
    if not slug or slug in GENERIC_SLUGS:
        return PolicyResult(False, "generic memory")
    return PolicyResult(True)


def validate_v2_topic_text(content: str) -> PolicyResult:
    frontmatter, body = _split_frontmatter(content)
    if frontmatter is None:
        return PolicyResult(False, "missing frontmatter")
    if re.search(r"(?m)^metadata\s*:", frontmatter):
        return PolicyResult(False, "legacy-format skipped")
    if not re.search(r"(?m)^name:\s*\S+", frontmatter):
        return PolicyResult(False, "missing name")
    if not re.search(r"(?m)^description:\s*\S+", frontmatter):
        return PolicyResult(False, "missing description")
    match = re.search(r"(?m)^type:\s*(\S+)\s*$", frontmatter)
    if not match or match.group(1) not in VALID_V2_TYPES:
        return PolicyResult(False, "missing type")
    text = f"{frontmatter}\n{body}"
    secret_text = _remove_redacted_secret_placeholders(text)
    if "evidence:" not in body.lower():
        return PolicyResult(False, "missing evidence")
    if any(re.search(pattern, secret_text) for pattern in SECRET_PATTERNS):
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


def _remove_redacted_secret_placeholders(text: str) -> str:
    result = re.sub(r"(?i)Authorization:\s*(Bearer|Basic)\s+\[REDACTED\]", "Authorization: [REDACTED]", text)
    result = re.sub(
        r"(?i)\b(access_token|client_secret|api_key|app_secret|QQ_BOT_CLIENT_SECRET)\s*[:=]\s*\[REDACTED\]",
        "[REDACTED]",
        result,
    )
    result = re.sub(r"(?i)(--token|--secret|--password)\s+\[REDACTED\]", "[REDACTED]", result)
    return result
