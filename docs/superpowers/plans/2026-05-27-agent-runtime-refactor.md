# AgentRuntime 模块化重构实施计划

> **给 Coding Agent：** 请按本文分批执行。你只负责代码和测试，不更新 README / ARCHITECTURE / DEVNOTES / PROGRESS / ROADMAP / 日期计划 等主项目文档；实现完成后把变更、测试结果和风险点交给 Codex review，由 Codex 统一更新文档和 git。

**目标：** 把 `src/xcode_cli/core/agent.py` 从“大而全的运行时控制器”重构为轻量 orchestration，让 slash command、session/resume/compaction、tool call 执行、审批 UI、streaming/render 状态分别进入清晰模块。

**架构：** 本轮优先保持行为不变，先补回归测试，再按低风险到高风险拆分。第一阶段先拆 `commands/`、`conversation/`、`tooling/`、`ui/` 等新包；暂不直接新建 `core/memory/`，因为当前已有 `core/memory.py`，同名包迁移需要单独设计，避免 import 行为变脆。

**技术栈：** Python 3.10+、pytest、现有同步 `AgentRuntime`、`prompt_toolkit`、Rich、OpenAI-compatible tool calling。

---

## 总约束

- 必须保持产品语义不变，不要借重构顺手改功能。
- 不引入 `asyncio`。
- 不改变现有 slash command 名称和用户可见行为。
- 不降低权限安全边界：显式 `deny` 永远优先于 memory auto-allow 和 session auto-approve。
- 不改变 transcript / checkpoint / `/resume` 的持久化格式。
- 不改主项目文档，只改代码和测试。
- 每批完成后都要能独立跑通测试，不要做半截迁移。
- 如果发现现有测试与真实行为冲突，先停下来在交付说明中写清楚，不要静默改语义。

---

## 目标目录结构

第一轮重构后的建议结构：

```text
src/xcode_cli/core/
  agent.py                         # 只保留 AgentRuntime 组合依赖、REPL 主循环、LLM loop 编排
  commands/
    __init__.py
    slash.py                       # COMMANDS、SlashCompleter、命令分发
    env.py                         # /env
    memory.py                      # /memory 命令处理，不迁移 MemoryManager
    context.py                     # /context 展示
    plan.py                        # /plan 展示和审批输入
  conversation/
    __init__.py
    compaction.py                  # /compact 与自动 compression checkpoint 编排
    resume.py                      # /resume 命令编排，复用 SessionResumeBuilder
  tooling/
    __init__.py
    approval.py                    # 审批 scope、方向键菜单、TTY fallback、auto approve
    execution.py                   # tool call 执行、diff preview、结果摘要、assistant/tool messages
  ui/
    __init__.py
    shell.py                       # welcome、bottom toolbar、用户/助手输出等轻量 UI helper
    streaming.py                   # 后续批次再抽，先不急着动
```

说明：

- `commands/memory.py` 只表示 `/memory` 命令处理，不是 memory 模型本体。
- 当前 `src/xcode_cli/core/memory.py` 暂时保持原位，避免同名 `memory/` 包和 `memory.py` 并存。
- 如果后续要把 memory 模型也包化，应单独做一批：`core/memory.py` -> `core/memory/manager.py` + `core/memory/__init__.py`，并全量更新 import。

---

## 批次 0：补重构安全网

**目的：** 在搬代码前锁住最容易被拆坏的行为。

**文件：**

- 修改：`tests/test_agent_memory_permissions.py`
- 新增：`tests/test_agent_tool_loop.py`
- 可选修改：`tests/test_agent_resume_command.py`

### Task 0.1：补 explicit deny + memory path 回归测试

- [ ] 在 `tests/test_agent_memory_permissions.py` 增加测试：当 `write_file` 被 session rule 显式设置为 `deny` 时，即使命中 resolved memory path，也不能执行工具。

建议测试结构：

```python
def test_explicit_deny_memory_write_does_not_execute(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    memory_path = agent.memory.memory_dir_path() / "project_tech_stack.md"
    executed: list[dict] = []
    approvals: list[str] = []

    agent.permissions.set_session_rule("write_file", "deny")
    monkeypatch.setattr(
        agent,
        "_prompt_tool_approval",
        lambda tool_name, scope: approvals.append(f"{tool_name}:{scope}") or "yes",
    )
    agent.tools._tools["write_file"].execute = lambda **kwargs: executed.append(kwargs) or "ok"
    agent.llm.complete = _single_tool_call_llm([
        ToolCall(
            id="call_denied_memory",
            name="write_file",
            args={"path": str(memory_path), "content": "memory body"},
        )
    ])

    result = agent._run_llm_loop([], "system")

    assert result == "done"
    assert approvals == []
    assert executed == []
```

