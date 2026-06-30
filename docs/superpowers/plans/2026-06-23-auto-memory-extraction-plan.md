# Auto Memory Extraction Implementation Plan

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工交互验收未执行/未记录。
日期：2026-06-23

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build local REPL auto memory extraction with stable memory paths, bounded manifest scanning, controlled after-turn hooks, and Claude-style relevant memory recall.

**Architecture:** Keep Xcode's prompt-driven file memory model and add small focused modules around it: project-key path helper, manifest scanner, memory writer/extractor, after-turn hook runner, and relevant-memory prefetch/recall. Do not introduce public memory CRUD tools, user script hooks, skill hook execution, vector DB, or global `asyncio`.

**Tech Stack:** Python 3.10+, pytest, existing synchronous `AgentRuntime`, `MemoryManager`, `SessionStore`, `LLMClient`, `PermissionManager`, `ThreadPoolExecutor`.

---

## Parent Spec

- `docs/superpowers/specs/2026-06-23-auto-memory-extraction-design.md`

## File Structure

- Create: `src/xcode_cli/core/project_key.py`
  - Shared stable project-key helper used by `SessionStore` and `MemoryManager`.
- Modify: `src/xcode_cli/core/session.py`
  - Delegate `SessionStore.project_key()` to shared helper.
- Modify: `src/xcode_cli/core/memory.py`
  - Use stable project key for auto memory directory, expose legacy directory helpers, keep index fallback.
- Create: `src/xcode_cli/core/memory_manifest.py`
  - Bounded frontmatter scanner and `MemoryManifestEntry`.
- Create: `src/xcode_cli/core/memory_writer.py`
  - Safe memory-scoped writer, slug sanitization, duplicate handling, secret redaction, `MEMORY.md` index updates.
- Create: `src/xcode_cli/core/memory_extraction.py`
  - No-tool extraction side query parsing and write orchestration.
- Create: `src/xcode_cli/core/hooks.py`
  - Internal-only `AfterTurnHookRunner` and `AfterTurnSuccessEvent`.
- Create: `src/xcode_cli/core/memory_recall.py`
  - Manifest selector side query, bounded file reading, session/tool-state dedupe, system reminder rendering.
- Modify: `src/xcode_cli/core/tooling/execution.py`
  - Track whether a memory-scoped write occurred during the active turn.
- Modify: `src/xcode_cli/core/agent.py`
  - Wire prefetch, relevant memory injection safe points, after-turn hook execution, and local REPL-only extraction.
- Modify: `src/xcode_cli/core/prompting.py`
  - Keep `MEMORY.md` index as常驻索引 and document dynamic relevant memory section separately if needed.
- Modify: `docs/current/ROADMAP.md`
  - Mark spec/plan written and point to this implementation plan.
- Modify after implementation only: `docs/current/ARCHITECTURE.md`, `docs/current/PROGRESS.md`, `docs/current/DEVNOTES.md`
  - Do not claim implementation before code and verification land.

## Task Order

| Task | Risk | File |
|------|------|------|
| 1 | P0 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-01-stable-memory-paths.md` |
| 2 | P0/P1 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-02-memory-manifest-scanner.md` |
| 3 | P0 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-03-memory-writer.md` |
| 4 | P0/P1 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-04-after-turn-hook.md` |
| 5 | P0/P1 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-05-memory-extraction-service.md` |
| 6 | P1 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-06-relevant-memory-recall.md` |
| 7 | P1/P2 | `docs/superpowers/plans/2026-06-23-auto-memory-extraction/task-07-docs-and-verification.md` |

## Cross-task Validation

Run focused checks after each task, then run the full closeout matrix after Task 7:

```text
pytest tests/test_memory.py tests/test_prompting_memory.py -q
pytest tests/test_memory_manifest.py -q
pytest tests/test_memory_extraction.py -q
pytest tests/test_memory_recall.py -q
pytest tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q
pytest tests/test_external_turn.py tests/test_qqchat_service.py -q
python -m compileall -q src
pytest -q
git diff --check
```

Expected closeout:

- Stable memory path matches `SessionStore.project_key()` and does not collide for same leaf directory.
- Legacy `<cwd.name>/memory` remains readable but new writes go to stable project key.
- Manifest scanner never injects or scans `MEMORY.md` as a topic file.
- Local REPL successful assistant turns can trigger extraction; QQchat/external turns do not.
- Hook and extraction failures do not alter `_history`, transcript, or user-visible reply.
- Relevant memory recall uses no-tool side query, bounded reads, strict selector validation, and dedupe.
- No implementation claim is written to current docs until verification evidence exists.

## Closeout Evidence

- `pytest tests/test_memory.py tests/test_prompting_memory.py -q`：`46 passed in 2.03s`。
- `pytest tests/test_memory_manifest.py -q`：`4 passed in 1.59s`。
- `pytest tests/test_memory_extraction.py -q`：`8 passed in 0.47s`。
- `pytest tests/test_memory_recall.py -q`：`4 passed in 0.53s`。
- `pytest tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q`：`13 passed in 11.50s`。
- `pytest tests/test_external_turn.py tests/test_qqchat_service.py -q`：`26 passed in 0.62s`。
- `python -m compileall -q src`：退出码 0。
- `pytest -q`：`588 passed in 38.53s`。
- `git diff --check`：退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。
