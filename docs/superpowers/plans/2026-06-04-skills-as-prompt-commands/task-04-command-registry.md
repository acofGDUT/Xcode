# Task 4: 建立动态 CommandRegistry

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Create: `src/xcode_cli/core/commands/registry.py`
- Modify: `src/xcode_cli/core/commands/slash.py`
- Modify: `src/xcode_cli/core/commands/dispatcher.py`
- Test: `tests/test_skill_command_registry.py`
- Modify: `tests/test_slash_dispatcher.py`
- Modify: `tests/test_init_command.py`

- [ ] **Step 1: 写 registry 测试**

创建 `tests/test_skill_command_registry.py`：

```python
from pathlib import Path

from xcode_cli.core.commands.registry import CommandRegistry
from xcode_cli.skills.model import Skill


def test_registry_keeps_init_and_adds_user_invocable_skill():
    skill = Skill(
        name="review",
        display_name=None,
        description="Review code",
        body="Review $ARGUMENTS",
        root=Path("D:/Xcode/.xcode/skills/review"),
    )

    registry = CommandRegistry.from_skills([skill])

    assert registry.get("/init") is not None
    command = registry.get("/review")
    assert command is not None
    assert command.kind == "prompt"
    assert command.source == "skill"


def test_skill_cannot_override_builtin_command():
    skill = Skill(
        name="init",
        display_name=None,
        description="Malicious init replacement",
        body="Do something else",
        root=Path("D:/Xcode/.xcode/skills/init"),
    )

    registry = CommandRegistry.from_skills([skill])

    command = registry.get("/init")
    assert command is not None
    assert command.source == "builtin"
    assert command.description != "Malicious init replacement"


def test_registry_excludes_non_user_invocable_skill():
    skill = Skill(
        name="internal",
        display_name=None,
        description="Internal",
        body="Hidden",
        root=Path("D:/Xcode/.xcode/skills/internal"),
        user_invocable=False,
    )

    registry = CommandRegistry.from_skills([skill])

    assert registry.get("/internal") is None
    assert "/internal" not in registry.visible_commands()
```

- [ ] **Step 2: 修改 SlashCommand**

在 `src/xcode_cli/core/commands/slash.py` 中扩展 dataclass：

```python
@dataclass(frozen=True)
class SlashCommand:
    name: str
    kind: str
    description: str
    handler: Callable[[str], str]
    source: str = "builtin"
    argument_hint: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
```

- [ ] **Step 3: 创建 registry**

`CommandRegistry` 需要：

```python
class CommandRegistry:
    @classmethod
    def from_skills(cls, skills: list[Skill]) -> "CommandRegistry":
        registry = cls()
        registry.register_many(BUILTIN_PROMPT_COMMANDS.values())
        for skill in skills:
            if not skill.user_invocable:
                continue
            registry.register(create_skill_slash_command(skill))
        return registry

    def get(self, command_name: str) -> SlashCommand | None:
        return self._commands.get(command_name.lower())

    def visible_commands(self) -> dict[str, str]:
        return {name: cmd.description for name, cmd in sorted(self._commands.items())}
```

`from_skills()` 先注册 built-in `/init`，再注册 user-invocable skills。注册 skill command 时，如果名称已存在，保留 built-in command，不覆盖，并让 validation 层报告冲突 notice。

- [ ] **Step 4: 修改 dispatcher**

`SlashCommandDispatcher.__init__` 接收 `registry: CommandRegistry`，不再直接 import `PROMPT_COMMANDS`。

`dispatch()` 查找顺序：

```python
prompt_cmd = self._registry.get(head)
if prompt_cmd and prompt_cmd.kind == "prompt":
    args = " ".join(parts[1:]) if len(parts) > 1 else ""
    return SlashDispatchResult(kind="prompt", turn_input=prompt_cmd.handler(args))
```

- [ ] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_skill_command_registry.py tests/test_slash_dispatcher.py tests/test_init_command.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/xcode_cli/core/commands/registry.py src/xcode_cli/core/commands/slash.py src/xcode_cli/core/commands/dispatcher.py tests/test_skill_command_registry.py tests/test_slash_dispatcher.py tests/test_init_command.py
git commit -m "feat: register skills as prompt commands"
```
