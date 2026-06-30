# Task 04: Controlled After-turn Hook

**Risk layer:** P0/P1

## Goal

Introduce an internal-only `after_turn_success` hook for local REPL success paths, without executing user script hooks or skill hooks.

## Suggested Files

- Create: `src/xcode_cli/core/hooks.py`
- Modify: `src/xcode_cli/core/tooling/execution.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_agent_memory_hooks.py`
- Test: `tests/test_agent_user_turn.py`
- Test: `tests/test_external_turn.py`

## Constraints

- Hook fires only after local REPL assistant message is appended to session and `_history`.
- Hook does not fire on LLM failure, missing key, missing package, interruption, or external turn.
- Hook exceptions do not alter main reply, `_history`, or transcript.
- Do not execute skill frontmatter `hooks`.

## Steps

- [x] **Step 1: Write failing hook tests**

Create `tests/test_agent_memory_hooks.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.agent import AgentRuntime


def _make_agent(tmp_path: Path, monkeypatch) -> AgentRuntime:
    import xcode_cli.paths
    import xcode_cli.core.agent as agent_mod

    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(json.dumps({"model": "test", "auto_memory": True}), encoding="utf-8")
    for sub in ("sessions", "skills", "bin"):
        (xcode_dir / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)
    agent = AgentRuntime()
    agent._session_id = "session-1"
    return agent


def test_after_turn_hook_runs_after_successful_local_repl_turn(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    events = []
    agent.after_turn_hooks.register(lambda event: events.append(event))
    agent._run_llm_loop = MagicMock(return_value="assistant reply")

    agent._run_user_turn("remember my preference")

    assert len(events) == 1
    assert events[0].session_id == "session-1"
    assert events[0].user_display_content == "remember my preference"
    assert events[0].assistant_text == "assistant reply"
    assert agent._history[-1] == {"role": "assistant", "content": "assistant reply"}


def test_after_turn_hook_exception_does_not_break_reply(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent.after_turn_hooks.register(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    agent._run_llm_loop = MagicMock(return_value="assistant reply")

    agent._run_user_turn("hello")

    assert agent._history[-1] == {"role": "assistant", "content": "assistant reply"}


def test_after_turn_hook_does_not_run_on_llm_error(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    events = []
    agent.after_turn_hooks.register(lambda event: events.append(event))
    agent._run_llm_loop = MagicMock(return_value="[v0] LLM request failed: timeout")

    agent._run_user_turn("hello")

    assert events == []
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_agent_memory_hooks.py -q
```

Expected:

- Fails because `AgentRuntime.after_turn_hooks` and `hooks.py` do not exist.

- [x] **Step 3: Implement internal hook runner**

Create `src/xcode_cli/core/hooks.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class AfterTurnSuccessEvent:
    session_id: str
    cwd: str
    user_display_content: str
    user_model_content: str
    assistant_text: str
    recent_history: list[dict[str, Any]]
    wrote_memory_this_turn: bool = False


AfterTurnHook = Callable[[AfterTurnSuccessEvent], None]


class AfterTurnHookRunner:
    def __init__(self) -> None:
        self._hooks: list[AfterTurnHook] = []
        self.warnings: list[str] = []

    def register(self, hook: AfterTurnHook) -> None:
        self._hooks.append(hook)

    def run_after_turn_success(self, event: AfterTurnSuccessEvent) -> None:
        for hook in list(self._hooks):
            try:
                hook(event)
            except Exception as exc:
                self.warnings.append(str(exc))
```

- [x] **Step 4: Track memory write in tool execution**

Modify `ToolExecutionResult` in `src/xcode_cli/core/tooling/execution.py`:

```python
    wrote_memory: bool = False
```

Inside `ToolCallExecutor.execute()`, initialize:

```python
        wrote_memory = False
```

After a successful tool execution:

```python
            if is_memory_write and not output.content.startswith("Error:"):
                wrote_memory = True
```

Return it:

```python
            wrote_memory=wrote_memory,
```

In `AgentRuntime._run_llm_loop()`, add an instance field update when tool calls finish:

```python
            if tool_result.wrote_memory:
                self._turn_wrote_memory = True
```

- [x] **Step 5: Wire hook into AgentRuntime**

Modify imports in `src/xcode_cli/core/agent.py`:

```python
from xcode_cli.core.hooks import AfterTurnHookRunner, AfterTurnSuccessEvent
```

In `AgentRuntime.__init__`:

```python
        self.after_turn_hooks = AfterTurnHookRunner()
        self._turn_wrote_memory = False
```

At the start of `_run_user_turn()`:

```python
        self._turn_wrote_memory = False
```

After assistant message is appended to session and `_history`, add:

```python
        self.after_turn_hooks.run_after_turn_success(
            AfterTurnSuccessEvent(
                session_id=self._session_id,
                cwd=self.cwd,
                user_display_content=turn.display_content,
                user_model_content=turn.model_content,
                assistant_text=final_text,
                recent_history=list(self._history[-12:]),
                wrote_memory_this_turn=self._turn_wrote_memory,
            )
        )
```

- [x] **Step 6: Run focused hook tests**

Run:

```text
pytest tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py tests/test_external_turn.py -q
```

Expected:

- Hook tests pass.
- Existing user turn tests pass.
- External turn tests pass and do not observe hook execution.

- [x] **Step 7: Stop for review**

If committing is requested:

```text
git add src/xcode_cli/core/hooks.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/agent.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py tests/test_external_turn.py
git commit -m "feat: add internal after-turn hook"
```

