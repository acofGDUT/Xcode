# 输出与工具轮次稳定化实施计划

> **给 Coding Agent：** 请按本文分批执行。你只负责代码和测试，不更新 README / ARCHITECTURE / DEVNOTES / PROGRESS / ROADMAP / 日期计划 等主项目文档；实现完成后把变更、测试结果、未完成项和风险点交给 Codex review，由 Codex 统一更新文档和 git。

**目标：** 同时收口 3 个 P1 问题：工具调用 UI 折叠、工具调用轮次不中断、流式输出去重。

**架构：** 在第一轮 AgentRuntime 模块化基础上继续拆 `agent.py`。本任务已落地 `core/ui/streaming.py` 管理 Thinking、token buffer、是否流式打印和最终渲染；增强 `core/tooling/execution.py` 的工具调用显示状态；把 `_run_llm_loop()` 收口到 context-budget 驱动的多轮 tool loop。保持同步实现，不引入 `asyncio`。

**技术栈：** Python 3.10+、pytest、Rich、prompt_toolkit、现有同步 `AgentRuntime`、OpenAI-compatible tool calling。

---

## 总约束

- 不引入 `asyncio`。
- 不改变 tool message / assistant tool_calls 的 OpenAI-compatible 结构。
- 不改变权限语义：显式 `deny` 优先于 memory auto-allow 和 session auto-approve。
- 不改变 `/resume`、`/compact`、memory 自管理权限和 transcript 格式。
- 不更新主项目文档，只写代码和测试。
- 不为了 UI 折叠隐藏 diff preview、审批菜单、危险命令预览或工具错误。
- 不新增固定 tool round 上限。单次 turn 可以执行任意多轮 tool calls，由 context budget、用户中断和模型最终停止自然限制。
- 如实现 `Ctrl+O` 有 TTY 风险，先保留可测试的显示状态接口和非 TTY fallback，不要为了快捷键破坏 prompt 输入或审批菜单。

---

## 设计结论

### 1. 工具轮次不中断

当前实现已改为 `while True` 的多轮 tool loop，本轮收口重点是用测试锁定该行为：

- 每轮开始先做 context compression 检查。
- 如果 compression 后仍超过预算，由 `ContextManager` 和后续 LLM 请求自然处理，不新增隐藏轮次上限。
- 每轮 LLM 返回 tool_calls 时，执行工具、追加 assistant/tool messages、写 transcript，然后继续下一轮。
- 如果 LLM 返回无 tool_calls，正常返回 final text。
- 如果 LLM 返回空文本且无 tool_calls，返回一个可读 fallback，例如 `"No response."`，不要让用户误以为卡住。
- `KeyboardInterrupt` 仍返回 `"Interrupted."`。

### 2. 流式输出去重

推荐做“智能流式”而不是继续“先完整流式，再完整 Rich render”：

- `buffer_then_render`：不流式打印 token，完整收完后 Rich render。
- `streaming_plus_final_render`：
  - 默认可以先流式打印普通文本。
  - 一旦检测到内容需要最终 Rich render，例如出现 fenced code block、Markdown table、标题等结构化 Markdown，停止继续向下流式打印后续 token，只继续 buffer。
  - 最终如果发生过“停止流式并等待 final render”，则只渲染完整最终版本，不再继续把剩余 token raw 打印出来。
  - 如果全程都是普通文本且已经流式打印完，则 final 阶段不再二次完整渲染。

第一版不要求回收已经打印出的少量前缀；重点是避免“一整段 raw + 一整段 Rich”双份输出。

### 3. 工具调用 UI 折叠

第一版先实现默认折叠摘要：

```text
  tools: 3 calls: read_file, grep, glob
```

展开模式保留原格式：

```text
  ## tool.read_file
    path: D:\Xcode\...
```

要求：

- 默认折叠普通工具调用详情。
- dangerous tools 仍必须醒目出现在摘要中：`write_file`、`edit_file`、`run_shell`。
- diff preview、command preview、审批菜单、工具结果摘要不折叠。
- 提供可测试的显示状态，例如 `ToolDisplayState(expanded=False)`。
- `Ctrl+O` 可以作为后续 TTY 增强；如果本轮实现，必须保留非 TTY fallback，并在交付说明中明确是否完成了原生 Windows 验收。

---

## 目标文件结构

