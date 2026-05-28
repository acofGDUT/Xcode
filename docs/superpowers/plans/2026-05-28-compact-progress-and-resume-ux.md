# /compact 进度反馈 + /resume 方向键选择

## 目标

实现两个 P1 交互体验优化：

1. `/compact`（含自动压缩）调用 LLM 期间显示动态进度，复用 Thinking/Live 风格
2. `/resume` 从数字输入改为方向键菜单，复用审批菜单的键盘读取模式

## 前置约束

- Python >= 3.10，同步模型，不引入 asyncio
- prompt_toolkit 在 Git Bash/mingw 有已知限制，关键交互需在 cmd.exe/PowerShell 验收
- 工具异常全部捕获，不能打崩主循环
- 不引入不必要的抽象——只有两个使用者不需要基类
- 所有用户界面字符串使用中文，代码标识符使用英文

---

## 功能一：`/compact` 进度反馈

### 现状

- `ConversationCompactor.compact_history()` 调用 `ContextManager.compress()`，后者内部调 `llm_client.complete()` 生成摘要，这是一个可能较慢的阻塞 LLM 调用
- 手动 `/compact` 和自动压缩（`_run_llm_loop` 中 `should_compress` 触发）都走 `compact_history()`
- 当前整个压缩过程静默，用户看到终端停住，无法判断是在压缩还是卡死

### 目标

- 压缩开始时显示 "Compacting context... (Xs)" 动态进度
- 复用 `_run_llm_loop()` 中已有的 Think Live 模式（`rich.live.Live` + daemon thread 更新 elapsed time）
- 手动和自动压缩共用同一套进度展示

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/xcode_cli/core/conversation/compaction.py` | **主要改动**：在 `compact_history()` 中包裹 Live 进度 |

### 实现方案

在 `ConversationCompactor.compact_history()` 中，调用 `self.context.compress()` 前后加入 Live 进度：

```
def compact_history(self, history):
    before_messages = len(history)
    before_tokens = self.context.estimate_tokens(history)
    previous_summary = self.find_previous_summary(history)

    # ---- 新增：启动 Live 进度 ----
    start_time = time.monotonic()
    stop_event = threading.Event()
    
    def _update_progress():
        while not stop_event.is_set():
            elapsed = time.monotonic() - start_time
            live.update(Text(f"Compacting context... ({elapsed:.1f}s)", style="dim"))
            time.sleep(0.1)
    
    live = Live(
        Text("Compacting context... (0.0s)", style="dim"),
        console=self.console,
        refresh_per_second=8,
        transient=True,
    )
    live.start()
    progress_thread = threading.Thread(target=_update_progress, daemon=True)
    progress_thread.start()
    # ---------------------------

    try:
        result = self.context.compress(history, self.llm, previous_summary)
    finally:
        # ---- 新增：停止 Live 进度 ----
        stop_event.set()
        progress_thread.join(timeout=0.2)
        live.stop()
        # ---------------------------

    if not result.checkpoint_message:
        return None
    
    # ... 后续不变 ...
