# Textual Batch 6 Default-Ready Blockers Implementation Plan

> **For agentic workers:** REQUIRED WORKFLOW: Follow project SDD (`docs/current/SDD.md`). This plan is a specification-driven coding brief, not a TDD red/green script. Implement task-by-task, run the listed verification commands, and stop for review after each task group if behavior diverges from the plan.

**Goal:** Make `xcode chat --textual` safer to evaluate as a future default by closing terminal-output, Windows interaction, `/env`, narrow approval/diff, and fallback blockers.

**Architecture:** Textual remains the development entrypoint in this batch. Do not switch `xcode chat` default yet. Batch 6 should strengthen the single-renderer boundary: runtime/tool output must enter `UIEvent`/Textual surfaces, widget actions must continue to send `UICommand`, and legacy UI remains available as fallback.

**Tech Stack:** Python 3.10+, Textual, Rich, pytest, existing `RuntimeController`, `ChatApp`, `UIEvent`, `UICommand`, `RuntimeServices`.

---

## Scope

Batch 6 is about default-readiness blockers. It is not a UI polish batch and not the default-entry switch.

Implement:

- Runtime/tool stdout/stderr/logging boundary checks for Textual.
- `run_shell` output semantics in Textual, including stdout/stderr visibility without direct terminal writes.
- `/env` Textual path consistency: either keep read-only with correct copy, or implement a minimal edit flow if small enough.
- Narrow-window approval/diff resilience.
- Textual startup fallback strategy and capability checks.
- cmd.exe / PowerShell manual acceptance checklist.
- Documentation sync.

Do not implement:

- `xcode chat` default Textual switch.
- Pet visuals or animated pet assets.
- Full theme system.
- Full `/env` dashboard clone unless explicitly approved.
- Large frontend beautification.
- Direct widget calls to LLM/tools/filesystem mutation.

## Current Baseline

Current branch:

```text
app-v2
```

Current status expected before implementation:

```text
git status --short --branch
## app-v2...origin/app-v2
```

Last known verification:

```text
pytest -q
433 passed
```

Known Batch 4/5 state:

- `xcode chat --textual` exists.
- legacy remains available.
- `/resume` and `/compact` are wired to real services.
- `/env` is currently read-only in Textual.
- `run_shell` stdout/stderr capture and Windows E2E are still blockers.

---

## Files And Responsibilities

Primary implementation files:

- `src/xcode_cli/main.py`
  - Textual startup and legacy fallback behavior.
  - Help text for `--textual` / `--legacy`.

- `src/xcode_cli/core/runtime/controller.py`
  - Tool execution boundary.
  - `RunSlashCommandCommand` behavior.
  - `SaveEnvCommand` / `/env` handling.
  - Emitting runtime/tool output UI events.

- `src/xcode_cli/core/runtime/output.py`
  - Runtime/tool output sink models. Extend only if actually used.

- `src/xcode_cli/core/ui/events.py`
  - Add UI events only if existing `ToolOutputProduced`, `SystemNoticeAdded`, or `UICommandFailed` cannot express the behavior.

- `src/xcode_cli/core/ui/textual/app.py`
  - Consume output/log events.
  - Approval/diff narrow-window behavior.
  - `/env` interaction if needed.

- `src/xcode_cli/core/ui/textual/widgets.py`
  - ApprovalCard sizing/truncation.
  - Optional Env selector/editor widget only if selected approach requires it.

- `src/xcode_cli/core/tools/shell.py`
  - Preserve captured subprocess behavior.
  - Do not allow subprocess stdout/stderr to stream directly into terminal.

Test files:

- `tests/test_runtime_controller.py`
- `tests/test_textual_chat_app.py`
- `tests/test_textual_slash_commands.py`
- `tests/test_shell.py`
- `tests/test_ui_events_commands.py`

Docs:

- `docs/current/PROGRESS.md`
- `docs/current/ARCHITECTURE.md`
- `docs/current/DEVNOTES.md`
- Optional: `docs/current/ROADMAP.md` if default-switch criteria change.

---

## Task 1: Fix `/env` Textual Copy And Decide Minimal Behavior

**Goal:** Remove the current misleading Textual `/env` copy and make the behavior explicit.

**Files:**

