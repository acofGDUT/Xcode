# `/init` Prompt Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an old-Claude-style `/init` command that expands into a fixed repository-initialization prompt and then runs through Xcode's ordinary agent turn.

**Architecture:** `/init` is a prompt command, not a local scanner. Command metadata and prompt text live with slash command infrastructure; `AgentRuntime` receives the expanded prompt and reuses the existing normal user-message path so transcript, `_history`, context, approvals, and LLM error handling stay unchanged.

**Tech Stack:** Python 3.10+, prompt_toolkit completion, pytest, current synchronous `AgentRuntime`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/xcode_cli/core/commands/slash.py` | Define slash command metadata, `SlashCommand`, `INIT_PROMPT`, `init_handler()`, and `/init` completion. |
| `src/xcode_cli/core/agent.py` | Let slash commands optionally return a prompt string; feed prompt commands into the normal user-turn path. |
| `src/xcode_cli/core/ui/shell.py` | Show `/init` in the command suggestions table. |
| `tests/test_init_command.py` | Cover prompt command metadata, prompt contents, completion, and runtime handoff. |
| `docs/current/ARCHITECTURE.md` | After implementation, document prompt commands in the slash command section. |
| `docs/current/PROGRESS.md` | Mark `/init` as implemented after tests pass. |
| `docs/current/ROADMAP.md` | Move `/init` from planned to completed/implemented wording. |

---

### Task 1: Add `/init` Command Metadata and Prompt

**Files:**
- Modify: `src/xcode_cli/core/commands/slash.py`
- Create: `tests/test_init_command.py`

- [ ] **Step 1: Write failing tests for prompt metadata and contents**

Create `tests/test_init_command.py` with:

```python
from __future__ import annotations

from prompt_toolkit.document import Document

from xcode_cli.core.commands.slash import INIT_PROMPT, PROMPT_COMMANDS, SlashCompleter, init_handler


def test_init_handler_returns_repository_initialization_prompt() -> None:
    prompt = init_handler("")

    assert prompt == INIT_PROMPT
    assert "create an XCODE.md file" in prompt
    assert "future instances of xcode" in prompt
    assert "AGENTS.md" in prompt
    assert "CLAUDE.md" in prompt
    assert ".github/copilot-instructions.md" in prompt
    assert "README.md" in prompt
    assert "# XCODE.md" in prompt
    assert "This file provides guidance to xcode" in prompt
    assert "which files you used as sources" in prompt


def test_init_is_registered_as_prompt_command() -> None:
    command = PROMPT_COMMANDS["/init"]

    assert command.name == "init"
    assert command.kind == "prompt"
    assert command.description == "Initialize a new XCODE.md file with codebase documentation"
    assert command.handler("") == INIT_PROMPT


def test_slash_completer_includes_init() -> None:
    completer = SlashCompleter()
    completions = list(completer.get_completions(Document("/in"), None))

    assert any(completion.text == "/init" for completion in completions)
    assert any("Initialize a new XCODE.md" in str(completion.display_text) for completion in completions)
```

- [ ] **Step 2: Run tests and verify they fail for missing symbols**

Run:

```powershell
pytest tests/test_init_command.py -q
```

Expected result:

```text
ImportError or AttributeError mentioning INIT_PROMPT, PROMPT_COMMANDS, or init_handler
```

- [ ] **Step 3: Implement command metadata and prompt**

Modify `src/xcode_cli/core/commands/slash.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.completion import Completer, Completion


@dataclass(frozen=True)
class SlashCommand:
    name: str
    kind: str
    description: str
    handler: Callable[[str], str]


INIT_PROMPT = """Please analyze this codebase and create an XCODE.md file, which will be given to future instances of xcode to operate in this repository.

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
"""


def init_handler(args: str) -> str:
    return INIT_PROMPT


