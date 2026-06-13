# Task 5: Compact boundary and restoration metadata

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P1. Boundary and metadata improve model behavior and debugging, but must not weaken P0 message validity.

**Files:**

- Modify: `src/xcode_cli/core/context.py`
- Modify: `src/xcode_cli/core/conversation/compaction.py`
- Modify if needed: `src/xcode_cli/core/session_resume.py`
- Test: `tests/test_context.py`
- Test: `tests/test_compaction.py`
- Test if needed: `tests/test_session_resume.py`

## Goal

Move from a single checkpoint system message to an explicit compact boundary plus versioned summary metadata.

## Steps

- [x] **Step 1: Write failing boundary tests**

In `tests/test_context.py`, assert compacted history contains:

```text
system: Compact boundary...
system: Conversation summary checkpoint...
```

The boundary must appear before the summary.

- [x] **Step 2: Add `summary_format=xcode.v2`**

Update `ConversationCompactor.write_checkpoint()` metadata:

```json
{
  "summary_format": "xcode.v2",
  "source_message_count": 90,
  "remaining_message_count": 14,
  "protected_tail_messages": 10,
  "micro_compacted_tool_results": 0,
  "rejected_summary": false
}
```

Preserve compatibility with older `xcode.v1` checkpoints.

- [x] **Step 3: Restore cheap critical context**

At minimum, ensure compacted history preserves:

- latest user message;
- external entrypoint scope message if present;
- active plan summary if plan mode is active and already represented in history.

Recent-read-file and invoked-skill reinjection may be deferred to a later task if no audit metadata exists yet, but the metadata shape should leave room for it.

- [x] **Step 4: Update resume support if needed**

`SessionResumeBuilder` should resume from `xcode.v2` checkpoints the same way it resumes from old checkpoints. It may ignore unknown metadata fields.

- [x] **Step 5: Run focused tests**

```powershell
pytest tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q
```

Expected: PASS.

- [x] **Step 6: Review checklist**

- Boundary text does not contain tool-call-looking markup.
- Metadata is useful but not required for old checkpoints.
- Unknown metadata does not break resume.
- Boundary does not duplicate system prompt responsibilities.
