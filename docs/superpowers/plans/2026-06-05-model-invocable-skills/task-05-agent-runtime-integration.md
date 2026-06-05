# Task 5: 接入 AgentRuntime、system prompt 和 allowed-tools 续接

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `src/xcode_cli/core/prompting.py`
- Modify: `src/xcode_cli/core/commands/registry.py`
- Test: `tests/test_model_invocable_skill_flow.py`
- Test: `tests/test_prompting_skills.py`

- [ ] **Step 1: 写 system prompt listing 测试**

创建 `tests/test_prompting_skills.py`：

```python
from xcode_cli.core.config import Config
from xcode_cli.core.prompting import build_system_prompt


def test_system_prompt_includes_skill_listing_and_guidance():
    prompt = build_system_prompt(
        Config(max_tokens=128000),
        cwd="D:/Xcode",
        skill_listing="Available skills:\n- review: Review code changes",
    )

    assert "Available skills:" in prompt
    assert "- review: Review code changes" in prompt
    assert "call the skill tool" in prompt
    assert "Do not call the skill tool for weak or speculative matches." in prompt
    assert "Do not use the skill tool for built-in CLI commands." in prompt


def test_system_prompt_omits_skill_guidance_without_listing():
    prompt = build_system_prompt(Config(), cwd="D:/Xcode", skill_listing="")

    assert "call the skill tool" not in prompt
```

- [ ] **Step 2: 写 AgentRuntime flow 测试**

创建 `tests/test_model_invocable_skill_flow.py`，用 fake LLM 第一次返回 skill tool call、第二次返回最终回答。断言第二次 LLM request 的 messages 中包含 loaded skill marker，tool schemas 被 allowed-tools 收窄，且不再包含 `skill` 工具：

```python
from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.llm import LLMResponse, ToolCall


def make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=None):
    import xcode_cli.core.agent as agent_mod
    import xcode_cli.paths
    from xcode_cli.core.agent import AgentRuntime

    project_dir = tmp_path / "project"
    skill_dir = project_dir / ".xcode" / "skills" / "review"
    skill_dir.mkdir(parents=True)
    allowed_tools_block = ""
    if allowed_tools is not None:
        allowed_tools_block = "allowed-tools:\n" + "".join(f"  - {name}\n" for name in allowed_tools)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: Review code changes\n"
        f"{allowed_tools_block}"
        "---\n"
        "Review $ARGUMENTS\n",
        encoding="utf-8",
    )
    xcode_dir = tmp_path / ".xcode-home"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(agent_mod, "PromptSession", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "AutoSuggestFromHistory", MagicMock(return_value=MagicMock()), raising=True)
    monkeypatch.setattr(agent_mod, "resolve_project_root", MagicMock(return_value=str(project_dir)), raising=True)

    runtime = AgentRuntime()
    return runtime


def test_skill_tool_loads_prompt_and_narrows_followup_tool_schemas(tmp_path, monkeypatch):
    runtime = make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=["read"])
    runtime._session_id = runtime.sessions.new_session_id()

    seen_schemas = []
    seen_messages = []

    def fake_complete(system_prompt, messages, tool_schemas, on_text_token=None, on_reasoning_token=None):
        seen_schemas.append([schema["function"]["name"] for schema in tool_schemas])
        seen_messages.append(messages.copy())
        if len(seen_schemas) == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="skill", args={"skill": "review", "args": "src/foo.py"})],
            )
        return LLMResponse(content="review complete", tool_calls=[])

    runtime.llm.complete = fake_complete

    runtime._run_user_turn("review src/foo.py")

    assert "skill" in seen_schemas[0]
    assert seen_schemas[1] == ["read_file"]
    assert any("<xcode_loaded_skill name=\"review\"" in str(msg) for msg in seen_messages[1])
```

再增加一个无 `allowed-tools` 的防递归测试：

```python
def test_skill_tool_is_removed_after_loading_even_without_allowed_tools(tmp_path, monkeypatch):
    runtime = make_runtime_with_review_skill(tmp_path, monkeypatch, allowed_tools=None)
    runtime._session_id = runtime.sessions.new_session_id()
    seen_schemas = []

    def fake_complete(system_prompt, messages, tool_schemas, on_text_token=None, on_reasoning_token=None):
        seen_schemas.append([schema["function"]["name"] for schema in tool_schemas])
        if len(seen_schemas) == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="skill", args={"skill": "review", "args": "src/foo.py"})],
            )
        return LLMResponse(content="review complete", tool_calls=[])

    runtime.llm.complete = fake_complete

    runtime._run_user_turn("review src/foo.py")

    assert "skill" in seen_schemas[0]
    assert "skill" not in seen_schemas[1]
    assert "read_file" in seen_schemas[1]
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
pytest tests/test_prompting_skills.py tests/test_model_invocable_skill_flow.py -q
```

