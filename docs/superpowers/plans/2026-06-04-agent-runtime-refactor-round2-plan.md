# AgentRuntime 第二轮重构实施计划

> **给 agentic workers：** 本计划按任务拆分执行。Coding Agent 只执行 Task 1-3 的代码任务；Task 4-5 由 Codex 负责文档收口、最终验证和 review。每个代码任务完成后必须停下等待 Codex review。

**目标：** 抽出 SlashCommandDispatcher、SkillCommandService 和普通 user turn，降低 `AgentRuntime` 耦合，为后续 skills 功能开发打基础。

**架构：** 本轮只移动命令层和普通 turn glue，不重写 `_run_llm_loop()`。CLI 和 REPL 的 skill 命令共享同一个服务。`AgentRuntime` 保留 REPL orchestration 和 LLM/tool loop 入口。

**技术栈：** Python 3.10+、Typer、prompt_toolkit、Rich、pytest。

---

## 文件结构

| 文件 | 责任 |
|------|------|
| `src/xcode_cli/core/commands/dispatcher.py` | 新增 slash command dispatcher 和 dispatch result |
| `src/xcode_cli/core/commands/skill.py` | 新增 `SkillCommandService` |
| `src/xcode_cli/core/agent.py` | 接入 dispatcher/service，抽 `_run_user_turn()`，减少 command handler glue |
| `src/xcode_cli/main.py` | CLI skill 子命令改用 `SkillCommandService` |
| `tests/test_slash_dispatcher.py` | dispatcher 行为测试 |
| `tests/test_skill_command_service.py` | skill service 行为测试 |
| `tests/test_agent_user_turn.py` | user turn 行为测试 |
| `docs/current/ARCHITECTURE.md` | Codex 在实现后更新 |
| `docs/current/DEVNOTES.md` | Codex 在实现后更新 |
| `docs/current/PROGRESS.md` | Codex 在实现后更新 |

---

## Task 1：抽 SkillCommandService

**执行者：Coding Agent**

**文件：**
- 新建：`src/xcode_cli/core/commands/skill.py`
- 修改：`src/xcode_cli/core/agent.py`
- 修改：`src/xcode_cli/main.py`
- 新建：`tests/test_skill_command_service.py`

### 步骤

- [ ] 写失败测试：`SkillCommandService.list()` 在无 skill 时输出 `No skills installed.`
- [ ] 写失败测试：`install(path)` 调用 `SkillManager.install()` 并输出 installed skill。
- [ ] 写失败测试：`enable(name)` 会写入 `Config.enabled_skills`，重复 enable 不重复添加。
- [ ] 写失败测试：`disable(name)` 会从 `Config.enabled_skills` 删除指定 skill。
- [ ] 实现 `SkillCommandService`。
- [ ] 将 `AgentRuntime._handle_skill_command()` 改为委托 `SkillCommandService.run(parts)`。
- [ ] 将 `main.py` 中 `skill_install/list/enable/disable` 改为调用 `SkillCommandService`。
- [ ] 跑 focused tests：

```powershell
pytest tests/test_skill_command_service.py tests/test_agent_memory_command.py tests/test_prompting_memory.py -q
```

### 验收点

- `main.py` 和 `agent.py` 不再各自实现一套 skill enable/disable/list/install 逻辑。
- `/skill` 用户可见输出不变。
- `xcode skill ...` 用户可见输出不变。
- 不改 `SkillManager` 安装语义；安全 hardening 留给后续 skills foundation 批次。

### Codex Review 点

- 检查是否真的消除了重复逻辑。
- 检查 service 是否没有依赖 `AgentRuntime`。
- 检查测试是否覆盖 CLI/REPL 共享服务的关键行为。

---

## Task 2：抽 SlashCommandDispatcher

**执行者：Coding Agent**

**文件：**
- 新建：`src/xcode_cli/core/commands/dispatcher.py`
- 修改：`src/xcode_cli/core/agent.py`
- 新建：`tests/test_slash_dispatcher.py`
- 可能修改：`tests/test_init_command.py`

### 步骤

- [ ] 写失败测试：`/init` dispatch 返回 `kind="prompt"` 和 `INIT_PROMPT`。
- [ ] 写失败测试：`/help` dispatch 返回 `kind="handled"`，并调用 help 展示回调。
- [ ] 写失败测试：未知命令打印 `Unknown command` 并返回 `kind="handled"`。
- [ ] 写失败测试：`/skill list` 会委托 `SkillCommandService.run(parts)`。
- [ ] 实现 `SlashDispatchResult` 和 `SlashCommandDispatcher`。
- [ ] `AgentRuntime.__init__()` 中创建 dispatcher。
- [ ] `run_chat()` 中调用 dispatcher，不再直接调用 `_handle_slash_command()`。
- [ ] 删除或缩小 `AgentRuntime._handle_slash_command()`；如果保留，只作为 dispatcher 兼容 wrapper。
- [ ] 跑 focused tests：

