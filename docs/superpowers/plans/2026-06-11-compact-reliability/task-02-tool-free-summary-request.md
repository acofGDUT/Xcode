# Task 2: Tool-free summary LLM request

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P0. Compaction summary calls must not expose an empty `tools=[]` + `tool_choice="auto"` combination that can confuse OpenAI-compatible providers.

**Files:**

- Modify: `src/xcode_cli/core/llm.py`
- Test: `tests/test_llm.py`
- Test if needed: `tests/test_context.py`

## Goal

When `tool_schemas` is empty, `LLMClient.complete()` should create a no-tool request. It should not pass `tools=[]` and should not pass `tool_choice="auto"`.

## Steps

- [x] **Step 1: Write failing LLM request test**

In `tests/test_llm.py`, fake the OpenAI client and capture request kwargs:

- with `tool_schemas=[]`, assert `tools` is absent and `tool_choice` is absent, or assert an explicit provider-safe no-tool value if chosen;
- with non-empty `tool_schemas`, assert existing `tools` + `tool_choice="auto"` behavior remains.

- [x] **Step 2: Update request construction**

Build request kwargs incrementally:

```python
request_kwargs = {
    "model": model,
    "messages": [...],
    "temperature": 0.2,
    "stream": True,
}
if tool_schemas:
    request_kwargs["tools"] = tool_schemas
    request_kwargs["tool_choice"] = "auto"
```

- [x] **Step 3: Preserve streaming behavior**

Do not change chunk parsing except as required by this request shape. Existing stream interruption handling must remain intact.

- [x] **Step 4: Run focused tests**

```powershell
pytest tests/test_llm.py -q
```

Expected: PASS.

- [x] **Step 5: Review checklist**

- Summary calls are tool-free.
- Normal tool-calling turns still expose tools.
- Missing API key and package errors still behave the same.
- Stream consumption exceptions still return `[v0] LLM request failed: ...`.
