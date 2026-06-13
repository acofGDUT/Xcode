# Task 4: Pair-safe compact tail

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P0. Invalid `assistant.tool_calls` / `tool` ordering can make providers reject or mishandle the next LLM request.

**Files:**

- Modify: `src/xcode_cli/core/context.py`
- Modify if useful: `src/xcode_cli/core/session_resume.py`
- Test: `tests/test_context.py`
- Test if needed: `tests/test_session_resume.py`

## Goal

Tail selection during compaction must preserve valid tool-call pairs and keep the latest user message.

## Steps

- [x] **Step 1: Write failing orphan tool tests**

In `tests/test_context.py`, construct histories where fixed last-8 selection would keep:

- a `tool` message without its declaring assistant;
- an assistant with two `tool_calls` but only one matching `tool`;
- a latest user message just before a large tool block.

Expected compacted history:

- no orphan tool message;
- no assistant `tool_calls` with missing results;
- latest user message is retained.

- [x] **Step 2: Extract or reuse pair-cleanup logic**

`SessionResumeBuilder._remove_orphans()` already has pair-aware cleanup. Either:

- extract shared helper into a small module, or
- implement an equivalent local helper in `context.py` with tests.

Avoid broad refactors unless they clearly reduce duplication.

- [x] **Step 3: Implement pair-safe tail builder**

Suggested behavior:

```text
start from latest messages
expand backwards to include assistant/tool pairs
drop incomplete pairs if they cannot fit
always include latest user message
```

Use message count and token budget as constraints. The first implementation can keep a conservative message-count cap, but it must be protocol-valid.

- [x] **Step 4: Run focused tests**

```powershell
pytest tests/test_context.py tests/test_session_resume.py -q
```

Expected: PASS.

- [x] **Step 5: Review checklist**

- No orphan `tool` messages after compaction.
- No incomplete assistant `tool_calls` after compaction.
- Latest user intent survives.
- Resume behavior does not regress.
