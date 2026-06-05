# Task 2: 建立 compact skill listing 预算器

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Create: `src/xcode_cli/skills/listing.py`
- Test: `tests/test_skill_listing.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_skill_listing.py`：

```python
from pathlib import Path

from xcode_cli.skills.listing import (
    DEFAULT_CHAR_BUDGET,
    MAX_LISTING_DESC_CHARS,
    SkillListingFormatter,
    skill_listing_char_budget,
)
from xcode_cli.skills.model import Skill


def _skill(name="review", **overrides):
    data = dict(
        name=name,
        display_name=None,
        description="Review code changes",
        body="FULL BODY MUST NOT APPEAR",
        root=Path(f"D:/Xcode/.xcode/skills/{name}"),
        when_to_use="Use when reviewing diffs",
        allowed_tools=["read_file", "grep"],
        argument_hint="[path]",
        paths=["src/**"],
        hooks={"pre": "echo no"},
    )
    data.update(overrides)
    return Skill(**data)


def test_char_budget_uses_one_percent_context_with_default_fallback():
    assert skill_listing_char_budget(128000) == 5120
    assert skill_listing_char_budget(0) == DEFAULT_CHAR_BUDGET


def test_listing_contains_only_name_description_and_when_to_use():
    content = SkillListingFormatter().format([_skill("review")], context_window_tokens=128000)

    assert "review" in content
    assert "Review code changes" in content
    assert "Use when reviewing diffs" in content
    assert "FULL BODY MUST NOT APPEAR" not in content
    assert "allowed_tools" not in content
    assert "argument-hint" not in content
    assert "src/**" not in content
    assert "echo no" not in content


def test_listing_truncates_long_summary_before_name_only_degradation():
    long_text = "x" * (MAX_LISTING_DESC_CHARS + 200)
    content = SkillListingFormatter().format(
        [_skill("review", description=long_text, when_to_use=long_text)],
        context_window_tokens=2000,
    )

    assert len(content) <= skill_listing_char_budget(2000)
    assert "...[truncated]" in content or "- review" in content


def test_listing_degrades_to_name_only_when_budget_is_tiny():
    skills = [_skill(f"skill-{i}", description="x" * 500, when_to_use="y" * 500) for i in range(20)]
    content = SkillListingFormatter().format(skills, context_window_tokens=100)

    assert "- skill-0" in content
    assert "Review code changes" not in content
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_skill_listing.py -q
```

Expected: FAIL，提示 `No module named 'xcode_cli.skills.listing'`。

- [ ] **Step 3: 实现 listing formatter**

创建 `src/xcode_cli/skills/listing.py`：

```python
from __future__ import annotations

from xcode_cli.skills.model import Skill

SKILL_BUDGET_CONTEXT_PERCENT = 0.01
CHARS_PER_TOKEN = 4
DEFAULT_CHAR_BUDGET = 8_000
MAX_LISTING_DESC_CHARS = 250


def skill_listing_char_budget(context_window_tokens: int | None) -> int:
    if not isinstance(context_window_tokens, int) or context_window_tokens <= 0:
        return DEFAULT_CHAR_BUDGET
    return int(context_window_tokens * SKILL_BUDGET_CONTEXT_PERCENT * CHARS_PER_TOKEN)


class SkillListingFormatter:
    def format(self, skills: list[Skill], context_window_tokens: int | None) -> str:
        ordered = sorted(skills, key=lambda skill: skill.name.lower())
        budget = skill_listing_char_budget(context_window_tokens)

        for mode in ("full", "truncated", "name_only"):
            content = self._format_entries(ordered, mode=mode, budget=budget)
            if len(content) <= budget:
                return content
        return self._format_name_only_with_omissions(ordered, budget)

    def _format_entries(self, skills: list[Skill], *, mode: str, budget: int) -> str:
        lines = ["Available skills:"]
        for skill in skills:
            if mode == "name_only":
                lines.append(f"- {skill.name}")
                continue
            summary = _summary(skill)
            if mode == "truncated":
                summary = _truncate(summary, MAX_LISTING_DESC_CHARS)
            lines.append(f"- {skill.name}: {summary}")
        return "\n".join(lines)

    def _format_name_only_with_omissions(self, skills: list[Skill], budget: int) -> str:
        lines = ["Available skills:"]
        omitted = 0
        for skill in skills:
            candidate = "\n".join([*lines, f"- {skill.name}"])
            if len(candidate) > budget:
                omitted += 1
                continue
            lines.append(f"- {skill.name}")
        if omitted:
            suffix = f"- ... {omitted} skill(s) omitted due to context budget"
            if len("\n".join([*lines, suffix])) <= budget:
                lines.append(suffix)
        return "\n".join(lines)


def _summary(skill: Skill) -> str:
    parts = [skill.description.strip()]
    if skill.when_to_use:
        parts.append(f"when_to_use: {skill.when_to_use.strip()}")
    return " | ".join(part for part in parts if part)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = "...[truncated]"
    return text[: max(limit - len(suffix), 0)].rstrip() + suffix
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
pytest tests/test_skill_listing.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/xcode_cli/skills/listing.py tests/test_skill_listing.py
git commit -m "feat: format model skill listings within budget"
```
