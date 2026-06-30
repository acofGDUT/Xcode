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
