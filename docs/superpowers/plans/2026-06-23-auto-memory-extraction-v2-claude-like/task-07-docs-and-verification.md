# Task 07: Docs And Verification

Status: Completed on 2026-06-24. Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.

**Risk layer:** P1/P2

## Goal

Close out extraction v2 with focused and full verification, then update current docs only with facts backed by real command output.

## Suggested Files

- Modify after implementation: `docs/current/ARCHITECTURE.md`
- Modify after implementation: `docs/current/PROGRESS.md`
- Modify after implementation: `docs/current/ROADMAP.md`
- Modify after implementation: `docs/current/DEVNOTES.md`
- Modify after implementation: `docs/superpowers/specs/2026-06-23-auto-memory-extraction-v2-claude-like-design.md`
- Modify after implementation: `docs/superpowers/plans/2026-06-23-auto-memory-extraction-v2-claude-like-plan.md`
- Modify after implementation: task files in `docs/superpowers/plans/2026-06-23-auto-memory-extraction-v2-claude-like/`

## Constraints

- Do not claim recall v2 is implemented.
- Do not remove recall v2 from ROADMAP.
- If PowerShell/cmd.exe manual acceptance is not executed, state that explicitly.
- Do not stage logs, secrets, cache files, or generated artifacts.

## Steps

- [x] **Step 1: Run focused verification**

Run:

```text
pytest tests/test_prompting_memory_v2.py -q
pytest tests/test_memory_manifest_v2.py -q
pytest tests/test_memory_extraction_policy.py -q
pytest tests/test_memory_extraction_subagent.py -q
pytest tests/test_memory_extraction_runner.py -q
pytest tests/test_agent_memory_extraction_v2.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q
pytest tests/test_memory_extraction.py tests/test_memory_manifest.py tests/test_memory.py -q
```

Expected:

- All focused tests pass.
- Any old v1 tests still present have been updated to v2 expectations or explicitly limited to legacy compatibility.

- [x] **Step 2: Run full verification**

Run:

```text
python -m compileall -q src
pytest -q
git diff --check
```

Expected:

- `compileall` exits 0.
- Full `pytest -q` passes.
- `git diff --check` exits 0; Windows LF/CRLF warnings are acceptable only if exit code is 0.

- [x] **Step 3: Update architecture**

In `docs/current/ARCHITECTURE.md`, replace v1 extraction wording with:

```markdown
Auto memory extraction v2 runs through `MemoryExtractionRunner`. The local REPL `after_turn_success` hook only submits an event and does not wait for extraction. The runner enforces one running extraction at a time, keeps only the latest pending event during overlap, and runs one trailing extraction after the current task finishes.

`MemoryExtractionSubagent` inherits the main v2 memory prompt, adds an extraction-specific user message with recent-message and manifest constraints, and uses only memory-scoped tools from `memory_tools.py`. The subagent can read/write/edit auto memory files, but cannot read project files, run shell/git/tests/build, call MCP tools, or dispatch agents.

New auto memory topics use v2 frontmatter: `name`, `description`, and top-level `type`; body content must include `Evidence:`. Old `metadata.type` topics are not valid v2 manifest entries by default.
```

- [x] **Step 4: Update progress with real evidence**

In `docs/current/PROGRESS.md`, add a new section:

```markdown
## NN. Auto memory extraction v2: 2026-06-24

Status: Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded. Auto memory recall v2 remains unimplemented.

Verification:
- `pytest tests/test_prompting_memory_v2.py -q`: actual pytest output.
- `pytest tests/test_memory_extraction_runner.py -q`: actual pytest output.
- `python -m compileall -q src`: exit code 0.
- `pytest -q`: actual pytest output.
- `git diff --check`: exit code 0; record Windows LF/CRLF warnings if those are the only output.
```
Replace placeholders with actual command output only after commands run.

- [x] **Step 5: Update roadmap**

In `docs/current/ROADMAP.md`:

- Remove or downgrade `Auto memory extraction v2` only if implementation and verification are complete.
- Keep `Auto memory recall v2` as `spec written; implementation pending; should run after extraction v2`.
- Keep manual PTY gaps if not executed.

- [x] **Step 6: Update devnotes**

In `docs/current/DEVNOTES.md`, add or update extraction v2 review notes:

```markdown
## NN. Auto memory extraction v2 boundaries

**Status**: Resolved for local REPL implementation; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.
- The after-turn hook submits to `MemoryExtractionRunner` only; it must not execute user scripts or skill hooks.
- The runner is single-flight and keeps only the latest pending event during overlap.
- Extraction subagent tools are memory-scoped only; project reads, shell, git, tests, MCP and dispatch_agent remain denied.
- New topic files use v2 frontmatter and must include `Evidence:`.
- Recall v2 is a separate plan and remains unimplemented until its own task set lands.
```

- [x] **Step 7: Update spec and plan status**

In `docs/superpowers/specs/2026-06-23-auto-memory-extraction-v2-claude-like-design.md` and the total plan, update status to the real result:

```markdown
> Status: Code implementation and automated regression are complete; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded.```

Only use this wording after verification has run.

- [x] **Step 8: Self-review docs**

Run:

```text
rg -n "not executed|not recorded|TODO|planned|Expected: PASS" docs/current docs/superpowers/specs/2026-06-23-auto-memory-extraction-v2-claude-like-design.md docs/superpowers/plans/2026-06-23-auto-memory-extraction-v2-claude-like-plan.md
```

Expected:

- No vague completion wording.
- No placeholder command output remains after implementation closeout.

- [x] **Step 9: Final git status review**

Run:

```text
git status --short
git diff --stat
```

Expected:

- Only intended source, tests, specs, plans, and current docs changed.
- No logs, secrets, cache files, or generated artifacts staged.

If committing is requested:

```text
git add src/xcode_cli/core docs/current docs/superpowers/specs/2026-06-23-auto-memory-extraction-v2-claude-like-design.md docs/superpowers/plans/2026-06-23-auto-memory-extraction-v2-claude-like-plan.md docs/superpowers/plans/2026-06-23-auto-memory-extraction-v2-claude-like tests
git commit -m "feat: implement claude-like memory extraction v2"
```
