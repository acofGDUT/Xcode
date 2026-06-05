# Task 2: 实现 Skill 数据结构和 loader

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Create: `src/xcode_cli/skills/model.py`
- Create: `src/xcode_cli/skills/loader.py`
- Test: `tests/test_skill_loader.py`

- [ ] **Step 1: 写 loader 测试**

创建 `tests/test_skill_loader.py`：

```python
from pathlib import Path

from xcode_cli.skills.loader import SkillLoader


def test_loads_skill_from_project_xcode_skills(tmp_path):
    skill_dir = tmp_path / ".xcode" / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: Code Review
description: Review code changes
allowed-tools:
  - read
  - grep
argument-hint: "[path]"
arguments:
  - target
when_to_use: Use when reviewing diffs
disable-model-invocation: false
user-invocable: true
---

Review $ARGUMENTS.
""",
        encoding="utf-8",
    )

    result = SkillLoader(tmp_path).load()

    assert len(result.skills) == 1
    skill = result.skills[0]
    assert skill.name == "review"
    assert skill.display_name == "Code Review"
    assert skill.description == "Review code changes"
    assert skill.allowed_tools == ["read", "grep"]
    assert skill.argument_hint == "[path]"
    assert skill.argument_names == ["target"]
    assert skill.when_to_use == "Use when reviewing diffs"
    assert skill.disable_model_invocation is False
    assert skill.user_invocable is True
    assert "Review $ARGUMENTS." in skill.body


def test_supporting_files_are_not_loaded_into_skill_body(tmp_path):
    skill_dir = tmp_path / ".xcode" / "skills" / "review"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: Review code\n---\nRead ${XCODE_SKILL_DIR}/references/style.md when needed.",
        encoding="utf-8",
    )
    (refs_dir / "style.md").write_text("Large reference content", encoding="utf-8")

    result = SkillLoader(tmp_path).load()

    assert len(result.skills) == 1
    assert "Large reference content" not in result.skills[0].body
    assert "references/style.md" in result.skills[0].body


def test_description_falls_back_to_first_body_line(tmp_path):
    skill_dir = tmp_path / ".xcode" / "skills" / "explain"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Explain code clearly.\n\nMore detail.", encoding="utf-8")

    result = SkillLoader(tmp_path).load()

    assert result.skills[0].description == "Explain code clearly."


def test_invalid_frontmatter_skips_skill_and_records_notice(tmp_path):
    skill_dir = tmp_path / ".xcode" / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nallowed-tools: [\n---\nBody", encoding="utf-8")

    result = SkillLoader(tmp_path).load()

    assert result.skills == []
    assert result.notices
    assert "broken" in result.notices[0].message


def test_allowed_tools_supports_comma_separated_claude_style_names(tmp_path):
    skill_dir = tmp_path / ".xcode" / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: Review code\nallowed-tools: Read, Grep, Bash\n---\nReview.",
        encoding="utf-8",
    )

    result = SkillLoader(tmp_path).load()

    assert result.skills[0].allowed_tools == ["Read", "Grep", "Bash"]
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
pytest tests/test_skill_loader.py -q
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 model**

创建 `src/xcode_cli/skills/model.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Skill:
    name: str
    display_name: str | None
    description: str
    body: str
    root: Path
    allowed_tools: list[str] = field(default_factory=list)
    argument_hint: str | None = None
    argument_names: list[str] = field(default_factory=list)
    when_to_use: str | None = None
    model: str | None = None
    effort: str | None = None
    disable_model_invocation: bool = False
    user_invocable: bool = True
    context: str | None = None
    agent: str | None = None
    paths: list[str] = field(default_factory=list)
    hooks: dict[str, Any] | None = None
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillLoadNotice:
    path: Path
    message: str


@dataclass(frozen=True)
class SkillLoadResult:
    skills: list[Skill]
    notices: list[SkillLoadNotice] = field(default_factory=list)
```

- [ ] **Step 4: 实现 loader**

创建 `src/xcode_cli/skills/loader.py`。当前 `pyproject.toml` 没有 PyYAML，第一版不要新增依赖，使用安全的最小 frontmatter 解析器，只支持本计划需要的标量、逗号分隔列表、inline list、字符串列表和简单字典保留。

核心接口：

```python
class SkillLoader:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)

    def load(self) -> SkillLoadResult:
        skills_root = self.project_root / ".xcode" / "skills"
        if not skills_root.exists():
            return SkillLoadResult(skills=[])
        skills: list[Skill] = []
        notices: list[SkillLoadNotice] = []
        for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                skills.append(self._load_skill(skill_dir, skill_md))
            except ValueError as exc:
                notices.append(SkillLoadNotice(path=skill_md, message=f"{skill_dir.name}: {exc}"))
        return SkillLoadResult(skills=skills, notices=notices)
```

必须从：

```python
self.project_root / ".xcode" / "skills"
```

加载一层子目录。

最小 parser 的行为要求：

```python
def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("invalid frontmatter: missing closing marker")
    raw = text[4:end]
    body = text[end + len("\n---"):].lstrip("\r\n")
    return _parse_simple_yaml(raw), body
```

`_parse_simple_yaml()` 至少支持：

- `key: value`
- `key: true` / `key: false`
- `key: Read, Grep, Bash`
- `key: [Read, Grep, Bash]`
- `key:` 后接缩进列表：

```yaml
allowed-tools:
  - read
  - grep
```

遇到明显无法解析的行时抛 `ValueError`，由 `load()` 记录 notice 并跳过该 skill。

不要读取 `references/`、`scripts/`、`templates/` 或 `assets/` 的内容；这些 supporting files 只作为目录包的一部分存在，后续由模型按需通过工具读取。

- [ ] **Step 5: 运行测试**

Run:

```powershell
pytest tests/test_skill_loader.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/xcode_cli/skills/model.py src/xcode_cli/skills/loader.py tests/test_skill_loader.py
git commit -m "feat: load project skills from SKILL markdown"
```
