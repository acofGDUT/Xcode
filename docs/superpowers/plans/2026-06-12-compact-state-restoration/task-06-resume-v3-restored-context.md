# Task 6: Resume v3 Restored Context

**Risk layer:** P0/P1

**Goal:** Resume v3 checkpoints with boundary, cumulative summary, restored context, and post-checkpoint messages.

**Files:**
- Modify: `src/xcode_cli/core/session_resume.py`
- Modify: `tests/test_session_resume.py`

- [ ] **Step 1: Write failing v3 resume tests**

Build a transcript with:

```text
message boundary
message checkpoint
compaction_checkpoint summary_format=xcode.v3
message Compact restored context
message user after checkpoint
```

Assert `SessionResumeBuilder.build()` returns model history containing boundary, checkpoint summary, restored context, and post-checkpoint user message.

- [ ] **Step 2: Keep v2 compatibility test**

Add or preserve a v2 checkpoint test showing old transcripts still restore summary + post-checkpoint messages.

- [ ] **Step 3: Strip transcript metadata**

Ensure `_message_for_model_history()` removes `metadata`, `message_id`, `message_seq`, `event_id`, and `event_seq` fields before returning model messages. Keep the existing user `metadata.model_content` behavior.

- [ ] **Step 4: Verify task**

Run:

```powershell
pytest tests/test_session_resume.py -q
```

Expected: v3 and v2 resume paths both pass.