PROMPT_COMMANDS = {
    "/init": SlashCommand(
        name="init",
        kind="prompt",
        description="Initialize a new XCODE.md file with codebase documentation",
        handler=init_handler,
    ),
}


COMMANDS = {
    "/help": "Show available commands",
    "/init": PROMPT_COMMANDS["/init"].description,
    "/context": "Show token usage and context budget",
    "/dashboard": "Open API configuration dashboard",
    "/skill": "Manage skills (list/install/enable/disable)",
    "/env": "Open interactive config dashboard",
    "/plan": "Plan mode controls (enter/show/approve/reject)",
    "/memory": "Memory status and auto-memory toggle",
    "/resume": "List and resume previous sessions",
    "/compact": "Compress current conversation context",
    "/exit": "Exit chat",
}
```

Then add a dedicated `/init` branch before `/skill` in `SlashCompleter.get_completions()`:

```python
        if text.startswith("/init"):
            yield Completion(
                "/init",
                start_position=-len(text),
                display="/init — Initialize a new XCODE.md file with codebase documentation",
            )
            return
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
pytest tests/test_init_command.py -q
```

Expected result:

```text
3 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src/xcode_cli/core/commands/slash.py tests/test_init_command.py
git commit -m "feat: add init prompt command metadata"
```

---

### Task 2: Route Prompt Commands Through the Normal Agent Turn

**Files:**
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `tests/test_init_command.py`

- [ ] **Step 1: Add failing runtime handoff test**

Append to `tests/test_init_command.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock


def _setup_tmp_xcode_home(tmp_path: Path, monkeypatch) -> Path:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(
        json.dumps({"model": "test-model", "api_key": "test-key"}),
        encoding="utf-8",
    )
    for subdir in ("sessions", "skills", "bin"):
        (xcode_dir / subdir).mkdir(parents=True, exist_ok=True)
    return xcode_dir


def _make_agent(tmp_path: Path, monkeypatch):
    import xcode_cli.core.agent as agent_mod

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    _setup_tmp_xcode_home(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)

    from xcode_cli.core.agent import AgentRuntime

    agent = AgentRuntime()
    agent._session_id = "test-session"
    agent._history = []
    return agent


def test_handle_slash_command_returns_init_prompt(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)

    result = agent._handle_slash_command("/init")

    assert result == INIT_PROMPT
    assert agent._history == []


