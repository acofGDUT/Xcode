# Plan: 修复 `/resume` 长列表重复渲染

> Parent spec: [2026-06-08-resume-menu-rendering-fix-design.md](../specs/2026-06-08-resume-menu-rendering-fix-design.md)

**Risk layer:** P1。该问题影响 `/resume` 方向键菜单的用户可见终端体验；真实 PowerShell/cmd.exe 行为必须用手工验收补足。

**Goal:** 把 `/resume` TTY 菜单从“全量列表 + 按 session 数清屏”改为“固定高度窗口 + 稳定行数刷新 + 单行预览”，避免 session 很多或预览换行时重复渲染。

## 涉及文件

优先修改：

- `src/xcode_cli/core/conversation/resume.py`

优先补测试：

- `tests/test_resume.py`
- `tests/test_agent_resume_command.py` 如当前项目仍有旧 resume command 测试覆盖

文档收口：

- `docs/current/DEVNOTES.md`
- `docs/current/PROGRESS.md`

## 约束

- 不引入 `asyncio`。
- 不改变 session resume 的恢复逻辑，只改选择菜单渲染。
- 非 TTY 数字输入 fallback 必须保持现有行为。
- 不让用户输入内容进入 Rich markup 解析。
- 不为了这个 bug 引入大而全的 TUI 抽象。

## Step 1: 写失败测试

建议在 `tests/test_resume.py` 中增加纯 helper 行为测试。如果当前 helper 是私有方法，可以实例化 `ResumeCommandService` 后直接测私有 helper；这是终端 UI bugfix，锁住私有渲染契约是合理的。

新增窗口计算测试：

```python
def test_resume_visible_window_centers_selected_when_possible():
    from xcode_cli.core.conversation.resume import ResumeCommandService

    assert ResumeCommandService._visible_window(total=30, selected=0, limit=9) == (0, 9)
    assert ResumeCommandService._visible_window(total=30, selected=15, limit=9) == (11, 20)
    assert ResumeCommandService._visible_window(total=30, selected=29, limit=9) == (21, 30)
```

新增单行预览测试：

```python
def test_resume_preview_is_single_line():
    from xcode_cli.core.conversation.resume import ResumeCommandService

    preview = ResumeCommandService._single_line_preview("第一行\n第二行\t第三行", max_chars=20)

    assert "\n" not in preview
    assert "\t" not in preview
    assert "第一行 第二行 第三行" in preview
```

新增长列表渲染窗口测试：

```python
def test_resume_render_only_prints_visible_window(fake_console, fake_sessions):
    service = ResumeCommandService(sessions=None, context=None, console=fake_console, prompt=None)

    service._render_session_list(fake_sessions(30), selected=15)

    output = "\n".join(fake_console.lines)
    assert "16/30" in output
    assert "session-15-preview" in output
    assert "session-1-preview" not in output
    assert "session-30-preview" not in output
```

新增刷新固定行数测试。可以 monkeypatch `sys.stdout` 为记录对象，或者把清理动作抽成 `_clear_rendered_session_list(line_count)` 后测传参：

```python
def test_resume_refresh_uses_fixed_rendered_line_count(monkeypatch, fake_console, fake_sessions):
    service = ResumeCommandService(sessions=None, context=None, console=fake_console, prompt=None)
    cleared = []
    monkeypatch.setattr(service, "_clear_rendered_session_list", lambda count: cleared.append(count))

    service._refresh_session_list(fake_sessions(30), selected=15)

    assert cleared == [service._resume_menu_line_count()]
    assert cleared[0] < 30
```

先运行：

```powershell
pytest tests\test_resume.py tests\test_agent_resume_command.py -q
```

预期：失败，提示 helper 或固定窗口行为尚未实现。

## Step 2: 实现固定窗口 helper

在 `src/xcode_cli/core/conversation/resume.py` 中增加模块常量：

```python
VISIBLE_RESUME_ROWS = 9
```

在 `ResumeCommandService` 中增加 helper：

```python
@staticmethod
def _visible_window(total: int, selected: int, limit: int = VISIBLE_RESUME_ROWS) -> tuple[int, int]:
    ...

@staticmethod
def _single_line_preview(text: str | None, max_chars: int = 60) -> str:
    ...

@staticmethod
def _resume_menu_line_count(limit: int = VISIBLE_RESUME_ROWS) -> int:
    return limit + 2
```

实现注意：

- `_visible_window()` 必须处理 `total == 0`，返回 `(0, 0)`。
- `_single_line_preview()` 对 `None` 或空字符串返回 `"(empty)"`。
- 空白归一化可以用 `" ".join(text.split())`。
- 截断时保留省略号，例如超过 `max_chars` 时返回 `text[: max_chars - 1] + "..."` 或项目已有风格；如果使用三个点，要相应调整长度。

## Step 3: 改造渲染函数

修改 `_render_session_list(sessions, selected)`：

