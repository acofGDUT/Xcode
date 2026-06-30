from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
import threading
from typing import Any

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult


@dataclass(frozen=True)
class PendingExtraction:
    event: AfterTurnSuccessEvent
    auto_memory_enabled: bool


class MemoryExtractionRunner:
    def __init__(self, *, subagent: Any, timeout_seconds: float = 30.0) -> None:
        self.subagent = subagent
        self.timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.RLock()
        self._running: Future | None = None
        self._pending: PendingExtraction | None = None
        self._shutdown = False
        self._drain_pending = False
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
            if self._shutdown and (not wait or self._drain_pending):
                running = self._running
            else:
                self._shutdown = True
                self._drain_pending = wait
                if not wait:
                    self._pending = None
                running = self._running

        if wait:
            self._wait_until_idle(running)
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _start_locked(self, pending: PendingExtraction) -> None:
        self._last_result = MemoryExtractionResult(action="running")
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
            if self._pending is None:
                return
            if self._shutdown and not self._drain_pending:
                self._pending = None
                return
            pending = self._pending
            self._pending = None
            self._start_locked(pending)

    def _wait_until_idle(self, running: Future | None) -> None:
        while running is not None:
            try:
                running.result(timeout=self.timeout_seconds)
            except TimeoutError:
                with self._lock:
                    self._last_result = MemoryExtractionResult(action="failed", reason="timeout")
                return
            except Exception:
                pass
            with self._lock:
                running = self._running
