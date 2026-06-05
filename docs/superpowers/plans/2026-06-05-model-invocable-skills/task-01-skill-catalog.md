# Task 1: 建立 SkillCatalog

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Create: `src/xcode_cli/skills/catalog.py`
- Test: `tests/test_skill_catalog.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_skill_catalog.py`：

```python
from pathlib import Path

from xcode_cli.skills.catalog import SkillCatalog
from xcode_cli.skills.model import Skill


def _skill(name="review", **overrides):
    data = dict(
        name=name,
        display_name=None,
        description="Review code",
        body="Review $ARGUMENTS",
        root=Path(f"D:/Xcode/.xcode/skills/{name}"),
    )
    data.update(overrides)
    return Skill(**data)


def test_find_accepts_plain_or_slash_name():
    catalog = SkillCatalog([_skill("review")], builtin_commands={"/help"})

    assert catalog.find("review").name == "review"
    assert catalog.find("/review").name == "review"


def test_model_invocable_does_not_require_user_invocable():
    skill = _skill("internal", user_invocable=False, disable_model_invocation=False)
    catalog = SkillCatalog([skill], builtin_commands=set())

    assert [item.name for item in catalog.model_invocable_skills()] == ["internal"]
    assert catalog.user_invocable_skills() == []


def test_model_invocable_excludes_disabled_fork_and_builtin_conflicts():
    catalog = SkillCatalog(
        [
            _skill("review"),
            _skill("manual-only", disable_model_invocation=True),
            _skill("forked", context="fork"),
            _skill("help"),
        ],
        builtin_commands={"/help"},
    )

    assert [item.name for item in catalog.model_invocable_skills()] == ["review"]


def test_validate_model_invocation_returns_clear_errors():
    catalog = SkillCatalog(
        [
            _skill("review"),
            _skill("manual-only", disable_model_invocation=True),
            _skill("forked", context="fork"),
        ],
        builtin_commands={"/compact"},
    )

    assert catalog.validate_model_invocation("").startswith("Error:")
    assert "not found" in catalog.validate_model_invocation("missing")
    assert "built-in" in catalog.validate_model_invocation("/compact")
    assert "disabled" in catalog.validate_model_invocation("manual-only")
    assert "fork" in catalog.validate_model_invocation("forked")
    assert catalog.validate_model_invocation("review") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_skill_catalog.py -q
```

Expected: FAIL，提示 `No module named 'xcode_cli.skills.catalog'`。

- [ ] **Step 3: 实现 SkillCatalog**

创建 `src/xcode_cli/skills/catalog.py`：

```python
from __future__ import annotations

from xcode_cli.skills.model import Skill


class SkillCatalog:
    def __init__(self, skills: list[Skill], builtin_commands: set[str]) -> None:
        self._builtin_commands = {_command_name(name) for name in builtin_commands}
        self._skills = {_skill_key(skill.name): skill for skill in skills}

    def find(self, name: str) -> Skill | None:
        return self._skills.get(_skill_key(name))

    def user_invocable_skills(self) -> list[Skill]:
        return [
            skill
            for skill in self._sorted_skills()
            if skill.user_invocable and not self._conflicts_with_builtin(skill.name)
        ]

    def model_invocable_skills(self) -> list[Skill]:
        return [
            skill
            for skill in self._sorted_skills()
            if self.validate_model_invocation(skill.name) is None
        ]

    def validate_model_invocation(self, name: str) -> str | None:
        normalized = _skill_key(name)
        if not normalized:
            return "Error: skill name is required."
        if self._conflicts_with_builtin(normalized):
            return f"Error: '{normalized}' is a built-in command, not a skill."

        skill = self.find(normalized)
        if skill is None:
            return f"Error: skill not found: {normalized}"
        if skill.disable_model_invocation:
            return f"Error: skill '{skill.name}' has model invocation disabled."
        if (skill.context or "").strip().lower() == "fork":
            return f"Error: skill '{skill.name}' requires fork execution, which is not supported yet."
        return None

    def _sorted_skills(self) -> list[Skill]:
        return [self._skills[name] for name in sorted(self._skills)]

    def _conflicts_with_builtin(self, name: str) -> bool:
        return _command_name(name) in self._builtin_commands


def _skill_key(name: str) -> str:
    return name.strip().lower().lstrip("/")


def _command_name(name: str) -> str:
    key = _skill_key(name)
    return f"/{key}" if key else ""
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
pytest tests/test_skill_catalog.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/xcode_cli/skills/catalog.py tests/test_skill_catalog.py
git commit -m "feat: add model-invocable skill catalog"
```