```

### 关键细节

1. **`transient=True`**：压缩完成后进度行自动消失，不留残余输出
2. **`finally` 保护**：即使 `compress()` 抛异常，Live 也必须停止，避免终端状态残留
3. **不需要改 `ContextManager`**：进度是 UI 层关注点，`ContextManager.compress()` 保持纯逻辑
4. **不需要改 `agent.py`**：两个调用路径都经过 `compact_history()`，改一处覆盖所有场景
5. **不需要改 `ConversationCompactor.__init__`**：`self.console` 已存在

### 自动压缩路径的额外考虑

自动压缩发生在 `_run_llm_loop()` 中，此时 Thinking Live 已经停止（`stop_thinking()` 在第一个 text token 到达时已调用）。两个 Live 不会同时运行，无冲突。

但有一处注意：自动压缩的 Live 会在 Thinking Live 停止后、新一轮 LLM 调用开始前显示。如果压缩很快（<0.5s），Live 可能一闪而过——这是正常的，不需要特殊处理。

### 验收标准

- 手动 `/compact`：终端显示 "Compacting context... (X.Xs)"，秒数递增，压缩完成后消失，然后显示压缩结果摘要
- 自动压缩触发时同样显示进度
- `Nothing to compact.` 路径不显示 Live（因为没调 LLM）
- 压缩期间按 Ctrl+C 不导致终端状态残留
- `pytest` 全量通过
- 原生 PowerShell/cmd.exe 手工验收

---

## 功能二：`/resume` 方向键选择

### 现状

- `ResumeCommandService.run()` 使用 `prompt_toolkit.PromptSession.prompt()` 读取数字输入
- session 列表用 `self.console.print()` 渲染为编号列表
- `ToolApprovalController` 已实现方向键读取（`_read_key()`）、选项渲染（`_render_options()`）、选项刷新（`_refresh_options()`），支持 Windows（msvcrt）和 Unix（termios）

### 目标

- session 列表改为方向键 ↑/↓ 上下浏览，Enter 确认选择，Esc 取消
- 列表项展示：session 时间、最近用户输入（截断 60 字符）、checkpoint 标记
- 非 TTY 环境回退到当前数字输入方式（保持现有行为）
- 选择菜单不污染 `_history`，取消时不影响 runtime status

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/xcode_cli/core/conversation/resume.py` | **主要改动**：`run()` 中 TTY 路径改用方向键菜单 |
| `src/xcode_cli/core/tooling/approval.py` | **轻量改动**：将 `_read_key()` 提取为模块级函数（可选，见下方讨论） |

### 方案 A：提取共享键盘读取函数（推荐）

`ToolApprovalController._read_key()` 是纯函数逻辑，不依赖 `self`。将它提取为 `core/tooling/approval.py` 中的模块级函数 `read_key()`，`ResumeCommandService` 直接导入使用。

改动：

1. `approval.py`：将 `_read_key()` 改为模块级 `read_key()`，`ToolApprovalController._read_key()` 改为调用 `read_key()`
2. `resume.py`：`from xcode_cli.core.tooling.approval import read_key`，在 `run()` 中实现方向键菜单循环

### 方案 B：内联到 ResumeCommandService

在 `resume.py` 中复制一份 `_read_key()`。简单粗暴，但违反 DRY 原则。

**推荐方案 A**。`read_key()` 在两个类中都需要，且逻辑完全一致，提取为模块函数不会引入不必要的抽象。

### 实现伪码（`ResumeCommandService.run()` TTY 路径）

```python
def run(self) -> ResumeResult | None:
    sessions = self.sessions.list_sessions()
    if not sessions:
        self.console.print("No recent sessions found for this project.")
        return None

    # --- 非 TTY fallback（保持现有数字输入逻辑，不变） ---
    if not sys.stdin.isatty():
        return self._run_number_input(sessions)

    # --- 新增：TTY 方向键菜单 ---
    selected = 0
    self._render_session_list(sessions, selected)

    while True:
        key = read_key()
        if key in {"up", "k"}:
            selected = (selected - 1) % len(sessions)
            self._refresh_session_list(sessions, selected)
        elif key in {"down", "j"}:
            selected = (selected + 1) % len(sessions)
            self._refresh_session_list(sessions, selected)
        elif key == "enter":
            self.console.print()  # 换行，结束菜单
            break
        elif key in {"escape", "q"}:
            self.console.print()
            self.console.print("Cancelled.")
            return None
        # 数字快捷键（可选保留）：按对应数字直接跳转到该项
        elif key in {str(i) for i in range(1, len(sessions) + 1)}:
            selected = int(key) - 1
            self._refresh_session_list(sessions, selected)
        elif key == "c":
            raise KeyboardInterrupt

    # 选中后执行恢复（与现有逻辑相同）
    selected_session = sessions[selected]
    # ... 后续不变 ...
```

### 渲染方法

