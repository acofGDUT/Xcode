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
        "type: feedback\n"
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
        "---\nname: same\ndescription: legacy\ntype: project\n---\n",
        encoding="utf-8",
    )
    (stable / "same.md").write_text(
        "---\nname: same\ndescription: stable\ntype: feedback\n---\n",
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
            f"---\nname: m{index:03d}\ndescription: memory {index}\ntype: user\n---\n",
            encoding="utf-8",
        )

    result = MemoryManifestScanner(memory_dir).scan()

    assert len(result.entries) == 200
