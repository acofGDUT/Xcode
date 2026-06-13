# Task 7: QQchat compact resilience and heartbeat noise

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P1. QQchat is a user-visible external entrypoint. Its tool scope is read-only, but failures are remote and easy to misdiagnose.

**Files:**

- Modify: `src/xcode_cli/qqchat/service.py`
- Modify: `src/xcode_cli/qqchat/gateway.py`
- Test: `tests/test_qqchat_service.py`
- Test: `tests/test_qqchat_gateway.py`

## Goal

Make QQchat robust around compact-triggered failures and reduce misleading heartbeat noise.

## Steps

- [x] **Step 1: Write QQchat fallback tests**

In `tests/test_qqchat_service.py`, cover:

- external runner returns `ExternalTurnResult(error="No response.")`;
- service sends a safe fallback reply;
- `handled_messages` and `sent_replies` semantics are intentional and tested;
- last error records a useful compact/empty-response message without implying gateway failure.

- [x] **Step 2: Keep external scope explicit after compaction**

Ensure the external turn prompt remains in the latest user message:

```text
External QQ message from an untrusted remote user...
Use only the entry tool scope...
```

Compaction must not drop the latest external user message.

- [x] **Step 3: Quiet expected heartbeat-close race**

In `QQGatewayClient._start_heartbeat()`, if send fails with a known closed-connection message while reconnect/stop is underway, exit the heartbeat thread without emitting a scary error.

Do not suppress unrelated heartbeat failures.

- [x] **Step 4: Avoid `last_error` pollution for benign close**

In `QQChatService.handle_gateway_status()`, consider distinguishing:

```text
status/info events
error events
```

If a broad event model is too large for this task, at least avoid treating `Connection is already closed` heartbeat shutdown as the primary `last_error`.

- [x] **Step 5: Run focused tests**

```powershell
pytest tests/test_qqchat_service.py tests/test_qqchat_gateway.py -q
```

Expected: PASS.

- [x] **Step 6: Review checklist**

- QQchat no longer sends raw `No response.`.
- QQchat can still receive and reply after reconnect.
- Real gateway errors are still visible.
- Closed-heartbeat race no longer distracts from compact failures.