```text
src/xcode_cli/core/
  agent.py                         # 保留 REPL + LLM loop orchestration
  ui/
    streaming.py                   # 已新增：StreamingTurnRenderer / StreamingTurnResult
  tooling/
    execution.py                   # 增强：工具调用显示状态、摘要/展开渲染
    display.py                     # 可选：如果 execution.py 过长，可把 tool display 拆到这里
tests/
  test_agent_tool_loop.py          # 增强：任意多轮工具调用、拒绝/异常后继续
  test_streaming_renderer.py       # 已新增：流式去重状态机
  test_tool_display.py             # 已新增：工具调用折叠/展开摘要
```

如果实现时发现 `execution.py` 仍可读，可以不新建 `tooling/display.py`；但 tool display 逻辑必须有单元测试。

---

## 批次 0：补当前行为安全网

**目的：** 先锁定三条核心行为，再改实现。

**文件：**

- 修改：`tests/test_agent_tool_loop.py`
- 新增：`tests/test_streaming_renderer.py`
- 新增：`tests/test_tool_display.py`

### Task 0.1：补“超过 10 轮仍继续”的回归测试

- [x] 修改 `tests/test_agent_tool_loop.py`。
- [x] 把旧 max-rounds 语义改成“第 11 或第 12 次 LLM 调用后仍可返回 final text”，断言不会停在轮次上限错误。

建议测试：

```python
def test_llm_loop_allows_more_than_ten_tool_rounds(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] <= 12:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id=f"call_{calls[0]}", name="read_file", args={"path": "x"})],
            )
        return LLMResponse(content="final after many tools", tool_calls=[])

    agent.llm.complete = fake_complete
    agent.tools._tools["read_file"].execute = lambda **kwargs: "ok"

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "final after many tools"
    assert calls[0] == 13
    assert len([m for m in history if m.get("role") == "tool"]) == 12
```

- [x] 运行：

```bash
pytest tests/test_agent_tool_loop.py::test_llm_loop_allows_more_than_ten_tool_rounds -q
```

验收结果：已通过。当前实现已不存在固定 10 轮上限。

### Task 0.2：补工具拒绝后继续生成最终回复测试

- [x] 在 `tests/test_agent_tool_loop.py` 增加测试：`run_shell` 审批返回 `no` 后，模型第二轮收到 tool result 并返回最终文本。

建议测试：

```python
def test_llm_loop_continues_after_user_denies_tool(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    calls = [0]

    def fake_complete(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_shell", name="run_shell", args={"command": "echo hi"})],
            )
        assert any(
            m.get("role") == "tool" and "User denied tool" in str(m.get("content", ""))
            for m in kwargs["messages"]
        )
        return LLMResponse(content="I will continue without shell.", tool_calls=[])

    agent.llm.complete = fake_complete
    monkeypatch.setattr(agent.approval, "prompt", lambda tool_name, scope: "no")

    history: list[dict] = []
    result = agent._run_llm_loop(history, "system")

    assert result == "I will continue without shell."
    assert calls[0] == 2
```

- [x] 运行：

```bash
pytest tests/test_agent_tool_loop.py::test_llm_loop_continues_after_user_denies_tool -q
```

验收结果：已通过。

### Task 0.3：补 streaming 去重状态测试

- [x] 新增 `tests/test_streaming_renderer.py`。
- [x] 为 `StreamingTurnRenderer` 建立状态测试。
- [x] 覆盖普通文本：token 可以被流式打印，final 阶段不应再次 Rich render。
- [x] 覆盖代码块：检测到 ```` ``` ```` 后停止后续 raw streaming，final 阶段渲染完整内容一次。

建议测试轮廓：

```python
from xcode_cli.core.ui.streaming import StreamingTurnRenderer


class _ConsoleSpy:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def print(self, *args, **kwargs) -> None:
        self.events.append((args, kwargs))


def test_plain_streaming_does_not_final_render_again() -> None:
    console = _ConsoleSpy()
    renderer = StreamingTurnRenderer(console, render_mode="streaming_plus_final_render", render_markdown=lambda text: console.print("render", text))

    renderer.on_text_token("hello")
    renderer.on_text_token(" world")
    result = renderer.finish("hello world")

    assert result.printed_stream is True
    assert result.needs_final_render is False
    assert not any(args and args[0] == "render" for args, _ in console.events)