- Modify: `src/xcode_cli/core/runtime/controller.py`
- Modify: `tests/test_textual_slash_commands.py`
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`

**Required behavior:**

- `/help` must not say Textual `/env` is editable unless editing is actually implemented.
- Current acceptable Batch 6 default: keep `/env` read-only and say so clearly.
- `SaveEnvCommand` can remain reserved for future minimal editing, but must not imply widgets directly write config.

**Implementation guidance:**

Change [controller.py](D:/Xcode/src/xcode_cli/core/runtime/controller.py) `/help` line from:

```python
"/env - Show editable environment settings",
```

to:

```python
"/env - Show environment settings",
```

or:

```python
"/env - Show read-only environment settings",
```

The `/env` output should continue to include:

```text
read-only environment display
provider: ...
base_url: ...
model: ...
api_key: ***
max_tokens: ...
max_summary_chars: ...
```

**Tests:**

- Add or update `tests/test_textual_slash_commands.py` so `/help` output does not contain `editable environment`.
- Keep existing `SaveEnvCommand` redaction tests.

**Verification:**

```powershell
pytest tests/test_textual_slash_commands.py -q
```

Expected: pass.

---

## Task 2: Runtime Output Boundary Audit And Guardrails

**Goal:** Ensure Textual path is moving toward one terminal writer. Tools and runtime code should not write directly to stdout/stderr while ChatApp is active.

**Files:**

- Modify: `src/xcode_cli/core/runtime/controller.py`
- Modify: `src/xcode_cli/core/runtime/output.py`
- Modify: `tests/test_runtime_controller.py`
- Optional Modify: `src/xcode_cli/core/config.py` only if a Textual-path direct print is found and can be safely rerouted.

**Required behavior:**

- Tool execution results must enter Textual through existing UI events:
  - `ToolOutputProduced(output_type="result" | "stdout" | "stderr" | "error")`
  - `ToolError`
  - `UICommandFailed`
- Do not use `print()`, `console.print()`, `sys.stdout.write()`, or Rich Live from Textual runtime paths.
- Do not use process-wide `contextlib.redirect_stdout` around arbitrary tool execution unless the coding agent proves it is safe for Textual; redirecting global stdout is risky in a multithreaded Textual app.
- Prefer auditing and removing direct writers from Textual-reachable code paths.

**Implementation guidance:**

1. Audit direct terminal writers reachable from Textual:

```powershell
rg -n "print\\(|console\\.print|sys\\.stdout|sys\\.stderr|Live\\(" src/xcode_cli
```

2. Classify each result:

- Legacy-only path: leave it.
- CLI tool subcommand path: leave it.
- Textual runtime path: route through `UIEvent` or make it return a string instead.

3. If adding a runtime log event is necessary, prefer:

```python
@dataclass(frozen=True)
class RuntimeLogProduced(UIEvent):
    level: str
    message: str
    source: str = ""
```

Then `ChatApp` should render it as non-model-visible system notice or compact runtime log block.

Only add this event if existing `SystemNoticeAdded` is not enough.

**Tests:**

Add a controller-level test that a fake tool returning stdout-like content produces UI-visible output through events and does not require direct stdout.

Example assertion shape:

```python
assert any(
    isinstance(event, ToolOutputProduced)
    and event.tool_name == "fake_tool"
    for event in events
)
```

If direct writer audit finds no Textual-reachable direct writers, document that in `DEVNOTES.md` and keep the implementation minimal.

**Verification:**

```powershell
pytest tests/test_runtime_controller.py -q
pytest tests/test_ui_events_commands.py -q
```

Expected: pass.

---

## Task 3: `run_shell` Textual Output Semantics

**Goal:** Make shell output safe and legible in Textual without changing model-visible tool_result semantics unnecessarily.

**Files:**

- Modify: `src/xcode_cli/core/tools/shell.py`
- Modify: `src/xcode_cli/core/runtime/controller.py`
- Modify: `src/xcode_cli/core/ui/textual/app.py`
- Modify: `tests/test_shell.py`
- Modify: `tests/test_runtime_controller.py`
- Modify: `tests/test_textual_chat_app.py`

**Required behavior:**

- `run_shell` must keep using `subprocess.run(..., capture_output=True, encoding="utf-8", errors="replace")`.
- Shell stdout/stderr must not stream directly to terminal.
- Textual should show shell command preview before approval.
- After execution, shell output should be visible as a tool result block.
- Long shell output should be truncated or summarized in UI without losing model-visible tool result unless existing behavior already truncates model-visible content.

**Implementation guidance:**

Current `run_shell()` returns a combined string. That is acceptable for model-visible result.

For UI display:

- Keep `CommandPreviewAvailable` before permission.
- Keep `ToolOutputProduced(output_type="result", content=result_str)` after execution if already emitted by `AgentEngine`.
- If `AgentEngine` does not emit output for tool results, add the event in the least invasive place.
- Do not split stdout/stderr in the model result unless you can do it without breaking existing tests.

If improving `run_shell()` return format, prefer stable labels:

```text
stdout:
...

