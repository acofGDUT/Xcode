from pathlib import Path

import pytest

from xcode_cli.skills.model import Skill
from xcode_cli.skills.prompt import SkillPromptExpander, UnsupportedSkillInvocation


def _skill(**overrides):
    data = dict(
        name="review",
        display_name=None,
        description="Review",
        body="Use args: $ARGUMENTS\nDir: ${XCODE_SKILL_DIR}",
        root=Path("D:/Xcode/.xcode/skills/review"),
    )
    data.update(overrides)
    return Skill(**data)


def test_expands_arguments_and_skill_dir():
    result = SkillPromptExpander().expand(_skill(), "src/foo.py")

    assert "Use args: src/foo.py" in result.prompt
    assert "D:/Xcode/.xcode/skills/review" in result.prompt.replace("\\", "/")
    assert result.allowed_tools is None


def test_context_fork_is_not_executed_inline():
    with pytest.raises(UnsupportedSkillInvocation):
        SkillPromptExpander().expand(_skill(context="fork"), "")


def test_allowed_tools_are_normalized():
    result = SkillPromptExpander().expand(
        _skill(allowed_tools=["Read", "Grep", "Bash", "unknown_tool"]),
        "src",
    )

    assert result.allowed_tools == ["read_file", "grep", "run_shell", "unknown_tool"]
