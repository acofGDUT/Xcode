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
| [docs/current/PROGRESS.md](docs/current/PROGRESS.md) | How the project reached its current state | Phase/Batch history, review conclusions, acceptance state, current next steps |
| [docs/current/ARCHITECTURE.md](docs/current/ARCHITECTURE.md) | How the system works now | Current component relationships, data flows, memory/context/session/approval models |
| [docs/current/ROADMAP.md](docs/current/ROADMAP.md) | What remains to build | Future goals, unfinished capabilities, implementation sketches, acceptance ideas |
| [docs/current/DEVNOTES.md](docs/current/DEVNOTES.md) | Why decisions were made and where risks are | Known issues, design decisions, compatibility limits, validation risks |

Recommended reading order:

1. `docs/current/PROGRESS.md`
2. `docs/current/ARCHITECTURE.md`
3. `docs/current/ROADMAP.md`
4. `docs/current/DEVNOTES.md`

Root-level `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `DEVNOTES.md`, and `日期计划.md` are compatibility entrypoints. Old root documents were archived to `docs/old/2026-05-25-before-docs-restructure/`.

`日期计划.md` is now a journal rather than a primary project document. The current journal copy is `docs/journal/2026-05-25-日期计划.md`.

## 中文文档导航

根目录 `README.md` 是当前唯一的文档索引，核心项目文档都在 `docs/current/`：

| 文档 | 说明 |
|------|------|
| [docs/current/PROGRESS.md](docs/current/PROGRESS.md) | 项目是怎么一步步推进到现在的，包含阶段历史、当前状态、阻塞和下一步 |
| [docs/current/ARCHITECTURE.md](docs/current/ARCHITECTURE.md) | 当前系统怎么工作，包含组件关系、数据流、memory/context/session/approval 模型 |
| [docs/current/ROADMAP.md](docs/current/ROADMAP.md) | 后续还要做什么，包含未完成能力、目标态和实现草案 |
| [docs/current/DEVNOTES.md](docs/current/DEVNOTES.md) | 踩坑、边界、设计决策、兼容性风险和问题状态 |

推荐阅读顺序：

1. [docs/current/PROGRESS.md](docs/current/PROGRESS.md)
2. [docs/current/ARCHITECTURE.md](docs/current/ARCHITECTURE.md)
3. [docs/current/ROADMAP.md](docs/current/ROADMAP.md)
4. [docs/current/DEVNOTES.md](docs/current/DEVNOTES.md)

根目录的 `ARCHITECTURE.md`、`ROADMAP.md`、`PROGRESS.md`、`DEVNOTES.md`、`日期计划.md` 现在主要作为兼容入口。旧版主文档归档在 [docs/old/2026-05-25-before-docs-restructure](docs/old/2026-05-25-before-docs-restructure)。

`日期计划.md` 现在是工作日志，当前副本位于 [docs/journal/2026-05-25-日期计划.md](docs/journal/2026-05-25-%E6%97%A5%E6%9C%9F%E8%AE%A1%E5%88%92.md)。

## Development Workflow

Xcode uses a **Spec-first + TDD-core + E2E-acceptance** workflow:

- Spec-first: meaningful feature, architecture, permission, context, session, or tool-loop changes start from `docs/superpowers/specs/` and `docs/superpowers/plans/`.
- TDD-core: high-risk behavior is protected by failing tests before implementation, especially permissions, tool errors, session recovery, memory paths, context accounting, and regression fixes.
- E2E-acceptance: terminal-native behavior is validated in real cmd.exe/PowerShell when prompt_toolkit, Rich rendering, approval menus, hotkeys, or Windows paths are involved.

Testing is risk-layered:

| Layer | Scope | Expectation |
|-------|-------|-------------|
| P0 | Security, state, tool loop, session, memory, context, Windows compatibility | Automated regression tests required. |
| P1 | User-visible commands, task/sub-agent behavior, config merge, rendering state | Focused behavior tests expected. |
| P2 | Simple wrappers, wording, low-risk display details, docs | Smoke/manual validation is enough when tests would be noisy. |

## Requirements

- Python >= 3.10
- Windows is the primary target
- Linux/macOS are partial targets; ripgrep bootstrap is currently Windows-focused

## License

MIT