def test_run_chat_feeds_init_prompt_through_normal_user_turn(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    prompts = iter(["/init", "/exit"])
    agent.prompt.prompt.side_effect = lambda *args, **kwargs: next(prompts)
    agent._run_llm_loop = MagicMock(return_value="created XCODE.md")

    agent.run_chat()

    assert agent._run_llm_loop.call_count == 1
    assert agent._history[0] == {"role": "user", "content": INIT_PROMPT}
    assert agent._history[1] == {"role": "assistant", "content": "created XCODE.md"}
```

- [ ] **Step 2: Run tests and verify runtime tests fail**

Run:

```powershell
pytest tests/test_init_command.py -q
```

Expected result:

```text
FAIL because _handle_slash_command currently returns None and run_chat continues after slash commands
```

- [ ] **Step 3: Import prompt commands in agent runtime**

Modify the existing import in `src/xcode_cli/core/agent.py`:

```python
from xcode_cli.core.commands.slash import PROMPT_COMMANDS, SlashCompleter
```

- [ ] **Step 4: Let `run_chat()` continue with expanded prompt commands**

In `src/xcode_cli/core/agent.py`, replace the slash-command block in `run_chat()`:

```python
                if user_input.startswith("/"):
                    prompt_command_text = self._handle_slash_command(user_input)
                    if prompt_command_text is None:
                        continue
                    user_input = prompt_command_text
```

Keep the existing plan approval and ordinary user-message path after this block unchanged.

- [ ] **Step 5: Change `_handle_slash_command()` return type and add prompt command branch**

Update the signature and first part of `_handle_slash_command()`:

```python
    def _handle_slash_command(self, command: str) -> str | None:
        parts = command.split(maxsplit=1)
        head = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        prompt_command = PROMPT_COMMANDS.get(head)
        if prompt_command is not None:
            return prompt_command.handler(args)
```

Keep every existing side-effect command returning `None`. For example:

```python
        if head == "/help":
            self._show_command_suggestions()
            self.console.print("/init")
            self.console.print("/skill list|install <path>|enable <name>|disable <name>")
            self.console.print("/env  (配置仪表盘)")
            self.console.print("/context")
            self.console.print("/memory | /memory auto on|off")
            self.console.print("/dashboard")
            return None
```

At the end, return `None` after printing the unknown command:

```python
        self.console.print(f"Unknown command: {command}. Try /help")
        return None
```

- [ ] **Step 6: Run focused tests and verify they pass**

Run:

```powershell
pytest tests/test_init_command.py -q
```

Expected result:

```text
5 passed
```

- [ ] **Step 7: Run nearby slash/runtime regression tests**

Run:

```powershell
pytest tests/test_init_command.py tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q
```

Expected result:

```text
all selected tests pass
```

- [ ] **Step 8: Commit Task 2**

Run:

```powershell
git add src/xcode_cli/core/agent.py tests/test_init_command.py
git commit -m "feat: route init through normal agent turn"
```

---

### Task 3: Surface `/init` in Help and Command Suggestions

**Files:**
- Modify: `src/xcode_cli/core/ui/shell.py`
- Modify: `tests/test_init_command.py`

- [ ] **Step 1: Add failing test for command suggestions**

Append to `tests/test_init_command.py`:

```python
from io import StringIO

from rich.console import Console


def test_shell_command_suggestions_include_init(tmp_path: Path, monkeypatch) -> None:
    from xcode_cli.core.ui.shell import ShellUI

    agent = _make_agent(tmp_path, monkeypatch)
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)
    shell = ShellUI(
        console=console,
        config_store=agent.config_store,
        context=agent.context,
        session_start_getter=lambda: 0.0,
        tool_count_getter=lambda: 0,
        token_getter=lambda: 0,
        cwd=agent.cwd,
    )

    shell.show_command_suggestions()

    rendered = output.getvalue()
    assert "/init" in rendered
    assert "Initialize a new XCODE.md" in rendered
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest tests/test_init_command.py::test_shell_command_suggestions_include_init -q
```

Expected result:

```text
FAIL because /init is not rendered in ShellUI.show_command_suggestions()
```

- [ ] **Step 3: Add `/init` to ShellUI command suggestions**

Modify `src/xcode_cli/core/ui/shell.py` inside `show_command_suggestions()`:

```python
        table.add_row("/help", "Show available commands")
        table.add_row("/init", "Initialize a new XCODE.md file with codebase documentation")
        table.add_row("/context", "Show token usage and context budget")
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
pytest tests/test_init_command.py -q
```

Expected result:

```text
6 passed
```

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src/xcode_cli/core/ui/shell.py tests/test_init_command.py
git commit -m "docs: surface init in slash command help"
```

---

### Task 4: Update Current Project Documentation

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/DEVNOTES.md` only if implementation behavior differs from the design

- [ ] **Step 1: Update `ARCHITECTURE.md` slash command table**

In `docs/current/ARCHITECTURE.md`, add `/init` to the slash command section with this behavior:

```markdown
| `/init` | prompt command registry + `AgentRuntime` normal turn path | Expands to the repository initialization prompt and runs as an ordinary user task so the agent can create or improve `XCODE.md` with existing tools |
```

- [ ] **Step 2: Update `ROADMAP.md` status**

In `docs/current/ROADMAP.md`, change the `/init` priority row from `未实现` to `完成` after implementation:

```markdown
| P1 | `/init` prompt command | 完成 | 复刻旧版 Claude `/init`，把固定初始化 prompt 当作普通用户任务送入 agent turn，由 Agent 自己读取项目并创建或更新 `XCODE.md` |
```

Keep the detailed section as implementation background.

- [ ] **Step 3: Update `PROGRESS.md` status**

In `docs/current/PROGRESS.md`, change the status row from `规划中` to `完成并通过测试` after tests pass:

```markdown
| `/init` prompt command | 旧版 Claude 风格 prompt command，生成或改进仓库级 `XCODE.md` | 完成并通过测试 | `2026-06-04-init-command-plan.md` |
```

Add implementation evidence to the `/init` progress section:

```markdown
实现后验收：

