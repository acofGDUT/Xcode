# Textual Resume Legacy Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Textual `/resume` behave like a Claude-style transient text interaction while keeping restored-session feedback aligned with legacy `/resume` output.

**Architecture:** `/resume` selection is a transient Textual widget that visually looks like normal transcript text, but it must not write repeated selection updates into `RichLog`. Restored-session feedback is a normal system notice in the message flow and must carry the same information legacy `ResumeCommandService` prints after a successful restore.

**Tech Stack:** Python 3.10+, Textual, Rich `Text`, existing `RuntimeController`, `UIEvent`, `ChatApp`, `ResumeSelector`, pytest.

---

## Scope

Implement only the `/resume` changes below:

- The session selector should look like plain transcript text, not a bordered component, modal, card, or panel.
- The selector should update the `>` marker in place through `ResumeSelector`, not by repeatedly writing into `RichLog`.
- Confirming a selection should hide the selector and dispatch `ResumeSessionCommand`.
- Cancelling should hide the selector and show legacy-aligned `Cancelled.`.
- Successful restore feedback should align with legacy `/resume` output.
- Tests and docs must be updated.

Do not:

- Switch `xcode chat` default to Textual.
- Add CLI `--resume` or `--continue`.
- Add search, preview expansion, final full-screen resume UI, or pet UI.
- Change transcript persistence semantics.
- Put the transient selector into long-term message history.

## Files

- Modify: `src/xcode_cli/core/ui/events.py`
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Modify: `src/xcode_cli/core/ui/textual/app.py`
- Modify: `src/xcode_cli/core/ui/textual/widgets.py`
- Modify: `tests/test_ui_events_commands.py`
- Modify: `tests/test_runtime_controller.py`
- Modify: `tests/test_textual_chat_app.py`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`

---

## Task 1: Extend `ResumeCompleted` With Legacy Restore Metadata

**Files:**
- Modify: `src/xcode_cli/core/ui/events.py`
- Modify: `tests/test_ui_events_commands.py`

- [ ] **Step 1: Write the failing event test**

Add or update the resume event test in `tests/test_ui_events_commands.py` so `ResumeCompleted` carries all legacy restore fields:

```python
def test_resume_completed_event_carries_legacy_restore_metadata(self):
    completed = ResumeCompleted(
        session_id="s1",
        restored_from_checkpoint=True,
        message_count=10,
        estimated_tokens=1234,
        last_user_input="continue the UI migration",
    )

    assert completed.session_id == "s1"
    assert completed.restored_from_checkpoint is True
    assert completed.message_count == 10
    assert completed.estimated_tokens == 1234
    assert completed.last_user_input == "continue the UI migration"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
pytest tests/test_ui_events_commands.py -q
```

Expected before implementation: failure because `ResumeCompleted` does not accept the new fields.

- [ ] **Step 3: Update the event type**

Change `ResumeCompleted` in `src/xcode_cli/core/ui/events.py` to:

```python
@dataclass(frozen=True)
class ResumeCompleted(UIEvent):
    """Session resume completed."""
    session_id: str
    restored_from_checkpoint: bool
    message_count: int
    estimated_tokens: int
    last_user_input: str | None = None
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```powershell
pytest tests/test_ui_events_commands.py -q
```

Expected: pass.

---

## Task 2: Emit Legacy Restore Metadata From `RuntimeController`

**Files:**
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Modify: `tests/test_runtime_controller.py`

- [ ] **Step 1: Write the failing controller test**

Update the existing successful resume test in `tests/test_runtime_controller.py` or add a focused one:

```python
def test_dispatch_resume_session_emits_legacy_restore_metadata(tmp_path, monkeypatch):
    from xcode_cli.core.runtime.controller import RuntimeController
    from xcode_cli.core.ui.commands import ResumeSessionCommand
    from xcode_cli.core.ui.events import ResumeCompleted

    class SessionInfo:
        session_id = "session_123"
        path = tmp_path / "session_123.jsonl"
        updated_at = 0
        message_count = 2
        estimated_tokens = 0
        last_user_input = "last prompt"
        has_checkpoint = True

    class Store:
        def list_sessions(self):
            return [SessionInfo()]

        def load_history(self, session_id):
            return [{"role": "user", "content": "last prompt"}]

    class ResumeResult:
        history = [{"role": "system", "content": "summary"}, {"role": "user", "content": "last prompt"}]
        restored_from_checkpoint = True
        message_count = 2
        estimated_tokens = 321

    class Builder:
        def __init__(self, context, token_budget):
            pass

        def build(self, path):
            return ResumeResult()

    monkeypatch.setattr(
        "xcode_cli.core.runtime.controller.SessionResumeBuilder",
        Builder,
    )

    events = []
    controller = RuntimeController(
        event_sink=events.append,
        session_store=Store(),
        context_manager=object(),
    )

    controller.dispatch(ResumeSessionCommand(session_id="session_123"))

    completed = next(event for event in events if isinstance(event, ResumeCompleted))
    assert completed.session_id == "session_123"
    assert completed.restored_from_checkpoint is True
    assert completed.message_count == 2
    assert completed.estimated_tokens == 321
    assert completed.last_user_input == "last prompt"
```

