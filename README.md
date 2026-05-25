# Xcode

> A terminal-native AI coding agent. Tools, sub-agents, plan mode, persistent memory, and an approval-first terminal workflow for local coding.

## Quick Start

```bash
pip install -e .
xcode
```

Configure an OpenAI-compatible provider:

```bash
xcode
/env set <your-api-key>
/env base-url <provider-base-url>
/env model <model-name>
```

Environment variables are also supported:

```bash
export XCODE_API_KEY=<key>
export XCODE_BASE_URL=<url>
export XCODE_MODEL=<model>
```

## Core Features

- 13 built-in tools: file read/write/edit, search, shell, sub-agent dispatch, task tracking, and plan mode.
- Streaming LLM output with tool calling through OpenAI-compatible APIs.
- Approval-first workflow for write/edit/shell tools, including diff preview before file changes.
- Inline approval menu with `Yes`, `No`, and `Yes, for this conversation`.
- Project/user/auto memory model based on XCODE.md and indexed memory files.
- Context token estimation, configurable `max_tokens`, and automatic compression.
- Slash commands for environment config, context inspection, memory status, plan mode, and skills.

## Documentation

The root `README.md` is the single documentation index. Detailed current project documents live in `docs/current/`:

| Document | Answers | Boundary |
|----------|---------|----------|
| `docs/current/PROGRESS.md` | How the project reached its current state | Phase/Batch history, review conclusions, acceptance state, current next steps |
| `docs/current/ARCHITECTURE.md` | How the system works now | Current component relationships, data flows, memory/context/session/approval models |
| `docs/current/ROADMAP.md` | What remains to build | Future goals, unfinished capabilities, implementation sketches, acceptance ideas |
| `docs/current/DEVNOTES.md` | Why decisions were made and where risks are | Known issues, design decisions, compatibility limits, validation risks |

Recommended reading order:

1. `docs/current/PROGRESS.md`
2. `docs/current/ARCHITECTURE.md`
3. `docs/current/ROADMAP.md`
4. `docs/current/DEVNOTES.md`

Root-level `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `DEVNOTES.md`, and `日期计划.md` are compatibility entrypoints. Old root documents were archived to `docs/old/2026-05-25-before-docs-restructure/`.

`日期计划.md` is now a journal rather than a primary project document. The current journal copy is `docs/journal/2026-05-25-日期计划.md`.

## Requirements

- Python >= 3.10
- Windows is the primary target
- Linux/macOS are partial targets; ripgrep bootstrap is currently Windows-focused

## License

MIT