Expected: FAIL，提示 `build_system_prompt()` 不接收 `skill_listing` 或没有 skill tool。

- [ ] **Step 4: 修改 prompting**

修改 `src/xcode_cli/core/prompting.py`：

```python
def build_system_prompt(config: Config, cwd: str = "", skill_listing: str = "") -> str:
    ...
    if skill_listing:
        sections.append(
            "\n## Available Skills\n"
            f"{skill_listing}\n\n"
            "Skill usage rules:\n"
            "- When an available skill clearly matches the user's current task, call the skill tool before doing the task.\n"
            "- Do not call the skill tool for weak or speculative matches.\n"
            "- Do not mention a skill unless you actually invoke it.\n"
            "- Do not guess skill names.\n"
            "- Do not use the skill tool for built-in CLI commands.\n"
            "- If the current turn already contains an <xcode_loaded_skill> marker, follow that skill instead of invoking the skill tool again."
        )
```

- [ ] **Step 5: 修改 AgentRuntime 构造**

在 `AgentRuntime.__init__()`：

```python
self._skill_catalog = SkillCatalog(self._skill_load_result.skills, builtin_commands=set(COMMANDS))
self._skill_invocation = SkillInvocationService(self._skill_catalog)
self._skill_listing_formatter = SkillListingFormatter()
self._command_registry = CommandRegistry.from_skills(
    self._skill_catalog.user_invocable_skills(),
    invocation_service=self._skill_invocation,
)
...
self.tools.register(create_skill_tool(self._skill_invocation))
```

注意：`create_skill_tool()` 只应该在有 model-invocable skills 时注册；如果没有 listing，可以不注册，避免空工具干扰模型。

- [ ] **Step 6: 修改 system prompt 构建**

在 `_run_user_turn()` 中：

```python
cfg = self.config_store.load()
skill_listing = self._skill_listing_formatter.format(
    self._skill_catalog.model_invocable_skills(),
    context_window_tokens=cfg.max_tokens,
)
system_prompt = build_system_prompt(cfg, self.cwd, skill_listing=skill_listing)
```

当没有 model-invocable skills 时传入空字符串，不要把空的 `Available skills:` section 注入 system prompt：

```python
model_skills = self._skill_catalog.model_invocable_skills()
skill_listing = (
    self._skill_listing_formatter.format(model_skills, context_window_tokens=cfg.max_tokens)
    if model_skills
    else ""
)
```

- [ ] **Step 7: 续接 allowed-tools 和 blocked-tools**

在 `AgentRuntime.__init__()` 增加：

```python
self._current_blocked_tools: set[str] = set()
```

在 `_run_user_turn()` 开头，和 `_current_allowed_tools` 一起重置当前 turn 的 blocked tools：

```python
self._current_allowed_tools = turn.allowed_tools
self._current_blocked_tools = set()
```

在 `_run_llm_loop()` 调用 `tool_executor.execute()` 后：

```python
if tool_result.activated_allowed_tools is not None:
    self._current_allowed_tools = tool_result.activated_allowed_tools
if tool_result.blocked_tools:
    self._current_blocked_tools.update(tool_result.blocked_tools)
```

这样 SkillTool 加载后的下一次 LLM request 只暴露 skill allowed-tools，并且无论 skill 是否声明 `allowed-tools`，都不会继续暴露 `skill` 工具。

`ToolRegistry.get_openai_schemas()` 需要接收 `blocked_tools`：

```python
self.tools.get_openai_schemas(
    allowed_tools=self._current_allowed_tools,
    blocked_tools=self._current_blocked_tools,
)
```

当 `allowed_tools is None` 时，返回默认工具集合减去 blocked tools；当 `allowed_tools` 非空时，返回白名单集合再减去 blocked tools。

- [ ] **Step 8: 运行测试确认通过**

Run:

```powershell
pytest tests/test_prompting_skills.py tests/test_model_invocable_skill_flow.py tests/test_skill_allowed_tools.py tests/test_init_command.py -q
```

Expected: PASS。

- [ ] **Step 9: 提交**

```powershell
git add src/xcode_cli/core/agent.py src/xcode_cli/core/prompting.py src/xcode_cli/core/commands/registry.py tests/test_prompting_skills.py tests/test_model_invocable_skill_flow.py
git commit -m "feat: inject model-invocable skill listings"
```
