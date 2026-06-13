# Task 3: Summary prompt and quality gate

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P0. Bad summaries can permanently pollute later context and cause repeated empty responses.

**Files:**

- Modify: `src/xcode_cli/core/context.py`
- Modify: `src/xcode_cli/core/conversation/compaction.py`
- Test: `tests/test_context.py`
- Test: `tests/test_compaction.py`

## Goal

Replace the current free-form summary request with a structured prompt and quality gate. Reject bad summaries instead of writing corrupted checkpoints.

## Steps

- [x] **Step 1: Write failing summary rejection tests**

In `tests/test_context.py`, cover:

- summary content starts with `<tool_call>`;
- summary content is JSON that looks like a tool/function call;
- summary content is empty;
- summary content is only `(middle conversation compressed)`;
- rejected summary returns no checkpoint and keeps original messages.

- [x] **Step 2: Write compactor preservation test**

In `tests/test_compaction.py`, cover:

- `ConversationCompactor.compact_history()` returns `None` or a failed outcome on rejected summary;
- caller does not replace `history[:]` with corrupted messages;
- live progress stops in both success and rejection paths.

- [x] **Step 3: Introduce structured prompt**

Update summary prompt to demand stable sections:

```text
Summary:
- User intent and active task
- Decisions and constraints
- Files and code changes
- Tool results and errors
- Pending tasks
- Current state
- Next steps
- Recent user messages
```

The prompt must explicitly say: no tool calls, no XML tool tags, no JSON tool invocation payloads, output summary text only.

- [x] **Step 4: Implement quality gate helper**

Suggested helper:

```python
def validate_compact_summary(summary: str, *, source_token_estimate: int) -> str | None:
    ...
```

Return normalized summary if valid, else `None`.

- [x] **Step 5: Add metadata for rejected summary**

If the implementation writes an event, use:

```json
{"type": "compaction_failed", "reason": "invalid_summary_tool_call_like"}
```

Do not write malformed summary into model history.

- [x] **Step 6: Run focused tests**

```powershell
pytest tests/test_context.py tests/test_compaction.py -q
```

Expected: PASS.

- [x] **Step 7: Review checklist**

- `<tool_call>` summaries are rejected.
- Rejection does not lose current user message.
- Existing good summary behavior remains.
- Summary truncation happens only after validation.