- `/init` 已注册到 help 和 slash completion。
- prompt command handler 只返回固定 prompt，不扫描项目、不写文件。
- `AgentRuntime` 将展开后的 prompt 作为普通 user message 写入 `_history` 和 transcript，并复用普通 LLM/tool loop。
- 测试：`pytest tests/test_init_command.py tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q` 通过。
```

- [ ] **Step 4: Run documentation diff check**

Run:

```powershell
git diff --check
```

Expected result:

```text
no trailing whitespace errors
```

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add docs/current/ARCHITECTURE.md docs/current/ROADMAP.md docs/current/PROGRESS.md docs/current/DEVNOTES.md
git commit -m "docs: document init prompt command"
```

---

### Task 5: Final Verification

**Files:**
- Verify all touched files

- [ ] **Step 1: Run py_compile for touched Python modules**

Run:

```powershell
python -m py_compile src/xcode_cli/core/commands/slash.py src/xcode_cli/core/agent.py src/xcode_cli/core/ui/shell.py
```

Expected result:

```text
command exits 0
```

- [ ] **Step 2: Run focused regression tests**

Run:

```powershell
pytest tests/test_init_command.py tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q
```

Expected result:

```text
all selected tests pass
```

- [ ] **Step 3: Run full test suite**

Run:

```powershell
pytest -q
```

Expected result:

```text
all tests pass
```

- [ ] **Step 4: Run diff check**

Run:

```powershell
git diff --check
```

Expected result:

```text
no trailing whitespace errors
```

- [ ] **Step 5: Manual smoke test in PowerShell**

Run:

```powershell
xcode chat
```

Then type:

```text
/help
/init
```

Expected result:

```text
/help shows /init.
/init starts a normal agent turn.
If API credentials are missing, the same missing-key error shown for ordinary prompts appears.
If the model attempts to write XCODE.md, the normal write/edit approval flow appears.
```

- [ ] **Step 6: Final commit**

If the earlier task commits were not used, commit the complete implementation:

```powershell
git add src/xcode_cli/core/commands/slash.py src/xcode_cli/core/agent.py src/xcode_cli/core/ui/shell.py tests/test_init_command.py docs/current/ARCHITECTURE.md docs/current/ROADMAP.md docs/current/PROGRESS.md docs/current/DEVNOTES.md
git commit -m "feat: add init prompt command"
```

---

## Self-Review

Spec coverage:

- Prompt-command behavior is covered by Tasks 1 and 2.
- Fixed initialization prompt content is covered by Task 1.
- No local scanning and no direct `XCODE.md` writes are protected by architecture and runtime handoff tests in Task 2.
- Help/completion visibility is covered by Tasks 1 and 3.
- Documentation closeout is covered by Task 4.
- Verification and manual PowerShell smoke testing are covered by Task 5.

Placeholder scan:

- The plan contains no deferred implementation placeholders.
- Every code-changing step includes exact snippets or exact commands.

Type consistency:

- `SlashCommand`, `INIT_PROMPT`, `PROMPT_COMMANDS`, and `init_handler()` are introduced in Task 1 and reused consistently in later tasks.
- `_handle_slash_command()` consistently returns `str | None`, where `str` means expanded prompt and `None` means side-effect command handled or unknown command printed.
