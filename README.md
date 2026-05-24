# Xcode

> A terminal-native AI coding agent. Tools, sub-agents, plan mode, persistent memory — works with any OpenAI-compatible API.

## Features

- **13 built-in tools**: read_file, write_file, edit_file, grep (ripgrep), glob, run_shell, dispatch_agent (sub-agents), task_create/update/list, enter_plan_mode, write_plan, exit_plan_mode
- **Streaming output**: real-time token streaming with thinking/reasoning display and timing stats
- **Sub-agents**: EXPLORE / PLAN / GENERAL types with tool whitelist isolation, parallel execution via ThreadPoolExecutor
- **Plan mode**: enter → explore → write plan → request user approval → execute
- **Memory system**: two-tier (Project XCODE.md + User XCODE.md + Auto Memory with individual .md files + MEMORY.md index)
- **Permission system**: three-level (session > project > global), allow/deny/ask per tool
- **Context management**: token estimation + automatic compression via LLM summarization
- **Skill system**: installable, pluggable skills with SKILL.md injection
- **Rich UI**: Markdown rendering, syntax-highlighted code blocks, unified diff display

## Quick Start

```bash
# Install
pip install -e .

# Configure API key
xcode
/env set <your-api-key>

# Or via environment variables
export XCODE_API_KEY=<key>
export XCODE_BASE_URL=<url>    # optional
export XCODE_MODEL=<model>     # default: gpt-4o-mini
```

## Supported Providers

Any OpenAI-compatible API:

| Provider | Base URL |
|----------|----------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Others | Set via `XCODE_BASE_URL` |

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/dashboard` | API configuration TUI |
| `/skill` | Manage skills |
| `/env` | Configure API settings |
| `/plan` | Plan mode controls |
| `/memory` | Memory status + toggle |
| `/exit` | Exit chat |

## Project Structure

```
src/xcode_cli/
  main.py
  core/
    agent.py           # AgentRuntime: REPL loop, tool registration, plan/memory commands
    llm.py             # OpenAI-compatible client, streaming + tool calling
    tool_registry.py   # ToolDef + ToolRegistry
    prompting.py       # BASE_SYSTEM_PROMPT + memory rules
    config.py          # Config + ConfigStore
    memory.py          # MemoryManager: XCODE.md + auto memory
    planning.py        # PlanMode state machine
    context.py         # ContextManager: token compression
    permissions.py     # PermissionManager: three-level permissions
    sub_agent.py       # SubAgentExecutor
    task_tracker.py    # Task CRUD + dependency management
    tools/
      files.py         # read_file / write_file / edit_file
      search.py        # grep (rg) / glob
      shell.py         # run_shell
      agent_tool.py    # dispatch_agent
  ui/
    renderer.py        # Rich Markdown / Diff rendering
  skills/
    manager.py         # Skill installation and management
```

## Development Docs

| Order | Document | Content |
|-------|----------|---------|
| 1 | `PROGRESS.md` | Phase/task completion status |
| 2 | `ROADMAP.md` | Full requirement spec, function signatures, data structures |
| 3 | `ARCHITECTURE.md` | Component relationships, data flows, design decisions |
| 4 | `DEVNOTES.md` | Known issues, design tradeoffs |

## Requirements

- Python >= 3.10
- Windows (primary), Linux/macOS (partial — ripgrep bootstrap is Windows-only)

## License

MIT
