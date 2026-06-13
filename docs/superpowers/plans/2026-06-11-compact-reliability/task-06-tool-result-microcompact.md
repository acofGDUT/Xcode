# Task 6: Tool result micro-compact

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P1/P0. Reducing old tool outputs is P1, but preserving protocol-valid tool messages is P0.

**Files:**

- Modify: `src/xcode_cli/core/context.py`
- Modify if needed: `src/xcode_cli/core/tooling/execution.py`
- Test: `tests/test_context.py`

## Goal

Before full compaction, replace old, large tool result content with compact placeholders while preserving message roles, tool call IDs, and protocol ordering.

## Steps

- [x] **Step 1: Write failing micro-compact tests**

In `tests/test_context.py`, cover:

- old `read_file` result over threshold is replaced with placeholder;
- recent protected-tail tool result is not micro-compacted;
- `tool_call_id` remains unchanged;
- token estimate decreases;
- placeholder includes enough metadata to understand what was cleared.

- [x] **Step 2: Define thresholds**

Recommended initial constants:

```text
microcompact_min_age_messages = 12
microcompact_result_chars = 12000
microcompact_placeholder_chars < 300
```

Keep constants in `ContextManager` or config only if the existing config model clearly supports it. Do not add config churn before behavior is stable.

- [x] **Step 3: Implement helper**

Suggested helper:

```python
def microcompact_tool_results(
    messages: list[dict[str, Any]],
    *,
    protected_tail_start: int,
) -> tuple[list[dict[str, Any]], int]:
    ...
```

Return new messages and count of compacted tool results.

- [x] **Step 4: Integrate before full summary**

Compaction should:

```text
micro-compact old large tool results
recompute token estimate
if still above threshold, run full summary
```

If micro-compaction alone brings history below threshold, allow returning a lightweight outcome without LLM summary only if the caller can persist that rewrite safely. Otherwise keep it as an internal preprocessing step.

- [x] **Step 5: Run focused tests**

```powershell
pytest tests/test_context.py -q
```

Expected: PASS.

- [x] **Step 6: Review checklist**

- No tool message loses its `tool_call_id`.
- Placeholder cannot be mistaken for real tool output.
- Recent active evidence is not cleared prematurely.
- Full compaction metadata reports `micro_compacted_tool_results`.