- 计算 `start, end = self._visible_window(len(sessions), selected)`。
- header 显示 `Select session to resume: {selected + 1}/{len(sessions)}`。
- 只遍历 `sessions[start:end]`。
- 不足 `VISIBLE_RESUME_ROWS` 的部分输出空白占位行，确保总行数固定。
- footer 输出操作提示。
- 用户内容渲染不要启用 markup。可用 `Text` 拼接样式，或 `console.print(..., markup=False)` 并避免 Rich style 字符串包住用户输入。

建议输出形态：

```text
Select session to resume: 16/30
    2026-06-08 10:01  preview...
  > 2026-06-08 10:02  selected preview... [checkpoint]
    2026-06-08 10:03  preview...
↑/↓ move · Enter resume · Esc cancel
```

## Step 4: 改造刷新函数

修改 `_refresh_session_list(sessions, selected)`：

- 不再使用 `len(sessions) + 1`。
- 使用 `count = self._resume_menu_line_count()`。
- 可保留现有 ANSI 上移 + 清行模式，但固定清理 `count` 行。
- 为方便测试，建议抽出：

```python
def _clear_rendered_session_list(self, count: int) -> None:
    sys.stdout.write(f"\x1b[{count}A")
    for _ in range(count):
        sys.stdout.write("\x1b[2K")
        sys.stdout.write("\x1b[1B")
    sys.stdout.write(f"\x1b[{count}A")
    sys.stdout.flush()
```

然后 `_refresh_session_list()` 调用：

```python
count = self._resume_menu_line_count()
self._clear_rendered_session_list(count)
self._render_session_list(sessions, selected)
```

## Step 5: 保持交互行为

检查 `run()` 中现有行为仍保持：

- ↑/k 选中上一条，支持 wrap。
- ↓/j 选中下一条，支持 wrap。
- Enter 恢复当前选中 session。
- Esc/q 取消。
- 数字快捷键保留。如果 session 超过 9 条，只能支持单字符 `1` 到 `9` 跳转；不要尝试在原始键盘读取中解析多位数字，避免引入输入状态复杂度。可以在文档或 footer 中不主动宣传数字快捷键。
- 非 TTY 仍走 `_run_number_input()`。

## Step 6: 验证

运行：

```powershell
python -m py_compile src\xcode_cli\core\conversation\resume.py
pytest tests\test_resume.py tests\test_agent_resume_command.py -q
git diff --check
```

如果项目没有 `tests/test_resume.py` 或测试文件名不同，使用实际覆盖 `/resume` 的测试文件。

## Step 7: 手工验收

必须补原生终端记录。

PowerShell：

```text
1. 构造或保留至少 30 个当前项目 session。
2. 运行 xcode chat。
3. 输入 /resume。
4. 连续按 ↓ 至少 20 次，再连续按 ↑ 至少 20 次。
5. 缩窄终端窗口，重复滚动。
6. 使用包含中文长句的 last_user_input session，确认预览仍单行。
7. 按 Esc 取消，确认回到正常输入。
8. 再次 /resume，按 Enter 恢复一条 session。
```

cmd.exe：

```text
1. 重复 PowerShell 的长列表连续滚动。
2. 验证 Enter 恢复和 Esc 取消。
```

验收记录必须说明是否仍看到重复渲染、旧行残留、光标错位或 prompt_toolkit 输入异常。

## Review 检查点

- 是否仍有 `len(sessions) + 1` 用于 TTY 菜单清理。
- 是否所有用户预览内容都被单行化。
- 是否固定窗口渲染，不再全量打印长列表。
- 是否非 TTY 数字输入行为未变。
- 是否取消不污染 `_history`。
- 是否有原生 Windows 手工验收记录；没有时不能声称真实终端问题完全修复。

## 建议提交信息

```powershell
git add src/xcode_cli/core/conversation/resume.py tests/test_resume.py tests/test_agent_resume_command.py docs/current/DEVNOTES.md docs/current/PROGRESS.md
git commit -m "fix: stabilize resume menu rendering"
```

## 2026-06-09 实现收口

已实现：

- `ResumeCommandService` TTY 菜单改为固定 9 行窗口。
- header 显示 `current/total`。
- session 预览先单行化，再按显示宽度截断。
- 窄窗口下 checkpoint 标记可缩短，降低换行风险。
- `_refresh_session_list()` 固定清理 `header + visible rows + footer` 行，不再按 `len(sessions) + 1` 清理。

已验证：

```powershell
python -m py_compile src\xcode_cli\core\conversation\resume.py src\xcode_cli\core\runtime_status.py src\xcode_cli\core\agent.py
pytest tests\test_agent_resume_command.py tests\test_resume.py tests\test_runtime_status.py -q
```

结果：44 passed。

仍未完成：

- 原生 PowerShell/cmd.exe 中构造 30 条以上 session 的连续方向键滚动手工记录。
- 窄窗口 + 中文长预览的真实终端手工记录。
