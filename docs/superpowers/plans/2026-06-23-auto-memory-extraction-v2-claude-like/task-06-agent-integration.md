# Task 06: Agent Integration

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P0/P1

## Goal

Wire v2 extraction runner into `AgentRuntime` so after-turn hook submission is non-blocking, local REPL only, and shutdown happens from `run_chat()` without leaking background work.

## Suggested Files

- Modify: `src/xcode_cli/core/agent.py`
- Modify: `src/xcode_cli/core/memory_extraction.py`
- Test: `tests/test_agent_memory_extraction_v2.py`
- Test: `tests/test_agent_memory_hooks.py`
- Test: `tests/test_agent_user_turn.py`
- Test: `tests/test_external_turn.py`

## Constraints

- QQchat/external/headless turns must not trigger automatic long-term memory extraction.
- LLM failure, missing API key, missing package, and `No response.` still do not trigger after-turn extraction.
- Hook exceptions and runner submit failures must not affect assistant reply or `_history`.
- Existing recall prefetch executor shutdown remains intact.
- Main loop must not wait for extraction subagent.

## Steps

- [x] **Step 1: Add integration tests**

Create `tests/test_agent_memory_extraction_v2.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import MagicMock

from xcode_cli.core.agent import AgentRuntime
from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult


def _make_agent(tmp_path: Path, monkeypatch) -> AgentRuntime:
    import xcode_cli.paths
    import xcode_cli.core.agent as agent_mod

    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    xcode_dir = tmp_path / ".xcode"
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(json.dumps({"auto_memory": True, "model": "test"}), encoding="utf-8")
    for subdir in ("sessions", "skills", "bin"):
        (xcode_dir / subdir).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)
    agent = AgentRuntime()
    agent._session_id = "session-1"
    return agent


def _event(text: str) -> AfterTurnSuccessEvent:
    return AfterTurnSuccessEvent(
        session_id="session-1",
        cwd="D:/Xcode",
        user_display_content=text,
        user_model_content=text,
        assistant_text="Done.",
        recent_history=[{"role": "user", "content": text}, {"role": "assistant", "content": "Done."}],
        wrote_memory_this_turn=False,
    )


class RecordingRunner:
    def __init__(self) -> None:
        self.submissions = []
        self.shutdown_calls = []

    def submit(self, event, *, auto_memory_enabled: bool) -> None:
        self.submissions.append((event, auto_memory_enabled))

    def latest_result(self):
        return MemoryExtractionResult(action="skipped", reason="test")

    def shutdown(self, wait: bool = False) -> None:
        self.shutdown_calls.append(wait)


class SlowSubmitRunner(RecordingRunner):
    def submit(self, event, *, auto_memory_enabled: bool) -> None:
        time.sleep(0.05)
        super().submit(event, auto_memory_enabled=auto_memory_enabled)


def test_agent_after_turn_submits_to_memory_runner(tmp_path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    runner = RecordingRunner()
    agent.memory_extraction_runner = runner

    agent._run_memory_extraction_hook(_event("remember review preference"))

    assert len(runner.submissions) == 1
    assert runner.submissions[0][1] is True


def test_agent_memory_hook_submit_exception_is_swallowed(tmp_path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)

    class BrokenRunner:
        def submit(self, event, *, auto_memory_enabled: bool) -> None:
            raise RuntimeError("boom")

    agent.memory_extraction_runner = BrokenRunner()

    agent._run_memory_extraction_hook(_event("remember this"))


def test_run_chat_shutdowns_memory_runner(tmp_path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    runner = RecordingRunner()
    agent.memory_extraction_runner = runner
    monkeypatch.setattr(agent.prompt, "prompt", lambda *args, **kwargs: "/exit")

    agent.run_chat()

    assert runner.shutdown_calls == [False]
```

The helper above mirrors the existing `_make_agent()` pattern in `tests/test_agent_memory_hooks.py`, so this test file can run independently.

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_agent_memory_extraction_v2.py -q
```

Expected:

- Tests fail because `AgentRuntime` still owns synchronous `MemoryExtractionService`.

- [x] **Step 3: Initialize v2 subagent and runner**

In `src/xcode_cli/core/agent.py`, replace:

```python
self.memory_extraction = MemoryExtractionService(...)
self.after_turn_hooks.register(self._run_memory_extraction_hook)
```

with:

```python
from xcode_cli.core.memory_extraction_runner import MemoryExtractionRunner
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionSubagent

self.memory_extraction_subagent = MemoryExtractionSubagent(
    memory=self.memory,
    permissions=self.permissions,
    llm=self.llm,
)
self.memory_extraction_runner = MemoryExtractionRunner(subagent=self.memory_extraction_subagent)
self.after_turn_hooks.register(self._run_memory_extraction_hook)
```

- [x] **Step 4: Make hook submit non-blocking**

Change `_run_memory_extraction_hook()` to:

```python
def _run_memory_extraction_hook(self, event: AfterTurnSuccessEvent) -> None:
    try:
        cfg = self.config_store.load()
        self.memory_extraction_runner.submit(event, auto_memory_enabled=cfg.auto_memory)
    except Exception:
        pass
```

The runner itself records detailed failures; this hook protects the main loop.

- [x] **Step 5: Shutdown runner in `run_chat()`**

In `run_chat()` `finally`, add before runtime status delete:

```python
try:
    self.memory_extraction_runner.shutdown(wait=False)
except Exception:
    pass
```

Keep existing memory recall prefetch executor shutdown.

- [x] **Step 6: Preserve v1 skip boundaries**

Run and update tests so these remain true:

- Main model wrote memory this turn -> subagent returns `"memory already written"`.
- `auto_memory=false` -> runner still accepts event but subagent skips.
- User says "do not remember this" / "ignore memory" -> subagent skips before LLM.
- External/QQchat turn never calls local after-turn hook.

- [x] **Step 7: Run focused tests**

Run:

```text
pytest tests/test_agent_memory_extraction_v2.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py tests/test_external_turn.py -q
```

Expected:

- Agent hook tests pass.
- Local REPL success submits to runner.
- Error and `No response.` paths do not submit.
- External turn tests still show no auto memory extraction.

- [x] **Step 8: Stop for review**

Review before continuing:

- Main assistant response is appended before hook submission.
- Hook does not wait for runner completion.
- Shutdown handles repeated calls.

If committing is requested:

```text
git add src/xcode_cli/core/agent.py src/xcode_cli/core/memory_extraction.py tests/test_agent_memory_extraction_v2.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py tests/test_external_turn.py
git commit -m "feat: wire background memory extraction"
```
