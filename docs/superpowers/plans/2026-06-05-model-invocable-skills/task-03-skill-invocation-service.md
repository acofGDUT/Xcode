# Task 3: 抽 SkillInvocationService

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Create: `src/xcode_cli/skills/invocation.py`
- Modify: `src/xcode_cli/core/commands/registry.py`
- Test: `tests/test_skill_invocation_service.py`
- Test: `tests/test_skill_prompt_command_flow.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_skill_invocation_service.py`：

```python
from pathlib import Path

from xcode_cli.skills.catalog import SkillCatalog
from xcode_cli.skills.invocation import SkillInvocationService
from xcode_cli.skills.model import Skill


def _skill(name="review", **overrides):
    data = dict(
        name=name,
        display_name=None,
        description="Review code",
        body="Review $ARGUMENTS in ${XCODE_SKILL_DIR}",
        root=Path(f"D:/Xcode/.xcode/skills/{name}"),
        source_path=Path(f"D:/Xcode/.xcode/skills/{name}/SKILL.md"),
        source_hash="sha256:test",
        allowed_tools=["Read", "Grep"],
    )
    data.update(overrides)
    return Skill(**data)


def test_user_invocation_returns_display_and_model_metadata():
    catalog = SkillCatalog([_skill("review")], builtin_commands=set())
    service = SkillInvocationService(catalog)

    invocation = service.invoke_for_user("review", "src/foo.py")

    assert invocation.display_content == "/review src/foo.py"
    assert "Review src/foo.py" in invocation.model_content
    assert invocation.allowed_tools == ["read_file", "grep"]
    assert invocation.model_metadata["source"] == "user"
    assert invocation.model_metadata["skill"] == "review"
    assert invocation.model_metadata["model_content"] == invocation.model_content
    assert invocation.audit_metadata["source"] == "user"
    assert invocation.audit_metadata["skill"] == "review"
    assert invocation.audit_metadata["source_path"].endswith("SKILL.md")
    assert invocation.audit_metadata["skill_source_hash"] == "sha256:test"
    assert "model_content" not in invocation.audit_metadata


def test_model_invocation_allows_non_user_invocable_skill():
    catalog = SkillCatalog([_skill("internal", user_invocable=False)], builtin_commands=set())
    service = SkillInvocationService(catalog)

    invocation = service.invoke_for_model("internal", None)

    assert invocation.audit_metadata["source"] == "model"
    assert invocation.audit_metadata["skill"] == "internal"
    assert "model_content" not in invocation.audit_metadata


def test_model_invocation_returns_error_for_disabled_skill():
    catalog = SkillCatalog([_skill("manual-only", disable_model_invocation=True)], builtin_commands=set())
    service = SkillInvocationService(catalog)

    result = service.invoke_for_model("manual-only", "")

    assert isinstance(result, str)
    assert result.startswith("Error:")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_skill_invocation_service.py -q
```

Expected: FAIL，提示 `No module named 'xcode_cli.skills.invocation'`。

- [ ] **Step 3: 实现 SkillInvocationService**

创建 `src/xcode_cli/skills/invocation.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from xcode_cli.skills.catalog import SkillCatalog
from xcode_cli.skills.prompt import SkillPromptExpander, UnsupportedSkillInvocation


@dataclass(frozen=True)
class SkillInvocation:
    display_content: str
    model_content: str
    model_metadata: dict[str, object]
    audit_metadata: dict[str, object]
    allowed_tools: list[str] | None


class SkillInvocationService:
    def __init__(self, catalog: SkillCatalog) -> None:
        self._catalog = catalog
        self._expander = SkillPromptExpander()

    def invoke_for_user(self, skill_name: str, args: str | None) -> SkillInvocation | str:
        return self._invoke(skill_name, args or "", source="user", validate_model=False)

    def invoke_for_model(self, skill_name: str, args: str | None) -> SkillInvocation | str:
        error = self._catalog.validate_model_invocation(skill_name)
        if error is not None:
            return error
        return self._invoke(skill_name, args or "", source="model", validate_model=True)

    def _invoke(
        self,
        skill_name: str,
        args: str,
        *,
        source: Literal["user", "model"],
        validate_model: bool,
    ) -> SkillInvocation | str:
        skill = self._catalog.find(skill_name)
        if skill is None:
            return f"Error: skill not found: {skill_name.strip().lstrip('/')}"
        try:
            expanded = self._expander.expand(skill, args)
        except UnsupportedSkillInvocation as exc:
            return f"Error: {exc}"

        audit_metadata: dict[str, object] = {
            "kind": "skill_invocation",
            "source": source,
            "skill": skill.name,
            "args": args,
        }
        if skill.source_path is not None:
            audit_metadata["source_path"] = str(skill.source_path)
        if skill.source_hash is not None:
            audit_metadata["skill_source_hash"] = skill.source_hash

        model_metadata = dict(audit_metadata)
        model_metadata["model_content"] = expanded.prompt

        display = f"/{skill.name}" + (f" {args}" if args else "")
        return SkillInvocation(
            display_content=display,
            model_content=expanded.prompt,
            model_metadata=model_metadata,
            audit_metadata=audit_metadata,
            allowed_tools=expanded.allowed_tools,
        )
```

- [ ] **Step 4: 让 registry 复用 service**

修改 `src/xcode_cli/core/commands/registry.py`，让 `CommandRegistry.from_skills()` 接收可选 `invocation_service`；skill handler 调用 `invoke_for_user()`，不直接创建 `SkillPromptExpander()`。

关键行为：

```python
def create_skill_slash_command(skill: Skill, service: SkillInvocationService) -> SlashCommand:
    def handler(args: str) -> object:
        return service.invoke_for_user(skill.name, args)
```

如果 handler 返回 `SkillInvocation`，dispatcher 应转换为：

```python
UserTurnInput(
    display_content=invocation.display_content,
    model_content=invocation.model_content,
    metadata=invocation.model_metadata,
    allowed_tools=invocation.allowed_tools,
)
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```powershell
pytest tests/test_skill_invocation_service.py tests/test_skill_prompt_command_flow.py tests/test_skill_command_registry.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/xcode_cli/skills/invocation.py src/xcode_cli/core/commands/registry.py tests/test_skill_invocation_service.py tests/test_skill_prompt_command_flow.py tests/test_skill_command_registry.py
git commit -m "feat: share skill invocation expansion"
```
