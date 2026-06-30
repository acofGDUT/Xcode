# Auto Memory Extraction v2 Claude-like Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Status: Code implementation and automated regression are complete as of 2026-06-24; PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded. Auto memory recall v2 remains unimplemented and out of scope for this plan.

**Goal:** Upgrade auto memory extraction from v1 no-tool JSON classification to a Claude-like, memory-only background extraction subagent with v2 topic format, policy guards, single-flight scheduling, and bounded audit.

**Architecture:** Keep v1's stable auto memory directory, after-turn event, manifest scanner, and memory writer as the base. Replace the synchronous `MemoryExtractionService.after_turn()` path with a background runner that invokes a restricted memory extraction subagent using only memory-scoped tools and v2 memory rules. Do not change the main REPL loop to global `asyncio`, do not execute user/script/skill hooks, and do not implement recall v2 in this plan.

**Tech Stack:** Python 3.10+, pytest, existing synchronous `AgentRuntime`, `LLMClient`, `ToolDef`/`ToolRegistry`, `MemoryManager`, `MemoryWriter`, `MemoryManifestScanner`, `PermissionManager`, `ThreadPoolExecutor`.

---

## Evidence and References

- Parent spec: [2026-06-23-auto-memory-extraction-v2-claude-like-design.md](../specs/2026-06-23-auto-memory-extraction-v2-claude-like-design.md).
- Prior v1 plan: [2026-06-23-auto-memory-extraction-plan.md](2026-06-23-auto-memory-extraction-plan.md).
- Prior v1 task directory: [2026-06-23-auto-memory-extraction/](2026-06-23-auto-memory-extraction/).
- Related but separate follow-up spec: [2026-06-23-auto-memory-recall-v2-claude-like-design.md](../specs/2026-06-23-auto-memory-recall-v2-claude-like-design.md).
- Historical docs entry before implementation: `docs/current/ROADMAP.md` listed `Auto memory extraction v2` as spec/plan written and not implemented. Closeout moved implementation evidence to `PROGRESS.md`; recall v2 remains in `ROADMAP.md`.

## Scope

This plan implements **Auto Memory Extraction v2** only.

