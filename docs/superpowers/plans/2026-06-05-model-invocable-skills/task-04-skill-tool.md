# Task 4: 增加 SkillTool 和 structured tool result

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Create: `src/xcode_cli/core/tools/skill_tool.py`
- Modify: `src/xcode_cli/core/tool_registry.py`
- Modify: `src/xcode_cli/core/tooling/execution.py`
- Test: `tests/test_skill_tool.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_skill_tool.py`：

```python
from pathlib import Path

from xcode_cli.core.tool_registry import ToolRegistry
from xcode_cli.core.tools.skill_tool import create_skill_tool
from xcode_cli.skills.catalog import SkillCatalog
from xcode_cli.skills.invocation import SkillInvocationService
from xcode_cli.skills.model import Skill


def _skill(name="review", **overrides):
    data = dict(
        name=name,
        display_name=None,
        description="Review code",
        body="Review $ARGUMENTS",
        root=Path(f"D:/Xcode/.xcode/skills/{name}"),
        source_path=Path(f"D:/Xcode/.xcode/skills/{name}/SKILL.md"),
        source_hash="sha256:test",
        allowed_tools=["read_file"],
    )
    data.update(overrides)
    return Skill(**data)


def test_skill_tool_schema_is_read_only_and_accepts_skill_args():
    tool = create_skill_tool(SkillInvocationService(SkillCatalog([_skill()], builtin_commands=set())))

    assert tool.name == "skill"
    assert tool.is_read_only is True
    assert "skill" in tool.parameters
    assert "args" in tool.parameters
    assert tool.required == ["skill"]


def test_skill_tool_returns_loaded_marker_audit_metadata_and_blocks_recursion():
    registry = ToolRegistry()
    registry.register(create_skill_tool(SkillInvocationService(SkillCatalog([_skill()], builtin_commands=set()))))

    result = registry.execute("skill", {"skill": "review", "args": "src/foo.py"})

    assert "<xcode_loaded_skill name=\"review\" source=\"model\">" in result.content
    assert "Review src/foo.py" in result.content
    assert result.audit_metadata["kind"] == "skill_invocation"
    assert result.audit_metadata["skill"] == "review"
    assert result.allowed_tools == ["read_file"]
    assert result.blocked_tools == ["skill"]
    assert "model_content" not in result.audit_metadata


def test_skill_tool_rejects_disabled_model_invocation():
    registry = ToolRegistry()
    service = SkillInvocationService(
        SkillCatalog([_skill("manual-only", disable_model_invocation=True)], builtin_commands=set())
    )
    registry.register(create_skill_tool(service))

    result = registry.execute("skill", {"skill": "manual-only"})

    assert result.content.startswith("Error:")
    assert result.audit_metadata == {}
    assert result.blocked_tools == []
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_skill_tool.py -q
```

Expected: FAIL，提示没有 `skill_tool` 或 `ToolRegistry.execute()` 返回 str 没有 `.content`。

- [ ] **Step 3: 支持 structured tool result**

修改 `src/xcode_cli/core/tool_registry.py`：

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolOutput:
    content: str
    metadata: dict[str, object] = field(default_factory=dict)
    audit_metadata: dict[str, object] = field(default_factory=dict)
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] = field(default_factory=list)
```

字段语义：

- `content`：模型可见 tool result。SkillTool 成功时这里保存 loaded skill marker + 完整 prompt。
- `metadata`：执行层内部 metadata，不用于额外 session audit event。
- `audit_metadata`：可写入 `skill_invocation` event，不得包含完整 `model_content`。
- `allowed_tools`：后续 LLM loop 的工具白名单。
- `blocked_tools`：后续 LLM loop 必须排除的工具。SkillTool 成功时必须包含 `skill`，防止递归。

调整 `ToolDef.execute` 类型允许返回 `str | ToolOutput`。`ToolRegistry.execute()` 中：

```python
result = tool.execute(**args)
if isinstance(result, ToolOutput):
    return result
return ToolOutput(content=str(result))
```

未知工具和异常也返回 `ToolOutput(content="Error: ...")`。

- [ ] **Step 4: 实现 SkillTool**

创建 `src/xcode_cli/core/tools/skill_tool.py`：

```python
from __future__ import annotations

from xcode_cli.core.tool_registry import ToolDef, ToolOutput
from xcode_cli.skills.invocation import SkillInvocation, SkillInvocationService


def create_skill_tool(service: SkillInvocationService) -> ToolDef:
    def execute(skill: str, args: str | None = None) -> ToolOutput:
        result = service.invoke_for_model(skill, args)
        if isinstance(result, str):
            return ToolOutput(content=result)
        return ToolOutput(
            content=_loaded_skill_content(result),
            audit_metadata=result.audit_metadata,
            allowed_tools=result.allowed_tools,
            blocked_tools=["skill"],
        )

    return ToolDef(
        name="skill",
        description=(
            "Load a project skill when it clearly matches the user's current task. "
            "Use only skill names from the Available skills listing."
        ),
        parameters={
            "skill": {
                "type": "string",
                "description": "The skill name from the Available skills listing. A leading slash is allowed.",
            },
            "args": {
                "type": "string",
                "description": "Optional arguments to pass as $ARGUMENTS.",
            },
        },
        required=["skill"],
        execute=execute,
        is_read_only=True,
    )


def _loaded_skill_content(invocation: SkillInvocation) -> str:
    name = str(invocation.audit_metadata.get("skill", ""))
    return (
        f"<xcode_loaded_skill name=\"{name}\" source=\"model\">\n"
        f"{invocation.model_content}\n"
        "</xcode_loaded_skill>"
    )
```

- [ ] **Step 5: 更新 ToolCallExecutor**

修改 `src/xcode_cli/core/tooling/execution.py`：

- `executed_calls` 保存 `ToolOutput`。
- tool message content 使用 `output.content`。
- `ToolExecutionResult` 增加：

```python
activated_allowed_tools: list[str] | None = None
blocked_tools: list[str] = field(default_factory=list)
skill_invocations: list[dict[str, object]] = field(default_factory=list)
```

- 当 tool output `audit_metadata["kind"] == "skill_invocation"` 时，把 `audit_metadata` 放入 `skill_invocations`。
- 当 tool output `allowed_tools is not None` 时，把它写入 `activated_allowed_tools`。
- 合并所有 tool output `blocked_tools`。
- `_summarize_tool_result()` 对 `tool_name == "skill"` 返回 `loaded skill <name>`，不能打印完整 prompt。

- [ ] **Step 6: 运行测试确认通过**

Run:

```powershell
pytest tests/test_skill_tool.py tests/test_skill_allowed_tools.py tests/test_agent_tool_loop.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add src/xcode_cli/core/tools/skill_tool.py src/xcode_cli/core/tool_registry.py src/xcode_cli/core/tooling/execution.py tests/test_skill_tool.py tests/test_skill_allowed_tools.py tests/test_agent_tool_loop.py
git commit -m "feat: add model-invocable skill tool"
```