def test_structured_markdown_stops_streaming_and_final_renders_once() -> None:
    console = _ConsoleSpy()
    renderer = StreamingTurnRenderer(console, render_mode="streaming_plus_final_render", render_markdown=lambda text: console.print("render", text))

    renderer.on_text_token("Here is code:\n")
    renderer.on_text_token("```python\n")
    renderer.on_text_token("print('hi')\n```")
    result = renderer.finish("Here is code:\n```python\nprint('hi')\n```")

    assert result.needs_final_render is True
    render_events = [args for args, _ in console.events if args and args[0] == "render"]
    assert len(render_events) == 1
```

- [x] 运行：

```bash
pytest tests/test_streaming_renderer.py -q
```

验收结果：已通过，模块和测试均已落地。

### Task 0.4：补工具显示折叠测试

- [x] 新增 `tests/test_tool_display.py`。
- [x] 新建 `core/tooling/display.py` 并为其补单元测试。
- [x] 覆盖：
  - 多个工具调用折叠成一行摘要。
  - expanded 模式保留 `## tool.name` 和参数。
  - dangerous tools 在摘要中可见。

建议测试轮廓：

```python
from xcode_cli.core.llm import ToolCall
from xcode_cli.core.tooling.display import ToolCallDisplay, ToolDisplayState


def test_collapsed_tool_summary_lists_count_and_names() -> None:
    display = ToolCallDisplay(ToolDisplayState(expanded=False))
    calls = [
        ToolCall(id="1", name="read_file", args={"path": "a.py"}),
        ToolCall(id="2", name="grep", args={"pattern": "foo"}),
        ToolCall(id="3", name="glob", args={"pattern": "*.py"}),
    ]

    lines = display.render_calls(calls)

    assert lines == ["tools: 3 calls: read_file, grep, glob"]


def test_expanded_tool_display_includes_arguments() -> None:
    display = ToolCallDisplay(ToolDisplayState(expanded=True))
    calls = [ToolCall(id="1", name="read_file", args={"path": "a.py"})]

    lines = display.render_calls(calls)

    assert any("## tool.read_file" in line for line in lines)
    assert any("path:" in line and "a.py" in line for line in lines)


def test_collapsed_summary_marks_dangerous_tools() -> None:
    display = ToolCallDisplay(ToolDisplayState(expanded=False))
    calls = [ToolCall(id="1", name="write_file", args={"path": "a.py", "content": "x"})]

    lines = display.render_calls(calls)

    assert "write_file" in lines[0]
    assert "danger" in lines[0].lower()
```

- [x] 运行：

```bash
pytest tests/test_tool_display.py -q
```

验收结果：已通过，`ToolCallDisplay` 已落地。

---

## 批次 1：实现 streaming 去重并抽 `ui/streaming.py`

**目的：** 把 `_run_llm_loop()` 里的 token buffer、Thinking Live、final render 判断迁移到可测试模块，并修复重复输出。

**文件：**

- 已新增：`src/xcode_cli/core/ui/streaming.py`
- 修改：`src/xcode_cli/core/agent.py`
- 测试：`tests/test_streaming_renderer.py`

### Task 1.1：创建 StreamingTurnRenderer

- [x] 新增 `src/xcode_cli/core/ui/streaming.py`。
- [x] 实现 `StreamingTurnResult`：

```python
from dataclasses import dataclass


@dataclass
class StreamingTurnResult:
    content: str
    reasoning_content: str
    printed_stream: bool
    needs_final_render: bool
```

- [x] 实现 `StreamingTurnRenderer`，最低接口：

```python
class StreamingTurnRenderer:
    def __init__(self, console, render_mode: str, render_markdown) -> None:
        self.console = console
        self.render_mode = render_mode
        self.render_markdown = render_markdown
        self.content_buffer: list[str] = []
        self.reasoning_buffer: list[str] = []
        self.printed_stream = False
        self._streaming_stopped_for_final_render = False

    def on_text_token(self, token: str) -> None:
        ...

    def on_reasoning_token(self, token: str) -> None:
        ...

    def finish(self, final_text: str) -> StreamingTurnResult:
        ...
```

- [x] 结构化 Markdown 检测第一版使用简单启发式：

```python
def _needs_rich_render(text: str) -> bool:
    return "```" in text or "\n|" in text or "\n#" in text or text.startswith("#")
