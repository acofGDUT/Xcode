# Task 7: End-To-End Compact Regression

**Risk layer:** P0/P1

**Goal:** Update compact command regressions and run focused plus full verification after Tasks 1-6.

**Files:**
- Modify as needed based on Tasks 1-6
- Modify: `tests/test_agent_resume_command.py` if `/compact` command assertions need v3 updates

- [ ] **Step 1: Update `/compact` command regression**

Existing tests that assert `summary_format=xcode.v2` should be updated to `xcode.v3` only after v3 metadata is implemented. Add assertions for `restored_context_sections` when the fake work state has content.

- [ ] **Step 2: Run focused regression**

Run:

```powershell
python -m compileall -q src
pytest tests/test_work_state.py tests/test_agent_tool_loop.py tests/test_external_turn.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py tests/test_agent_resume_command.py -q
```

Expected: focused compact/session/tool-loop suite passes.

- [ ] **Step 3: Run full suite**

Run:

```powershell
pytest -q
git diff --check
```

Expected: full pytest passes; `git diff --check` exits 0. LF/CRLF warnings are acceptable only if the command exits 0.
