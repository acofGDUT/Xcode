# Compact Reliability Redesign

> Date: 2026-06-11
> Status: Implemented by code and automated regression on 2026-06-12; PowerShell/cmd.exe native PTY `/compact` handler acceptance passed; real QQ platform acceptance is owned by the user and not recorded here.
> Risk layer: P0/P1. This work touches context compaction, OpenAI-compatible message validity, QQchat external turns, session persistence, and long-running agent recovery.

## Background

This document started as the 2026-06-11 design spec and now also records the implemented scope. At the time of the failure, Xcode implemented compaction as a lightweight history rewrite in `ContextManager.compress()`:

```text
first user message
system checkpoint summary
last 8 messages
```

That was enough for early `/compact` and `/resume` support, but it failed under long QQchat-driven work sessions with many tool calls and large tool outputs.

Observed failure session:

```text
C:\Users\LONG\.xcode\projects\D--MusicChatAgent\sessions\4f6d33a4-d1b1-4a90-9778-3c027910f844.jsonl
```

Important evidence from that session:

- Line 92: first `compaction_checkpoint` summary starts with `<tool_call> ... </tool_call>` instead of a natural-language summary.
- Lines 112, 125, 138: repeated compactions reduce the in-memory history back to 10 messages.
- Line 138: `source_token_estimate` reaches `797558` despite only 21 source messages, because retained summaries and tool results are very large.
- Lines 139, 141, 143, 145, 147: `No response.` is persisted as normal assistant output and then repeatedly pollutes later QQchat turns.

The immediate user-visible symptom is:

```text
QQ receives user messages, Xcode processes them, but replies "No response."
```

The gateway heartbeat warning is a separate connection-lifecycle noise issue. It is not the primary cause of the empty model reply.

## External References

Public Claude Code documentation confirms these high-level behaviors:

