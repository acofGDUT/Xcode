# Textual Memory Full Migration Plan

> 本计划交给 Coding Agent 执行。项目默认 SDD：先按本 plan 实现和验证，再由 Codex review，review 通过后由 Codex 同步 `docs/current/*` 权威文档。

## 背景

Textual path 已经具备基础 `/memory` 状态展示，并通过 `RuntimeServices` 创建了 `MemoryManager`。但这还不等于 memory 完整迁移。

Legacy REPL 的 memory 行为包括：

- `build_system_prompt(config, skills, cwd)` 注入 resolved memory paths、Project/User XCODE.md、Auto Memory Index。
- 模型通过普通文件工具 `read_file` / `write_file` / `edit_file` 读写 memory，不提供专用 memory CRUD 工具。
- `write_file` / `edit_file` 命中 resolved memory path 时走 memory-scoped auto-allow；显式 `deny` 仍优先。
- `/memory` 展示 auto-memory、Project/User memory 路径与存在状态、memory dir、memory 文件数和 index entry 数。
- `/memory auto on|off` 会修改 `Config.auto_memory`，后续 system prompt 立即按新配置生效。

本批次目标是让 Textual path 在这些行为上和 legacy 对齐。

## 目标

- Textual 每一轮 LLM 调用使用的 system prompt 必须包含和 legacy 一致的 memory 规则、resolved memory paths 和当前 memory context。
- Textual tool registry 必须暴露 memory 所需的普通文件工具：`read_file`、`write_file`、`edit_file`；不要新增 `memory_save/list/get/delete`。
- Textual 权限路径必须保持 memory-scoped auto-allow，且 explicit `deny` 优先于 memory auto-allow。
- Textual 中模型写入 memory 后，下一轮 system prompt 必须能读取最新 memory 内容或 auto memory index。
- Textual `/memory` 展示和 legacy 语义对齐，并支持 `/memory auto on|off`。
- 测试覆盖 system prompt、工具注册、权限、写入后生效、slash command 展示和配置切换。

## 非目标

- 不引入专用 memory CRUD 工具。
- 不改变 `MemoryManager` 路径模型。
- 不改变 transcript JSONL 格式。
- 不做默认入口切换。
- 不实现 `/memory` 全屏编辑 screen。
- 不引入 asyncio。
- 不要求 Coding Agent 修改 `docs/current/PROGRESS.md`、`ARCHITECTURE.md`、`DEVNOTES.md`、`ROADMAP.md`；这些由 Codex review 后同步。

## 当前差距

已具备：

- `RuntimeServices.system_prompt()` 已调用 `build_system_prompt(self.config_store.load(), self.skills, self.cwd)`。
- `RuntimeServices.create_textual_controller()` 已把 `memory_manager` 传给 `RuntimeController`。
- `RuntimeController._is_memory_write_tool_call()` 已能识别 `write_file` / `edit_file` 的 memory target。
- `RuntimeServices._register_default_tools()` 已注册 `ALL_TOOLS`。
- `/memory` 已有基础只读 notice。

仍需补齐或锁定：

- 缺少 Textual system prompt memory parity 测试。
- 缺少 Textual tool registry memory 工具暴露测试。
- `/memory auto on|off` 在 Textual path 还未实现。
- `/memory` 输出不完整，缺少 Project/User exists/missing、memory dir、memory files、index entries。
- 缺少“Textual 写入 memory 后下一轮 prompt 立即生效”的回归测试。
- 权限测试已有基础覆盖，但需要按 Textual full migration 的验收要求锁定 explicit `deny`、memory auto-allow、普通文件仍审批三类行为。

## 文件范围

优先修改：

- `src/xcode_cli/core/runtime/controller.py`
- `src/xcode_cli/core/runtime/services.py`
- `tests/test_runtime_controller.py`
- `tests/test_textual_slash_commands.py`
- 可新增 `tests/test_textual_memory.py`

原则上不改：

- `src/xcode_cli/core/memory.py`，除非测试暴露真实路径/统计 bug。
- `src/xcode_cli/core/prompting.py`，除非 Textual parity 测试证明 prompt 注入和 legacy 不一致。
- `docs/current/*`，由 Codex review 后同步。

## Task 1：锁定 Textual system prompt memory parity

**目标**：证明 Textual path 使用和 legacy 一致的 `build_system_prompt()` memory 注入。

