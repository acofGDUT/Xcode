# Task 4.5: 增加 skill validation

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Create: `src/xcode_cli/skills/validation.py`
- Test: `tests/test_skill_validation.py`

- [ ] **Step 1: 写 validation 测试**

创建 `tests/test_skill_validation.py`：

```python
from pathlib import Path

from xcode_cli.skills.model import Skill
from xcode_cli.skills.validation import validate_skills


def _skill(name="review", **overrides):
    data = dict(
        name=name,
        display_name=None,
        description="Review code",
        body="Review.",
        root=Path(f"D:/Xcode/.xcode/skills/{name}"),
    )
    data.update(overrides)
    return Skill(**data)


def test_warns_when_skill_conflicts_with_builtin_command():
    notices = validate_skills([_skill("init")], builtin_commands={"/init", "/help"})

    assert any("conflicts with built-in command" in n.message for n in notices)


def test_warns_when_description_uses_fallback():
    notices = validate_skills(
        [_skill(description="Review.", raw_frontmatter={})],
        builtin_commands=set(),
    )

    assert any("description missing" in n.message for n in notices)


def test_warns_for_unknown_allowed_tool():
    notices = validate_skills(
        [_skill(allowed_tools=["Read", "UnknownTool"])],
        builtin_commands=set(),
    )

    assert any("UnknownTool" in n.message for n in notices)
```

- [ ] **Step 2: 实现 validation**

创建 `src/xcode_cli/skills/validation.py`：

```python
from __future__ import annotations

from xcode_cli.skills.model import Skill, SkillLoadNotice
from xcode_cli.skills.prompt import normalize_tool_name


_KNOWN_TOOL_NAMES = {
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "glob",
    "run_shell",
    "dispatch_agent",
    "read",
    "write",
    "edit",
    "shell",
    "bash",
    "task",
}


def validate_skills(skills: list[Skill], builtin_commands: set[str]) -> list[SkillLoadNotice]:
    notices: list[SkillLoadNotice] = []
    for skill in skills:
        if f"/{skill.name}" in builtin_commands:
            notices.append(SkillLoadNotice(skill.root, f"{skill.name}: conflicts with built-in command"))
        if "description" not in skill.raw_frontmatter:
            notices.append(SkillLoadNotice(skill.root, f"{skill.name}: description missing; using body fallback"))
        for tool in skill.allowed_tools:
            normalized = normalize_tool_name(tool)
            if normalized == tool and tool.strip().lower() not in _KNOWN_TOOL_NAMES:
                notices.append(SkillLoadNotice(skill.root, f"{skill.name}: unknown allowed tool {tool}"))
        if skill.context == "fork":
            notices.append(SkillLoadNotice(skill.root, f"{skill.name}: context=fork is not supported yet"))
        if skill.hooks:
            notices.append(SkillLoadNotice(skill.root, f"{skill.name}: hooks are parsed but not executed"))
    return notices
```

- [ ] **Step 3: 运行测试**

Run:

```powershell
pytest tests/test_skill_validation.py tests/test_skill_command_registry.py -q
```

Expected: PASS。

- [ ] **Step 4: 提交**

```powershell
git add src/xcode_cli/skills/validation.py tests/test_skill_validation.py tests/test_skill_command_registry.py
git commit -m "feat: validate project skills"
```
