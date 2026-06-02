# 用 Textual 实现 Claude Code 风格的终端 UI

## 核心哲学：单一渲染器

Claude Code 的 Ink 和 Textual 共享同一个架构原则：

```
❌ 多库拼装（会花屏）           ✅ 单一渲染器（不会花屏）
                                 
prompt_toolkit → stdout          App.run() → 独占终端
Rich Live #1   → stdout          ├── Screen 栈
Rich Live #2   → stdout          ├── Widget 树
console.print  → stdout          ├── CSS 布局
print()        → stdout          └── 单帧 diff → stdout
                                 
多个写者竞争 stdout              一个写者拥有整个 framebuffer
ANSI 序列交织 → 乱码             原子写入，永不花屏
```

**Textual 就是 Python 生态里的 Ink。**

---

## 一、主对话界面布局

### Claude Code 做了什么

用 Flexbox 把终端分成三个区域，PromptInput **不是绝对定位**，而是自然流中的 flex 子元素：

```
┌─ FullscreenLayout ────────────────────┐
│                                        │
│  ScrollBox (flexGrow={1})              │  ← 占满剩余空间
│    ├── Messages（对话历史）            │     内部独立滚动
│    ├── tool JSX（diff、代码输出等）    │
│    ├── <Box flexGrow={1} />（占位）   │
│    └── Spinner / 思考状态              │
│                                        │
├────────────────────────────────────────┤
│  Bottom (flexShrink={0})               │  ← 自然高度，不收缩
│    ├── SuggestionsOverlay（浮动）      │
│    ├── 权限确认弹窗（出现时撑高）       │     输入框跟着上移
│    ├── TaskList（展开时撑高）           │
│    └── PromptInput（输入框）            │
│                                        │
│  Modal (position="absolute", bottom=0) │  ← 命令弹窗覆盖层
└────────────────────────────────────────┘
```

### Textual 实现

```python
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Input, Static, RichLog


class ChatScreen(Screen):
    """主对话界面"""

    CSS = """
    #transcript {
        flex: 1;                    /* 占满剩余空间 */
        overflow-y: auto;          /* 独立滚动 */
    }
    #bottom {
        height: auto;              /* 自然高度，随内容变化 */
    }
    """

    def compose(self) -> ComposeResult:
        # 对话区（可独立滚动）
        with Container(id="transcript"):
            yield RichLog(markup=True, wrap=True, id="chat-log")

        # 底部区域（自然流，不固定）
        with Container(id="bottom"):
            yield Static(id="permission-hint")    # 权限提示，出现时撑高
            yield Input(placeholder="Ask anything...", id="prompt")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """用户发送消息"""
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold green]You:[/] {event.value}")
        event.input.clear()
        # 调用 API、展示 thinking、流式输出...
```

**关键**：`#bottom` 用 `height: auto`，当权限弹窗或 TaskList 出现时自动撑高，输入框跟着上移——不需要任何手动坐标计算。

---

## 二、输入处理与命令补全

### Claude Code 做了什么

```
键盘 → stdin raw mode
  → parseMultipleKeypresses()      解析 ANSI 转义序列
  → processKeysInBatch()           批量分发
  → EventEmitter.emit('input')     发布事件
  → useInput() hooks               订阅（PromptInput、BaseTextInput 等）
  → setState()                     更新 React 状态
  → 单帧渲染 → diff → stdout
```

输入框检测 `/` 时调用 `commandSuggestions.ts`（Fuse.js 模糊搜索），结果通过 `PromptInputFooterSuggestions` 组件浮动渲染在输入框上方。

### Textual 实现

```python
from textual.widgets import Input
from textual.containers import Container
from textual.reactive import reactive


class CommandDropdown(Container):
    """命令补全下拉框，浮动在输入框上方"""

    visible: reactive[bool] = reactive(False)
    selected: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    CommandDropdown {
        dock: bottom;              /* 钉在输入框上方 */
        height: auto;
        max-height: 7;
        background: $panel;
        border: solid $primary;
        display: none;
    }
    CommandDropdown.visible {
        display: block;
    }
    """

    def __init__(self, commands: list[dict]):
        super().__init__()
        self.commands = commands

    def update_matches(self, query: str):
        """对标 commandSuggestions.ts — 模糊匹配"""
        if not query.startswith("/"):
            self.visible = False
            return

        q = query[1:].lower()
        matches = [
            c for c in self.commands
            if q in c["name"].lower()
        ][:6]  # 最多 6 行

        self._matches = matches
        self.selected = 0
        self.visible = bool(matches)
        self.refresh()

    def render(self):
        if not self._matches:
            return ""
        lines = []
        for i, cmd in enumerate(self._matches):
            cursor = "❯" if i == self.selected else " "
            lines.append(
                f"{cursor} /{cmd['name']:<24} {cmd['description'][:40]}"
            )
        return "\n".join(lines)
```

