# dispatch_agent Auto-Allow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let local REPL model calls to `dispatch_agent` run without an approval prompt while preserving explicit permission overrides and QQchat remote-entry blocking.

**Status:** Code implementation, focused automated regression, documentation update, and review completed on 2026-06-12. Commit steps were intentionally not run because this workspace is on `main` with pre-existing unrelated changes and the user did not request a commit.

**Architecture:** Keep `dispatch_agent` registered as `is_read_only=False`; change only the default permission policy so it is a default-allowed local orchestration tool. Preserve `PermissionManager` override order, `ToolCallExecutor` behavior, QQchat `ToolScope` filtering, and sub-agent tool whitelists.

**Tech Stack:** Python 3.10+, pytest, existing Xcode CLI permission system, existing synchronous AgentRuntime/tool loop.

---

## Scope And Files

**Parent spec:** `docs/superpowers/specs/2026-06-11-dispatch-agent-auto-allow-design.md`

**Risk layer:** P0/P1. Permission defaults are P0 safety behavior; removing a visible approval prompt is P1 user experience.

**Modify:**
- `src/xcode_cli/core/permissions.py`
- `tests/test_task_permissions.py`
- `tests/test_agent_tool_loop.py`
- `tests/test_external_turn.py`
- `docs/current/ARCHITECTURE.md`
- `docs/current/DEVNOTES.md`
- `docs/current/PROGRESS.md`

**Do not modify:**
- `src/xcode_cli/core/tools/agent_tool.py`: `dispatch_agent` should remain `is_read_only=False`.
- `src/xcode_cli/core/external_turn.py`: `dispatch_agent` should remain forbidden for QQchat.
- `src/xcode_cli/core/sub_agent.py`: EXPLORE / PLAN sub-agents should remain read/search only and should not gain recursive dispatch.

## Task 1: PermissionManager Default Allows dispatch_agent

**Files:**
- Modify: `tests/test_task_permissions.py`
- Modify: `src/xcode_cli/core/permissions.py`

- [x] **Step 1: Add failing permission default tests**

Append these tests to `tests/test_task_permissions.py`:

```python
def test_dispatch_agent_default_allow(tmp_path: Path) -> None:
    pm = PermissionManager(str(tmp_path))
    assert pm.check("dispatch_agent") == "allow"


def test_dispatch_agent_deny_override(tmp_path: Path) -> None:
    settings_dir = tmp_path / ".xcode"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"dispatch_agent": "deny"}}),
        encoding="utf-8",
    )
    pm = PermissionManager(str(tmp_path))
    assert pm.check("dispatch_agent") == "deny"


def test_dispatch_agent_explicit_ask_override(tmp_path: Path) -> None:
    settings_dir = tmp_path / ".xcode"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"dispatch_agent": "ask"}}),
        encoding="utf-8",
    )
    pm = PermissionManager(str(tmp_path))
    assert pm.check("dispatch_agent") == "ask"
```

- [x] **Step 2: Run permission tests and verify the new default test fails**

Run:

```powershell
pytest tests\test_task_permissions.py -q
```

Expected: `test_dispatch_agent_default_allow` fails because `PermissionManager.check("dispatch_agent")` currently returns `ask`. The explicit `deny` and explicit `ask` tests should already pass because explicit rules are read before defaults.

- [x] **Step 3: Implement the minimal default permission change**

In `src/xcode_cli/core/permissions.py`, change `_default_level()` from:

```python
    def _default_level(self, tool_name: str) -> str:
        if tool_name in {"task_create", "task_update"}:
            return "allow"
```

to:

```python
    def _default_level(self, tool_name: str) -> str:
        if tool_name in {"task_create", "task_update", "dispatch_agent"}:
            return "allow"
```

Do not change `check()` ordering. Session, project, and global explicit rules must keep priority over default allow.

- [x] **Step 4: Run permission tests and verify they pass**

Run:

```powershell
pytest tests\test_task_permissions.py -q
```

Expected: all tests in `tests/test_task_permissions.py` pass.

- [ ] **Step 5: Commit task 1 if working in a development branch**

Run:

```powershell
git add src\xcode_cli\core\permissions.py tests\test_task_permissions.py
git commit -m "fix: allow local dispatch agent by default"
```

Expected: commit succeeds. If this implementation is being prepared for review without commits, leave the files unstaged and record the same summary in the closeout.

## Task 2: Tool Loop Does Not Prompt For dispatch_agent Unless Explicit Ask

**Files:**
- Modify: `tests/test_agent_tool_loop.py`
- No additional implementation expected after Task 1

- [x] **Step 1: Add a runtime regression test for the no-approval path**

Append this test to `tests/test_agent_tool_loop.py`:

