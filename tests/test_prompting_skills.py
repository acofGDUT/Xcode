from xcode_cli.core.config import Config
from xcode_cli.core.prompting import build_system_prompt


def _setup_xcode_home(tmp_path, monkeypatch):
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    return xcode_dir


def test_system_prompt_includes_skill_listing_and_guidance(tmp_path, monkeypatch):
    _setup_xcode_home(tmp_path, monkeypatch)

    prompt = build_system_prompt(
        Config(max_tokens=128000),
        cwd="D:/Xcode",
        skill_listing="Available skills:\n- review: Review code changes",
    )

    assert "Available skills:" in prompt
    assert "- review: Review code changes" in prompt
    assert "call the skill tool" in prompt
    assert "Do not call the skill tool for weak or speculative matches." in prompt
    assert "Do not use the skill tool for built-in CLI commands." in prompt


def test_system_prompt_omits_skill_guidance_without_listing(tmp_path, monkeypatch):
    _setup_xcode_home(tmp_path, monkeypatch)

    prompt = build_system_prompt(Config(), cwd="D:/Xcode", skill_listing="")

    assert "call the skill tool" not in prompt
