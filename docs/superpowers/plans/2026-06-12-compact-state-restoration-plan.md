# Compact State Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Detailed task checklists live in the task files listed below.

Status: Code implementation and automated regression completed on 2026-06-14. PowerShell/cmd.exe native PTY restored-context `/compact`, v3 `/resume`, and QQchat platform acceptance have not been run/recorded, so implementation closeout still carries manual acceptance gaps.

**Goal:** Add deterministic compact restored context and auditable cumulative checkpoint lineage on top of the existing compact reliability baseline.

**Architecture:** Introduce a bounded `WorkStateTracker` that records active files, recent file excerpts, diagnostics, build/test status, plan summary, and invoked skill metadata during normal tool execution. `ConversationCompactor` will render that snapshot into a `Compact restored context` system message and write `xcode.v3` checkpoint lineage metadata without weakening the existing summary quality gate, pair-safe tail, or QQchat error boundary.

**Tech Stack:** Python 3.10+、pytest、现有同步 `AgentRuntime`、`ToolCallExecutor`、`ContextManager`、`ConversationCompactor`、`SessionStore`、`SessionResumeBuilder`、`ExternalTurnRunner`。不引入 asyncio、embedding、vector DB 或外部服务。

**Execution Record (2026-06-14):**

- Tasks 1-7 were implemented and reviewed task-by-task: `WorkStateTracker`, local tool-loop recording, external work-state isolation, restored-context insertion, `xcode.v3` checkpoint metadata, v3 resume behavior, and `/compact` integration regression.
- Task 8 synced current docs and recorded the remaining manual acceptance gaps.
- Automated evidence: `python -m compileall -q src` exit 0; focused pytest matrix `117 passed in 13.80s`; full `pytest -q` `564 passed in 28.96s`; `git diff --check` exit 0 with only Windows LF/CRLF conversion warnings.
- Follow-up hardening on 2026-06-14 removed fixed first-user retention from compacted `_history`, expanded restored-context redaction, classified `xcodebuild test`/`swift test`/JS test commands as latest tests, and connected plan-mode summaries to current plan restoration. Verification: `python -m compileall -q src` exit 0; focused regression `119 passed in 15.65s`; full `pytest -q` `566 passed in 31.81s`; `git diff --check` exit 0 with only Windows LF/CRLF warnings.

---

## References

- Spec: `docs/superpowers/specs/2026-06-12-compact-state-restoration-design.md`
- Existing compact baseline: `docs/superpowers/specs/2026-06-11-compact-reliability-design.md`
- Current compact code:
  - `src/xcode_cli/core/context.py`
  - `src/xcode_cli/core/conversation/compaction.py`
  - `src/xcode_cli/core/session_resume.py`
  - `src/xcode_cli/core/tooling/execution.py`
  - `src/xcode_cli/core/external_turn.py`

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/xcode_cli/core/work_state.py` | Create | Work-state dataclasses, bounded snapshot rendering, shell-output diagnostics parsing, redaction helpers |
| `src/xcode_cli/core/tooling/execution.py` | Modify | Record successful and failed tool calls into an optional work-state tracker |
| `src/xcode_cli/core/agent.py` | Modify | Own local REPL work state, pass work state into local and external tool loops, expose plan/task snapshot data |
| `src/xcode_cli/core/external_turn.py` | Modify | Maintain isolated work state per external conversation |
| `src/xcode_cli/core/context.py` | Modify | Accept restored context message during compression and filter old restored context from cumulative summary input |
| `src/xcode_cli/core/conversation/compaction.py` | Modify | Build restored context, return/write `xcode.v3` checkpoint metadata, preserve rejected-summary behavior |
| `src/xcode_cli/core/session.py` | Modify | Add compatible event/message metadata helpers for checkpoint lineage |
| `src/xcode_cli/core/session_resume.py` | Modify | Restore v3 boundary + summary + restored context and ignore transcript metadata in model history |
| `tests/test_work_state.py` | Create | Unit tests for tracker, renderer, parser, redaction and budget behavior |
| `tests/test_agent_tool_loop.py` | Modify | Tool loop updates work state without changing tool messages |
| `tests/test_external_turn.py` | Modify | External work-state isolation |
| `tests/test_context.py` | Modify | Restored context insertion and filtering |
| `tests/test_compaction.py` | Modify | v3 checkpoint metadata and transcript write order |
| `tests/test_session_resume.py` | Modify | v3 resume compatibility |
| `docs/current/ROADMAP.md` | Modify after implementation | Move item from planned to implemented or update status |
| `docs/current/PROGRESS.md` | Modify after implementation | Record implementation evidence |
| `docs/current/DEVNOTES.md` | Modify after implementation | Record invariants and risks |
| `docs/current/ARCHITECTURE.md` | Modify after implementation | Describe actual v3 compact architecture only after code lands |

## Task Files

Implement in this order. Each task file is the canonical checklist for that task.

| Task | Risk | Document | Purpose |
|------|------|----------|---------|
| 1 | P0/P1 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-01-work-state-tracker-core.md` | Create `WorkStateTracker`, restored-context rendering, parsing, redaction, and budget behavior |
| 2 | P0 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-02-record-work-state-from-tool-execution.md` | Feed tool results into work state without changing model-visible tool messages |
| 3 | P0 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-03-external-turn-work-state-isolation.md` | Keep local REPL, QQchat, and external conversations isolated |
| 4 | P0/P1 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-04-insert-restored-context-during-compact.md` | Insert restored context only after successful compact summary validation |
| 5 | P0 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-05-xcode-v3-checkpoint-lineage-metadata.md` | Persist `xcode.v3` checkpoint id, parent, hash, index, and optional range metadata |
| 6 | P0/P1 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-06-resume-v3-restored-context.md` | Resume v3 checkpoints with boundary, summary, restored context, and post-checkpoint messages |
| 7 | P0/P1 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-07-end-to-end-compact-regression.md` | Update compact command regressions and run focused/full verification |
| 8 | P1/P2 | `docs/superpowers/plans/2026-06-12-compact-state-restoration/task-08-docs-and-manual-acceptance-records.md` | Sync current docs after evidence and record manual acceptance results |

## Execution Constraints

- Execute one task at a time; stop for Codex review after each task.
- Code tasks must follow TDD-core: write failing regression tests first, then minimal implementation, then refactor.
- Keep all changes synchronous; do not introduce asyncio.
- Work-state tracking is best-effort and must never raise into the agent loop.
- Do not record secrets or full command logs in restored context.
- Do not let restored context break OpenAI-compatible tool-call ordering.
- Do not feed restored context into cumulative summary repeatedly.
- Keep QQchat/external work state isolated from local REPL state and from other external conversations.
- Do not rewrite old session JSONL files.
- Do not update `docs/current/ARCHITECTURE.md` to describe v3 as current behavior until code and verification are complete.

## Recommended Final Verification

```powershell
python -m compileall -q src
pytest tests/test_work_state.py tests/test_agent_tool_loop.py tests/test_external_turn.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py tests/test_agent_resume_command.py -q
pytest -q
git diff --check
```

Manual acceptance required before closing implementation; status on 2026-06-14: not yet run/recorded.

- PowerShell and cmd.exe native PTY `/compact` with restored context.
- `/resume` from v3 checkpoint.
- Real or controlled QQchat external conversation compact continuation.
- Transcript inspection for checkpoint parent/hash chain and no secret leakage.
