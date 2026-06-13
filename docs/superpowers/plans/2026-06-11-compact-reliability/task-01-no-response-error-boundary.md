# Task 1: No response external error boundary

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P0. Empty LLM output currently becomes a normal assistant message in QQchat/external history, which can create a self-reinforcing failure loop.

**Files:**

- Modify: `src/xcode_cli/core/external_turn.py`
- Modify if needed: `src/xcode_cli/qqchat/service.py`
- Test: `tests/test_external_turn.py`
- Test if needed: `tests/test_qqchat_service.py`

## Goal

Treat `No response.` as an LLM failure for external entrypoints. It must not be appended to in-memory conversation history or persisted as a normal assistant message.

## Steps

- [x] **Step 1: Write failing external-turn regression test**

Add coverage in `tests/test_external_turn.py`:

- fake `run_llm_loop` returns `"No response."`;
- `ExternalTurnRunner.run()` returns `ExternalTurnResult(error="No response.")`;
- session store contains the user message but no assistant `"No response."`;
- state history contains the user message but no assistant `"No response."`.

- [x] **Step 2: Update `_is_llm_error()`**

In `external_turn.py`, classify these as errors:

```text
No response.
[v0] LLM request failed:
[v0] Missing API key
[v0] openai package not installed
```

Prefer a helper name that communicates semantic intent, such as `_is_external_turn_failure()`.

- [x] **Step 3: Add QQchat fallback behavior if needed**

If QQchat currently sends `result.text` for errors, ensure the reply is safe and clear:

```text
模型本轮没有返回内容，Xcode 已保留当前会话。请重试，或让我先压缩/恢复上下文。
```

Do not claim the original task succeeded.

- [x] **Step 4: Run focused tests**

```powershell
pytest tests/test_external_turn.py tests/test_qqchat_service.py -q
```

Expected: PASS.

- [x] **Step 5: Review checklist**

- `No response.` cannot enter assistant history for external turns.
- Existing `[v0]` error behavior remains unchanged.
- Normal assistant replies still persist.
- QQchat still replies to users with a safe message when appropriate.