- [ ] 运行：

```bash
pytest tests/test_agent_memory_permissions.py -q
```

预期：新增测试通过。

### Task 0.2：补多轮 tool_calls 回归测试

- [ ] 新增 `tests/test_agent_tool_loop.py`，构造 fake LLM：第一轮返回 `read_file`，第二轮返回 `grep` 或另一个只读工具，第三轮返回最终文本。
- [ ] 断言 `_run_llm_loop()` 不会在第一轮 tool call 后提前停止。
- [ ] 断言 history 中按顺序出现 assistant tool_calls、tool result、第二轮 assistant tool_calls、第二轮 tool result、最终文本。

建议测试核心：

```python
def test_llm_loop_continues_across_multiple_tool_rounds(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name="read_file", args={"path": "README.md"})],
            )
        if calls[0] == 2:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_2", name="grep", args={"pattern": "Xcode", "path": "."})],
            )
        return LLMResponse(content="final answer", tool_calls=[])

    executed: list[str] = []
    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: executed.append("read_file") or "read result"
    agent.tools._tools["grep"].execute = lambda **kwargs: executed.append("grep") or "grep result"

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "final answer"
    assert calls[0] == 3
    assert executed == ["read_file", "grep"]
    assert [m["role"] for m in history] == ["assistant", "tool", "assistant", "tool"]
```

- [ ] 运行：

```bash
pytest tests/test_agent_tool_loop.py -q
```

预期：测试通过。

---

## 批次 1：拆 slash command 和轻量 UI

**目的：** 先拆低风险模块，让 `agent.py` 体积下降，同时不碰 `_run_llm_loop()` 的核心行为。

**文件：**

- 新增：`src/xcode_cli/core/commands/__init__.py`
- 新增：`src/xcode_cli/core/commands/slash.py`
- 新增：`src/xcode_cli/core/ui/__init__.py`
- 新增：`src/xcode_cli/core/ui/shell.py`
- 修改：`src/xcode_cli/core/agent.py`
- 测试：现有 agent command 相关测试

### Task 1.1：迁移 COMMANDS 和 SlashCompleter

- [ ] 创建 `src/xcode_cli/core/commands/slash.py`。
- [ ] 从 `agent.py` 迁移 `COMMANDS` 和 `SlashCompleter`。
- [ ] `agent.py` 改为：

```python
from xcode_cli.core.commands.slash import SlashCompleter
```

- [ ] 保持 prompt 初始化不变：

```python
self.prompt = PromptSession(completer=SlashCompleter(), auto_suggest=AutoSuggestFromHistory())
```

- [ ] 运行：

```bash
pytest tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q
```

预期：通过。

### Task 1.2：迁移 welcome、toolbar、bubble 输出

- [ ] 创建 `src/xcode_cli/core/ui/shell.py`。
- [ ] 增加 `ShellUI`，只承载无业务状态或轻状态 UI：

```python
class ShellUI:
    def __init__(self, console, config_store, context, session_start_getter, tool_count_getter, token_getter, cwd: str) -> None:
        self.console = console
        self.config_store = config_store
        self.context = context
        self._session_start_getter = session_start_getter
        self._tool_count_getter = tool_count_getter
        self._token_getter = token_getter
        self.cwd = cwd
```

- [ ] 迁移这些方法的逻辑：

```text
_render_welcome()
_show_command_suggestions()
_bottom_toolbar()
_print_user_bubble()
_print_assistant_bubble()
_render_assistant_prefix()
```

- [ ] `AgentRuntime` 保留同名薄 wrapper，先委托给 `self.shell_ui`，避免一次性改太多测试：

```python
def _bottom_toolbar(self) -> str:
    return self.shell_ui.bottom_toolbar()
```

- [ ] 运行：

```bash
pytest tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/ui/shell.py src/xcode_cli/core/commands/slash.py
```

预期：通过。

---

## 批次 2：拆审批控制器

**目的：** 把方向键审批菜单、TTY fallback、scope 判断、session auto approve 从 `agent.py` 中抽离，为后续 tool execution 拆分做准备。

**文件：**

- 新增：`src/xcode_cli/core/tooling/__init__.py`
- 新增：`src/xcode_cli/core/tooling/approval.py`
- 修改：`src/xcode_cli/core/agent.py`
- 测试：`tests/test_agent_memory_permissions.py`，可新增 `tests/test_tool_approval.py`

### Task 2.1：创建 ToolApprovalController

- [ ] 创建 `src/xcode_cli/core/tooling/approval.py`。
- [ ] 迁移以下逻辑：

```text
_approval_scope_for_tool()
_read_approval_key()
_render_approval_options()
_refresh_approval_options()
_prompt_tool_approval()
```

- [ ] 设计接口：

