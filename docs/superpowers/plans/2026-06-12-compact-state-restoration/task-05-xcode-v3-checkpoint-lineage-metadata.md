# Task 5: xcode.v3 Checkpoint Lineage Metadata

**Risk layer:** P0

**Goal:** Persist auditable checkpoint lineage metadata while keeping old sessions compatible.

**Files:**
- Modify: `src/xcode_cli/core/session.py`
- Modify: `src/xcode_cli/core/conversation/compaction.py`
- Modify: `tests/test_compaction.py`

- [ ] **Step 1: Write failing metadata tests**

Assert `write_checkpoint()` appends a `compaction_checkpoint` event with:

```python
assert event["summary_format"] == "xcode.v3"
assert event["checkpoint_id"].startswith("ckpt_")
assert event["summary_hash"].startswith("sha256:")
assert event["restored_context_hash"].startswith("sha256:")
assert event["checkpoint_index"] == 1
```

Add a second checkpoint test that verifies `parent_checkpoint_id` points to the first checkpoint.

- [ ] **Step 2: Add compatible transcript metadata helpers**

Add helper methods to `SessionStore`:

```python
def latest_compaction_checkpoint(self, session_id: str) -> dict[str, Any] | None: ...
def message_count(self, session_id: str) -> int: ...
```

Do not require old session events to have ids. If adding `message_seq`/`message_id`, store them inside `metadata` and ensure resume strips metadata from model history.

- [ ] **Step 3: Generate lineage fields**

In `ConversationCompactor.write_checkpoint()`:

- compute `checkpoint_id`;
- read latest checkpoint as parent;
- compute `summary_hash`, `previous_summary_hash`, `restored_context_hash`;
- compute optional `covered_message_range` only when message sequence data is available;
- keep `source_message_count`, `source_token_estimate`, `remaining_message_count`, `protected_tail_messages`, `micro_compacted_tool_results`, and `rejected_summary=false`.

- [ ] **Step 4: Change v3 transcript write order**

For v3 write:

```text
boundary message
checkpoint summary message
compaction_checkpoint event
restored context message
```

This keeps restored context after the resume boundary event.

- [ ] **Step 5: Verify task**

Run:

```powershell
pytest tests/test_compaction.py tests/test_session_resume.py -q
```

Expected: metadata and existing resume tests pass.
