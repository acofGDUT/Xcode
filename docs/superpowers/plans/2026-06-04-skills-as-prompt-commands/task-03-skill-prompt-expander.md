# Task 3: 实现 skill prompt 展开

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Create: `src/xcode_cli/skills/prompt.py`
- Test: `tests/test_skill_prompt.py`

- [ ] **Step 1: 写 prompt 展开测试**

创建 `tests/test_skill_prompt.py`：

```python
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
```

- [ ] **Step 2: 实现 expander**

创建 `src/xcode_cli/skills/prompt.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

from xcode_cli.skills.model import Skill


class UnsupportedSkillInvocation(Exception):
    pass


@dataclass(frozen=True)
class ExpandedSkillPrompt:
    prompt: str
    allowed_tools: list[str] | None


_TOOL_ALIASES = {
    "read": "read_file",
    "read_file": "read_file",
    "write": "write_file",
    "write_file": "write_file",
    "edit": "edit_file",
    "edit_file": "edit_file",
    "grep": "grep",
    "glob": "glob",
    "shell": "run_shell",
    "bash": "run_shell",
    "run_shell": "run_shell",
    "task": "dispatch_agent",
    "dispatch_agent": "dispatch_agent",
}


def normalize_tool_name(name: str) -> str:
    key = name.strip().lower()
    return _TOOL_ALIASES.get(key, name)


class SkillPromptExpander:
    def expand(self, skill: Skill, args: str) -> ExpandedSkillPrompt:
        if skill.context == "fork":
            raise UnsupportedSkillInvocation(
                "This skill requires fork execution, which is not supported yet."
            )

        prompt = skill.body.replace("$ARGUMENTS", args)
        prompt = prompt.replace("${XCODE_SKILL_DIR}", str(skill.root))
        allowed = [normalize_tool_name(t) for t in skill.allowed_tools]
        return ExpandedSkillPrompt(prompt=prompt, allowed_tools=allowed or None)
```

- [ ] **Step 3: 运行测试**

Run:

```powershell
pytest tests/test_skill_prompt.py -q
```

Expected: PASS。

- [ ] **Step 4: 提交**

```powershell
git add src/xcode_cli/skills/prompt.py tests/test_skill_prompt.py
git commit -m "feat: expand skill prompts"
```