stderr:
...
```

or keep current combined output and only adjust UI rendering.

**Tests:**

- `tests/test_shell.py` keeps UTF-8/errors behavior locked.
- Add runtime controller test for `run_shell`:
  - emits `CommandPreviewAvailable` before permission.
  - after approval/execution, emits UI-visible output/result event.
- Add ChatApp test that shell result content renders as a tool result block.

**Verification:**

```powershell
pytest tests/test_shell.py tests/test_runtime_controller.py tests/test_textual_chat_app.py -q
```

Expected: pass.

---

## Task 4: Approval And Diff Narrow-Window Resilience

**Goal:** Approval/diff should remain usable in narrow terminals. The user must be able to see the diff preview and the three choices.

**Files:**

- Modify: `src/xcode_cli/core/ui/textual/widgets.py`
- Modify: `src/xcode_cli/core/ui/textual/app.py`
- Modify: `tests/test_textual_chat_app.py`

**Required behavior:**

- `ApprovalCard` remains compact.
- Choices are vertical rows:

```text
> Yes
  No
  Yes, this conversation
```

- Diff lines keep red/green/cyan semantics.
- The approval choices must stay visible even when diff is long.
- `v` expansion remains disabled unless a separate permission surface design is approved.
- `y/n/a`, up/down, Enter still work while input is focused.

**Implementation guidance:**

Current `ApprovalCard._compact_diff_lines(max_lines=4)` is acceptable. Confirm it still preserves option visibility.

If narrow terminals still clip choices:

- Reduce diff visible lines to 3 in very small heights.
- Keep `#approval-card` max-height conservative.
- Do not move approval into a modal/screen.
- Do not put approval action into long-term message history.

**Tests:**

Add or update tests to assert:

- long diff render contains `Yes`, `No`, and `Yes, this conversation`.
- long diff render contains at most the configured number of diff content lines plus truncation marker.
- plus/minus/hunk styles are assigned by `render()` for added/removed/hunk lines.
- `v` is not consumed as an expansion command.

**Verification:**

```powershell
pytest tests/test_textual_chat_app.py -q
```

Expected: pass.

---

## Task 5: Textual Startup Fallback Strategy

**Goal:** Keep `--textual` safe during development and prepare for future default switching.

**Files:**

- Modify: `src/xcode_cli/main.py`
- Modify: `tests` only if Typer command tests exist or are added.
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/current/PROGRESS.md`

**Required behavior:**

- `xcode chat --textual` remains the explicit APPv2 entry.
- `xcode chat --legacy` remains available.
- Do not switch default `xcode chat` to Textual.
- If Textual import/startup fails before the app is running, print a concise message and fall back to legacy only if it is safe.
- Do not fall back in the middle of an active Textual session.

**Implementation guidance:**

In `main.py`, wrap startup narrowly:

```python
if textual:
    try:
        from xcode_cli.core.runtime.services import RuntimeServices
        from xcode_cli.core.ui.textual.app import ChatApp
    except Exception as exc:
        console.print(f"Textual UI unavailable, falling back to legacy: {exc}")
        AgentRuntime().run_chat()
        return

    services = RuntimeServices.create()
    try:
        ChatApp(controller=services.create_textual_controller()).run()
    except Exception as exc:
        console.print(f"Textual UI exited with error: {exc}")
        raise
