# Task 工具免审与 UI 展示

## 目标

1. `task_create` / `task_update` 免用户审批（Xcode 自管理基础设施，同 memory）
2. 一轮工具执行完毕后，若有 task 变更，汇总展示 task 列表（状态图标 + 标题）

## 权限：默认 allow

### 改动

`PermissionManager._default_level()` 加两行：

```python
if tool_name in {"task_create", "task_update"}:
    return "allow"
```

### 理由

- task 工具是 Xcode 的自我管理工具，不操作用户文件，和 memory 同类
- `task_list` 已通过 `is_read_only=True` 被 allow，现在补齐另外两个
- 用户仍可通过 `settings.json` 显式 deny

## 展示：轮次结束后汇总 task 面板

### 触发时机

`agent.py` 的 `_run_llm_loop()` 中，`executor.execute()` 返回后，检查本轮是否有 `task_create` 或 `task_update` 调用。有则渲染。

### 渲染内容

`self.task_tracker.list_all()` → 过滤掉 `deleted` 状态 → 渲染为 Rich Panel。

```
┌─ Tasks ──────────────────────────────────────────┐
│  ◐ 添加用户认证模块                               │
│  ✓ 修复登录 bug                                   │
│  ◻ 更新文档                                       │
└──────────────────────────────────────────────────┘
```

状态图标：

| status | 图标 |
|--------|------|
| pending | ◻ |
| in_progress | ◐ |
| completed | ✓ |
| deleted | 不展示 |

面板上方留空行，与工具结果区域视觉分离。

只有非空 task 列表才渲染，全部 deleted 时不渲染。

### 渲染位置

`executor.execute()` 返回后、下一轮 LLM 调用前。即在 tool results 输出和下一轮 thinking 之间。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `src/xcode_cli/core/permissions.py` | `_default_level()` 加 `task_create` / `task_update` → allow |
| `src/xcode_cli/core/agent.py` | `_run_llm_loop()` 中工具执行后检查 task 变更并渲染面板 |

## 验收标准

- `task_create` / `task_update` 执行时不出审批菜单
- 用户仍可在 `.xcode/settings.json` 中设置 `{"task_create": "deny"}` 覆盖
- 一轮工具调用包含 task_create 时，工具结果输出后渲染 task 面板
- 面板显示当前所有非 deleted 任务，每行 `[图标] [标题]`
- 面板使用 Rich Panel 样式，终端可见且美观
- `task_list` 行为不变（已经是 allow + 只读）
- `pytest` 全量通过
- 原生 PowerShell/cmd.exe 手工验收 task 面板显示
