# Task 02: Memory Manifest Scanner

**Risk layer:** P0/P1

## Goal

Add a bounded scanner that reads auto memory topic frontmatter from stable and legacy memory dirs without injecting full bodies or treating `MEMORY.md` as a topic file.

## Suggested Files

- Create: `src/xcode_cli/core/memory_manifest.py`
- Modify: `src/xcode_cli/core/memory.py`
- Test: `tests/test_memory_manifest.py`
- Test: `tests/test_memory.py`

## Constraints

- Scan only `.md` files and exclude `MEMORY.md`.
- Read at most first 30 lines or 16 KiB per file.
- Keep at most 200 newest candidates.
- Bad frontmatter and read errors are warnings, not exceptions.
- Stable entries override legacy entries with the same filename.

## Steps

- [x] **Step 1: Write scanner tests**

Create `tests/test_memory_manifest.py`:

```python
from __future__ import annotations

from pathlib import Path

from xcode_cli.core.memory_manifest import MemoryManifestScanner


def test_scanner_reads_frontmatter_and_excludes_memory_index(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text("- [Index](one.md) - hook\n", encoding="utf-8")
    (memory_dir / "one.md").write_text(
        "---\n"
        "name: one\n"
        "description: User likes concise answers\n"
        "metadata:\n"
        "  type: feedback\n"
        "---\n"
        "Body should not be needed for manifest.\n",
        encoding="utf-8",
    )

    result = MemoryManifestScanner(memory_dir).scan()

    assert [entry.filename for entry in result.entries] == ["one.md"]
    assert result.entries[0].description == "User likes concise answers"
    assert result.entries[0].type == "feedback"
    assert result.entries[0].source == "stable"
    assert result.warnings == []


def test_scanner_skips_bad_frontmatter_with_warning(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "bad.md").write_text("---\nname bad\n---\nbody\n", encoding="utf-8")

    result = MemoryManifestScanner(memory_dir).scan()

    assert result.entries == []
    assert result.warnings
    assert "bad.md" in result.warnings[0]


def test_stable_entry_wins_over_legacy_entry(tmp_path: Path) -> None:
    stable = tmp_path / "stable"
    legacy = tmp_path / "legacy"
    stable.mkdir()
    legacy.mkdir()
    (legacy / "same.md").write_text(
        "---\nname: same\ndescription: legacy\nmetadata:\n  type: project\n---\n",
        encoding="utf-8",
    )
    (stable / "same.md").write_text(
        "---\nname: same\ndescription: stable\nmetadata:\n  type: feedback\n---\n",
        encoding="utf-8",
    )

    result = MemoryManifestScanner(stable, legacy).scan()

    assert len(result.entries) == 1
    assert result.entries[0].description == "stable"
    assert result.entries[0].source == "stable"


def test_scanner_keeps_200_newest_entries(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    for index in range(205):
        path = memory_dir / f"m{index:03d}.md"
        path.write_text(
            f"---\nname: m{index:03d}\ndescription: memory {index}\nmetadata:\n  type: user\n---\n",
            encoding="utf-8",
        )

    result = MemoryManifestScanner(memory_dir).scan()

    assert len(result.entries) == 200
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_manifest.py -q
```

Expected:

- Import fails because `xcode_cli.core.memory_manifest` does not exist.

- [x] **Step 3: Implement scanner models and bounded read**

Create `src/xcode_cli/core/memory_manifest.py`:

```python
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
    metadata = frontmatter.get("metadata")
    raw_type = ""
    if isinstance(metadata, dict):
        raw_type = str(metadata.get("type") or "")
    memory_type = raw_type if raw_type in VALID_TYPES else "unknown"
    if not description:
        raise ValueError("missing description")
    stat = path.stat()
    return MemoryManifestEntry(
        filename=path.name,
        file_path=path,
        mtime_ms=int(stat.st_mtime * 1000),
        description=description,
        type=memory_type,
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
```

- [x] **Step 4: Add MemoryManager scanner factory**

Modify `src/xcode_cli/core/memory.py`:

```python
    def manifest_dirs(self) -> tuple[Path, Path | None]:
        legacy = self.legacy_memory_dir if self.legacy_memory_dir != self.memory_dir else None
        return self.memory_dir, legacy
```

- [x] **Step 5: Run focused tests**

Run:

```text
pytest tests/test_memory_manifest.py tests/test_memory.py -q
```

Expected:

- All tests pass.

- [x] **Step 6: Stop for review**

If committing is requested:

```text
git add src/xcode_cli/core/memory_manifest.py src/xcode_cli/core/memory.py tests/test_memory_manifest.py tests/test_memory.py
git commit -m "feat: scan auto memory manifests"
```