```

Keep the second exception strict. Once Textual is running, unexpected failure should be visible and debuggable rather than silently starting a second REPL over a broken terminal.

If this behavior is too aggressive, document it and keep fallback as docs-only for Batch 6.

**Tests:**

If adding command tests is too heavy, do an import smoke test:

```powershell
python -c "from xcode_cli.core.runtime.services import RuntimeServices; from xcode_cli.core.ui.textual.app import ChatApp; print('ok')"
```

**Verification:**

```powershell
python -m py_compile src/xcode_cli/main.py
```

Expected: pass.

---

## Task 6: Windows Manual E2E Checklist

**Goal:** Create a concrete manual acceptance path for cmd.exe and PowerShell.

**Files:**

- Create: `docs/current/TEXTUAL_BATCH6_MANUAL_ACCEPTANCE.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/DEVNOTES.md`

**Required content:**

The checklist must cover both shells:

```cmd
cd /d D:\Xcode
xcode chat --textual
```

PowerShell:

```powershell
cd D:\Xcode
xcode chat --textual
```

Manual cases:

- Start and exit with `Ctrl+Q`.
- Send a normal prompt and see assistant streaming.
- Run `/help`.
- Run `/env` and confirm read-only copy.
- Run `/resume` with more than 10 sessions if available; confirm list window scrolls.
- Run `/compact`; confirm input is blocked during compaction.
- Ask for a file edit; confirm diff is visible and choices remain visible.
- Approve with up/down + Enter.
- Reject with `n`; confirm tool rejected result is visible.
- Ask for shell command; confirm command preview appears before approval and stdout/stderr appear inside Textual UI.
- Resize terminal narrower and repeat file edit approval.

Each item should have:

- Steps
- Expected result
- Pass/fail notes field

**Verification:**

No automated test required for the document. Coding agent should paste actual manual results into the checklist after running it.

---

## Task 7: Documentation Sync And Batch 6 Readiness Decision

**Goal:** Keep project docs aligned with the implementation and make the next decision explicit.

**Files:**

- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`
- Optional Modify: `docs/current/ROADMAP.md`

**Required updates:**

`PROGRESS.md`:

- Add Batch 6 section.
- List completed blockers.
- List remaining blockers.
- State explicitly:

```text
Batch 6 does not switch default entry. Default switch remains gated on Windows E2E and terminal-output boundary review.
```

`ARCHITECTURE.md`:

- Update Textual path boundaries.
- Describe any new runtime output/log events or fallback behavior.

`DEVNOTES.md`:

- Record any terminal writer audit findings.
- Record Windows E2E results or skipped items.
- Record `/env` decision.

`ROADMAP.md`:

- Only update if default-switch criteria changed.

**Verification:**

```powershell
rg -n "default-ready|Batch 6|run_shell|Windows E2E|fallback|/env" docs/current
```

Expected: docs clearly state what is done and what remains.

---

## Final Verification Commands

Run these before handing back to Codex review:

```powershell
python -m py_compile src/xcode_cli/main.py src/xcode_cli/core/runtime/controller.py src/xcode_cli/core/runtime/output.py src/xcode_cli/core/ui/events.py src/xcode_cli/core/ui/textual/app.py src/xcode_cli/core/ui/textual/widgets.py
```

```powershell
pytest tests/test_shell.py tests/test_runtime_controller.py tests/test_textual_slash_commands.py tests/test_textual_chat_app.py tests/test_ui_events_commands.py -q
```

```powershell
pytest -q
```

Expected:

- `py_compile` exits 0.
- focused tests pass.
- full test suite passes.

Manual:

- Complete `docs/current/TEXTUAL_BATCH6_MANUAL_ACCEPTANCE.md` in cmd.exe and PowerShell.

---

## Review Gate

After implementation, Codex should review before Batch 7 or default-switch planning.

Review should answer:

- Are there any remaining direct terminal writers reachable from Textual?
- Does `run_shell` output stay inside Textual UI?
- Does `/env` copy match behavior?
- Are approval choices visible in narrow terminals?
- Did cmd.exe and PowerShell manual acceptance pass?
- Is default switch still blocked or newly eligible?

Expected Batch 6 outcome:

```text
Textual remains explicit --textual, but default-ready blockers are reduced and documented.
```

Not expected:

```text
xcode chat defaults to Textual.
```
