from __future__ import annotations

from xcode_cli.core.config import Config
from xcode_cli.core.prompting import build_system_prompt


def test_auto_memory_prompt_uses_v2_frontmatter(tmp_path, monkeypatch) -> None:
    import xcode_cli.paths

    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", tmp_path / ".xcode", raising=True)
    prompt = build_system_prompt(Config(auto_memory=True), str(tmp_path))

    assert "metadata:\n  type:" not in prompt
    assert "type: <user|feedback|project|reference>" in prompt
    assert "Evidence:" in prompt
    assert "MEMORY.md" in prompt


def test_auto_memory_prompt_rejects_task_summaries_and_generic_topics(tmp_path, monkeypatch) -> None:
    import xcode_cli.paths

    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", tmp_path / ".xcode", raising=True)
    prompt = build_system_prompt(Config(auto_memory=True), str(tmp_path))

    assert "Do NOT save task progress" in prompt
    assert "Do NOT save implementation details" in prompt
    assert "generic slugs" in prompt
