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


def test_appends_arguments_when_body_has_no_arguments_placeholder():
    result = SkillPromptExpander().expand(
        _skill(body="Review carefully."),
        "只检查登录模块，不要跑全量测试",
    )

    assert result.prompt == (
        "Review carefully.\n\n"
        "ARGUMENTS:\n"
        "只检查登录模块，不要跑全量测试"
    )


def test_does_not_append_arguments_when_placeholder_was_used():
    result = SkillPromptExpander().expand(
        _skill(body="Review this: $ARGUMENTS"),
        "src/foo.py",
    )

    assert result.prompt == "Review this: src/foo.py"
    assert "ARGUMENTS:" not in result.prompt


def test_does_not_append_arguments_when_args_are_blank():
    result = SkillPromptExpander().expand(
        _skill(body="Review carefully."),
        "   ",
    )

    assert result.prompt == "Review carefully."


def test_context_fork_is_not_executed_inline():
    with pytest.raises(UnsupportedSkillInvocation):
        SkillPromptExpander().expand(_skill(context="fork"), "")