```powershell
pytest tests/test_slash_dispatcher.py tests/test_init_command.py tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py -q
```

### 验收点

- `/init` 仍进入普通 user turn。
- side-effect commands 仍直接处理后回到输入循环。
- `/help`、`/context`、`/env`、`/plan`、`/memory`、`/resume`、`/compact` 行为不变。
- dispatcher 不知道 LLM/tool loop 细节。

### Codex Review 点

- 检查 dispatcher 结果模型是否清晰。
- 检查 `AgentRuntime` 是否变薄，而不是把复杂度换个名字塞回去。
- 检查现有 tests 是否仍能证明 side-effect command 不进入 LLM turn。

---

## Task 3：抽 `_run_user_turn()`

**执行者：Coding Agent**

**文件：**
- 修改：`src/xcode_cli/core/agent.py`
- 新建：`tests/test_agent_user_turn.py`
- 可能修改：`tests/test_init_command.py`

### 步骤

- [ ] 写失败测试：`_run_user_turn("hello")` 会写入 `_history` user 和 assistant。
- [ ] 写失败测试：`_run_user_turn(INIT_PROMPT)` 行为与普通 prompt 相同。
- [ ] 写失败测试：LLM missing key/error 结果不追加 assistant 到 `_history`。
- [ ] 抽出 `_run_user_turn(user_input: str) -> None`。
- [ ] `run_chat()` 中普通输入和 dispatcher prompt result 都调用 `_run_user_turn()`。
- [ ] 保持 `_run_llm_loop()` 原地不动。
- [ ] 跑 focused tests：

```powershell
pytest tests/test_agent_user_turn.py tests/test_init_command.py tests/test_agent_tool_loop.py tests/test_task_display.py -q
```

### 验收点

- `run_chat()` 行数下降，主要负责 REPL 输入循环。
- `_run_user_turn()` 成为普通 turn 的唯一入口。
- `/init`、未来外部入口、未来 session fork 都可以复用该方法。
- `_run_llm_loop()` 不做整体迁移。

### Codex Review 点

- 检查是否存在第二条普通 turn 路径。
- 检查 LLM 错误处理是否和旧逻辑一致。
- 检查 plan mode pending approval 逻辑是否保持。

---

## Task 4：文档收口

**执行者：Codex**

**文件：**
- 修改：`docs/current/ARCHITECTURE.md`
- 修改：`docs/current/DEVNOTES.md`
- 修改：`docs/current/PROGRESS.md`
- 必要时修改：`docs/current/ROADMAP.md`

### 步骤

- [ ] 更新 `ARCHITECTURE.md`：
  - 记录 `SlashCommandDispatcher`。
  - 记录 `SkillCommandService`。
  - 记录 `_run_user_turn()` 和 `_run_llm_loop()` 的边界。
- [ ] 更新 `DEVNOTES.md`：
  - 记录第二轮重构边界。
  - 记录 `_run_llm_loop()` 暂不搬迁的原因。
- [ ] 更新 `PROGRESS.md`：
  - 标记 AgentRuntime Refactor Round 2 完成。
  - 写入测试证据。
- [ ] 如状态变化，更新 `ROADMAP.md`。

---

## Task 5：最终验证与 review

**执行者：Codex**

### 验证命令

```powershell
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/skill.py src/xcode_cli/main.py
pytest tests/test_skill_command_service.py tests/test_slash_dispatcher.py tests/test_agent_user_turn.py tests/test_init_command.py tests/test_agent_env.py tests/test_agent_memory_command.py tests/test_agent_resume_command.py tests/test_agent_tool_loop.py tests/test_task_display.py -q
pytest -q
git diff --check
```

### 最终 review 清单

- [ ] `agent.py` 行数下降。
- [ ] `main.py` 和 `agent.py` 没有重复 skill 业务逻辑。
- [ ] `/help`、`/init`、`/skill`、`/memory`、`/plan`、`/context`、`/resume`、`/compact` 行为不变。
- [ ] `_run_user_turn()` 是普通 user turn 的唯一入口。
- [ ] `_run_llm_loop()` 没有被大规模重写。
- [ ] 文档与实现一致。
- [ ] 没有覆盖或回滚用户已有脏工作区改动。

---

## 执行要求

- Coding Agent 每完成 Task 1、Task 2、Task 3 中任意一个任务后必须停止，提交 diff 和测试结果给 Codex review。
- Coding Agent 不执行 Task 4 和 Task 5。
- Codex review 通过后才能进入下一个代码任务。
- 如果任一任务需要改 `_run_llm_loop()`，必须先暂停并说明原因。