建议测试：

1. 创建临时项目目录、临时 `.xcode` home。
2. 写入：
   - `<project>/XCODE.md`
   - `<xcode_home>/XCODE.md`
   - auto memory index `MEMORY.md`
3. 通过 `RuntimeServices.create(cwd=...)` 创建服务。
4. 调用 `services.system_prompt()`。
5. 断言包含：
   - `Resolved memory paths for this project`
   - Project XCODE.md resolved path
   - User XCODE.md resolved path
   - Auto memory dir
   - Auto memory index
   - `## Project Memory (XCODE.md)`
   - `## User Memory (XCODE.md)`
   - `## Auto Memory Index`

补充测试：

- `auto_memory=false` 时，Project/User memory 仍注入，Auto Memory Index 不注入。
- Textual controller 实际 submit turn 时，FakeLLM 捕获到的 `system_prompt` 包含上述 memory 内容。

验收：

```powershell
pytest tests/test_textual_memory.py -q
```

## Task 2：锁定 Textual tool registry memory 工具暴露

**目标**：证明 Textual path 暴露 memory 文件模型所需工具，而不是引入旧式 CRUD。

建议测试：

1. 用 `RuntimeServices.create(cwd=...)` 创建服务。
2. 获取 `services.tool_registry.list_names()` 或 `get_openai_schemas()`。
3. 断言包含：
   - `read_file`
   - `write_file`
   - `edit_file`
4. 断言不包含：
   - `memory_save`
   - `memory_list`
   - `memory_get`
   - `memory_delete`

验收：

```powershell
pytest tests/test_textual_memory.py -q
```

## Task 3：补齐 Textual memory 权限 parity

**目标**：Textual permission path 和 legacy 一样：memory-scoped 写入免审，explicit deny 优先，普通文件不被误放行。

建议测试：

1. **memory write auto-allow**
   - 注册 `write_file` fake tool。
   - PermissionManager 默认 `ask`。
   - ToolCall path 指向 `MemoryManager.memory_index_path()` 或 `project_memory_path()`。
   - 调用 `RuntimeController._execute_tools_in_turn()`。
   - 断言没有 `PermissionRequestEvent`，工具成功执行。

2. **explicit deny wins**
   - `PermissionManager.set_session_rule("write_file", "deny")`。
   - 同样写 memory target。
   - 断言工具不执行，返回 `Permission denied for tool: write_file`，并发出 `ToolRejected`。

3. **ordinary file still asks**
   - path 指向普通项目文件。
   - PermissionManager 默认 ask。
   - 在后台线程调用 `_execute_tools_in_turn()`，主测试线程轮询 `controller.drain_events()`，确认发出 `PermissionRequestEvent`。
   - 不要只设置 `controller._permission_provider` 后同步调用 `_execute_tools_in_turn()`；当前 `_request_permission_blocking()` 不会走 provider，会等待 `PermissionDecisionCommand`，测试会卡住。
   - 验证完 `PermissionRequestEvent` 后，用 `CancellationTokenSource.cancel()` 或 dispatch `PermissionDecisionCommand(choice="no")` 释放等待线程，并断言普通文件工具没有执行。

验收：

```powershell
pytest tests/test_runtime_controller.py tests/test_textual_memory.py -q
```

## Task 4：实现并测试 `/memory` slash parity

**目标**：Textual `/memory` 不只是显示路径，而是展示 legacy 同等状态，并支持 `auto on|off`。

实现要求：

- `/memory` 输出至少包含：
  - `Auto-memory: on|off`
  - `Project memory: <path> (exists|missing)`
  - `User memory: <path> (exists|missing)`
  - `Memory dir: <path>`
  - `Memory files: <count> (index: <entries> entries)`
- `/memory auto on`：
  - 设置 `cfg.auto_memory = True`
  - `config_store.save(cfg)`
  - 发出 system notice：`Auto-memory set to on`
- `/memory auto off`：
  - 设置 `cfg.auto_memory = False`
  - `config_store.save(cfg)`
  - 发出 system notice：`Auto-memory set to off`
- 无效参数显示：
  - `Usage: /memory | /memory auto on|off`

注意：

- Textual path 仍可以用 `SystemNoticeAdded` 展示，不要求新增 screen。
- 输出文案应尽量和 legacy 保持一致；如果为了 Textual 风格使用小写 key，需要测试明确锁定最终文案。

