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