- `/compact` frees context by summarizing the conversation so far and accepts optional focus instructions: [Claude Code commands](https://code.claude.com/docs/en/commands).
- Claude Code auto-compacts as the context approaches the limit, and `/compact` replaces conversation history with a structured summary: [Explore the context window](https://code.claude.com/docs/en/context-window).
- After compaction, root instructions and auto memory are re-injected, while path-scoped rules reload only when matching files are read again; invoked skill bodies are re-injected with token caps: [Explore the context window](https://code.claude.com/docs/en/context-window).
- Claude Code recommends proactive context management, custom compaction instructions, moving specialized instructions to skills, and delegating verbose work to subagents: [Manage costs effectively](https://code.claude.com/docs/en/costs).

The user also provided a source-level Claude Code analysis. Treat it as implementation inspiration, not as an official contract. The relevant design ideas are:

- compaction is context rewriting, not byte compression;
- summary generation should use a dedicated prompt and no tools;
- the compacted context should have a boundary marker and summary message;
- startup/project context, invoked skills, and recent file context should be restored after compaction;
- old tool results can be micro-compacted separately;
- tail retention must not break `tool_use` / `tool_result` pairs.

## Historical Xcode Failure Chain

The failure chain observed before the 2026-06-12 fix was:

```text
QQchat ExternalTurnRunner appends user message to state.history
  -> AgentRuntime._run_llm_loop sees token budget pressure
  -> ConversationCompactor.compact_history calls ContextManager.compress
  -> summary LLM returns bad or tool-call-like text
  -> summary is accepted without quality gates
  -> history is rewritten to first user + system checkpoint + last 8 messages
  -> model returns empty content and no tool calls
  -> _run_llm_loop returns "No response."
  -> ExternalTurnRunner treats "No response." as normal assistant text
  -> "No response." is persisted and appended to in-memory history
  -> later QQ turns inherit polluted context and repeat the failure
```

## Goals

1. Stop `No response.` from entering QQchat/external history as normal assistant output.
2. Make summary generation explicitly tool-free and robust for OpenAI-compatible providers.
3. Reject or recover from bad summaries, including `<tool_call>` text, empty summaries, JSON tool-call-looking payloads, and obvious provider/protocol leakage.
4. Preserve valid OpenAI-compatible message sequences after compaction, especially assistant `tool_calls` and matching `tool` messages.
5. Replace the old fixed `first user + checkpoint + 8 tail` strategy with a safer compact boundary model.
6. Add micro-compaction for old tool results so giant outputs do not force repeated full-history summaries.
7. Make QQchat/external turns resilient to compact failures and empty LLM output.
8. Add automated regression coverage based on the real failure shape, plus manual PowerShell/cmd.exe acceptance notes where needed.

## Non-Goals

- No embeddings, vector database, semantic retrieval, or long-term memory redesign.
- No global async rewrite.
- No destructive migration of existing project/session JSONL files. The redesign may append compatible transcript messages, such as a compact boundary `message(system)`, and add backward-compatible metadata fields to `compaction_checkpoint` events.
- No new network search or web fetch tools as part of this compact work.
- No attempt to clone Claude Code internals exactly. Xcode should adapt the pattern to its own Python CLI and OpenAI-compatible schema.

## Implemented Architecture

### 1. External Turn Empty Response Boundary

`ExternalTurnRunner` should classify these as LLM failures:

```text
[v0] LLM request failed: ...
[v0] Missing API key ...
[v0] openai package not installed ...
No response.
```

For external entrypoints, an empty response must not be appended as an assistant message. The runner should return `ExternalTurnResult(error=...)` so QQchat can decide what safe fallback to send.

The local terminal may still render a user-visible fallback, but the fallback should not pollute model history.

### 2. Tool-Free Summary Request

`LLMClient.complete()` should not pass `tools=[]` with `tool_choice="auto"` when no tools are available. For summarization calls:

```text
tool_schemas=[]
```

must produce a request with no `tools` field, or otherwise an explicit no-tool mode if the OpenAI-compatible provider supports it.

This avoids provider-specific behavior around empty tool arrays.

### 3. Structured Summary Prompt and Quality Gate

Summary prompts should ask for a structured summary with stable headings:

```text
Summary:
- User intent and active task
- Decisions and constraints
- Files and code changes
- Tool results and errors
- Pending tasks
- Current state
- Next steps
- Recent user messages
```

The code should accept only the summary section. A summary must be rejected if it:

- is empty after stripping;
- starts with or contains `<tool_call>`;
- looks like raw JSON tool call payload;
- contains `tool_calls` / `function_call` protocol leakage as the dominant content;
- is below the dynamic minimum useful length: start at 80 characters, raise to 300 when `source_token_estimate > 10000`, 600 when `source_token_estimate > 30000`, and 1000 when `source_token_estimate > 80000`;
- repeats only fallback text such as `(middle conversation compressed)`;
- exceeds `max_summary_chars` before controlled truncation.

Rejected summaries must not overwrite the last good checkpoint or the active in-memory history. On summary rejection, `ContextManager.compress()` returns a result with no checkpoint message; `ConversationCompactor.compact_history()` returns `None`; callers must not replace `history[:]` or write a `compaction_checkpoint`. A future implementation may append a separate `compaction_failed` audit/status event, but it must not feed a failed summary back into model history.

### 4. Compact Boundary Message

Add a recognizable boundary message before the summary:

```text
role=system
content="Compact boundary: earlier conversation has been summarized below. Do not treat omitted tool results as pending tool calls."
```

Then add the checkpoint summary as a separate system message. This makes the rewrite explicit for the model and for session inspection.

### 5. Pair-Safe Tail Selection

Tail selection must preserve OpenAI-compatible tool message invariants:

```text
assistant(tool_calls=[id1, id2])
tool(tool_call_id=id1)
tool(tool_call_id=id2)
```

Rules:

- Never keep a `tool` message without the preceding assistant message that declared the matching tool call.
- Never keep an assistant `tool_calls` entry without all corresponding tool messages.
- If a tool pair cannot fit, drop the whole pair from the tail and summarize it.
- Prefer retaining the latest user message even when tool-heavy tail is trimmed.
- If trimming removes tool results, the summary must mention the removal at a semantic level.

This can reuse the orphan-cleanup logic already present in `SessionResumeBuilder`.

### 6. Micro-Compact Old Tool Results

Before full compaction, old and large tool results should be reduced:

```text
[Old tool result content cleared: read_file D:\path\file.py, original ~12345 chars]
```

Applicable tools:

- `read_file`
- `grep`
- `glob`
- `run_shell`
- `write_file`
- `edit_file`
- `task_*`
- `skill`
- future `web_fetch` / `web_search`
- MCP tools, using registered tool name and result length

Rules:

- Do not micro-compact recent tool results inside the protected tail.
- Do not micro-compact tool outputs that are the only evidence for the immediately active task unless they are also summarized.
- Preserve tool call IDs and message roles so protocol order remains valid.
- Micro-compact before deciding whether full compaction is still necessary.

### 7. Context Restoration

Implemented in this round:

- compact boundary message;
- structured summary message;
- pair-safe protected tail;
- latest user retention where possible;
- external QQchat turn scope remains outside the compacted model history through `ExternalTurnRunner` state and tool scope handling;
- project root and memory paths continue to come from the normal system prompt construction path, not from a new compact payload.

Future restoration candidates, not part of the 2026-06-12 implemented acceptance scope:

- invoked skills, capped by tokens, if skill invocation metadata exists;
- recent read files, capped by count and content length, if read-file audit data exists;
- active plan summary if plan mode is active;
- session-start hooks, deferred tool listings, or MCP instruction deltas if Xcode later records that metadata.

These future candidates require separate tests and should not be treated as missing acceptance for the compact reliability fix.

### 8. Observability

Compaction should emit inspectable metadata:

```json
{
  "type": "compaction_checkpoint",
  "summary_format": "xcode.v2",
  "source_message_count": 90,
  "remaining_message_count": 14,
  "micro_compacted_tool_results": 7,
  "rejected_summary": false,
  "protected_tail_messages": 10
}
```

For rejected summaries, the implemented behavior is to return no compact outcome and leave in-memory history unchanged. A future `compaction_failed` event may be added for observability, but rejected summaries must still not replace in-memory history or produce a `compaction_checkpoint`.

## Risk Layering

P0:

- `No response.` must not pollute external histories.
- Summary failures must not overwrite good history.
- Compacted messages must remain valid for OpenAI-compatible tool calling.
- Tool exceptions and malformed provider output must not crash the agent loop.

P1:

- Better summary prompt and structured headings.
- Micro-compaction for old tool results.
- Compact metadata and `/context` visibility improvements.
- QQchat fallback copy and last_error behavior.

P2:

- Documentation, progress notes, and tuning constants.
- Cosmetic output around compact progress.

## Required Tests

Focused tests:

- `tests/test_external_turn.py`: `No response.` returns `ExternalTurnResult(error=...)` and is not appended as assistant history.
- `tests/test_llm.py`: `tool_schemas=[]` omits tools/tool_choice or enters explicit no-tool mode.
- `tests/test_context.py`: rejects `<tool_call>` summary and does not produce checkpoint.
- `tests/test_context.py`: pair-safe tail keeps assistant/tool messages together.
- `tests/test_context.py`: latest user message survives compaction.
- `tests/test_context.py`: old large tool results are micro-compacted outside the protected tail, recent protected-tail tool results are preserved, and metadata reports the count.
- `tests/test_compaction.py`: rejected summaries stop live progress and preserve original history.
- `tests/test_qqchat_service.py`: QQchat sends safe fallback for empty model output without recording it as successful handled assistant text.
- `tests/test_session_resume.py`: `xcode.v2` checkpoint remains resumable.

Verification commands used for implemented scope:

```powershell
python -m compileall -q src
pytest tests/test_external_turn.py tests/test_qqchat_service.py tests/test_qqchat_gateway.py tests/test_llm.py tests/test_context.py tests/test_compaction.py tests/test_session_resume.py -q
pytest -q
git diff --check
```

Recorded 2026-06-12 evidence:

- `python -m compileall -q src`: exit code 0.
- Focused compact/QQchat regression suite: `95 passed`.
- Full test suite: `533 passed`.
- `git diff --check`: exit code 0, with only Windows LF/CRLF warnings.
- PowerShell and cmd.exe native PTY `/compact` handler acceptance passed through slash dispatcher; both produced `summary_format=xcode.v2`, boundary message, no orphan `tool` message, and no summary request `tools` / `tool_choice`.

Manual acceptance still outside this spec:

- Real QQ platform single-chat and group-at regression. The user explicitly took over real QQ testing on 2026-06-12.
