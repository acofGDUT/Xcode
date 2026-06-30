from __future__ import annotations

from xcode_cli.core.hooks import AfterTurnSuccessEvent
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.memory_extraction_subagent import MemoryExtractionResult, MemoryExtractionSubagent
from xcode_cli.core.permissions import PermissionManager


class MemoryExtractionService:
    def __init__(self, *, memory: MemoryManager, permissions: PermissionManager, llm) -> None:
        self.subagent = MemoryExtractionSubagent(memory=memory, permissions=permissions, llm=llm)
        self.last_result = MemoryExtractionResult(action="skipped", reason="not run")

    def after_turn(self, event: AfterTurnSuccessEvent, *, auto_memory_enabled: bool = True) -> MemoryExtractionResult:
        try:
            result = self.subagent.run(event, auto_memory_enabled=auto_memory_enabled)
        except Exception as exc:
            result = MemoryExtractionResult(action="failed", reason=str(exc))
        self.last_result = result
        return result