```python
class ToolApprovalController:
    def __init__(self, console, auto_approve: dict[str, bool]) -> None:
        self.console = console
        self.auto_approve = auto_approve

    def scope_for_tool(self, tool_name: str) -> str | None:
        ...

    def prompt(self, tool_name: str, scope: str | None) -> str:
        ...
```

- [ ] `AgentRuntime.__init__()` 初始化：

```python
self._session_auto_approve: dict[str, bool] = {"write": False, "shell": False}
self.approval = ToolApprovalController(self.console, self._session_auto_approve)
```

- [ ] `AgentRuntime` 暂时保留 `_approval_scope_for_tool()` 和 `_prompt_tool_approval()` wrapper，委托给 controller，保证现有测试不用大改：

```python
def _approval_scope_for_tool(self, tool_name: str) -> str | None:
    return self.approval.scope_for_tool(tool_name)

def _prompt_tool_approval(self, tool_name: str, scope: str | None) -> str:
    return self.approval.prompt(tool_name, scope)
```

- [ ] 运行：

```bash
pytest tests/test_agent_memory_permissions.py tests/test_agent_tool_loop.py -q
```

预期：通过。

### Task 2.2：补 controller 单元测试

- [ ] 新增 `tests/test_tool_approval.py`，至少覆盖：

```text
write_file -> write
edit_file -> write
run_shell -> shell
read_file -> read_file
session auto approve 命中时直接返回 yes
non-TTY fallback 输入 y/n/a 的映射
```

- [ ] 运行：

```bash
pytest tests/test_tool_approval.py -q
```

预期：通过。

---

## 批次 3：拆 conversation resume / compaction 编排

**目的：** 让 `/resume`、`/compact`、自动 compression 的 checkpoint 写入从 `AgentRuntime` 中移出，统一成 conversation 层服务。

**文件：**

- 新增：`src/xcode_cli/core/conversation/__init__.py`
- 新增：`src/xcode_cli/core/conversation/compaction.py`
- 新增：`src/xcode_cli/core/conversation/resume.py`
- 修改：`src/xcode_cli/core/agent.py`
- 测试：`tests/test_agent_resume_command.py`、`tests/test_context.py`、`tests/test_session_resume.py`

### Task 3.1：创建 ConversationCompactor

- [ ] 创建 `src/xcode_cli/core/conversation/compaction.py`。
- [ ] 迁移 `_find_previous_summary()`。
- [ ] 封装手动 compact：

```python
class ConversationCompactor:
    def __init__(self, context, llm, sessions, console) -> None:
        self.context = context
        self.llm = llm
        self.sessions = sessions
        self.console = console

    def find_previous_summary(self, history: list[dict[str, Any]]) -> str:
        ...

    def compact_history(self, history: list[dict[str, Any]]) -> CompactOutcome:
        ...

    def write_checkpoint(self, session_id: str, outcome: CompactOutcome) -> None:
        ...
```

- [ ] `CompactOutcome` 使用 dataclass：

```python
@dataclass
class CompactOutcome:
    messages: list[dict[str, Any]]
    summary: str
    checkpoint_message: dict[str, Any]
    before_messages: int
    after_messages: int
    before_tokens: int
    after_tokens: int
```

- [ ] `AgentRuntime._handle_compact_command()` 改为调用 compactor，但用户可见输出保持不变。
- [ ] 自动 compression 分支也复用同一套 `compact_history()` + `write_checkpoint()`。
- [ ] 运行：

```bash
pytest tests/test_agent_resume_command.py tests/test_context.py tests/test_session_resume.py -q
```

预期：通过。

### Task 3.2：创建 ResumeCommandService

- [ ] 创建 `src/xcode_cli/core/conversation/resume.py`。
- [ ] 迁移 `_handle_resume_command()` 的列表、数字选择、builder 调用逻辑。
- [ ] 第一批只保持原有数字输入选择，不实现方向键选择；方向键 `/resume` 是后续体验任务。
- [ ] `AgentRuntime._handle_resume_command()` 保留薄 wrapper：

```python
def _handle_resume_command(self) -> None:
    result = self.resume_service.run()
    if result is not None:
        self._history[:] = result.history
        self._session_id = result.session_id
        self._runtime_status.update_session_id(result.session_id)
```

- [ ] 如接口设计更简单，也可以让 service 接收 `history` 引用并直接修改，但要在测试中证明行为不变。
- [ ] 运行：

```bash
pytest tests/test_agent_resume_command.py tests/test_session_resume.py -q
```

预期：通过。

---

## 批次 4：拆 tool call execution

**目的：** 把 `_run_llm_loop()` 中最复杂的 tool call 执行、审批、diff preview、tool result summary、assistant/tool message 构造拆成独立 executor。

