from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion

COMMANDS = {
    "/help": "Show available commands",
    "/context": "Show token usage and context budget",
    "/tasks": "Show current task list",
    "/dashboard": "Open API configuration dashboard",
    "/skill": "Manage skills (list/install/enable/disable)",
    "/env": "Open interactive config dashboard",
    "/plan": "Plan mode controls (enter/show/approve/reject)",
    "/memory": "Memory status and auto-memory toggle",
    "/resume": "List and resume previous sessions",
    "/compact": "Compress current conversation context",
    "/exit": "Exit chat",
}


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        if text.startswith("/dashboard"):
            yield Completion(
                "/dashboard",
                start_position=-len(text),
                display="/dashboard — Open API configuration dashboard",
            )
            return

        if text.startswith("/skill"):
            for cmd, desc in [
                ("/skill list", "List installed skills"),
                ("/skill install ", "Install skill from local path"),
                ("/skill enable ", "Enable an installed skill"),
                ("/skill disable ", "Disable an installed skill"),
            ]:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")
            return

        if text.startswith("/env"):
            yield Completion(
                "/env",
                start_position=-len(text),
                display="/env — Open interactive config dashboard",
            )
            return

        if text.startswith("/resume"):
            yield Completion("/resume", start_position=-len(text), display="/resume — List and resume previous sessions")
            return

        if text.startswith("/compact"):
            yield Completion("/compact", start_position=-len(text), display="/compact — Compress current conversation context")
            return

        for cmd, desc in COMMANDS.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")
