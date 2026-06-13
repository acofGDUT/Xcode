# Task 8: Docs And Manual Acceptance Records

**Risk layer:** P1/P2

**Goal:** Sync current docs only after implementation evidence exists, and record manual acceptance gaps explicitly.

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/superpowers/specs/2026-06-12-compact-state-restoration-design.md`
- Modify: `docs/superpowers/plans/2026-06-12-compact-state-restoration-plan.md`

- [ ] **Step 1: Update architecture only after implementation**

Describe the actual v3 runtime shape:

```text
first user + compact boundary + summary checkpoint + compact restored context + pair-safe protected tail
```

Also document v3 checkpoint metadata and `/resume` behavior.

- [ ] **Step 2: Update progress with evidence**

Record exact commands and results. Do not write “完成” until compileall, focused pytest, full pytest, and required manual acceptance evidence are present.

- [ ] **Step 3: Update roadmap status**

Move the item from “已写 spec/plan，待实现” to the true implementation status. If real QQ acceptance is still not run, state that explicitly.

- [ ] **Step 4: Add manual acceptance notes**

Record:

- PowerShell/cmd.exe `/compact` with restored context;
- `/resume` from v3 checkpoint;
- QQchat same-conversation continuation;
- QQchat conversation isolation.

- [ ] **Step 5: Final verification**

Run:

```powershell
git diff --check
```

Expected: exit code 0.