```

- [x] 规则：
  - `buffer_then_render`：`on_text_token()` 只 buffer，不打印。
  - `streaming_plus_final_render` 普通文本：流式打印，`finish()` 不调用 `render_markdown`。
  - `streaming_plus_final_render` 检测到结构化内容：停止继续 raw print，`finish()` 调用 `render_markdown(final_text)` 一次。
  - 所有 `console.print(..., markup=False)` 仍保留，避免 Rich markup 注入。

### Task 1.2：AgentRuntime 接入 renderer

- [x] 修改 `src/xcode_cli/core/agent.py`。
- [x] `_run_llm_loop()` 中保留 Thinking Live，并把 token buffer / final render 判断交给 `StreamingTurnRenderer`。
- [x] `render_markdown` 用 lambda 包装现有 `_print_assistant_bubble()`：

```python
renderer = StreamingTurnRenderer(
    self.console,
    render_mode=render_mode,
    render_markdown=lambda text: self._print_assistant_bubble(text),
)
```

- [x] `on_token()` 继续负责首次 token 停止 Thinking、打印 assistant prefix；然后调用 `renderer.on_text_token(token)`。
- [x] `response = self.llm.complete(... on_text_token=on_token, on_reasoning_token=on_reasoning_token)`。
- [x] `not response.tool_calls` 分支已接入 `renderer.finish(...)`。

```python
final_text = response.content or ""
turn_result = renderer.finish(final_text)
if final_text and turn_result.needs_final_render:
    if not assistant_turn_started:
        self._render_assistant_prefix()
        assistant_turn_started = True
    self._print_assistant_bubble(final_text)
return final_text
```

当前收口：`finish()` 在结构化内容场景下直接执行 `render_markdown(final_text)`；agent 仅在 `buffer_then_render` 模式下补最终 assistant bubble，避免再次双重渲染。

### Task 1.3：验证

- [x] 运行：

```bash
pytest tests/test_streaming_renderer.py -q
pytest tests/test_agent_tool_loop.py -q
```

验收结果：已通过。

---

## 批次 2：移除固定工具轮次上限

**目的：** 让一次 turn 能执行任意多轮工具调用，不被 `max_tool_rounds = 10` 截断。

**文件：**

- 修改：`src/xcode_cli/core/agent.py`
- 测试：`tests/test_agent_tool_loop.py`

### Task 2.1：改 `_run_llm_loop()` 为 context-budget driven

- [x] 删除：

```python
max_tool_rounds = 10
for _ in range(max_tool_rounds):
```

- [x] 改为：

```python
tool_round = 0
while True:
    tool_round += 1
    ...
```

- [x] 不要新增新的固定轮数上限。
- [x] 每轮 tool calls 执行后继续循环。
- [ ] 可以增加 dim 状态输出：

```python
self.console.print(f"[dim]tool round {tool_round}: {len(response.tool_calls)} call(s)[/dim]")
```

如果担心噪音，可以只在 debug/config 后续实现；本轮不强制。

### Task 2.2：处理空响应 fallback

- [x] 在 `if not response.tool_calls:` 分支中，如果 `final_text == ""`，返回可读文本：

```python
if not final_text:
    return "No response."
