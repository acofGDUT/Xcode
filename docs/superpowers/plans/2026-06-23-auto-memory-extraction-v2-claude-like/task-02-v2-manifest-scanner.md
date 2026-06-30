# Task 02: V2 Manifest Scanner

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P0/P1

## Goal

Make manifest scanning consume v2 topic frontmatter by default and skip old `metadata.type` topics with warnings, so extraction subagent dedupe is based on the same format it writes.

## Suggested Files

- Modify: `src/xcode_cli/core/memory_manifest.py`
- Create: `tests/test_memory_manifest_v2.py`
- Modify: `tests/test_memory_manifest.py`

## Constraints

- `MEMORY.md` is never a topic candidate.
- Each topic reads at most 30 lines or 16 KiB frontmatter.
- Stable memory dir wins over legacy if both contain the same filename.
- v2 extraction defaults to stable dir; legacy participation should remain explicit and bounded.
- Recall v2 remains out of scope.

## Steps

- [x] **Step 1: Add v2 scanner tests**

Create `tests/test_memory_manifest_v2.py`:

```python
from __future__ import annotations

from pathlib import Path

from xcode_cli.core.memory_manifest import MemoryManifestScanner


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_v2_manifest_reads_top_level_type_and_skips_memory_index(tmp_path: Path) -> None:
    _write(
        tmp_path / "review.md",
        "---\nname: review\ndescription: Findings first.\ntype: feedback\n---\nBody\n",
    )
    _write(tmp_path / "MEMORY.md", "- [Review](review.md) - hook\n")

    result = MemoryManifestScanner(tmp_path).scan()

    assert result.warnings == []
    assert [(entry.filename, entry.type, entry.description) for entry in result.entries] == [
        ("review.md", "feedback", "Findings first.")
    ]


def test_v2_manifest_skips_legacy_metadata_type_with_warning(tmp_path: Path) -> None:
    _write(
        tmp_path / "legacy.md",
        "---\nname: legacy\ndescription: old\nmetadata:\n  type: feedback\n---\nBody\n",
    )

    result = MemoryManifestScanner(tmp_path).scan()

    assert result.entries == []
    assert "legacy.md: legacy-format skipped" in result.warnings


def test_v2_manifest_skips_missing_type(tmp_path: Path) -> None:
    _write(tmp_path / "bad.md", "---\nname: bad\ndescription: missing type\n---\nBody\n")

    result = MemoryManifestScanner(tmp_path).scan()

    assert result.entries == []
    assert "bad.md: missing type" in result.warnings


def test_stable_still_overrides_legacy_for_same_filename(tmp_path: Path) -> None:
    stable = tmp_path / "stable"
    legacy = tmp_path / "legacy"
    _write(legacy / "same.md", "---\nname: same\ndescription: legacy\ntype: project\n---\n")
    _write(stable / "same.md", "---\nname: same\ndescription: stable\ntype: feedback\n---\n")

    result = MemoryManifestScanner(stable, legacy).scan()

    assert len(result.entries) == 1
    assert result.entries[0].description == "stable"
    assert result.entries[0].source == "stable"
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_manifest_v2.py -q
```

Expected:

- v2 top-level type test fails because current scanner reads `metadata.type`.
- legacy skip test fails because current scanner treats old format as valid.

- [x] **Step 3: Implement v2 type parsing**

In `src/xcode_cli/core/memory_manifest.py`, change `_entry_from_file()` to read only top-level `type`:

```python
raw_type = str(frontmatter.get("type") or "").strip()
if not raw_type:
    if isinstance(frontmatter.get("metadata"), dict):
        raise ValueError("legacy-format skipped")
    raise ValueError("missing type")
if raw_type not in VALID_TYPES:
    raise ValueError("invalid type")
```

Keep existing `description` validation and warning capture.

- [x] **Step 4: Update legacy v1 tests**

In `tests/test_memory_manifest.py`, convert new expected valid examples to top-level `type`. Add one explicit legacy skip assertion instead of expecting `metadata.type` to pass.

- [x] **Step 5: Run focused tests**

Run:

```text
pytest tests/test_memory_manifest_v2.py tests/test_memory_manifest.py -q
```

Expected:

- v2 scanner tests pass.
- Existing bounded-read, stable-over-legacy, and max-200 behavior still pass.

- [x] **Step 6: Stop for review**

Review before continuing:

- Scanner warnings are bounded strings with filenames only.
- No topic body is read beyond frontmatter limits.
- Old `metadata.type` is not silently accepted by v2 manifest.

If committing is requested:

```text
git add src/xcode_cli/core/memory_manifest.py tests/test_memory_manifest_v2.py tests/test_memory_manifest.py
git commit -m "feat: scan v2 memory manifest"
```
