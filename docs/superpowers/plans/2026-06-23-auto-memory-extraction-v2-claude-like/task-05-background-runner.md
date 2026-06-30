# Task 05: Background Runner

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P0/P1

## Goal

Add a non-blocking extraction runner that enforces single-flight execution, latest pending event, trailing run, timeout, shutdown, and audit state.

## Suggested Files

- Create: `src/xcode_cli/core/memory_extraction_runner.py`
- Test: `tests/test_memory_extraction_runner.py`

## Constraints

- `submit()` must return quickly and never wait for the LLM/subagent.
- At most one extraction runs at a time.
- Overlap stores only the latest pending event.
- When current run ends, one trailing run starts if a pending event exists.
- Shutdown must be idempotent and bounded.
- No global application `asyncio` migration.

## Steps

- [x] **Step 1: Add runner tests**

Create `tests/test_memory_extraction_runner.py`:

```python
from __future__ import annotations

import threading
import time

import pytest

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult
from xcode_cli.core.memory_extraction_runner import MemoryExtractionRunner


class BlockingSubagent:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.events = []

    def run(self, event, *, auto_memory_enabled: bool = True):
        self.events.append(event.user_model_content)
        self.started.set()
        self.release.wait(timeout=2)
        return MemoryExtractionResult(action="skipped", reason="done")


@pytest.fixture
def _event():
    def make_event(text: str) -> AfterTurnSuccessEvent:
        return AfterTurnSuccessEvent(
            session_id="session-1",
            cwd="D:/Xcode",
            user_display_content=text,
            user_model_content=text,
            assistant_text="Done.",
            recent_history=[{"role": "user", "content": text}, {"role": "assistant", "content": "Done."}],
            wrote_memory_this_turn=False,
        )

    return make_event


def test_runner_submit_is_non_blocking(_event) -> None:
    subagent = BlockingSubagent()
    runner = MemoryExtractionRunner(subagent=subagent, timeout_seconds=5)

    start = time.monotonic()
    runner.submit(_event("first"), auto_memory_enabled=True)
    elapsed = time.monotonic() - start

    assert elapsed < 0.2
    subagent.release.set()
    runner.shutdown(wait=True)


def test_runner_keeps_latest_pending_and_runs_trailing(_event) -> None:
    subagent = BlockingSubagent()
    runner = MemoryExtractionRunner(subagent=subagent, timeout_seconds=5)
    runner.submit(_event("first"), auto_memory_enabled=True)
    assert subagent.started.wait(timeout=1)

    runner.submit(_event("second"), auto_memory_enabled=True)
    runner.submit(_event("third"), auto_memory_enabled=True)
    subagent.release.set()
    runner.shutdown(wait=True)

    assert subagent.events == ["first", "third"]


def test_runner_shutdown_is_idempotent(_event) -> None:
    subagent = BlockingSubagent()
    runner = MemoryExtractionRunner(subagent=subagent, timeout_seconds=0.1)
    runner.submit(_event("first"), auto_memory_enabled=True)

    runner.shutdown(wait=False)
    runner.shutdown(wait=False)

    assert runner.latest_result().action in {"skipped", "failed", "running"}
```

The `_event` fixture above keeps these runner tests independent of other test modules.

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory_extraction_runner.py -q
```

Expected:

- Import fails because `memory_extraction_runner.py` does not exist.

- [x] **Step 3: Implement runner state**

Create `src/xcode_cli/core/memory_extraction_runner.py`:

```python
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
import threading

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult, MemoryExtractionSubagent


@dataclass(frozen=True)
class PendingExtraction:
    event: AfterTurnSuccessEvent
    auto_memory_enabled: bool


class MemoryExtractionRunner:
    def __init__(self, *, subagent: MemoryExtractionSubagent, timeout_seconds: float = 30.0) -> None:
        self.subagent = subagent
        self.timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._running: Future | None = None
        self._pending: PendingExtraction | None = None
        self._shutdown = False
        self._last_result = MemoryExtractionResult(action="skipped", reason="not run")

    def submit(self, event: AfterTurnSuccessEvent, *, auto_memory_enabled: bool) -> None:
        with self._lock:
            if self._shutdown:
                self._last_result = MemoryExtractionResult(action="skipped", reason="runner shut down")
                return
            pending = PendingExtraction(event=event, auto_memory_enabled=auto_memory_enabled)
            if self._running is not None and not self._running.done():
                self._pending = pending
                return
            self._start_locked(pending)

    def latest_result(self) -> MemoryExtractionResult:
        with self._lock:
            return self._last_result

    def shutdown(self, wait: bool = False) -> None:
        with self._lock:
            self._shutdown = True
            running = self._running
        if wait and running is not None:
            try:
                running.result(timeout=self.timeout_seconds)
            except Exception:
                pass
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _start_locked(self, pending: PendingExtraction) -> None:
        self._running = self._executor.submit(self._run_once, pending)
        self._running.add_done_callback(self._on_done)

    def _run_once(self, pending: PendingExtraction) -> MemoryExtractionResult:
        try:
            return self.subagent.run(pending.event, auto_memory_enabled=pending.auto_memory_enabled)
        except Exception as exc:
            return MemoryExtractionResult(action="failed", reason=str(exc))

    def _on_done(self, future: Future) -> None:
        try:
            result = future.result(timeout=0)
        except Exception as exc:
            result = MemoryExtractionResult(action="failed", reason=str(exc))
        with self._lock:
            self._last_result = result
            self._running = None
            if self._shutdown or self._pending is None:
                return
            pending = self._pending
            self._pending = None
            self._start_locked(pending)
```

- [x] **Step 4: Run focused tests**

Run:

```text
pytest tests/test_memory_extraction_runner.py -q
```

Expected:

- Runner tests pass.
- Submit path is non-blocking.
- Overlap keeps only latest pending event.

- [x] **Step 5: Stop for review**

Review before continuing:

- Callback does not call user-facing UI.
- Shutdown is safe if called before any submit.
- No unbounded queue can form.

If committing is requested:

```text
git add src/xcode_cli/core/memory_extraction_runner.py tests/test_memory_extraction_runner.py
git commit -m "feat: run memory extraction in background"
```
