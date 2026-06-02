"""Textual widgets for ChatApp."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, RichLog


class TranscriptArea(Widget):
    """Transcript area for displaying message history."""

    DEFAULT_CSS = """
    TranscriptArea {
        height: 1fr;
        overflow-y: auto;
        background: transparent;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLogHistory(id="history")


class RichLogHistory(RichLog):
    """RichLog used for finalized message history."""

    DEFAULT_CSS = """
    RichLogHistory {
        height: 1fr;
        background: transparent;
    }
    """

    def on_mount(self) -> None:
        self.wrap = True
        self.markup = False


class StreamingWidget(Widget):
    """Current streaming assistant output."""

    DEFAULT_CSS = """
    StreamingWidget {
        height: auto;
        max-height: 50%;
        background: transparent;
        padding: 0 1;
    }
    """

    text = reactive("")

    def render(self) -> str:
        return self.text

    def update_text(self, text: str) -> None:
        self.text = text

    def clear_text(self) -> None:
        self.text = ""


class NewMessagesPill(Widget):
    """Small notice shown when new messages arrive above the viewport."""

    DEFAULT_CSS = """
    NewMessagesPill {
        display: none;
        width: 100%;
        height: 1;
        background: transparent;
        color: $accent;
        content-align: center middle;
        text-style: bold underline;
        margin: 0;
    }
    """

    message_count = reactive(0)

    def render(self) -> str:
        if self.message_count > 0:
            suffix = "s" if self.message_count > 1 else ""
            return f"{self.message_count} new message{suffix}"
        return ""

    def show_pill(self, count: int) -> None:
        self.message_count = count
        self.display = True

    def hide_pill(self) -> None:
        self.message_count = 0
        self.display = False


class ApprovalAwareInput(Input):
    """Input that lets the app intercept approval/resume shortcuts first."""

    def on_key(self, event) -> None:
        app = self.app
        # Check resume selection first
        if getattr(app, "_is_resume_selecting", False):
            handler = getattr(app, "_handle_resume_key", None)
            if handler and handler(event.key.lower()):
                event.stop()
                return
        handler = getattr(app, "handle_permission_key", None)
        if handler and handler(event.key.lower()):
            self.value = ""
            event.stop()


class InputBox(Widget):
    """Input box for user prompts."""

    DEFAULT_CSS = """
    InputBox {
        height: auto;
        min-height: 3;
        max-height: 6;
        background: transparent;
        padding: 0 1;
        margin: 1 0 0 0;
        border-top: solid $surface-lighten-2;
        border-bottom: solid $surface-lighten-2;
        transition: border 200ms;
    }

    InputBox:focus-within {
        border-top: solid cyan;
        border-bottom: solid cyan;
        background: $boost;
    }

    ApprovalAwareInput {
        background: transparent;
        border: none;
        height: 1;
        min-height: 1;
        padding: 0;
        color: $text;
    }

    ApprovalAwareInput:focus {
        border: none;
    }

    ApprovalAwareInput > .input--placeholder {
        color: dimgrey;
        text-style: italic;
    }

    ApprovalAwareInput > .input--cursor {
        background: cyan;
        color: black;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield ApprovalAwareInput(placeholder="", id="input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            self.post_message(UserInputSubmitted(event.value))
            event.input.value = ""
        event.stop()


class UserInputSubmitted(Message):
    """Message posted when the user submits input."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class CommandSuggestions(Widget):
    """Slash command suggestions."""

    DEFAULT_CSS = """
    CommandSuggestions {
        display: none;
        height: auto;
        max-height: 10;
        background: $surface;
        border: round $primary;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield ListView(id="suggestions")

    def show_suggestions(self, suggestions: list[str]) -> None:
        list_view = self.query_one("#suggestions", ListView)
        list_view.clear()
        for suggestion in suggestions:
            list_view.append(ListItem(Label(suggestion)))
        self.display = True

    def hide_suggestions(self) -> None:
        self.display = False


class StatusBar(Widget):
    """One-line runtime status."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: transparent;
        color: $text-muted;
        padding: 0 1;
        text-style: dim;
    }
    """

    status_text = reactive("")

    def render(self) -> str:
        return self.status_text

    def update_status(self, text: str) -> None:
        self.status_text = text


class PetSurface(Widget):
    """Reserved pet slot, hidden by default."""

    DEFAULT_CSS = """
    PetSurface {
        display: none;
        height: 0;
        width: 0;
    }
    """


class PermissionPrompt(Widget):
    """Legacy permission prompt widget kept for compatibility tests."""

    DEFAULT_CSS = """
    PermissionPrompt {
        display: none;
        height: auto;
        min-height: 5;
        background: $panel;
        border: round $warning;
        padding: 1 2;
        margin: 1 2;
    }
    """

    request_id = reactive("")
    tool_call_id = reactive("")
    tool_name = reactive("")
    scope = reactive("")
    risk_summary = reactive("")

    class Decision(Message):
        def __init__(self, request_id: str, tool_call_id: str, choice: str) -> None:
            super().__init__()
            self.request_id = request_id
            self.tool_call_id = tool_call_id
            self.choice = choice

    def show_prompt(
        self,
        request_id: str,
        tool_call_id: str,
        tool_name: str,
        scope: str,
        risk_summary: str,
    ) -> None:
        self.request_id = request_id
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.scope = scope
        self.risk_summary = risk_summary
        self.display = True

    def hide_prompt(self) -> None:
        self.display = False
        self.request_id = ""
        self.tool_call_id = ""
        self.tool_name = ""
        self.scope = ""
        self.risk_summary = ""

    def render(self) -> str:
        if not self.display:
            return ""
        lines = [
            f"Tool: {self.tool_name}",
            f"Scope: {self.scope}",
            f"Risk: {self.risk_summary}",
            "[Y]es / [N]o / [A]ll for this scope",
        ]
        return "\n".join(lines)


class ApprovalCard(Widget):
    """Compact approval card with preview and selectable rows."""

    DEFAULT_CSS = """
    ApprovalCard {
        display: none;
        height: auto;
        max-height: 11;
        background: $surface;
        border: round $warning;
        padding: 0 1;
        margin: 0 0 1 0;
        overflow-y: auto;
    }
    """

    _choices = (
        ("yes", "Yes"),
        ("no", "No"),
        ("yes_all", "Yes, this conversation"),
    )

    request_id = reactive("")
    tool_call_id = reactive("")
    tool_name = reactive("")
    scope = reactive("")
    risk_summary = reactive("")
    preview_kind = reactive("")
    preview_title = reactive("")
    preview_content = reactive("")
    selected_index = reactive(0)

    class Decision(Message):
        def __init__(self, request_id: str, tool_call_id: str, choice: str) -> None:
            super().__init__()
            self.request_id = request_id
            self.tool_call_id = tool_call_id
            self.choice = choice

    def show_request(
        self,
        request_id: str,
        tool_call_id: str,
        tool_name: str,
        scope: str,
        risk_summary: str,
    ) -> None:
        self.request_id = request_id
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.scope = scope
        self.risk_summary = risk_summary
        self.selected_index = 0
        self.display = True

    def show_diff(self, file_path: str, diff_content: str) -> None:
        self.preview_kind = "diff"
        self.preview_title = file_path
        self.preview_content = diff_content
        self.display = True

    def show_command(self, command: str) -> None:
        self.preview_kind = "command"
        self.preview_title = "Command"
        self.preview_content = command
        self.display = True

    def hide_card(self) -> None:
        self.display = False
        self.request_id = ""
        self.tool_call_id = ""
        self.tool_name = ""
        self.scope = ""
        self.risk_summary = ""
        self.preview_kind = ""
        self.preview_title = ""
        self.preview_content = ""
        self.selected_index = 0

    @property
    def selected_choice(self) -> str:
        return self._choices[self.selected_index][0]

    def move_selection(self, delta: int) -> None:
        self.selected_index = (self.selected_index + delta) % len(self._choices)

    def submit_selected(self) -> None:
        self.post_message(
            self.Decision(self.request_id, self.tool_call_id, self.selected_choice)
        )

    def select_choice(self, choice: str) -> bool:
        for idx, (value, _) in enumerate(self._choices):
            if value == choice:
                self.selected_index = idx
                return True
        return False

    def _compact_diff_lines(self, max_lines: int = 4) -> tuple[list[str], bool]:
        """Return high-signal diff lines while preserving option rows."""
        raw_lines = self.preview_content.splitlines()
        content_lines = [
            line for line in raw_lines
            if not line.startswith("---") and not line.startswith("+++")
        ]
        return content_lines[:max_lines], len(content_lines) > max_lines

    def render(self) -> Text:
        text = Text()
        if not self.display:
            return text

        title = f"Approve {self.tool_name}"
        if self.scope:
            title += f" ({self.scope})"
        text.append(title, style="bold yellow")
        if self.risk_summary:
            text.append(f" - {self.risk_summary}", style="dim")

        if self.preview_content:
            text.append(f"\n{self.preview_title}", style="bold")
            if self.preview_kind == "command":
                text.append(f"\n$ {self.preview_content}", style="yellow")
            else:
                visible_lines, truncated = self._compact_diff_lines()
                for line in visible_lines:
                    if line.startswith("+") and not line.startswith("+++"):
                        style = "green"
                    elif line.startswith("-") and not line.startswith("---"):
                        style = "red"
                    elif line.startswith("@@"):
                        style = "cyan"
                    else:
                        style = "dim"
                    text.append(f"\n{line}", style=style)
                if truncated:
                    text.append("  ...", style="dim")

        for idx, (_, label) in enumerate(self._choices):
            selected = idx == self.selected_index
            prefix = ">" if selected else " "
            style = "bold cyan reverse" if selected else "dim"
            text.append(f"\n{prefix} {label}", style=style)
        return text


class DiffPreview(Widget):
    """Reserved legacy diff preview surface."""


class CommandPreview(Widget):
    """Reserved legacy command preview surface."""


class ResumeSelector(Widget):
    """Transient resume session selector with keyboard navigation."""

    VISIBLE_SESSION_LIMIT = 10

    DEFAULT_CSS = """
    ResumeSelector {
        display: none;
        height: 13;
        max-height: 13;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
    }
    """

    sessions: reactive[list[dict[str, object]]] = reactive(list)
    selected_index: reactive[int] = reactive(0)

    class SessionSelected(Message):
        """Posted when user confirms a session selection."""
        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class SelectionCancelled(Message):
        """Posted when user cancels resume selection."""
        pass

    def show_sessions(self, sessions: list[dict[str, object]]) -> None:
        """Display sessions for selection."""
        self.sessions = sessions
        self.selected_index = 0
        self.display = True

    def hide_selector(self) -> None:
        """Hide and reset the selector."""
        self.display = False
        self.sessions = []
        self.selected_index = 0

    def move_selection(self, delta: int) -> None:
        """Move the selection up or down."""
        if self.sessions:
            self.selected_index = (self.selected_index + delta) % len(self.sessions)

    def _visible_window_start(self) -> int:
        """Return the first visible session index."""
        count = len(self.sessions)
        if count <= self.VISIBLE_SESSION_LIMIT:
            return 0

        max_start = count - self.VISIBLE_SESSION_LIMIT
        start = self.selected_index - self.VISIBLE_SESSION_LIMIT + 1
        return max(0, min(start, max_start))

    def confirm_selection(self) -> None:
        """Post the selected session ID."""
        if 0 <= self.selected_index < len(self.sessions):
            session_id = str(self.sessions[self.selected_index].get("session_id", ""))
            if session_id:
                self.post_message(self.SessionSelected(session_id))
                self.hide_selector()

    def cancel(self) -> None:
        """Cancel selection."""
        self.hide_selector()
        self.post_message(self.SelectionCancelled())

    def render(self) -> Text:
        text = Text()
        if not self.display or not self.sessions:
            return text

        text.append("Resumable sessions:\n", style="bold")
        start = self._visible_window_start()
        visible_sessions = self.sessions[start:start + self.VISIBLE_SESSION_LIMIT]
        for offset, session in enumerate(visible_sessions):
            idx = start + offset
            session_id = str(session.get("session_id", ""))
            preview = str(session.get("last_user_input", "") or "(empty)").replace("\n", " ")
            message_count = session.get("message_count", 0)
            checkpoint = " [checkpoint]" if session.get("has_checkpoint") else ""

            prefix = ">" if idx == self.selected_index else " "
            style = "bold cyan" if idx == self.selected_index else "dim"
            line = f"{prefix} {session_id[:8]}... ({message_count} msgs{checkpoint}) {preview[:60]}\n"
            text.append(line, style=style)

        if len(self.sessions) > self.VISIBLE_SESSION_LIMIT:
            end = start + len(visible_sessions)
            text.append(f"{start + 1}-{end} of {len(self.sessions)}\n", style="dim")
        text.append("[up/down select, Enter confirm, Esc cancel]", style="dim")
        return text


class ActiveToolIndicator(Widget):
    """Shows currently running tool."""

    DEFAULT_CSS = """
    ActiveToolIndicator {
        display: none;
        height: 1;
        background: transparent;
        padding: 0 2;
        color: $accent;
    }
    """

    tool_name = reactive("")
    tool_call_id = reactive("")

    def show_tool(self, tool_call_id: str, tool_name: str) -> None:
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.display = True

    def show_task(self, subject: str) -> None:
        self.tool_call_id = ""
        self.tool_name = f"task: {subject}"
        self.display = True

    def hide_tool(self) -> None:
        self.tool_call_id = ""
        self.tool_name = ""
        self.display = False

    def render(self) -> str:
        if not self.display:
            return ""
        return f"Running {self.tool_name}..."
