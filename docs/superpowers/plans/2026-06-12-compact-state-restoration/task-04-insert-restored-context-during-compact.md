# Task 4: Insert Restored Context During Compact

**Risk layer:** P0/P1

**Goal:** Insert a bounded restored-context system message only after a successful compact summary.

**Files:**
- Modify: `src/xcode_cli/core/context.py`
- Modify: `src/xcode_cli/core/conversation/compaction.py`
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `tests/test_context.py`
- Modify: `tests/test_compaction.py`

- [ ] **Step 1: Write failing compact-order tests**

Assert successful compact produces:

```text
first user
Compact boundary
Conversation summary checkpoint
Compact restored context
protected tail
```

Also assert restored context is omitted when the builder returns empty text, and omitted when summary validation rejects the summary.

- [ ] **Step 2: Extend CompressionResult**

Add:

```python
restored_context_message: dict[str, Any] = field(default_factory=dict)
restored_context_sections: list[str] = field(default_factory=list)
```

- [ ] **Step 3: Extend ContextManager.compress()**

Add optional parameters:

```python
restored_context: str = ""
restored_context_sections: list[str] | None = None
```

Insert the restored-context system message after `checkpoint_message` and before protected tail only when summary validation succeeds.

- [ ] **Step 4: Filter old restored context from cumulative summary input**

When `previous_summary` exists, filter system messages containing `Conversation summary checkpoint:` and `Compact restored context:` from the new-content section.

- [ ] **Step 5: Build restored context in ConversationCompactor**

Inject a `work_state` or `restored_context_provider` into `compact_history()`. Keep the provider optional so existing tests can use the compactor without a tracker.

- [ ] **Step 6: Verify task**

Run:

```powershell
pytest tests/test_context.py tests/test_compaction.py -q
```

Expected: restored-context insertion and rejected-summary preservation pass.
