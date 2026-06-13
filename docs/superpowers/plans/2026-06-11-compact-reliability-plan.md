# Compact Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Status: Tasks 1-7 are code-complete with automated regression and per-task review. Task 8 docs, automated verification, and PowerShell/cmd.exe native PTY `/compact` handler acceptance are complete. Real QQ platform acceptance is delegated to the user per user request on 2026-06-12 and does not block this plan closeout.

**Goal:** 修复 QQchat/外部入口中 `No response.` 被当作正常回复写入历史的问题，并把 Xcode 的 compaction 从固定尾部裁剪升级为可校验、pair-safe、可观测、可恢复的上下文重写流程。

**Architecture:** 保持现有同步 `AgentRuntime` 主循环。先在 `ExternalTurnRunner` 建立空响应错误边界；再在 `LLMClient` 支持 no-tool summary request；随后升级 `ContextManager.compress()` 为 structured summary + quality gate + compact boundary + pair-safe tail；最后添加 micro-compact、QQchat fallback、metadata 和文档验收。所有变更必须保持 tool exception 不打崩主循环，并保护 OpenAI-compatible message 顺序。

**Tech Stack:** Python 3.10+、pytest、现有 Typer/Rich/prompt_toolkit、现有 OpenAI-compatible `LLMClient`、现有 `SessionStore`/`ConversationCompactor`/`ExternalTurnRunner`。不引入 asyncio，不引入 embedding/vector DB。

---

## Evidence and References

- Failure transcript: `C:\Users\LONG\.xcode\projects\D--MusicChatAgent\sessions\4f6d33a4-d1b1-4a90-9778-3c027910f844.jsonl`.
- Spec: [2026-06-11-compact-reliability-design.md](../specs/2026-06-11-compact-reliability-design.md).
- Claude Code official docs:
  - [`/compact` command](https://code.claude.com/docs/en/commands)
  - [Context window and compaction survivors](https://code.claude.com/docs/en/context-window)
  - [Cost/context management practices](https://code.claude.com/docs/en/costs)

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/xcode_cli/core/external_turn.py` | Modify | Treat empty/no-response output as LLM error for external turns |
| `src/xcode_cli/qqchat/service.py` | Modify | Safe fallback handling for external-turn errors |
| `src/xcode_cli/core/llm.py` | Modify | Omit tools/tool_choice when no tool schemas are present |
| `src/xcode_cli/core/context.py` | Modify | Structured summary prompt, summary quality gate, pair-safe tail, micro-compact helpers |
| `src/xcode_cli/core/conversation/compaction.py` | Modify | Preserve history on rejected compaction and write richer checkpoint metadata |
| `src/xcode_cli/core/session_resume.py` | Modify if needed | Resume `xcode.v2` checkpoint and keep pair safety |
| `src/xcode_cli/core/agent.py` | Modify | Integrate new compaction result metadata and empty-response semantics |
| `tests/test_external_turn.py` | Modify | No-response external error boundary |
| `tests/test_qqchat_service.py` | Modify | QQ fallback and no polluted success history |
| `tests/test_llm.py` | Modify | No-tool request behavior |
| `tests/test_context.py` | Modify | Summary validation, pair-safe compaction, latest-user retention, micro-compact |
| `tests/test_compaction.py` | Modify | Rejected compaction does not replace history |
| `tests/test_session_resume.py` | Modify if needed | Resume from `xcode.v2` checkpoint |
| `docs/current/ROADMAP.md` | Modify after implementation | Record compact reliability status |
| `docs/current/DEVNOTES.md` | Modify after implementation | Record compaction invariants and QQchat empty-response boundary |
| `docs/current/PROGRESS.md` | Modify after implementation | Record completed tasks and evidence |
| `docs/current/ARCHITECTURE.md` | Modify after implementation | Sync current compact architecture |

## Task Files

- [Task 1: No response external error boundary](2026-06-11-compact-reliability/task-01-no-response-error-boundary.md)
- [Task 2: Tool-free summary LLM request](2026-06-11-compact-reliability/task-02-tool-free-summary-request.md)
- [Task 3: Summary prompt and quality gate](2026-06-11-compact-reliability/task-03-summary-quality-gate.md)
- [Task 4: Pair-safe compact tail](2026-06-11-compact-reliability/task-04-pair-safe-compact-tail.md)
- [Task 5: Compact boundary and restoration metadata](2026-06-11-compact-reliability/task-05-boundary-restoration-metadata.md)
- [Task 6: Tool result micro-compact](2026-06-11-compact-reliability/task-06-tool-result-microcompact.md)
- [Task 7: QQchat compact resilience and heartbeat noise](2026-06-11-compact-reliability/task-07-qqchat-compact-resilience.md)
- [Task 8: Docs and final verification](2026-06-11-compact-reliability/task-08-docs-final-verification.md)

## Execution Constraints

- Execute one task at a time; stop for Codex review after each task.
- Code tasks must follow TDD-core: write failing regression tests first, then minimal implementation, then refactor.
- Do not let summary failure replace the active history.
- Do not persist `No response.` as a normal assistant message for QQchat/external turns.
- Do not break OpenAI-compatible `assistant.tool_calls` / `tool` message pairing.
- Do not introduce embeddings, vector DB, or asyncio.
- Do not change project files outside the task scope.
- Do not weaken tool permissions or external-entry tool scopes.
- Keep terminal UI output `markup=False` where model/provider text may contain brackets or markup-like payloads.

## Recommended Final Verification

```powershell
python -m compileall -q src
pytest tests/test_external_turn.py tests/test_qqchat_service.py tests/test_llm.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q
pytest -q
git diff --check
```

Manual acceptance records required:

- PowerShell/cmd.exe: run a long tool-heavy session and trigger `/compact`; inspect JSONL for `summary_format=xcode.v2`.
- QQchat: send messages after a compact-triggering turn; confirm no `No response.` assistant message is persisted.
- Transcript inspection: confirm no orphan `tool` messages in compacted model history.