```python
def _render_session_list(self, sessions, selected):
    self.console.print("[bold]Select session to resume:[/bold] [dim](↑/↓, Enter, Esc)[/dim]")
    for idx, s in enumerate(sessions):
        ts = datetime.utcfromtimestamp(s.updated_at).strftime("%Y-%m-%d %H:%M")
        preview = s.last_user_input[:60] if s.last_user_input else "(empty)"
        cp_mark = " [checkpoint]" if s.has_checkpoint else ""
        
        prefix = ">" if idx == selected else " "
        style = "bold cyan" if idx == selected else "dim"
        self.console.print(f"  {prefix} {ts}  {preview}{cp_mark}", style=style)

def _refresh_session_list(self, sessions, selected):
    count = len(sessions) + 1  # header line + N items
    sys.stdout.write(f"\x1b[{count}A")
    for _ in range(count):
        sys.stdout.write("\x1b[2K")
        sys.stdout.write("\x1b[1B")
    sys.stdout.write(f"\x1b[{count}A")
    sys.stdout.flush()
    self._render_session_list(sessions, selected)
```

### 关键细节

1. **`read_key()` 必须正确处理 stdin**：`ToolApprovalController._read_key()` 在 Unix 上使用 `termios.tcgetattr/setraw`。提取后确保 `ResumeCommandService` 的调用上下文（prompt_toolkit 环境）不会产生终端模式冲突
2. **prompt_toolkit 冲突风险**：`ResumeCommandService` 的 `__init__` 接收 `prompt: PromptSession`，说明调用者（`agent.py`）在使用 prompt_toolkit 管理输入。方向键菜单使用原始 `sys.stdin` 读取，可能与 prompt_toolkit 的终端状态冲突。**需要实际验证**
3. **如果冲突**：可以考虑在进入菜单前临时关闭 prompt_toolkit 的输入处理，或者在菜单中使用 prompt_toolkit 的 `PromptSession` 机制（但更复杂）
4. **escape 键歧义**：在 Unix 上 `\x1b` 既可能是 Esc 也可能是一段转义序列的开头。`read_key()` 当前处理是读 `\x1b` 后再尝试读 2 字节，如果匹配不到已知方向键就当作 `escape`。这是 `ToolApprovalController` 已验证的行为
5. **保持现有 recovery 逻辑不变**：选中后的 `SessionResumeBuilder` 调用、token budget 计算、结果输出与当前完全相同

### 验收标准

- TTY 环境：session 列表支持 ↑/↓ 浏览，当前项高亮，Enter 恢复，Esc 取消
- 列表项显示时间、最近输入预览、checkpoint 标记
- 取消不污染 `_history`，不影响 runtime status
- 非 TTY 环境：保持当前数字输入方式
- `/resume` 后恢复的 history 可正常进入 LLM 对话
- `pytest` 全量通过
- 原生 PowerShell/cmd.exe 手工验收（方向键、Enter、Esc 均正常）

---

## 测试要求

### Feature 1 新增测试

- `tests/test_compaction.py`（如有则扩展，无则新建或加在现有的 context 测试中）：
  - `compact_history` 在压缩成功时显示 Live（mock console 验证 `Live` 被启动和停止）
  - `compact_history` 在 `compress()` 抛异常时 `Live` 仍然停止（`finally` 覆盖）
  - `Nothing to compact` 路径不启动 Live

### Feature 2 新增测试

- `tests/test_resume.py`（如有则扩展，无则新建）：
  - TTY 环境下列表渲染正确
  - 非 TTY fallback 保持数字输入
  - `read_key()` 函数独立可测（如提取到模块函数）

---

## 实施顺序

1. Feature 2 的共享前置：提取 `read_key()` 到模块函数（改动小，影响面仅 `approval.py`）
2. Feature 2 主体：改造 `ResumeCommandService.run()`
3. Feature 1：改造 `ConversationCompactor.compact_history()`
4. 补测试
5. `pytest` 全量 + `py_compile` 验证
6. 原生 PowerShell/cmd.exe 手工验收两个功能
