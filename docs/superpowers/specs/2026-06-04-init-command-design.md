# `/init` Prompt Command Design

## Background

Xcode already has project memory (`XCODE.md`), slash commands, tool calling, plan mode, and approval-first file editing. What is missing is a first-run command that helps future Xcode instances understand a repository quickly.

The first version of `/init` should follow the old Claude-style behavior: it is a prompt command. The command handler should not inspect the project or write files itself. It should return a fixed prompt, and the runtime should feed that prompt into the normal agent turn so the LLM can use existing read/search/write/edit tools.

## Goal

When the user enters `/init`, Xcode should start a normal agent turn whose user prompt asks the agent to analyze the current repository and create or improve `XCODE.md`.

The resulting `XCODE.md` is a repository-local guidance file for future Xcode instances.

## Non-Goals

- Do not implement a local scanner in the slash handler.
- Do not parse README, dependency files, or rule files in Python for this feature.
- Do not directly create or overwrite `XCODE.md` from the command handler.
- Do not introduce a new tool.
- Do not rename the target file to `AGENTS.md` in this first version.

## User Experience

The user types:

```text
/init
```

The runtime treats the command as if the user had typed the initialization prompt manually:

```text
Please analyze this codebase and create an XCODE.md file...
```

From that point onward, the normal agent loop runs:

1. The prompt is appended to session transcript and `_history` as a user message.
2. Xcode builds the normal system prompt.
3. The LLM decides which files to read or search.
4. Tool approvals behave exactly like an ordinary user task.
5. The agent creates or edits `XCODE.md`.
6. The agent briefly summarizes what it learned and which files it used as sources.

## Command Model

Add a prompt-command concept for thin commands that expand into user prompts.

Recommended shape:

```python
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SlashCommand:
    name: str
    kind: str
    description: str
    handler: Callable[[str], str]
```

First version only needs one kind:

```text
prompt
```

`/init` is registered as:

```python
commands["init"] = SlashCommand(
    name="init",
    kind="prompt",
    description="Initialize a new XCODE.md file with codebase documentation",
    handler=init_handler,
)
```

The command parser should pass any text after `/init` to `init_handler(args)`, even though the first version ignores args.

## Initialization Prompt

Use this prompt body, with product name changed to xcode and target file changed to `XCODE.md`:

```text
Please analyze this codebase and create an XCODE.md file, which will be given to future instances of xcode to operate in this repository.

What to add:
1. Commands that will be commonly used, such as how to build, lint, and run tests. Include the necessary commands to develop in this codebase, such as how to run a single test.
2. High-level code architecture and structure so that future instances can be productive more quickly. Focus on the "big picture" architecture that requires reading multiple files to understand.

Usage notes:
- If there's already an XCODE.md, suggest improvements to it.
- When you make the initial XCODE.md, do not repeat yourself and do not include obvious instructions like "Provide helpful error messages to users", "Write unit tests for all new utilities", "Never include sensitive information (API keys, tokens) in code or commits".
- Avoid listing every component or file structure that can be easily discovered.
- Don't include generic development practices.
- If there are existing AI coding instructions such as AGENTS.md, CLAUDE.md, .cursor/rules/, .cursorrules, .github/copilot-instructions.md, .windsurfrules, or .clinerules, make sure to include the important parts.
- If there is a README.md, make sure to include the important parts.
- Do not make up information such as "Common Development Tasks", "Tips for Development", "Support and Documentation" unless this is expressly included in other files that you read.
- Be sure to prefix the file with the following text:

```markdown
# XCODE.md

This file provides guidance to xcode when working with code in this repository.
```

After creating or updating XCODE.md, briefly summarize what you learned about the project and which files you used as sources.
```

## Runtime Integration

Current `run_chat()` treats all slash commands as side-effect commands and then returns to the prompt loop. `/init` needs a way to return an expanded user prompt to the regular turn path.

Recommended runtime behavior:

```text
raw input: /init
  -> _handle_slash_command returns INIT_PROMPT or None
  -> run_chat replaces user_input with INIT_PROMPT
  -> run_chat continues through the existing normal user-message path
```

This keeps session transcript, `_history`, runtime status, context compression, LLM error handling, plan mode system prompt handling, and assistant message persistence consistent with ordinary user tasks.

## Existing `XCODE.md`

The command handler must not check whether `XCODE.md` exists. That decision belongs to the agent after it reads the repository.

The prompt must instruct:

- If no `XCODE.md` exists, create it.
- If `XCODE.md` exists, suggest improvements and use edit-style updates.
- Do not directly overwrite existing content unless the agent has read it and has a clear reason.

## Relevant Source Files

| File | Responsibility |
|------|----------------|
| `src/xcode_cli/core/commands/slash.py` | Slash command list and prompt_toolkit completions. Add `/init` metadata and prompt command helpers here or in a sibling module. |
| `src/xcode_cli/core/agent.py` | REPL loop and slash command dispatch. Reuse ordinary user turn execution for prompt commands. |
| `src/xcode_cli/core/ui/shell.py` | Command suggestion rendering if `/help` output needs to include `/init`. |
| `tests/test_init_command.py` | New tests for prompt command registration and runtime handoff. |

## Test Layer

This feature is **P1 user-visible behavior** with one P0-adjacent concern: it must not accidentally bypass normal tool approval or session history paths.

Required tests:

- `/init` command is registered with description and completion.
- `init_handler("")` returns the expected prompt and includes `XCODE.md`, `AGENTS.md`, `CLAUDE.md`, README, and the required header.
- Runtime handling of `/init` appends the expanded prompt as a user message and calls `_run_llm_loop()` through the normal path.
- `/init` does not directly call file/search tools from the handler.

Manual acceptance:

- In a real project, typing `/init` starts an ordinary agent turn.
- If API key is missing, `/init` shows the same missing-key error as an ordinary prompt.
- When the LLM wants to write `XCODE.md`, existing approval behavior still applies.

## Documentation Updates

When implemented, update:

- `docs/current/PROGRESS.md`
- `docs/current/ARCHITECTURE.md`
- `docs/current/ROADMAP.md`
- `docs/current/DEVNOTES.md` if any behavior differs from this design.

## Acceptance Criteria

- `/help` and slash completion expose `/init`.
- `/init` uses the fixed prompt and does not perform local scanning.
- The expanded prompt is persisted to transcript and `_history` as a user message.
- The normal LLM/tool loop runs after `/init`.
- Existing approval, memory, session, and context behavior are unchanged.
- Tests pass for command registration, prompt contents, and runtime handoff.
