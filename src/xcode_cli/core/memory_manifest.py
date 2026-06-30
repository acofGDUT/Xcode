from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


MAX_MANIFEST_FILES = 200
MAX_FRONTMATTER_LINES = 30
MAX_FRONTMATTER_BYTES = 16 * 1024
VALID_TYPES = {"user", "feedback", "project", "reference"}


@dataclass(frozen=True)
class MemoryManifestEntry:
    filename: str
    file_path: Path
    mtime_ms: int
    description: str
    type: str
    source: Literal["stable", "legacy"]


@dataclass(frozen=True)
class MemoryManifestResult:
    entries: list[MemoryManifestEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class MemoryManifestScanner:
    def __init__(self, memory_dir: Path, legacy_memory_dir: Path | None = None) -> None:
        self.memory_dir = memory_dir
        self.legacy_memory_dir = legacy_memory_dir

    def scan(self) -> MemoryManifestResult:
        warnings: list[str] = []
        entries_by_name: dict[str, MemoryManifestEntry] = {}
        for source, root in (("legacy", self.legacy_memory_dir), ("stable", self.memory_dir)):
            if root is None or not root.exists():
                continue
            for path in sorted(root.iterdir()):
                if not path.is_file():
                    continue
                if path.suffix.lower() != ".md" or path.name == "MEMORY.md":
                    continue
                try:
                    entry = _entry_from_file(path, source=source)
                except Exception as exc:
                    warnings.append(f"{path.name}: {exc}")
                    continue
                entries_by_name[path.name] = entry
        entries = sorted(entries_by_name.values(), key=lambda item: item.mtime_ms, reverse=True)
        return MemoryManifestResult(entries=entries[:MAX_MANIFEST_FILES], warnings=warnings)


def _entry_from_file(path: Path, *, source: Literal["stable", "legacy"]) -> MemoryManifestEntry:
    frontmatter = _read_frontmatter(path)
    description = str(frontmatter.get("description") or "").strip()
    if not description:
        raise ValueError("missing description")
    raw_type = str(frontmatter.get("type") or "").strip()
    if not raw_type:
        if isinstance(frontmatter.get("metadata"), dict):
            raise ValueError("legacy-format skipped")
        raise ValueError("missing type")
    if raw_type not in VALID_TYPES:
        raise ValueError("invalid type")
    stat = path.stat()
    return MemoryManifestEntry(
        filename=path.name,
        file_path=path,
        mtime_ms=int(stat.st_mtime * 1000),
        description=description,
        type=raw_type,
        source=source,
    )


def _read_frontmatter(path: Path) -> dict[str, object]:
    raw = path.read_bytes()[:MAX_FRONTMATTER_BYTES]
    text = raw.decode("utf-8")
    lines = text.splitlines()[:MAX_FRONTMATTER_LINES]
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing frontmatter")
    body: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return _parse_frontmatter_lines(body)
        body.append(line)
    raise ValueError("unterminated frontmatter")


def _parse_frontmatter_lines(lines: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    current_mapping: dict[str, str] | None = None
    current_key = ""
    for line in lines:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            if current_mapping is None or ":" not in line:
                raise ValueError(f"invalid frontmatter line: {line}")
            key, value = line.strip().split(":", 1)
            current_mapping[key.strip()] = value.strip()
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if value:
            result[current_key] = value
            current_mapping = None
        else:
            current_mapping = {}
            result[current_key] = current_mapping
    return result