```python
def test_dispatch_agent_default_allow_skips_approval_prompt(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]
    approvals: list[str] = []
    executed: list[dict] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_dispatch",
                        name="dispatch_agent",
                        args={"agent_type": "explore", "prompt": "Inspect README.md"},
                    )
                ],
            )
        return LLMResponse(content="continued after dispatch", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(
        agent.approval,
        "prompt",
        lambda tool_name, scope: approvals.append(f"{tool_name}:{scope}") or "no",
    )
    agent.tools._tools["dispatch_agent"].execute = (
        lambda **kwargs: executed.append(kwargs) or "sub-agent result"
    )

    result = agent._run_llm_loop([], "system")

    assert result == "continued after dispatch"
    assert approvals == []
    assert executed == [{"agent_type": "explore", "prompt": "Inspect README.md"}]
```

- [x] **Step 2: Add a runtime regression test for explicit deny**

Append this test to `tests/test_agent_tool_loop.py`:

```python
def test_dispatch_agent_explicit_deny_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    settings_dir = Path(agent.cwd) / ".xcode"
    settings_dir.mkdir(exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"dispatch_agent": "deny"}}),
        encoding="utf-8",
    )
    calls = [0]
    executed: list[dict] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_dispatch",
                        name="dispatch_agent",
                        args={"agent_type": "explore", "prompt": "Inspect README.md"},
                    )
                ],
            )
        assert any(
            m.get("role") == "tool" and "Permission denied for tool: dispatch_agent" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="continued without dispatch", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["dispatch_agent"].execute = (
        lambda **kwargs: executed.append(kwargs) or "sub-agent result"
    )

    result = agent._run_llm_loop([], "system")

    assert result == "continued without dispatch"
    assert executed == []
```

- [x] **Step 3: Add a runtime regression test for explicit ask**

Append this test to `tests/test_agent_tool_loop.py`:

```python
def test_dispatch_agent_explicit_ask_still_prompts(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    settings_dir = Path(agent.cwd) / ".xcode"
    settings_dir.mkdir(exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"permissions": {"dispatch_agent": "ask"}}),
        encoding="utf-8",
    )
    calls = [0]
    approvals: list[str] = []

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_dispatch",
                        name="dispatch_agent",
                        args={"agent_type": "explore", "prompt": "Inspect README.md"},
                    )
                ],
            )
        assert any(
            m.get("role") == "tool" and "User denied tool: dispatch_agent" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="continued after prompt", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(
        agent.approval,
        "prompt",
        lambda tool_name, scope: approvals.append(f"{tool_name}:{scope}") or "no",
    )

    result = agent._run_llm_loop([], "system")

    assert result == "continued after prompt"
    assert approvals == ["dispatch_agent:dispatch_agent"]
```

- [x] **Step 4: Run tool loop tests**

Run:

```powershell
pytest tests\test_agent_tool_loop.py -q
```

Expected: all tests pass after Task 1. If the explicit ask test fails because `approval.scope_for_tool("dispatch_agent")` returns a different scope value, keep the behavior and update the assertion to the exact string returned by the existing approval scope implementation.

- [ ] **Step 5: Commit task 2 if working in a development branch**

Run:

```powershell
git add tests\test_agent_tool_loop.py
git commit -m "test: cover dispatch agent approval policy"
```

Expected: commit succeeds. If this implementation is being prepared for review without commits, leave the file unstaged and record the same summary in the closeout.

## Task 3: QQchat Still Cannot Re-Enable dispatch_agent

**Files:**
- Modify: `tests/test_external_turn.py`
- No implementation expected

- [x] **Step 1: Add a QQchat tool-scope regression test**

Append this test to `tests/test_external_turn.py`:

```python
def test_qq_turn_filters_dispatch_agent_even_if_config_attempts_to_add_it():
    sessions = FakeSessionStore()
    loop = FakeLoop()
    runner = ExternalTurnRunner(
        session_store=sessions,
        run_llm_loop=loop,
        build_system_prompt=lambda: "system",
        default_tool_scope=ToolScope(
            source="qqchat",
            visible_tools=("read_file", "dispatch_agent"),
            execution_allowlist=("read_file", "dispatch_agent"),
            remote_approval=True,
        ),
    )

    runner.run("qq:c2c:user-a", UserTurnInput("QQ: inspect", "inspect"))

    tool_scope = loop.calls[0][2]
    assert tool_scope.visible_tools == ("read_file",)
    assert tool_scope.execution_allowlist == ("read_file",)
    assert tool_scope.remote_approval is False
    assert "dispatch_agent" not in tool_scope.visible_tools
    assert "dispatch_agent" not in tool_scope.execution_allowlist
```

- [x] **Step 2: Run external turn tests**

Run:

```powershell
pytest tests\test_external_turn.py -q
```

Expected: all tests pass. This test should pass with the existing `FORBIDDEN_EXTERNAL_TOOLS` behavior and protects the remote-entry safety boundary while Task 1 changes local defaults.

- [ ] **Step 3: Commit task 3 if working in a development branch**

Run:

```powershell
git add tests\test_external_turn.py
git commit -m "test: keep qqchat dispatch agent blocked"
```

