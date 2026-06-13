# Task 8: Docs and final verification

> Parent plan: [2026-06-11-compact-reliability-plan.md](../2026-06-11-compact-reliability-plan.md)
> Spec: [2026-06-11-compact-reliability-design.md](../../specs/2026-06-11-compact-reliability-design.md)

**Risk layer:** P2 for docs, P0/P1 for final evidence. Closeout must not claim completion without tests and transcript evidence.

**Files:**

- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/ROADMAP.md`
- Review: all task docs and tests touched by Tasks 1-7

## Goal

Synchronize current docs after implementation and collect verification evidence for the compact reliability redesign.

## Steps

- [x] **Step 1: Update architecture docs**

Update `docs/current/ARCHITECTURE.md` only after implementation is complete. Document:

- external empty-response error boundary;
- `xcode.v2` compact checkpoint shape;
- summary quality gate;
- pair-safe tail;
- micro-compact behavior;
- QQchat fallback behavior.

- [x] **Step 2: Update devnotes**

Update `docs/current/DEVNOTES.md` with:

- why `No response.` must not enter external histories;
- compact summary validation rules;
- tool-pair invariants;
- provider compatibility note for `tool_schemas=[]`;
- heartbeat closed-connection noise classification if Task 7 is implemented.

- [x] **Step 3: Update progress and roadmap**

Update:

- `docs/current/PROGRESS.md`: record completed compact reliability tasks and evidence.
- `docs/current/ROADMAP.md`: move compact reliability from current risk to completed/stabilized or list remaining work.

- [x] **Step 4: Run final automated verification**

```powershell
python -m compileall -q src
pytest tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_gateway.py tests/test_llm.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q
pytest -q
git diff --check
```

- [x] **Step 5: Manual acceptance**

Record:

- PowerShell/cmd.exe `/compact` run on a tool-heavy conversation;
- JSONL checkpoint inspection showing `summary_format=xcode.v2`;
- QQchat message after compact-triggering turn no longer persists raw `No response.`;
- no orphan `tool` messages in compacted model history.

- [x] **Step 6: Review checklist**

- All explicit tasks have evidence.
- Docs match implementation, not intended design.
- No unrelated worktree changes are included in summary.
- Any skipped tests or manual gaps are called out explicitly.

## Execution record

Status: docs, automated verification, and PowerShell/cmd.exe native PTY `/compact` handler acceptance completed on 2026-06-12. Real QQ platform acceptance is delegated to the user per user request on 2026-06-12.

Automated verification:

- `python -m compileall -q src`: passed.
- `pytest tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_gateway.py tests/test_llm.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q`: `95 passed`.
- `pytest -q`: `533 passed`.
- `git diff --check`: exit code 0; only Windows LF/CRLF conversion warnings.

Native PTY `/compact` acceptance:

- `winpty.PtyProcess` + PowerShell passed: slash dispatcher `/compact` returned `handled=true`, transcript contained `summary_format=xcode.v2`, boundary message written, `protected_tail_messages=8`, `micro_compacted_tool_results=1`, `rejected_summary=false`, no orphan tool messages, and summary request omitted `tools` / `tool_choice`.
- `winpty.PtyProcess` + cmd.exe passed with the same assertions.

Manual acceptance boundary:

- QQ single-chat and group-chat platform messages after a compact-triggering turn are user-owned acceptance and are not required for this agent closeout.
- 2026-06-12 attempted a redacted QQ auth connectivity check before the user redirected the scope. The sandboxed request failed with local socket permission denial (`WinError 10013`); no further QQ network testing is required from Codex for this plan.
