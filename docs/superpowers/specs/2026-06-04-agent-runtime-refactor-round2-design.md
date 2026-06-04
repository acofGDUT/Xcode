# AgentRuntime 第二轮重构设计

## 背景

第一轮 AgentRuntime 模块化已经完成了主要服务抽离：

- slash completion：`core/commands/slash.py`
- shell UI：`core/ui/shell.py`
- `/resume`：`core/conversation/resume.py`
- `/compact`：`core/conversation/compaction.py`
- 审批菜单：`core/tooling/approval.py`
- tool call 执行：`core/tooling/execution.py`
- streaming 状态：`core/ui/streaming.py`

但 `src/xcode_cli/core/agent.py` 仍然保留多类职责：

- REPL 主循环。
- slash command 解析和分发。
- `/skill`、`/memory`、`/plan`、`/context`、`/env` 等 command handler。
- 普通 user turn 的 transcript、history、system prompt、runtime status 和 LLM 调用编排。
- `_run_llm_loop()` 的 streaming、Thinking Live、tool loop、task panel、session tool transcript 写入。

下一步准备继续开发 skills 功能。当前 skills 相关逻辑分散在：

- `src/xcode_cli/core/agent.py`：交互式 `/skill ...`
- `src/xcode_cli/main.py`：CLI `xcode skill ...`
- `src/xcode_cli/skills/manager.py`：安装和列表管理
- `src/xcode_cli/core/prompting.py`：enabled skills 注入 system prompt

如果不先做一轮小型分层优化，skills 后续扩展会放大重复逻辑和 `agent.py` 耦合。

## 目标

实现 **AgentRuntime Refactor Round 2**，为后续 skills 功能开发降低耦合。

本轮目标：

1. 抽 `SlashCommandDispatcher`。
2. 抽 `SkillCommandService`，消除 `main.py` 和 `agent.py` 的 skill 重复逻辑。
3. 抽 `_run_user_turn()`，让普通用户输入和 `/init` prompt command 复用同一路径。
4. 保持 `_run_llm_loop()` 暂时不大动。

## 非目标

- 不重写 `_run_llm_loop()`。
- 不改 streaming/render 行为。
- 不改 tool approval 行为。
- 不引入 `asyncio`。
- 不引入抽象基类、事件总线或插件框架。
- 不在本轮实现新的 skills 功能。
- 不改变任何 slash command 的用户可见语义。

## 设计方案

### 1. SlashCommandDispatcher

新增 `src/xcode_cli/core/commands/dispatcher.py`。

职责：

- 接收原始 slash command 文本。
- 解析 command head 和 args。
- 优先处理 prompt command，例如 `/init`。
- 分发 side-effect command，例如 `/help`、`/skill`、`/memory`、`/plan`、`/context`、`/resume`、`/compact`。
- 返回一个明确结果，而不是让 `AgentRuntime` 根据字符串和 `None` 猜测状态。

建议结果模型：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashDispatchResult:
    kind: str
    prompt: str | None = None

    @classmethod
    def handled(cls) -> "SlashDispatchResult":
        return cls(kind="handled")

    @classmethod
    def prompt_command(cls, prompt: str) -> "SlashDispatchResult":
        return cls(kind="prompt", prompt=prompt)
```

第一版可以只需要两种结果：

- `handled`：side-effect command 已处理，REPL 回到下一轮输入。
- `prompt`：需要把 prompt 当作普通 user input 继续执行。

未知命令由 dispatcher 打印 `Unknown command: ...` 后返回 `handled`。

### 2. SkillCommandService

新增 `src/xcode_cli/core/commands/skill.py`。

职责：

- 封装 skill list/install/enable/disable 的业务逻辑。
- 同时供 CLI 和 REPL 调用。
- 统一处理 `ConfigStore.enabled_skills` 写入。
- 统一输出格式。

建议接口：

```python
class SkillCommandService:
    def __init__(self, manager: SkillManager, config_store: ConfigStore, console) -> None:
        ...

    def run(self, parts: list[str]) -> None:
        ...

    def list(self) -> None:
        ...

    def install(self, path: str) -> None:
        ...

    def enable(self, name: str) -> None:
        ...

    def disable(self, name: str) -> None:
        ...
