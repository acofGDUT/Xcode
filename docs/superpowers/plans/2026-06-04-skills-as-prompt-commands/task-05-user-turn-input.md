# Task 5: 接入 UserTurnInput，防止 skill prompt 污染 UI

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Create: `src/xcode_cli/core/turn.py`
- Modify: `src/xcode_cli/core/commands/dispatcher.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_skill_prompt_command_flow.py`
- Modify: `tests/test_agent_user_turn.py`

- [ ] **Step 1: 写 flow 测试**

创建 `tests/test_skill_prompt_command_flow.py`：

```python
from pathlib import Path
from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from xcode_cli.core.commands.registry import CommandRegistry
from xcode_cli.core.commands.dispatcher import SlashCommandDispatcher
from xcode_cli.skills.model import Skill


def _console() -> Console:
    return Console(file=StringIO(), force_terminal=True, width=120)


def _handlers() -> dict:
    return {
        "help_handler": MagicMock(),
        "context_handler": MagicMock(),
        "dashboard_handler": MagicMock(),
        "skill_handler": MagicMock(),
        "env_handler": MagicMock(),
        "plan_handler": MagicMock(),
        "memory_handler": MagicMock(),
        "resume_handler": MagicMock(),
        "compact_handler": MagicMock(),
    }


def test_skill_dispatch_returns_user_turn_input_with_display_and_model_content():
    skill = Skill(
        name="review",
        display_name=None,
        description="Review code",
        body="Review this: $ARGUMENTS",
        root=Path("D:/Xcode/.xcode/skills/review"),
    )
    registry = CommandRegistry.from_skills([skill])
    dispatcher = SlashCommandDispatcher(
        console=_console(),
        registry=registry,
        **_handlers(),
    )

    result = dispatcher.dispatch("/review src/foo.py")

    assert result.kind == "prompt"
    assert result.turn_input.display_content == "/review src/foo.py"
    assert result.turn_input.model_content == "Review this: src/foo.py"
    assert result.turn_input.metadata["skill"] == "review"
```

- [ ] **Step 2: 实现 UserTurnInput**

创建 `src/xcode_cli/core/turn.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UserTurnInput:
    display_content: str
    model_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] | None = None


def coerce_user_turn_input(value: str | UserTurnInput) -> UserTurnInput:
    if isinstance(value, UserTurnInput):
        return value
    return UserTurnInput(display_content=value, model_content=value)
```

- [ ] **Step 3: 修改 dispatch result**

`SlashDispatchResult` 改为：

```python
@dataclass(frozen=True)
class SlashDispatchResult:
    kind: str
    turn_input: UserTurnInput | None = None
```

`/init` 也返回 `UserTurnInput(display_content="/init", model_content=INIT_PROMPT)`。

- [ ] **Step 4: 修改 `_run_user_turn()`**

签名：

```python
def _run_user_turn(self, user_input: str | UserTurnInput) -> None:
```

内部：

```python
turn = coerce_user_turn_input(user_input)
self.sessions.append_message(self._session_id, {
    "role": "user",
    "content": turn.display_content,
    "metadata": {
        **turn.metadata,
        "model_content": turn.model_content,
        "skill_source_hash": turn.metadata.get("skill_source_hash"),
    },
})
self.sessions.append_user_history(self._session_id, turn.display_content)
self._print_user_bubble(turn.display_content)
self._history.append({"role": "user", "content": turn.model_content})
```

- [ ] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_skill_prompt_command_flow.py tests/test_agent_user_turn.py tests/test_init_command.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/xcode_cli/core/turn.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/agent.py tests/test_skill_prompt_command_flow.py tests/test_agent_user_turn.py tests/test_init_command.py
git commit -m "feat: route skill prompts through user turn metadata"
```