Expected: commit succeeds. If this implementation is being prepared for review without commits, leave the file unstaged and record the same summary in the closeout.

## Task 4: Documentation Closeout

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/DEVNOTES.md`
- Modify: `docs/current/PROGRESS.md`

- [x] **Step 1: Update architecture documentation**

In `docs/current/ARCHITECTURE.md`, add a short note in the permission/tool execution area:

```markdown
`dispatch_agent` remains registered as a non-read-only tool because it performs local orchestration and consumes model/tool work, but it is default-allowed by `PermissionManager` for local REPL turns. Explicit session/project/global `deny` or `ask` rules still override the default. QQchat and other external entry points continue to filter `dispatch_agent` through `ToolScope`.
```

Place it near the existing tool registry, permission, or sub-agent description. Do not describe `dispatch_agent` as read-only.

- [x] **Step 2: Update development notes**

In `docs/current/DEVNOTES.md`, add a note under the sub-agent or permission section:

```markdown
## dispatch_agent default approval boundary

**Status**: Resolved
**Related**: SubAgentExecutor / permission defaults / QQchat external tool scope

`dispatch_agent` is treated as a local orchestration tool: default permission is `allow`, so normal model-driven sub-agent dispatch does not interrupt the REPL with an approval prompt. This does not make the tool read-only. Explicit `deny` and explicit `ask` rules still take precedence, QQchat continues to filter `dispatch_agent`, and EXPLORE / PLAN sub-agents still only receive read/search tools.
```

- [x] **Step 3: Update progress documentation**

In `docs/current/PROGRESS.md`, add a short entry in the current status/progress list:

```markdown
| dispatch_agent 免审优化 | 本地主会话子 Agent 分派默认免审批，explicit deny/ask 与 QQchat 远程过滤保持生效 | 完成并通过聚焦回归 | `2026-06-11-dispatch-agent-auto-allow-design.md` / `2026-06-11-dispatch-agent-auto-allow.md` |
```

If the table layout has changed by implementation time, adapt the text to the current document structure while keeping the same facts and verification evidence.

- [x] **Step 4: Run documentation diff check**

Run:

```powershell
git diff --check
```

Expected: exits with code 0.

- [ ] **Step 5: Commit task 4 if working in a development branch**

Run:

```powershell
git add docs\current\ARCHITECTURE.md docs\current\DEVNOTES.md docs\current\PROGRESS.md
git commit -m "docs: record dispatch agent approval policy"
```

Expected: commit succeeds. If this implementation is being prepared for review without commits, leave the files unstaged and record the same summary in the closeout.

## Task 5: Final Verification

**Files:**
- Verify all modified files

- [x] **Step 1: Run compile check**

Run:

```powershell
python -m py_compile src\xcode_cli\core\permissions.py src\xcode_cli\core\tools\agent_tool.py src\xcode_cli\core\external_turn.py src\xcode_cli\core\sub_agent.py
```

Expected: exits with code 0.

- [x] **Step 2: Run focused tests**

Run:

```powershell
pytest tests\test_task_permissions.py tests\test_agent_tool_loop.py tests\test_external_turn.py -q
```

Expected: all tests pass.

- [x] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: exits with code 0.

- [x] **Step 4: Inspect changed files**

Run:

```powershell
git status --short
git diff -- src\xcode_cli\core\permissions.py tests\test_task_permissions.py tests\test_agent_tool_loop.py tests\test_external_turn.py docs\current\ARCHITECTURE.md docs\current\DEVNOTES.md docs\current\PROGRESS.md
```

Expected: changed files match this plan. No unrelated user files are modified.

- [x] **Step 5: Prepare closeout summary**

Use this structure:

```markdown
变更摘要：
- `dispatch_agent` 默认权限从 `ask` 改为 `allow`，但仍保持 `is_read_only=False`。
- 补充了 explicit deny/ask、本地主 loop 免审批、QQchat 过滤 `dispatch_agent` 的回归测试。
- 同步更新当前架构、开发笔记和进度文档。

验证：
- `python -m py_compile src\xcode_cli\core\permissions.py src\xcode_cli\core\tools\agent_tool.py src\xcode_cli\core\external_turn.py src\xcode_cli\core\sub_agent.py`
- `pytest tests\test_task_permissions.py tests\test_agent_tool_loop.py tests\test_external_turn.py -q`
- `git diff --check`
```

## Review Checklist

- [x] `dispatch_agent` is default-allowed only through `PermissionManager._default_level()`.
- [x] `dispatch_agent` remains `is_read_only=False`.
- [x] Explicit session/project/global `deny` still returns permission denied.
- [x] Explicit `ask` still calls `approval.prompt()`.
- [x] QQchat `ToolScope` cannot include `dispatch_agent`.
- [x] EXPLORE / PLAN sub-agent registered tools are unchanged.
- [x] Verification evidence is recorded before any completion claim.
