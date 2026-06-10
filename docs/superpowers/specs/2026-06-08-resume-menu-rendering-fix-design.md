# `/resume` 长列表重复渲染修复设计

> 本文定义 `/resume` 方向键菜单在长 session 列表、窄终端和中文预览下重复渲染/旧行残留的修复方案。当前任务只写 spec 和 plan，不直接修改功能代码。

## 背景

`/resume` 已经从数字输入升级为 TTY 方向键菜单。当前实现位于 `src/xcode_cli/core/conversation/resume.py`：

- `_render_session_list()` 使用 `console.print()` 渲染 header 和所有 session。
- `_refresh_session_list()` 使用手写 ANSI：上移 `len(sessions) + 1` 行、逐行清空、再重绘。

这套刷新方式隐含两个假设：

- 每个 session item 实际只占一行。
- 整个 session 列表都在终端可视区域内。

当 session 很多、终端较窄、`last_user_input` 含中文宽字符或被 Rich/终端换行时，上述假设会失效，导致旧行没有被完全清理，用户看到重复渲染或残留内容。

## 目标

- 修复 `/resume` TTY 菜单长列表方向键滚动时的重复渲染/旧行残留。
- 保持现有用户行为：↑/↓ 或 `k/j` 浏览，Enter 恢复，Esc/q 取消，数字快捷键可用，非 TTY 继续走数字输入 fallback。
- 列表项仍显示 session 更新时间、预览文本和 checkpoint 标记。
- 不改变 session transcript、resume builder、token budget 和恢复后的 `_history` 语义。
- 不引入 `asyncio`。

## 非目标

- 不做 CLI `--resume` / `--continue`。
- 不改 session schema。
- 不在本轮重做完整 TUI 框架。
- 不要求真实恢复大量历史内容，只修复选择菜单渲染。

## 推荐方案

第一版采用固定高度窗口，而不是全量渲染所有 session。

核心思路：

- TTY 菜单最多显示固定数量的 session，例如 9 条。
- 当 session 总数超过窗口高度时，只渲染当前选中项附近的一段窗口。
- header 显示当前位置，例如 `Select session to resume: 12/80`。
- footer 显示操作提示，例如 `↑/↓ move · Enter resume · Esc cancel`。
- 每个 item 的预览先做单行化，再按显示宽度截断，避免自动换行。
- `_refresh_session_list()` 只清理固定行数：`header + visible_rows + footer`。

这样即使真实 session 数量很多，刷新区域高度也稳定，不会因为全量列表超过屏幕而残留。

## 渲染窗口规则

建议默认：

```python
VISIBLE_RESUME_ROWS = 9
```

窗口计算：

- `total <= VISIBLE_RESUME_ROWS`：从 0 开始显示全部。
- `total > VISIBLE_RESUME_ROWS`：
  - 尽量让 selected 居中。
  - 靠近顶部时窗口从 0 开始。
  - 靠近底部时窗口以 `total - VISIBLE_RESUME_ROWS` 结束。

伪代码：

```python
def _visible_window(total: int, selected: int, limit: int) -> tuple[int, int]:
    if total <= limit:
        return 0, total
    half = limit // 2
    start = max(0, selected - half)
    start = min(start, total - limit)
    return start, start + limit
```

## 单行预览规则

预览必须稳定占一行：

- 把 `\r`、`\n`、`\t` 等空白归一化为空格。
- 使用显示宽度友好的截断，而不是只按 Python 字符数截断。
- 如暂不引入第三方依赖，可用 `wcwidth` 如果项目已有依赖；否则先用保守字符数截断，并在实现中预留 helper。
- 不允许 Rich markup 解析用户输入，渲染时保持 `markup=False` 或确保内容经过 escape。

建议 helper：

```python
def _single_line_preview(text: str | None, max_chars: int = 60) -> str:
    ...
```

## ANSI 刷新边界

如果继续使用 ANSI 清屏：

- `_render_session_list()` 应返回或记录本轮实际渲染行数。
- `_refresh_session_list()` 不再使用 `len(sessions) + 1`，而是使用固定窗口行数。
- 每次刷新前清理与上一轮相同数量的行；窗口高度不足时也补空白行，保证刷新区域高度稳定。

建议更保守的实现：

- header 固定 1 行。
- item 固定 `VISIBLE_RESUME_ROWS` 行，session 不足时输出空白占位行。
- footer 固定 1 行。
- 因此 refresh count 固定为 `VISIBLE_RESUME_ROWS + 2`。

## 可选方案

如果 Coding Agent 判断 prompt_toolkit 更稳，也可以改为 prompt_toolkit 的可控渲染区域，但本轮不要求引入复杂全屏 TUI。选择该路径时必须说明为什么比固定窗口更小、更稳。

## 测试要求

本轮属于 P1 用户可见终端交互 bugfix。自动化测试重点锁住渲染窗口和行数契约，真实终端刷新仍需手工验收。

必须补自动化测试：

- 窗口计算：顶部、中间、底部选中项都得到正确窗口。
- session 数量大于窗口高度时，渲染输出只包含窗口内 session，不输出全量 session。
- 每次刷新清理固定行数，而不是 `len(sessions) + 1`。
- 预览文本包含换行、制表符、长中文时会被单行化。
- Esc/q 取消仍返回 `None` 且不污染 `_history`。
- 非 TTY fallback 保持数字输入行为。

必须补手工验收：

- PowerShell：构造至少 30 个 session，运行 `/resume`，连续按住 ↓ 和 ↑，确认没有重复渲染或旧行残留。
- PowerShell：窄窗口 + 中文长预览，确认每项仍单行显示。
- cmd.exe：同样验证长列表连续滚动、Enter 恢复、Esc 取消。

## 验收标准

- `python -m py_compile src\xcode_cli\core\conversation\resume.py`
- `pytest tests\test_resume.py tests\test_agent_resume_command.py -q`
- `git diff --check`
- 手工验收记录写入实现收口文档或 PR/任务总结。

未完成原生 Windows 手工验收时，只能声明自动化行为和本地非交互路径通过，不能声称终端重复渲染已经在真实 Windows 控制台完全修复。