建议测试：

- `/memory` 展示完整字段。
- project/user memory exists/missing 状态准确。
- memory files 和 index entries 统计准确。
- `/memory auto off` 后，`ConfigStore.load().auto_memory is False`。
- `/memory auto on` 后，`ConfigStore.load().auto_memory is True`。
- `/memory auto maybe` 返回 usage。

验收：

```powershell
pytest tests/test_textual_slash_commands.py tests/test_textual_memory.py -q
```

## Task 5：写入 memory 后下一轮 system prompt 生效

**目标**：证明 Textual 中模型用 `write_file` / `edit_file` 写入 memory 后，下一轮 LLM 调用能读到最新 memory。

建议测试：

1. 创建 `RuntimeServices` 和 Textual controller。
2. FakeLLM 第一轮返回 `write_file` tool call，目标为 `project_memory_path()` 或 `memory_index_path()`，内容包含唯一标记，例如 `textual-memory-marker-1`。
3. 第一轮工具执行完成。
4. 第二轮 submit 普通消息。
5. FakeLLM 捕获第二轮 `system_prompt`。
6. 断言第二轮 prompt 包含 `textual-memory-marker-1`。

边界：

- 如果写入 auto memory index，确保 `auto_memory=true`。
- 如果写入 Project XCODE.md，则 auto_memory 开关不应影响 Project memory 注入。
- 不要要求同一轮写入后立刻改变本轮已经构建好的 system prompt；生效点是下一轮。

验收：

```powershell
pytest tests/test_textual_memory.py -q
```

## Task 6：Textual `/memory auto` 影响后续 prompt

**目标**：`/memory auto on|off` 不只是保存配置，还会影响后续 Textual prompt 注入。

建议测试：

1. 写入 auto memory index，内容为唯一标记。
2. 运行 `/memory auto off`。
3. 发送一轮普通消息，FakeLLM 捕获 system prompt。
4. 断言不包含 auto memory marker。
5. 运行 `/memory auto on`。
6. 再发送一轮普通消息。
7. 断言包含 auto memory marker。

验收：

```powershell
pytest tests/test_textual_memory.py tests/test_textual_slash_commands.py -q
```

## Task 7：手工验收

在 PowerShell 或 cmd.exe 中执行：

```powershell
xcode chat --textual
```

验收项：

1. 输入 `/memory`，应看到 auto-memory、Project/User memory、memory dir、memory files/index 信息。
2. 输入 `/memory auto off`，再输入 `/memory`，应看到 `Auto-memory: off`。
3. 输入 `/memory auto on`，再输入 `/memory`，应看到 `Auto-memory: on`。
4. 让模型记住一个项目偏好，并写入 Project XCODE.md 或 auto memory index。
5. 开启新一轮对话，询问刚才写入的偏好；模型应能通过 system prompt 或 read_file 找回。
6. 尝试写普通项目文件，仍应出现审批；写 resolved memory path 不应出现普通审批；显式 deny 场景需要自动化测试覆盖即可。

记录结果交给 Codex review。不要在实现未 review 前把 `docs/current/PROGRESS.md` 写成“完成”。

## Task 8：回归验证

至少运行：

```powershell
python -m py_compile src/xcode_cli/core/runtime/controller.py src/xcode_cli/core/runtime/services.py src/xcode_cli/core/prompting.py src/xcode_cli/core/memory.py
pytest tests/test_textual_memory.py tests/test_textual_slash_commands.py tests/test_runtime_controller.py -q
pytest -q
git diff --check
```

期望：

- 所有测试通过。
- 没有 whitespace 错误。
- Textual memory 行为和 legacy 对齐。

## Codex review 重点

- system prompt 是否真的每轮动态读取最新 Config 和 memory 文件。
- 是否误引入 memory CRUD 工具。
- memory auto-allow 是否只覆盖 resolved memory targets。
- explicit `deny` 是否优先于 memory auto-allow。
- `/memory auto on|off` 是否影响后续 prompt，而不是只改变展示。
- Textual UI event 是否没有污染 transcript。
- 文档是否由 Codex review 后同步：`PROGRESS.md`、`ARCHITECTURE.md`、`DEVNOTES.md`，必要时同步 `ROADMAP.md`。