If the local test helpers already provide fake session stores/builders, use them instead of duplicating classes, but keep the assertions above.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
pytest tests/test_runtime_controller.py -q
```

Expected before implementation: failure because `ResumeCompleted` is emitted with only `session_id` and `message_count`.

- [ ] **Step 3: Update `_handle_resume_session`**

In `src/xcode_cli/core/runtime/controller.py`, when emitting `ResumeCompleted`, include:

```python
self._enqueue_event(ResumeCompleted(
    session_id=command.session_id,
    restored_from_checkpoint=result.restored_from_checkpoint,
    message_count=result.message_count,
    estimated_tokens=result.estimated_tokens,
    last_user_input=selected_session.last_user_input,
))
```

Use the actual local variable names from `_handle_resume_session`. If the selected session object is currently not retained after validation, store it before building the resume result.

- [ ] **Step 4: Preserve existing failure semantics**

Confirm these existing behaviors remain unchanged:

- Missing `session_store` emits `UICommandFailed`.
- Nonexistent `session_id` emits `UICommandFailed`.
- Empty restored history emits `UICommandFailed`.
- Successful restore updates `_history`.

- [ ] **Step 5: Run focused runtime tests**

Run:

```powershell
pytest tests/test_runtime_controller.py -q
```

Expected: pass.

---

## Task 3: Make `ResumeSelector` Look Like Plain Transcript Text

**Files:**
- Modify: `src/xcode_cli/core/ui/textual/widgets.py`
- Modify: `tests/test_textual_chat_app.py`

- [ ] **Step 1: Add a widget rendering test**

Add a focused test that verifies `ResumeSelector.render()` includes the plain text selector content:

```python
def test_resume_selector_renders_plain_text_list():
    from xcode_cli.core.ui.textual.widgets import ResumeSelector

    selector = ResumeSelector()
    selector.show_sessions([
        {
            "session_id": "session_abcdef123",
            "last_user_input": "continue work",
            "message_count": 4,
            "has_checkpoint": True,
        },
        {
            "session_id": "session_xyz987",
            "last_user_input": "review code",
            "message_count": 2,
            "has_checkpoint": False,
        },
    ])

    rendered = selector.render()
    plain = rendered.plain

    assert "Resumable sessions:" in plain
    assert "> session_" in plain
    assert "continue work" in plain
    assert "[checkpoint]" in plain
    assert "Enter confirm" in plain
```

- [ ] **Step 2: Run the focused test**

Run:

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected before implementation: may fail if render output or session key handling does not match.

- [ ] **Step 3: Update `ResumeSelector.DEFAULT_CSS`**

In `src/xcode_cli/core/ui/textual/widgets.py`, make `ResumeSelector` visually plain:

```python
DEFAULT_CSS = """
ResumeSelector {
    display: none;
    height: auto;
    max-height: 12;
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
}
"""
```

Do not add borders, panels, cards, background colors, or modal styling.

- [ ] **Step 4: Update `ResumeSelector.render()`**

Make `render()` own the list text. It should produce stable plain text with only the selected row styled:

```python
def render(self) -> Text:
    text = Text()
    if not self.display or not self.sessions:
        return text

    text.append("Resumable sessions:\n", style="bold")
    for idx, session in enumerate(self.sessions):
        session_id = str(session.get("session_id", ""))
        preview = str(session.get("last_user_input", "") or "(empty)").replace("\n", " ")
        message_count = session.get("message_count", 0)
        checkpoint = " [checkpoint]" if session.get("has_checkpoint") else ""

        prefix = ">" if idx == self.selected_index else " "
        style = "bold cyan" if idx == self.selected_index else "dim"
        line = f"{prefix} {session_id[:8]}... ({message_count} msgs{checkpoint}) {preview[:60]}\n"
        text.append(line, style=style)

    text.append("[up/down select, Enter confirm, Esc cancel]", style="dim")
    return text