```

CLI `xcode skill ...` 可以直接调用 `install/list/enable/disable` 方法；REPL `/skill ...` 调用 `run(parts)`。

### 3. `_run_user_turn()`

在 `AgentRuntime` 内部抽出：

```python
def _run_user_turn(self, user_input: str) -> None:
    ...
```

职责：

- 写入 session transcript user message。
- 写入轻量 user history。
- 打印 user bubble。
- 追加 `_history` user message。
- 构造当前 system prompt。
- 设置 runtime status 为 busy/idle。
- 调用 `_run_llm_loop()`。
- 处理 LLM 错误。
- 写入 assistant transcript 和 `_history`。
- 如果 plan mode pending approval，显示审批提示。

`run_chat()` 只保留：

- 读取输入。
- 处理空输入、退出、`/` 命令建议。
- 调用 dispatcher。
- 如果 dispatcher 返回 prompt，继续调用 `_run_user_turn(prompt)`。
- 如果是普通用户输入，调用 `_run_user_turn(user_input)`。

### 4. `_run_llm_loop()` 边界

本轮不整体搬迁 `_run_llm_loop()`。

允许做的事情：

- 为适配 `_run_user_turn()` 做最小调用调整。
- 保持现有测试通过。

不允许做的事情：

- 把 Thinking Live、streaming callback、tool execution、task panel、session tool transcript 写入一次性搬到新文件。
- 顺手修改 render mode 行为。
- 顺手修改 tool loop 轮次逻辑。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `src/xcode_cli/core/commands/dispatcher.py` | 新增 slash command dispatcher |
| `src/xcode_cli/core/commands/skill.py` | 新增 `SkillCommandService` |
| `src/xcode_cli/core/agent.py` | 接入 dispatcher/service，抽 `_run_user_turn()`，删除重复 skill handler |
| `src/xcode_cli/main.py` | skill CLI 改用 `SkillCommandService` |
| `tests/test_slash_dispatcher.py` | 新增 dispatcher 行为测试 |
| `tests/test_skill_command_service.py` | 新增 skill service 测试 |
| `tests/test_agent_user_turn.py` | 新增普通 user turn 测试 |
| `docs/current/ARCHITECTURE.md` | 实现后更新当前架构 |
| `docs/current/DEVNOTES.md` | 实现后记录边界和取舍 |
| `docs/current/PROGRESS.md` | 实现后记录验收证据 |

## 测试层级

本轮属于 **P1 结构性重构**。

测试重点：

- 行为不变，而不是覆盖私有实现细节。
- `/help`、`/init`、`/skill`、`/memory`、`/plan`、`/context`、`/resume`、`/compact` 必须保持现有行为。
- CLI `xcode skill ...` 和 REPL `/skill ...` 使用同一服务。
- `/init` 仍作为普通 user turn 写入 `_history` 和 transcript。

## 验收标准

- `agent.py` 行数下降。
- `main.py` 和 `agent.py` 不再重复实现 skill list/install/enable/disable。
- `/help`、`/init`、`/skill`、`/memory`、`/plan`、`/context`、`/resume`、`/compact` 行为不变。
- `_run_llm_loop()` 未被大规模搬迁或重写。
- focused tests 通过。
- 全量 `pytest` 通过。
- `python -m py_compile` 通过。
- `git diff --check` 通过。
- 实现后文档更新 `ARCHITECTURE.md`、`DEVNOTES.md`、`PROGRESS.md`。

## 协作分工

- Coding Agent 执行代码任务，并在每个代码任务后停止，提交 diff 和测试结果给 Codex review。
- Codex 执行文档收口、最终验证、架构 review，不把这些任务交给 Coding Agent。