It intentionally does not implement Auto Memory Recall v2. Recall v2 remains a separate roadmap item that should run after extraction v2 stabilizes v2 topic frontmatter and memory quality.

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/xcode_cli/core/prompting.py` | Modify | Upgrade main agent auto memory prompt examples from v1 `metadata.type` to v2 top-level `type` and `Evidence:` rules |
| `src/xcode_cli/core/memory_writer.py` | Modify | Write v2 frontmatter, validate `Evidence:`, reject generic memories, and keep `MEMORY.md` relative links |
| `src/xcode_cli/core/memory_manifest.py` | Modify | Default scanner to v2 top-level `type`; skip old `metadata.type` topics with warnings |
| `src/xcode_cli/core/memory_extraction_policy.py` | Create | Shared guard functions for v2 topic validation, generic-slug rejection, task-summary rejection, and secret-like rejection |
| `src/xcode_cli/core/memory_tools.py` | Create | Memory-only tool registry for extraction subagent: memory-scoped read/write/edit and optional memory-scoped glob |
| `src/xcode_cli/core/memory_extraction_subagent.py` | Create | Five-turn memory-only tool loop, extraction prompt builder, manifest injection, saved topic audit |
| `src/xcode_cli/core/memory_extraction_runner.py` | Create | Single-flight background runner with latest pending event, trailing run, timeout, shutdown, and last result |
| `src/xcode_cli/core/memory_extraction.py` | Modify | Turn v1 service into compatibility facade or shared result holder; remove synchronous no-tool JSON path from runtime wiring |
| `src/xcode_cli/core/agent.py` | Modify | Hook submits to runner without waiting; `run_chat()` shuts runner down |
| `tests/test_prompting_memory_v2.py` | Create | Prompt v2 frontmatter and quality-rule regression |
| `tests/test_memory_manifest_v2.py` | Create | V2 manifest and legacy-format skip regression |
| `tests/test_memory_extraction_policy.py` | Create | V2 topic policy guard regression |
| `tests/test_memory_extraction_subagent.py` | Create/Modify | Memory sandbox and extraction subagent loop regression |
| `tests/test_memory_extraction_runner.py` | Create | Single-flight, latest pending, trailing run, shutdown regression |
| `tests/test_agent_memory_extraction_v2.py` | Create | Agent hook integration and non-blocking runner submission regression |
| `docs/current/ROADMAP.md` | Modify now | Record spec/plan written and v2 still unimplemented |
| `docs/current/ARCHITECTURE.md` | Modify after implementation | Sync current extraction v2 architecture only after verified code lands |
| `docs/current/PROGRESS.md` | Modify after implementation | Record real implementation and verification evidence |
| `docs/current/DEVNOTES.md` | Modify after implementation | Record v2 review boundaries and remaining risks |

## Task Files

- [Task 1: V2 format, policy, and prompt](2026-06-23-auto-memory-extraction-v2-claude-like/task-01-v2-format-policy-and-prompt.md)
- [Task 2: V2 manifest scanner](2026-06-23-auto-memory-extraction-v2-claude-like/task-02-v2-manifest-scanner.md)
- [Task 3: Memory tool sandbox](2026-06-23-auto-memory-extraction-v2-claude-like/task-03-memory-tool-sandbox.md)
- [Task 4: Extraction subagent loop](2026-06-23-auto-memory-extraction-v2-claude-like/task-04-extraction-subagent-loop.md)
- [Task 5: Background runner](2026-06-23-auto-memory-extraction-v2-claude-like/task-05-background-runner.md)
- [Task 6: Agent integration](2026-06-23-auto-memory-extraction-v2-claude-like/task-06-agent-integration.md)
- [Task 7: Docs and verification](2026-06-23-auto-memory-extraction-v2-claude-like/task-07-docs-and-verification.md)

## Execution Constraints

- Execute one task at a time; stop for Codex review after each task.
- Code tasks must follow TDD-core: write failing regression tests first, then minimal implementation, then refactor.
- Do not implement recall v2 in this plan.
- Do not reintroduce v1 `metadata.type` for new topic writes.
- Do not execute user script hooks or skill frontmatter hooks.
- Do not expose MCP tools, `dispatch_agent`, unrestricted project reads, unrestricted shell, git, tests, build commands, or non-memory writes to the extraction subagent.
- Do not change the main REPL loop to global `asyncio`; background extraction must provide a synchronous submission boundary, timeout, cancellation/shutdown behavior, and audit state.
- Do not let extraction failure modify the main assistant reply, `_history`, or session transcript.
- Do not allow explicit `deny write_file` to be bypassed by memory-scoped background writes.
- Do not let QQchat/external/headless turns trigger long-term memory extraction.
- Keep terminal UI output `markup=False` where model/provider text may contain brackets or markup-like payloads.
- Keep `ARCHITECTURE.md` in current-fact mode: update it only after implementation and verification.

## Recommended Final Verification

```powershell
pytest tests/test_prompting_memory_v2.py -q
pytest tests/test_memory_manifest_v2.py -q
pytest tests/test_memory_extraction_policy.py -q
pytest tests/test_memory_extraction_subagent.py -q
pytest tests/test_memory_extraction_runner.py -q
pytest tests/test_agent_memory_extraction_v2.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q
pytest tests/test_memory_extraction.py tests/test_memory_manifest.py tests/test_memory.py -q
python -m compileall -q src
pytest -q
git diff --check
```

Manual acceptance records required if this is claimed beyond automated v2 completion:

- PowerShell/cmd.exe: run local REPL turns that trigger after-turn extraction and confirm prompt input is not blocked by background memory work.
- Transcript inspection: confirm extraction failure or timeout does not alter the assistant reply, `_history`, or session transcript.
- Memory directory inspection: confirm saved topics use v2 frontmatter and `MEMORY.md` uses only relative links.
- External entry inspection: confirm QQchat/external/headless turns still do not trigger long-term memory extraction.
