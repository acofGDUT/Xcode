# Auto Memory Extraction v2 Claude-like Design

> Status: Code implementation and automated regression are complete as of 2026-06-24. PowerShell/cmd.exe native PTY manual acceptance has not been executed or recorded. Auto memory recall v2 remains unimplemented.
> Date: 2026-06-24

## Background

Auto memory v1 already had a stable project key, manifest scanner, after-turn hook, MemoryExtractionService, MemoryWriter, and relevant memory recall. Its extraction path was still a synchronous no-tool JSON side query: the model classified possible memories and a writer persisted them. That was useful, but it was not Claude-like: it had no restricted tool loop, could not inspect existing topic memory through memory-scoped tools, and had weak protection against generic task summaries.

Extraction v2 replaces that path with a restricted background memory extraction subagent. The subagent inherits the main memory rules, receives the current turn and bounded manifest context, and can only use memory-scoped read/write/edit/glob tools. It writes through the same MemoryWriter and policy guard as any other memory write.

This spec covers extraction v2 only. Relevant memory recall v2 is a separate follow-up in `2026-06-23-auto-memory-recall-v2-claude-like-design.md`.

## Goals

- Replace the v1 no-tool JSON extraction path with a Claude-like memory extraction subagent.
- Make v2 frontmatter the only format for new topic writes: `name`, `description`, and top-level `type`.
- Require an `Evidence:` section in topic body content.
- Reject missing evidence, generic slugs, task summaries, and secret-like content before writing.
- Expose only memory-scoped tools to the subagent.
- Keep after-turn extraction non-blocking for the main assistant reply, `_history`, and session transcript.
- Provide single-flight scheduling with latest pending event, trailing run, timeout, shutdown, and last-result audit state.
- Keep QQchat, external, and headless turns out of long-term memory extraction.

## Non-goals

- No public memory CRUD tools such as `memory_save`, `memory_list`, `memory_get`, or `memory_delete`.
- No user script hooks or skill frontmatter hook execution.
- No embeddings, vector database, indexing service, or daemon.
- No global async conversion of AgentRuntime, LLMClient.complete, ToolCallExecutor.execute, or the REPL loop.
- No automatic migration of legacy `metadata.type` topic files.
- No implementation of recall v2 in this plan.

## Architecture

```text
successful local REPL turn
        |
        v
AfterTurnHookRunner
        |
        v
MemoryExtractionRunner.submit(event)
        |
        v
single background worker
        |
        v
MemoryExtractionSubagent
        |
        +-- MemoryManifestScanner
        +-- memory-only ToolRegistry
        +-- MemoryWriter + policy guard
```

AgentRuntime submits an AfterTurnSuccessEvent only after a successful local REPL assistant turn. Submission does not wait for another LLM call, does not write transcript messages, and does not modify main history. run_chat shuts the runner down in its finally path with a bounded wait.

MemoryExtractionRunner is the synchronous boundary around background extraction. Only one extraction runs at a time. If another event arrives while one is active, the runner keeps only the latest pending event. When the active run completes, the latest pending event is executed as a trailing run.

MemoryExtractionSubagent uses the configured LLM client, but its tool schema contains only memory-only tools. It can run at most five model turns and save at most three topics in one extraction event.

## V2 Topic Format

New topic files must use this shape:

```markdown
---
name: review-findings-first
description: User prefers code review responses to lead with findings.
type: feedback
---

Rule: Lead review output with findings before summary.
Evidence: User said: "review output should lead with findings."
How to apply: In review mode, list issues first, ordered by severity.
```

Rules:

- `type` must be one of `user`, `feedback`, `project`, or `reference`.
- `metadata.type` is legacy and must not be used for new writes.
- `Evidence:` is required and must be specific.
- Generic slugs such as `memory`, `notes`, `summary`, or `task-complete` are rejected.
- Secrets such as API keys, tokens, authorization headers, passwords, private keys, and QQ bot secrets are rejected or redacted before write.
- Task completion logs, test pass summaries, and modified-file lists are not long-term memory unless they contain a stable user preference or project fact.

## Manifest Behavior

MemoryManifestScanner scans v2 topic files under the stable auto memory directory. `MEMORY.md` is an index and is not treated as a topic. Legacy `metadata.type` topic files produce skip warnings. Stable topic files take precedence over legacy fallback files.

The subagent receives bounded manifest context so it can update or skip existing topics instead of creating duplicates.

## Memory Tool Sandbox

Allowed tools:

- `read_file`: memory scope only.
- `write_file`: memory scope only, routed through MemoryWriter and policy guard.
- `edit_file`: memory scope only, and only after the file has been read by the subagent.
- `glob`: memory scope only.

Forbidden capabilities include shell, git, MCP, dispatch_agent, unrestricted project reads, unrestricted writes, task tools, skill invocation, hooks, and network tools.

Explicit `deny write_file` remains stronger than memory-scoped background writes.

## Prompt Contract

The main prompt and extraction subagent prompt must both say:

- Save only durable preferences, facts, constraints, or rules.
- Do not save ordinary task progress, test results, temporary plans, or generic completion summaries.
- Include concrete evidence.
- Do not save secrets.
- Use the manifest to avoid duplicate topics.

## Scheduling And Failure Semantics

- Extraction is submitted only after successful local REPL assistant turns.
- LLM errors, missing API key, missing package, `No response.`, interrupted turns, and unsuccessful assistant turns do not trigger extraction.
- Extraction failure is recorded as a warning or last result only; it does not change the main reply, `_history`, session transcript, or UI output.
- Shutdown has a bounded wait and must not hang process exit.

## Tests

Required coverage:

- Prompt v2 frontmatter and Evidence rules.
- Policy guard for missing evidence, generic slug, task summary, and secret-like content.
- Manifest scanner reads top-level v2 `type` and skips legacy `metadata.type`.
- Memory-only sandbox blocks non-memory reads/writes and disallowed tools.
- Subagent turn limit and three-topic save cap.
- Runner single-flight, latest pending, trailing run, shutdown, and last result.
- Agent hook integration and non-blocking submission.
- QQchat/external/headless turn isolation.
- Existing v1 memory baseline tests continue to pass.

## Acceptance Evidence

Verified on 2026-06-24:

- `pytest tests/test_prompting_memory_v2.py -q`: `2 passed in 0.33s`
- `pytest tests/test_memory_manifest_v2.py -q`: `4 passed in 0.23s`
- `pytest tests/test_memory_extraction_policy.py -q`: `5 passed in 0.20s`
- `pytest tests/test_memory_extraction_subagent.py -q`: `8 passed in 0.46s`
- `pytest tests/test_memory_extraction_runner.py -q`: `4 passed in 0.22s`
- `pytest tests/test_agent_memory_extraction_v2.py tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q`: `16 passed in 2.49s`
- `pytest tests/test_memory_extraction.py tests/test_memory_manifest.py tests/test_memory.py -q`: `50 passed in 3.49s`
- `python -m compileall -q src`: exit code 0
- `pytest -q`: `614 passed in 32.39s`
- `git diff --check`: exit code 0, with Windows LF/CRLF line-ending warnings only

Not executed: PowerShell/cmd.exe native PTY manual interactive acceptance.
