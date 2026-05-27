from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI

from xcode_cli.core.session_resume import SessionResumeBuilder


@dataclass
class ResumeResult:
    history: list[dict[str, Any]]
    session_id: str
    restored_from_checkpoint: bool
    message_count: int
    estimated_tokens: int
    last_user_input: str | None


class ResumeCommandService:
    def __init__(self, sessions, context, console, prompt: PromptSession) -> None:
        self.sessions = sessions
        self.context = context
        self.console = console
        self.prompt = prompt

    def run(self) -> ResumeResult | None:
        sessions = self.sessions.list_sessions()
        if not sessions:
            self.console.print("No recent sessions found for this project.")
            return None

        self.console.print("Recent sessions:")
        for i, s in enumerate(sessions, 1):
            ts = datetime.utcfromtimestamp(s.updated_at).strftime("%Y-%m-%d %H:%M")
            preview = s.last_user_input[:60] if s.last_user_input else "(empty)"
            cp_mark = " \\[checkpoint]" if s.has_checkpoint else ""
            self.console.print(f"  {i}. {s.session_id[:8]}...  {ts}  {preview}{cp_mark}")

        choice = self.prompt.prompt(
            ANSI("\x1b[96mSelect session number (empty to cancel)\x1b[0m ▸ ")
        ).strip()

        if not choice:
            self.console.print("Cancelled.")
            return None

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(sessions):
                self.console.print("Invalid selection.")
                return None
        except ValueError:
            self.console.print("Invalid selection.")
            return None

        selected = sessions[idx]
        resume_budget = int(self.context.max_tokens * 0.6)
        builder = SessionResumeBuilder(self.context, resume_budget)
        result = builder.build(selected.path)
        if not result.history:
            self.console.print("Failed to load session history.")
            return None

        self.console.print(f"Resumed session {selected.session_id}")
        self.console.print(f"Restored from checkpoint: {'yes' if result.restored_from_checkpoint else 'no'}")
        self.console.print(f"Restored messages: {result.message_count}")
        self.console.print(f"Estimated context: ~{result.estimated_tokens} tokens")
        if selected.last_user_input:
            self.console.print(f"Latest user input: {selected.last_user_input[:100]}")

        return ResumeResult(
            history=result.history,
            session_id=selected.session_id,
            restored_from_checkpoint=result.restored_from_checkpoint,
            message_count=result.message_count,
            estimated_tokens=result.estimated_tokens,
            last_user_input=selected.last_user_input,
        )
