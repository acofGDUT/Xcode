from __future__ import annotations

import threading
import time

import pytest

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory_extraction_runner import MemoryExtractionRunner
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult


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


class ImmediateSubagent:
    def run(self, event, *, auto_memory_enabled: bool = True):
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


def test_runner_submit_does_not_deadlock_when_subagent_finishes_immediately(_event) -> None:
    runner = MemoryExtractionRunner(subagent=ImmediateSubagent(), timeout_seconds=1)

    start = time.monotonic()
    runner.submit(_event("first"), auto_memory_enabled=True)
    elapsed = time.monotonic() - start

    assert elapsed < 0.2
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