```

Keep comments ASCII only.

- [ ] **Step 5: Run focused Textual tests**

Run:

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected: pass.

---

## Task 4: Stop Writing Resume Selection Updates Into `RichLog`

**Files:**
- Modify: `src/xcode_cli/core/ui/textual/app.py`
- Modify: `tests/test_textual_chat_app.py`

- [ ] **Step 1: Add a regression test for no repeated transcript writes**

Add or update a test in `tests/test_textual_chat_app.py`:

```python
def test_resume_selection_does_not_append_dynamic_notice_on_navigation(monkeypatch):
    from xcode_cli.core.ui.events import ResumeListLoaded
    from xcode_cli.core.ui.textual.app import ChatApp
    from xcode_cli.core.ui.textual.widgets import ResumeSelector

    app = ChatApp()
    selector = ResumeSelector()

    def fake_query_one(selector_id, expected_type=None):
        if selector_id == "#resume-selector":
            return selector
        raise LookupError(selector_id)

    calls = []
    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(app, "_append_notice_text", lambda *args, **kwargs: calls.append(args))

    app._handle_resume_list_loaded(ResumeListLoaded(sessions=[
        {"session_id": "s1", "last_user_input": "one", "message_count": 1},
        {"session_id": "s2", "last_user_input": "two", "message_count": 2},
    ]))
    app._handle_resume_key("down")
    app._handle_resume_key("up")

    assert calls == []
```

If `_append_notice_text` is removed in this task, adjust the assertion to verify no system notice block is appended for resume navigation.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected before implementation: failure because `_handle_resume_list_loaded()` and navigation call `_render_resume_list_notice()`.

- [ ] **Step 3: Update `_handle_resume_list_loaded`**

Change it to only show the transient selector:

```python
def _handle_resume_list_loaded(self, event: ResumeListLoaded) -> None:
    """Enter resume selection state or show no-session notice."""
    if not event.sessions:
        self.add_system_notice("resume_empty", "No recent sessions found for this project.")
        return

    selector = self.query_one("#resume-selector", ResumeSelector)
    selector.show_sessions(event.sessions)
    selector.scroll_visible()
    self._is_resume_selecting = True
```

The empty-state string should align with legacy: `No recent sessions found for this project.`

- [ ] **Step 4: Update `_handle_resume_key`**

Remove calls to `_render_resume_list_notice()`:

```python
if key in ("up", "k"):
    selector.move_selection(-1)
    return True
if key in ("down", "j"):
    selector.move_selection(1)
    return True
```

- [ ] **Step 5: Update confirm/cancel cleanup**

Confirm should hide the selector and dispatch:

```python
selector.hide_selector()
self._is_resume_selecting = False
self.controller.dispatch(ResumeSessionCommand(session_id=session_id))
```

Cancel should hide the selector and show legacy-aligned text:

```python
selector.hide_selector()
self._is_resume_selecting = False
self.add_system_notice("resume_cancelled", "Cancelled.")
```

- [ ] **Step 6: Remove dead RichLog dynamic notice helpers if unused**

If `_render_resume_list_notice()` and `_append_notice_text()` are no longer referenced anywhere in `ChatApp`, delete them.

Before deletion, run:

```powershell
rg -n "_render_resume_list_notice|_append_notice_text" src/xcode_cli/core/ui/textual tests
```

Expected after cleanup: no references except none.

- [ ] **Step 7: Run focused Textual tests**

Run:

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected: pass.

---

## Task 5: Render Successful Resume Feedback Like Legacy

**Files:**
- Modify: `src/xcode_cli/core/ui/textual/app.py`
- Modify: `tests/test_textual_chat_app.py`

- [ ] **Step 1: Update the successful resume UI test**

Replace the old assertion for `Resumed <id> with N messages.` with legacy-aligned output:

```python
def test_handle_resume_completed_adds_legacy_aligned_system_notice(monkeypatch):
    from xcode_cli.core.ui.events import ResumeCompleted
    from xcode_cli.core.ui.textual.app import ChatApp

    app = ChatApp()
    notices = []
    monkeypatch.setattr(app, "add_system_notice", lambda message_id, content: notices.append(content))

    app.handle_event(ResumeCompleted(
        session_id="session_1",
        restored_from_checkpoint=True,
        message_count=5,
        estimated_tokens=678,
        last_user_input="continue from last turn",
    ))

    content = notices[0]
    assert "Resumed session session_1" in content
    assert "Restored from checkpoint: yes" in content
    assert "Restored messages: 5" in content
    assert "Estimated context: ~678 tokens" in content
    assert "Latest user input: continue from last turn" in content
