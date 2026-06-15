from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from rich.live import Live
from rich.text import Text


@dataclass
class CompactOutcome:
    messages: list[dict[str, Any]]
    summary: str
    boundary_message: dict[str, Any]
    checkpoint_message: dict[str, Any]
    restored_context_message: dict[str, Any]
    before_messages: int
    after_messages: int
    before_tokens: int
    after_tokens: int
    protected_tail_messages: int = 0
    micro_compacted_tool_results: int = 0
    restored_context_sections: list[str] | None = None


class ConversationCompactor:
    def __init__(self, context, llm, sessions, console) -> None:
        self.context = context
        self.llm = llm
        self.sessions = sessions
        self.console = console
        self.last_failure_reason = ""
        self._lineage_by_session: dict[str, tuple[str, int, str]] = {}

    @staticmethod
    def find_previous_summary(history: list[dict[str, Any]]) -> str:
        for msg in reversed(history):
            if msg.get("role") == "system":
                content = str(msg.get("content", ""))
                if "Conversation summary checkpoint:" in content:
                    return content.split("Conversation summary checkpoint:\n", 1)[-1].strip()
        return ""

    def compact_history(
        self,
        history: list[dict[str, Any]],
        *,
        trigger: str = "auto",
        work_state=None,
    ) -> CompactOutcome | None:
        self.last_failure_reason = ""
        before_messages = len(history)
        before_tokens = self.context.estimate_tokens(history)
        previous_summary = self.find_previous_summary(history)
        restored_context = ""
        restored_context_sections: list[str] = []
        if work_state is not None:
            try:
                restored_context = work_state.render_restored_context()
                restored_context_sections = list(work_state.restored_context_sections())
            except Exception:
                restored_context = ""
                restored_context_sections = []

        # 启动 Live 进度
        start_time = time.monotonic()
        stop_event = threading.Event()

        def _update_progress():
            while not stop_event.is_set():
                elapsed = time.monotonic() - start_time
                live.update(Text(f"Compacting context... ({elapsed:.1f}s)", style="dim"))
                time.sleep(0.1)

        live = Live(
            Text("Compacting context... (0.0s)", style="dim"),
            console=self.console,
            refresh_per_second=8,
            transient=True,
        )
        live.start()
        progress_thread = threading.Thread(target=_update_progress, daemon=True)
        progress_thread.start()

        try:
            try:
                result = self.context.compress(
                    history,
                    self.llm,
                    previous_summary,
                    trigger=trigger,
                    restored_context=restored_context,
                    restored_context_sections=restored_context_sections,
                )
            except TypeError:
                result = self.context.compress(history, self.llm, previous_summary)
            except Exception as exc:
                self.last_failure_reason = f"summary request failed: {exc}"
                return None
        finally:
            # 停止 Live 进度
            stop_event.set()
            progress_thread.join(timeout=0.2)
            live.stop()

        if not result.checkpoint_message:
            reason = getattr(result, "failure_reason", "") or getattr(result, "status", "") or "no checkpoint"
            if reason == "success":
                reason = "no checkpoint"
            self.last_failure_reason = str(reason).replace("_", " ")
            return None

        after_messages = len(result.messages)
        after_tokens = self.context.estimate_tokens(result.messages)

        return CompactOutcome(
            messages=result.messages,
            summary=result.summary,
            boundary_message=result.boundary_message,
            checkpoint_message=result.checkpoint_message,
            restored_context_message=getattr(result, "restored_context_message", {}),
            before_messages=before_messages,
            after_messages=after_messages,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            protected_tail_messages=result.protected_tail_messages,
            micro_compacted_tool_results=result.micro_compacted_tool_results,
            restored_context_sections=list(getattr(result, "restored_context_sections", []) or []),
        )

    def write_checkpoint(self, session_id: str, outcome: CompactOutcome) -> None:
        parent_id, parent_index, parent_summary_hash = self._latest_lineage_for_session(session_id)
        checkpoint_index = parent_index + 1
        checkpoint_id = f"ckpt_{int(time.time() * 1000)}_{checkpoint_index}"
        summary_hash = _hash_text(outcome.summary)
        restored_context_content = str((outcome.restored_context_message or {}).get("content", ""))
        if outcome.boundary_message:
            self.sessions.append_message(session_id, outcome.boundary_message)
        self.sessions.append_message(session_id, outcome.checkpoint_message)
        self.sessions.append_event(session_id, {
            "type": "compaction_checkpoint",
            "summary": outcome.summary,
            "summary_format": "xcode.v3",
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_id,
            "checkpoint_index": checkpoint_index,
            "summary_hash": summary_hash,
            "previous_summary_hash": parent_summary_hash,
            "restored_context_hash": _hash_text(restored_context_content) if restored_context_content else "",
            "restored_context_sections": list(outcome.restored_context_sections or []),
            "source_message_count": outcome.before_messages,
            "source_token_estimate": outcome.before_tokens,
            "remaining_message_count": outcome.after_messages,
            "protected_tail_messages": outcome.protected_tail_messages,
            "micro_compacted_tool_results": outcome.micro_compacted_tool_results,
            "rejected_summary": False,
        })
        if outcome.restored_context_message:
            self.sessions.append_message(session_id, outcome.restored_context_message)
        self._lineage_by_session[session_id] = (checkpoint_id, checkpoint_index, summary_hash)

    def _latest_lineage_for_session(self, session_id: str) -> tuple[str | None, int, str]:
        memory = self._lineage_by_session.get(session_id, (None, 0, ""))
        persisted = self._persisted_lineage_for_session(session_id)
        if persisted[1] > memory[1]:
            return persisted
        return memory

    def _persisted_lineage_for_session(self, session_id: str) -> tuple[str | None, int, str]:
        latest_checkpoint = _latest_compaction_checkpoint(self.sessions, session_id)
        if not latest_checkpoint or latest_checkpoint.get("summary_format") != "xcode.v3":
            return (None, 0, "")
        checkpoint_id = str(latest_checkpoint.get("checkpoint_id") or "")
        checkpoint_index = _coerce_int(latest_checkpoint.get("checkpoint_index"), 0)
        summary_hash = str(latest_checkpoint.get("summary_hash") or "")
        if not checkpoint_id or checkpoint_index <= 0:
            return (None, 0, "")
        return (checkpoint_id, checkpoint_index, summary_hash)


def _hash_text(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _latest_compaction_checkpoint(sessions, session_id: str) -> dict[str, Any] | None:
    getter = getattr(sessions, "latest_compaction_checkpoint", None)
    if not callable(getter):
        return None
    try:
        event = getter(session_id)
    except Exception:
        return None
    return event if isinstance(event, dict) else None


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