Textual 里 Input 按键是**内置解析好的**（不需要自己写 ANSI escape parser）：

```python
class ChatScreen(Screen):
    def compose(self):
        yield CommandDropdown(commands=REGISTERED_COMMANDS)
        yield Input(placeholder="Type / for commands...", id="prompt")

    def on_input_changed(self, event: Input.Changed):
        # 每次按键都重新匹配
        dropdown = self.query_one(CommandDropdown)
        dropdown.update_matches(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        value = event.value.strip()

        if value.startswith("/"):
            self._dispatch_command(value)
        else:
            self._send_message(value)

        event.input.clear()
```

---

## 三、命令系统

### Claude Code 做了什么

三种命令类型，通过 `processSlashCommand.tsx` 统一 dispatch：

| 类型 | 例子 | 行为 | 渲染 |
|---|---|---|---|
| `prompt` | `/review` | 展开成文本块发给模型 | 无 UI，结果出现在对话区 |
| `local` | `/clear`, `/cost` | 直接执行 async 函数 | 无 UI，结果以 system 消息插入 |
| `local-jsx` | `/model`, `/config` | 返回 React 组件 | 弹窗覆盖在 dialog 区上方 |

`local-jsx` 命令通过 `setToolJSX()` → REPL → FullscreenLayout 的 `modal` slot（`position="absolute"`）显示。用 `ModalContext` 让 Pane 组件检测自己是否在 modal 里，自适应跳过重复的边框。

### Textual 实现

Textual 比 Ink 更适合这个模式——内置了 **Screen 栈**：

```python
from textual.screen import ModalScreen, Screen
from textual.app import App
from textual.widgets import ListView, ListItem, Label


# ========== 命令注册表 ==========

@dataclass
class Command:
    name: str
    description: str
    kind: str  # "prompt" | "local" | "screen"
    screen_fn: Callable[..., Screen] | None = None
    local_fn: Callable | None = None
    prompt_fn: Callable | None = None


# ========== ModelPicker（对标 /model） ==========

class ModelPicker(Screen):
    """Screen 被 push 到栈顶，自动覆盖下层"""

    DEFAULT_CSS = """
    ModelPicker {
        align: center middle;
    }
    #picker-container {
        width: 50%;
        max-height: 12;
        background: $panel;
        border: solid $primary;
        padding: 1;
    }
    """

    def __init__(self, current: str):
        super().__init__()
        self.current = current

    def compose(self):
        with Container(id="picker-container"):
            yield Label(f"Current: {self.current}")
            yield Label("▔" * 30)
            yield ListView(
                ListItem(Label("Claude Opus 4.8")),
                ListItem(Label("Claude Sonnet 4.6")),
                ListItem(Label("Claude Haiku 4.5")),
            )
            yield Label("Esc to cancel")

    def on_list_view_selected(self, event: ListView.Selected):
        self.dismiss(event.item.query_one(Label).renderable)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)


# ========== SettingsScreen（对标 /config） ==========

class SettingsScreen(Screen):
    """多 Tab 设置 — 用 TabbedContent 对标 Settings 组件"""

    def compose(self):
        with TabbedContent("Config", "Theme", "Model", "MCP"):
            with TabPane("Config"):
                yield Input(placeholder="API Key...")
            with TabPane("Theme"):
                yield Label("Theme settings...")
            # ...

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)


# ========== dispatch（对标 processSlashCommand.tsx） ==========

class ChatScreen(Screen):

    def _dispatch_command(self, input_text: str):
        parts = input_text[1:].split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""

        cmd = next(
            (c for c in REGISTERED_COMMANDS if c.name == cmd_name), None
        )
        if not cmd:
            return

        match cmd.kind:
            case "prompt":
                # 展开成文本，喂给模型（无 UI）
                text = cmd.prompt_fn(cmd_args)
                self._send_message(text)

            case "local":
                # 直接执行（无 UI），结果插入对话区
                result = asyncio.ensure_future(cmd.local_fn(cmd_args))
                self.query_one("#chat-log", RichLog).write(
                    f"[dim]{result}[/]"
                )

            case "screen":
                # 弹出 Screen（对标 push_screen = modal slot）
                screen = cmd.screen_fn(self, cmd_args)

                def on_done(result):
                    if result:
                        self.query_one("#chat-log", RichLog).write(
                            f"[dim]Selected: {result}[/]"
                        )

                screen.callback = on_done
                self.app.push_screen(screen, callback=on_done)
```

