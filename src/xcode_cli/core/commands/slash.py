from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion

COMMANDS = {
    "/help": "Show available commands",
    "/context": "Show token usage and context budget",
    "/dashboard": "Open API configuration dashboard",
    "/skill": "Manage skills (list/install/enable/disable)",
    "/env": "Manage API env for current process",
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
            for cmd, desc in [
                ("/env show", "Show current API key status"),
                ("/env set ", "Set and persist API key"),
                ("/env unset", "Unset API key from process and config"),
                ("/env base-url ", "Set provider base URL"),
                ("/env model ", "Set model name"),
                ("/env theme ", "Set syntax highlight theme"),
                ("/env max-tokens ", "Set max token budget for context compression"),
                ("/env edit", "Open ~/.xcode/config.json in default editor"),
            ]:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")
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
