# Task 工具免审与 UI 展示

## 目标

按 `docs/superpowers/specs/2026-05-28-task-auto-allow-and-ui-design.md` 实现：

1. `task_create` / `task_update` 默认免审（allow）
2. 一轮工具执行完毕后，有 task 变更时渲染 task 面板（状态图标 + 标题）

## 前置约束

- Python >= 3.10，同步模型，不引入 asyncio
- 不改 task 工具本身，只改权限和展示
- 所有用户界面字符串使用中文，代码标识符使用英文

---

## 功能一：权限免审

### 文件：`src/xcode_cli/core/permissions.py`

在 `_default_level()` 方法中，`run_shell` 判断之前加入：

```python
def _default_level(self, tool_name: str) -> str:
    if tool_name in {"task_create", "task_update"}:
        return "allow"
    if tool_name == "run_shell":
        return "ask"
    # ... 其余不变
```

逻辑：task 工具是 Xcode 自管理基础设施，与 memory 同类。用户仍可通过 `settings.json` 显式 deny 覆盖。

### 测试

在 `tests/test_permissions.py` 或现有的 permissions 测试中补充：

- `test_task_create_default_allow`：默认 `task_create` 返回 `allow`
- `test_task_update_default_allow`：默认 `task_update` 返回 `allow`
- `test_task_deny_overrides`：settings.json 中显式 deny `task_create` 生效

---

## 功能二：Task 面板渲染

### 文件：`src/xcode_cli/core/agent.py`

#### 找到 `_run_llm_loop()` 中 `executor.execute()` 调用位置

当前代码结构（大致）：

```python
result = self.executor.execute(response)
# 在此处插入 task 面板渲染
```

#### 插入 task 面板渲染逻辑

```python
result = self.executor.execute(response)

# 渲染 task 面板
self._render_task_panel(response.tool_calls)
```

#### 新增方法 `_render_task_panel`

```python
def _render_task_panel(self, tool_calls) -> None:
    # 检查本轮是否有 task 工具调用
    has_task_tool = any(tc.name in {"task_create", "task_update"} for tc in tool_calls)
    if not has_task_tool:
        return
    
    tasks = self.task_tracker.list_all()
    visible = [t for t in tasks if t.status != "deleted"]
    if not visible:
        return
    
    from rich.panel import Panel
    from rich.table import Table
    
    status_icons = {
        "pending": "◻",
        "in_progress": "◐",
        "completed": "✓",
    }
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2)   # 图标
    table.add_column()           # 标题
    
    for task in visible:
        icon = status_icons.get(task.status, "?")
        # 不同状态用不同颜色
        if task.status == "completed":
            style = "green"
        elif task.status == "in_progress":
            style = "yellow"
        else:
            style = "dim"
        table.add_row(icon, task.subject, style=style)
    
    self.console.print()
    self.console.print(Panel(table, title="Tasks", border_style="cyan"))
```

注意点：
- `tool_calls` 的 `tc.name` 属性——确认是直接属性还是 `.function.name`。通常 OpenAI tool_calls 结构是 `tc.function.name`。需以实际代码为准。
- 只在有非 deleted 任务时才渲染面板。
- 面板上方留空行（`self.console.print()`），与工具结果区域视觉分离。

### 测试

在 `tests/test_task_display.py`（新建）中：

- `test_render_task_panel_with_tasks`：有可见任务时渲染 Panel
- `test_render_task_panel_all_deleted`：全部 deleted 时不渲染
- `test_render_task_panel_no_task_tool`：本轮无 task 工具调用时不渲染
- `test_render_task_panel_icons`：不同状态显示对应图标

测试思路：构造 `AgentRuntime`，在 `task_tracker` 中预设 task，mock console 验证 `console.print` 调用。

---

## 实施顺序

1. `permissions.py`：加两行默认 allow
2. `agent.py`：插入 `_render_task_panel` 方法和调用
3. 补测试
4. `pytest` 全量 + `py_compile` 验证
5. 原生 PowerShell/cmd.exe 手工验收 task 面板

---

## 验收标准

- `task_create` / `task_update` 执行时不触发审批菜单
- settings.json 中 `{"task_create": "deny"}` 仍可拒绝
- 本轮有 task_create 或 task_update → 工具结果后显示 Task 面板
- 面板显示当前所有非 deleted 任务：`[图标] 标题`，不同状态不同颜色
- 全部 deleted 时不显示面板
- `pytest` 全量通过