### 对比：Ink 的方式 vs Textual 的方式

```
Ink（手动管理）                   Textual（框架管理）

setToolJSX({jsx, ...})           app.push_screen(screen)
  ↓                                ↓
FullscreenLayout 读状态            Screen 压栈，下层自动失焦
  ↓                                ↓
position="absolute" 硬画           框架渲染 + 框架 diff
  ↓                                ↓
onDone() → setToolJSX(null)       screen.dismiss(result)
  ↓                                ↓
手动清理 ModalContext              自动 pop，下层恢复
```

Textual 不需要 `ModalContext`、`Pane.useIsInsideModal()` 这些"检测自己在哪"的机制——每个 Screen 天然是独立的上下文。

---

## 四、Thinking / Spinner 状态

### Claude Code 做了什么

`SpinnerWithVerb` 组件在 ScrollBox 底部（`<Box flexGrow={1} />` 下面）渲染。API 调用中显示 "Thinking..."、"Writing..." 等，tool 执行中显示对应 verb。不是独立渲染器，就是 React 树里的一个节点。

### Textual 实现

```python
from textual.widgets import LoadingIndicator, Static


class ThinkingBar(Static):
    """可更新文本的 thinking 指示器"""

    def set_status(self, text: str):
        self.update(f"🤔 {text}")
        self.refresh()


# 在 ChatScreen 的 compose 里：
# 放在 transcript 底部，总是可见
class ChatScreen(Screen):
    def compose(self):
        with Container(id="transcript"):
            yield RichLog(...)
            yield ThinkingBar(id="thinking")   # 在对话下方

    async def _stream_response(self, chunks):
        thinking = self.query_one("#thinking", ThinkingBar)
        thinking.set_status("analyzing...")

        async for chunk in chunks:
            # 追加到 RichLog
            log = self.query_one("#chat-log", RichLog)
            log.write(chunk)
            await asyncio.sleep(0)

        thinking.set_status("")  # 清空
```

---

## 五、权限确认弹窗

### Claude Code 做了什么

`PermissionRequest` 渲染在 bottom 区域。出现时 bottom 区域高度增加，输入框自然上移。不是 modal overlay——用户可以看到背后的对话。

### Textual 实现

```python
class PermissionBar(Container):
    """权限确认条，出现在输入框上方"""

    visible: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    PermissionBar {
        dock: bottom;
        height: auto;
        background: $warning;
        color: $text;
        padding: 0 1;
        display: none;
    }
    PermissionBar.visible {
        display: block;
    }
    """

    class Result(Message):
        def __init__(self, allow: bool, persist: bool):
            self.allow = allow
            self.persist = persist
            super().__init__()

    def show(self, tool_name: str, command: str):
        self.visible = True
        self.tool_name = tool_name
        self.command = command
        self.refresh()

    def render(self):
        if not self.visible:
            return ""
        return (
            f"⚠ Allow [bold]{self.tool_name}[/] to run?\n"
            f"  $ {self.command}\n"
            f"  [Y]es  [A]llow always  [N]o  [Ctrl+C] abort"
        )

    def on_key(self, event):
        if event.key == "y":
            self.post_message(self.Result(allow=True, persist=False))
        elif event.key == "a":
            self.post_message(self.Result(allow=True, persist=True))
        elif event.key == "n":
            self.post_message(self.Result(allow=False, persist=False))
```

特点：出现时底部区域自然撑高，输入框和对话区都可见，不需要手动计算重叠。

---

## 六、Diff / 代码渲染

### Claude Code 做了什么

Tool 执行结果（`/diff` 的输出等）渲染在 ScrollBox 的 scrollable 区域。用 `RichLog` 的语法高亮能力。

### Textual 实现

Textual 的 RichLog 原生支持 Rich markup：