```

Add a second test for no latest input:

```python
def test_handle_resume_completed_omits_latest_input_when_missing(monkeypatch):
    from xcode_cli.core.ui.events import ResumeCompleted
    from xcode_cli.core.ui.textual.app import ChatApp

    app = ChatApp()
    notices = []
    monkeypatch.setattr(app, "add_system_notice", lambda message_id, content: notices.append(content))

    app.handle_event(ResumeCompleted(
        session_id="session_1",
        restored_from_checkpoint=False,
        message_count=5,
        estimated_tokens=678,
        last_user_input=None,
    ))

    content = notices[0]
    assert "Restored from checkpoint: no" in content
    assert "Latest user input:" not in content
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected before implementation: failure because `_handle_resume_completed()` renders the old single-line message.

- [ ] **Step 3: Update `_handle_resume_completed`**

In `src/xcode_cli/core/ui/textual/app.py`:

```python
def _handle_resume_completed(self, event: ResumeCompleted) -> None:
    """Render legacy-aligned resume completion."""
    lines = [
        f"Resumed session {event.session_id}",
        f"Restored from checkpoint: {'yes' if event.restored_from_checkpoint else 'no'}",
        f"Restored messages: {event.message_count}",
        f"Estimated context: ~{event.estimated_tokens} tokens",
    ]
    if event.last_user_input:
        lines.append(f"Latest user input: {event.last_user_input[:100]}")

    self.add_system_notice(
        f"resume_{event.session_id}",
        "\n".join(lines),
    )
```

- [ ] **Step 4: Run focused Textual tests**

Run:

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected: pass.

---

## Task 6: Documentation Sync

**Files:**
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`

- [ ] **Step 1: Update architecture wording**

In `docs/current/ARCHITECTURE.md`, replace any statement that says Textual `/resume` writes the selector list into `TranscriptArea` or uses `_append_notice_text`.

Use this meaning:

```text
Textual /resume enters a transient resume selection state. ResumeSelector is rendered as plain transcript-like text and updates the selected `>` marker in place. The selector is not written into long-term UI history and is removed on confirm/cancel. Successful restore feedback is a normal system notice and matches legacy /resume output: session id, checkpoint flag, restored message count, estimated tokens, and latest user input when available.
```

- [ ] **Step 2: Update progress/devnotes**

In `docs/current/PROGRESS.md` and `docs/current/DEVNOTES.md`, update the Batch 4/5 notes:

```text
/resume selection no longer rewrites RichLog on navigation. ResumeSelector owns the transient selector rendering, styled as plain text. Resume success output is legacy-aligned.
```

- [ ] **Step 3: Verify docs do not claim old behavior**

Run:

```powershell
rg -n "_append_notice_text|dynamic_notices|RichLog.*resume|resume_list" docs/current
```

Expected: no stale claim that `/resume` navigation rewrites RichLog or uses dynamic notices.

---

## Task 7: Verification

- [ ] **Step 1: Compile changed modules**

Run:

```powershell
python -m py_compile src/xcode_cli/core/ui/events.py src/xcode_cli/core/runtime/controller.py src/xcode_cli/core/ui/textual/app.py src/xcode_cli/core/ui/textual/widgets.py
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
pytest tests/test_ui_events_commands.py tests/test_runtime_controller.py tests/test_textual_chat_app.py -q
```

Expected: pass.

- [ ] **Step 3: Run existing Textual migration test set**

Run:

```powershell
pytest tests/test_textual_slash_commands.py tests/test_task_status_pet_slots.py tests/test_textual_chat_app.py tests/test_runtime_controller.py tests/test_ui_events_commands.py tests/test_slash_command_result.py -q
```

Expected: pass.

- [ ] **Step 4: Run full regression**

Run:

```powershell
pytest -q
```

Expected: pass.

- [ ] **Step 5: Manual cmd.exe acceptance**

Run:

```cmd
cd /d D:\Xcode
xcode chat --textual
```

Then test:

```text
/resume
```

Expected:

- The selector appears as plain text near the bottom of the chat UI.
- It has no box, card, border, modal feel, or background panel.
- Up/down or k/j moves only the `>` marker in place.
- The transcript does not accumulate repeated session lists.
- Enter hides the selector and restores the selected session.
- Restore feedback appears as:

```text
Resumed session <session_id>
Restored from checkpoint: yes/no
Restored messages: <message_count>
Estimated context: ~<estimated_tokens> tokens
Latest user input: <latest_user_input>
```

- Esc hides the selector and shows:

```text
Cancelled.
```

---

## Self-Review

- Spec coverage: selector visual behavior, no RichLog rewrite, confirm/cancel lifecycle, legacy restore metadata, tests, docs, and manual acceptance are covered.
- Placeholder scan: no TBD/TODO placeholders are used.
- Type consistency: `ResumeCompleted` fields are defined in Task 1, emitted in Task 2, and consumed in Task 5.