```

- [x] 不要写假 assistant tool_calls。
- [x] `run_chat()` 会把该 assistant 文本写入 transcript。

### Task 2.3：删除旧 max-rounds 测试并验证新语义

- [x] 删除或改写旧 max-rounds 测试。
- [x] 确保 `test_llm_loop_allows_more_than_ten_tool_rounds` 通过。
- [x] 增加空响应测试：

```python
def test_llm_loop_empty_response_returns_readable_fallback(tmp_path: Path, monkeypatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent.llm.complete = lambda **kwargs: LLMResponse(content="", tool_calls=[])

    result = agent._run_llm_loop([], "system")

    assert result == "No response."
```

- [x] 运行：

```bash
pytest tests/test_agent_tool_loop.py -q
```

验收结果：已通过。

---

## 批次 3：工具调用 UI 折叠

**目的：** 默认把连续 tool calls 从逐条完整参数刷屏改成一行摘要，同时保留展开能力和危险操作可见性。

**文件：**

- 新增：`src/xcode_cli/core/tooling/display.py`
- 修改：`src/xcode_cli/core/tooling/execution.py`
- 修改：`src/xcode_cli/core/agent.py`（如需要持有显示状态）
- 测试：`tests/test_tool_display.py`、`tests/test_agent_memory_permissions.py`

### Task 3.1：实现 ToolCallDisplay

- [x] 新增 `src/xcode_cli/core/tooling/display.py`。
- [x] 实现：

```python
from dataclasses import dataclass
from typing import Any


DANGEROUS_TOOLS = {"write_file", "edit_file", "run_shell"}


@dataclass
class ToolDisplayState:
    expanded: bool = False


class ToolCallDisplay:
    def __init__(self, state: ToolDisplayState) -> None:
        self.state = state

    def render_calls(self, tool_calls: list[Any]) -> list[str]:
        if self.state.expanded:
            return self._render_expanded(tool_calls)
        return [self._render_summary(tool_calls)]
```

- [x] `_render_summary()` 输出示例：

```text
tools: 3 calls: read_file, grep, glob
tools: 2 calls: read_file, write_file [danger]
```

- [x] `_render_expanded()` 保留现有 `## tool.name` 和参数截断逻辑。

### Task 3.2：ToolCallExecutor 接入折叠显示

- [x] 修改 `ToolCallExecutor.__init__()`，接收 `tool_display: ToolCallDisplay | None = None`。
- [x] `execute(response)` 开始时统一渲染本轮 tool call 列表：

```python
self._render_tool_calls(response.tool_calls)
```

- [x] 删除默认逐条 `_render_tool_call()` 打印。
- [x] 对每个工具的 diff preview、command preview、approval、result summary 保持原样。
- [x] expanded 模式输出保持与原格式接近。

### Task 3.3：AgentRuntime 持有显示状态

- [x] 在 `AgentRuntime.__init__()` 增加：

```python
from xcode_cli.core.tooling.display import ToolCallDisplay, ToolDisplayState

self.tool_display_state = ToolDisplayState(expanded=False)
self.tool_display = ToolCallDisplay(self.tool_display_state)
```

- [x] 初始化 `ToolCallExecutor(..., tool_display=self.tool_display)`。
- [x] 本轮未实现 `Ctrl+O`，保留默认折叠和展开状态模型。
- [x] `Ctrl+O` 作为原生 TTY 增强留后续。

### Task 3.4：验证

- [x] 运行：

```bash
pytest tests/test_tool_display.py -q
pytest tests/test_agent_memory_permissions.py -q
```

验收结果：已通过。memory 写入相关测试未因折叠而丢失 diff preview / approval 行为。

---

## 批次 4：集成回归与交付说明

**目的：** 确保三件 P1 能力没有互相打架。

**文件：**

- 修改：必要时补 `tests/test_agent_tool_loop.py`
- 不修改主项目文档

### Task 4.1：重点回归

- [x] 运行：

```bash
pytest tests/test_agent_tool_loop.py tests/test_streaming_renderer.py tests/test_tool_display.py tests/test_agent_memory_permissions.py tests/test_agent_resume_command.py -q
```

验收结果：已通过，重点回归结果为 `40 passed`。

### Task 4.2：全量验证

- [ ] 运行：

```bash
pytest -q
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/ui/streaming.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/tooling/display.py
```

当前状态：相关 `py_compile` 已通过；本轮只补跑了重点回归，是否再做一次全量 `pytest -q` 取决于后续提交窗口。

### Task 4.3：交付说明

Coding Agent 完成后，请交付：

- 改了哪些文件。
- 三个 P1 分别完成到什么程度：
  - 工具调用 UI 折叠。
  - 工具调用轮次不中断。
  - 流式输出去重。
- 是否实现了 `Ctrl+O`。如果没有，实现了什么 fallback。
- 是否仍需要原生 cmd.exe/PowerShell 手工验收。
- 测试命令和结果。

---

## 不属于本轮的任务

- 不更新主项目文档。
- 不实现 `/context` cost。
- 不实现 `/compact` 进度条。
- 不实现 `/resume` 方向键选择。
- 不实现 command handlers 第二轮拆分。
- 不做 CLI `--resume` / `--continue`。
- 不做 Phase 5 / Phase 6。

---

## Codex 验收补记

- 已补回归：`buffer_then_render` 模式下最终回答必须真正渲染到终端；新增 `test_llm_loop_buffer_then_render_prints_final_answer`，并完成最小修复。
- 重点验证结果：
  - `pytest tests/test_agent_tool_loop.py tests/test_streaming_renderer.py tests/test_tool_display.py tests/test_agent_memory_permissions.py tests/test_agent_resume_command.py -q`
  - 结果：`40 passed`
  - `python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/ui/streaming.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/tooling/display.py`
  - 结果：通过
- 当前未完成项只剩原生 Windows 手工 E2E、`Ctrl+O` 展开、`/compact` 进度反馈和 `/resume` 方向键选择，这些本来就不属于本轮交付范围。