**文件：**

- 新增：`src/xcode_cli/core/tooling/execution.py`
- 修改：`src/xcode_cli/core/agent.py`
- 测试：`tests/test_agent_memory_permissions.py`、`tests/test_agent_tool_loop.py`，可新增 `tests/test_tool_execution.py`

### Task 4.1：创建 ToolCallExecutor

- [ ] 创建 `src/xcode_cli/core/tooling/execution.py`。
- [ ] 迁移以下逻辑：

```text
_render_tool_call()
_is_memory_write_tool_call()
_summarize_tool_result()
tool call for-loop 内的 permission / approval / diff preview / execute / result render
assistant_msg 和 tool message 构造
```

- [ ] 设计返回结构：

```python
@dataclass
class ToolExecutionResult:
    assistant_message: dict[str, Any]
    tool_messages: list[dict[str, Any]]
    executed_count: int
```

- [ ] 建议 executor 初始化依赖：

```python
class ToolCallExecutor:
    def __init__(
        self,
        console,
        tools,
        permissions,
        approval,
        memory,
        config_store,
    ) -> None:
        ...
```

- [ ] `execute(response)` 接收 `LLMResponse`，返回 `ToolExecutionResult`。
- [ ] `AgentRuntime._run_llm_loop()` 中只负责：

```python
tool_result = self.tool_executor.execute(response)
history.append(tool_result.assistant_message)
history.extend(tool_result.tool_messages)
self._tool_call_count += tool_result.executed_count
self.sessions.append_message(...)
```

- [ ] 保持 transcript 写入位置可以暂时留在 `AgentRuntime`，不要在这一批强行把 session 写入也塞进 executor。

### Task 4.2：保护审批语义

- [ ] 确保执行顺序仍然是：

```text
render tool call
PermissionManager.check()
deny -> 不执行、不询问、写 denied result
write/edit -> diff preview
memory auto-allow -> 不询问、执行
session auto approve -> 不询问、执行
ask -> 审批菜单
allow -> 直接执行
```

- [ ] 特别注意：memory auto-allow 不能绕过 explicit deny。
- [ ] 运行：

```bash
pytest tests/test_agent_memory_permissions.py tests/test_agent_tool_loop.py -q
```

预期：通过。

### Task 4.3：全量回归

- [ ] 运行：

```bash
pytest -q
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/tooling/approval.py src/xcode_cli/core/conversation/compaction.py src/xcode_cli/core/conversation/resume.py
```

预期：全量通过。

---

## 批次 5：只做准备，不修 streaming 语义

**目的：** 为后续“流式输出重复显示”修复做准备，但本批不改变 streaming 产品行为。

**文件：**

- 可选新增：`src/xcode_cli/core/ui/streaming.py`
- 修改：`src/xcode_cli/core/agent.py`
- 测试：现有全量测试

### Task 5.1：评估是否抽 StreamingTurnState

- [ ] 如果批次 1-4 已经让 `agent.py` 足够清晰，本批可以先不动。
- [ ] 如果 `_run_llm_loop()` 仍然太长，可以只抽一个轻量 `StreamingTurnState`，承载：

```text
content_buffer
reasoning_buffer
start_time
first_text_token_elapsed_ms
thinking Live start/stop
on_token
on_reasoning_token
```

- [ ] 不要在本批修复 final render 重复显示。
- [ ] 不要改变 `response_render_mode` 的行为。
- [ ] 完成后运行：

```bash
pytest -q
```

预期：通过。

---

## 最终验收标准

Coding Agent 完成全部或阶段性批次后，请在交付说明中提供：

- 修改了哪些文件。
- 新增了哪些模块和测试。
- `agent.py` 大致从多少行/多少 KB 降到多少。
- 哪些行为明确保持不变。
- 是否有未完成批次。
- 测试命令和结果。

最低验收命令：

```bash
pytest -q
python -m py_compile src/xcode_cli/core/agent.py
```

如果新增了模块，还要把新增模块加入 `py_compile` 命令。

重点回归：

```bash
pytest tests/test_agent_memory_permissions.py tests/test_agent_tool_loop.py tests/test_agent_resume_command.py tests/test_context.py tests/test_session_resume.py -q
```

---

## 不属于本计划的后续任务

这些任务先不要在本轮顺手实现：

- `/resume` 方向键上下选择 + Enter。
- `/compact` 进度条或动态状态。
- 工具调用 UI 折叠和 `Ctrl+O` 展开。
- streaming token 和 final render 去重。
- CLI `--resume` / `--continue`。
- 把 `core/memory.py` 迁移为 `core/memory/` 包。
- 更新主项目文档。

这些都可以在本轮重构稳定后，由 Codex review 后再开独立任务。