```python
from rich.syntax import Syntax
from rich.panel import Panel


class DiffView(Static):
    """Diff 展示组件"""

    def show_diff(self, old: str, new: str):
        import difflib
        diff = difflib.unified_diff(
            old.splitlines(), new.splitlines(),
            fromfile="a", tofile="b", lineterm=""
        )
        diff_text = "\n".join(diff)
        # 用 Rich 的 Syntax 渲染
        syntax = Syntax(diff_text, "diff", theme="monokai")
        self.update(syntax)


# 在对话区插入 diff
class ChatScreen(Screen):
    def _insert_diff(self, old: str, new: str):
        log = self.query_one("#chat-log", RichLog)
        log.write(DiffView().show_diff(old, new))
```

---

## 七、快捷键系统

### Claude Code 做了什么

`useInput()` hook + keybinding 配置文件。Ink 层解析 `Ctrl+P`、`Ctrl+C` 等，通过 EventEmitter 分发给 React 组件。

### Textual 实现

```python
class ChatScreen(Screen):

    BINDINGS = [
        Binding("ctrl+p", "quick_open", "Quick open"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "dismiss", "Dismiss"),
        Binding("up", "scroll_up", "", show=False),
        Binding("down", "scroll_down", "", show=False),
    ]

    def action_quick_open(self):
        self.app.push_screen(QuickOpenDialog())

    def action_dismiss(self):
        if self.app.screen_stack:
            self.app.pop_screen()
```

---

## 八、Streaming 流式输出

### Claude Code 做了什么

API 返回 stream，每个 chunk 更新 React state → Ink diff → 终端逐字输出。同一帧内的多个 chunk 在 React batch 中合并。

### Textual 实现

```python
async def _stream_api_response(self, prompt: str):
    log = self.query_one("#chat-log", RichLog)
    thinking = self.query_one("#thinking", ThinkingBar)

    thinking.set_status("thinking...")

    full_response = ""
    async for chunk in api_stream(prompt):
        full_response += chunk
        # 每次更新 widget，Textual 自动 diff 后输出
        log.clear()  # 或者用更精细的策略
        log.write(f"[bold purple]Claude:[/] {full_response}")

    thinking.set_status("")
```

---

## 九、完整项目结构建议

```
your_project/
├── app.py                    # App 入口，启动 Textual
├── screens/
│   ├── chat.py               # 主对话界面（对标 REPL.tsx）
│   ├── onboarding.py         # 首次设置（对标 Onboarding.tsx）
│   └── doctor.py             # 健康检查（对标 Doctor.tsx）
├── commands/
│   ├── __init__.py           # 命令注册表（对标 commands.ts）
│   ├── model_picker.py       # /model（对标 commands/model/model.tsx）
│   ├── config_screen.py      # /config（对标 commands/config/config.tsx）
│   └── theme_picker.py       # /theme
├── widgets/
│   ├── command_dropdown.py   # 命令补全下拉
│   ├── permission_bar.py     # 权限确认条
│   ├── thinking_bar.py       # Thinking 指示器
│   ├── diff_view.py          # Diff 展示
│   └── message_list.py       # 虚拟滚动消息列表
├── services/
│   ├── api_client.py         # API 调用（对标 services/api/）
│   └── mcp.py                # MCP 协议（对标 services/mcp/）
└── state/
    └── session.py            # 会话状态（对标 state/）
```

---

## 十、关键架构决策总结

| 场景 | Ink / React 方式 | Textual 方式 | 选择 |
|---|---|---|---|
| 主布局 | Flexbox + position:absolute | CSS Grid/Dock + Screen 栈 | Textual 更简单 |
| 命令弹窗 | setToolJSX 状态切换 + absolute 定位 | push_screen / pop_screen | **Textual 完胜** |
| 输入解析 | 手写 ANSI escape parser | 框架内置 | **Textual 完胜** |
| 命令补全 | PromptOverlayContext 传送门 | dock: bottom 定位 | Textual 更简单 |
| 声明式 UI | JSX 条件渲染 `{x && <Y/>}` | 命令式 compose + reactive | Ink 更灵活 |
| 流式更新 | React batch + diff | widget.update + 框架 diff | 持平 |
| 状态管理 | useState / AppState store | reactive / screen 属性 | 持平 |
| 虚拟滚动 | 手写 VirtualMessageList | 暂无内置，需自己裁剪 | Ink 更成熟 |

**底线**：Textual 完全能实现 Claude Code 的 UI 模式。Screen 栈做命令弹窗甚至比 Ink 的 modal slot 更干净。唯一不如 Ink 的是"声明式条件渲染"场景（Textual 的 compose 是初始化的，动态显示/隐藏需要 `display: none/block` + `refresh()`），但这不影响核心体验。
