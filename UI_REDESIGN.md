# UI 重新设计 — 对齐 Claude Code 体验

> 2026-05-24 建立

---

## 设计目标

让 Xcode 的终端 UI 在视觉和交互模式上向 Claude Code 对齐。核心原则：

1. **信息密度优先** — 不用 Panel 包裹每条消息，用彩色前缀区分角色
2. **先审后执行** — 写文件/编辑文件时，先展示 diff，用户确认后才执行
3. **工具可见** — 工具调用实时展示名称 + 参数摘要，不隐藏
4. **状态可感知** — 底部状态栏实时显示 token 用量、耗时、会话时长

---

## 一、对话气泡重构

### 当前问题

```python
# user 消息 — 用 Panel 包裹，占 3 行
self.console.print(Panel(text, title="you", border_style="bright_cyan", title_align="left"))

# assistant 消息 — 又一个 Panel header
console.print(Panel.fit("assistant", title="assistant", border_style="magenta"))
```

每条消息都用 Panel 包裹，屏幕空间浪费严重，长对话时滚动过快。

### 目标样式

```
you ▸ 帮我看看 src/main.py 的第 10-20 行

assistant ▸ (2.3s)
好的，我来读取这段代码。

  ## tool.read_file  path=src/main.py offset=9 limit=12
  10  def main():
  11      parser = argparse.ArgumentParser()
  ...

assistant ▸
这段代码定义了 CLI 入口，argparse 负责解析命令行参数...
```

### 实现方案

**`agent.py` 改动：**

1. **`_print_user_bubble()`** — 去掉 Panel，改为彩色前缀：

```python
def _print_user_bubble(self, text: str) -> None:
    self.console.print()
    self.console.print("[bright cyan]you[/bright cyan] ▸ ", end="")
    self.console.print(text)
```

2. **`_run_llm_loop()` 中的 assistant 前缀** — 已有 `[magenta]assistant[/magenta] ▸`，保持不变。

3. **`_print_assistant_bubble()`** — 去掉 `Panel.fit("assistant")` header，直接渲染 markdown 内容：

```python
def _print_assistant_bubble(self, text: str) -> None:
    # 不再打印 Panel header，直接渲染
    OutputRenderer.render(self.console, text)
```

4. **`renderer.py` 的 `render()` 方法** — 去掉开头的 `Panel.fit("assistant")` 行：

```python
# 删除这行：
# console.print(Panel.fit("assistant", title="assistant", border_style="magenta"))
```

代码块仍然用 Panel 包裹（带语法高亮），这是合理的——代码需要视觉隔离。

---

## 二、工具调用展示重构

### 当前问题

```python
# 执行前只打印一行 dim
self.console.print(f"[dim]## tool.{tc.name}[/dim]")

# 执行后打印截断结果
self.console.print(f"[dim]{result[:200]}[/dim]")
```

信息太少，用户不知道工具带了什么参数、结果是什么。

### 目标样式

```
## tool.read_file
   path: src/main.py
   offset: 9
   limit: 12

## tool.edit_file
   path: src/main.py
   old_string: "def foo():\n    pass"
   new_string: "def foo():\n    return 42"
   [Diff preview here — 见第三节]

## tool.run_shell
   command: python -m pytest tests/ -x
   [bold yellow]Shell 命令需要确认 (y/n)[/bold yellow]
```

### 实现方案

**`agent.py` — 工具调用展示函数：**

```python
def _render_tool_call(self, tc) -> None:
    """展示工具调用名称和参数摘要"""
    self.console.print(f"[bold cyan]## tool.{tc.name}[/bold cyan]")
    # 参数摘要（每行一个 key: value）
    for key, value in tc.args.items():
        val_str = str(value)
        if len(val_str) > 120:
            val_str = val_str[:120] + "..."
        self.console.print(f"   [dim]{key}:[/dim] {val_str}")
```

**`_run_llm_loop()` 中替换原来的 dim 打印：**

```python
# 替换：
# self.console.print(f"[dim]## tool.{tc.name}[/dim]")
# 改为：
self._render_tool_call(tc)
```

**工具结果展示** — 改为折叠式：只在出错时显示完整结果，成功时显示一行确认：

```python
result = self.tools.execute(tc.name, tc.args)
if str(result).startswith("Error:"):
    self.console.print(f"[bold red]{result}[/bold red]")
else:
    # 成功：显示简短确认
    self.console.print(f"[dim]  → done ({len(str(result))} chars)[/dim]")
```

---

## 三、先审后执行（Diff → Confirm → Execute）

### 当前问题

```python
# 当前流程：先执行，再展示 diff
result = self.tools.execute(tc.name, tc.args)  # ← 已经写入了！
# ... 然后才展示 diff
OutputRenderer.render_diff(self.console, old_text, new_text, file_path)
```

用户看到 diff 的时候文件已经被改了，diff 展示变成了"事后通知"而非"事前审批"。

### Claude Code 的流程

```
1. LLM 调用 edit_file(path, old_string, new_string)
2. Claude Code 读取文件，计算 diff
3. 展示 diff + 工具参数
4. 询问用户：Allow / Deny
5. 用户 Allow → 执行写入
6. 用户 Deny → 跳过，返回 "User denied"
```

### 实现方案

**核心改动：`_run_llm_loop()` 中 `edit_file` / `write_file` 的处理顺序**

```python
for tc in response.tool_calls:
    self._render_tool_call(tc)

    # ── 权限检查（现有逻辑，位置不变）──
    level = self.permissions.check(tc.name)
    if level == "deny":
        result = f"Permission denied for tool: {tc.name}"
        self.console.print(f"[bold red]{result}[/bold red]")
        executed_calls.append((tc, result))
        continue

    # ── 写文件/编辑文件：先 diff，再确认 ──
    if tc.name in {"edit_file", "write_file"}:
        file_path = str(tc.args.get("path", ""))
        if file_path:
            # 读取旧内容
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    old_text = f.read()
            except FileNotFoundError:
                old_text = ""

            # 预览新内容（不实际写入）
            if tc.name == "write_file":
                new_text = tc.args.get("content", "")
            else:
                # edit_file: 模拟替换
                new_text = old_text.replace(
                    tc.args.get("old_string", ""),
                    tc.args.get("new_string", ""),
                    1 if not tc.args.get("replace_all") else -1,
                )

            # 展示 diff
            OutputRenderer.render_diff(self.console, old_text, new_text, file_path)

            # 如果权限是 ask，现在询问
            if level == "ask":
                approved = self.permissions.prompt_user(tc.name, tc.args)
                if not approved:
                    result = f"User denied tool: {tc.name}"
                    self.console.print(f"[dim]{result}[/dim]")
                    executed_calls.append((tc, result))
                    continue

            # 用户同意，执行写入
            result = self.tools.execute(tc.name, tc.args)
            self.console.print(f"[dim]  → {result[:100]}[/dim]")
            executed_calls.append((tc, result))
            continue

    # ── shell 命令：先展示命令，再确认 ──
    if tc.name == "run_shell" and level == "ask":
        cmd = tc.args.get("command", "")
        self.console.print(f"[bold yellow]  $ {cmd}[/bold yellow]")
        approved = self.permissions.prompt_user(tc.name, tc.args)
        if not approved:
            result = f"User denied tool: {tc.name}"
            self.console.print(f"[dim]{result}[/dim]")
            executed_calls.append((tc, result))
            continue

    # ── 其他工具：直接执行 ──
    result = self.tools.execute(tc.name, tc.args)
    self.console.print(f"[dim]  → {str(result)[:100]}[/dim]")
    executed_calls.append((tc, result))
```

**关键变化：**
- `edit_file` / `write_file`：先读文件 → 计算 diff → 展示 diff → 询问 → 执行
- `run_shell`：先展示命令 → 询问 → 执行
- 其他只读工具（read_file / grep / glob）：直接执行，不询问

---

## 四、状态栏增强

### 当前问题

```python
def _bottom_toolbar(self) -> str:
    return f" model={model} | provider={provider} | skills={skills_count} | api={api} "
```

信息静态，不反映会话状态。

### 目标样式

```
 model=gpt-4o-mini | tokens≈12.3k/128k | tools: 3 calls | session 5m23s | api=ready
```

### 实现方案

**`agent.py` — 跟踪会话状态：**

```python
class AgentRuntime:
    def __init__(self):
        # ... 现有代码 ...
        self._session_start = time.monotonic()
        self._tool_call_count = 0
        self._estimated_tokens = 0
```

**`_run_llm_loop()` 中更新计数：**

```python
# 每次工具调用后
self._tool_call_count += 1

# 每次 LLM 返回后，更新 token 估算
self._estimated_tokens = self.context.estimate_tokens(history)
```

**`_bottom_toolbar()` 增强：**

```python
def _bottom_toolbar(self) -> str:
    cfg = self.config_store.load()
    model = cfg.model or os.getenv("XCODE_MODEL", "gpt-4o-mini")
    has_key = bool(cfg.api_key or os.getenv("XCODE_API_KEY") or os.getenv("OPENAI_API_KEY"))
    api = "ready" if has_key else "missing-key"

    elapsed = time.monotonic() - self._session_start
    minutes, seconds = divmod(int(elapsed), 60)
    session_str = f"{minutes}m{seconds}s" if minutes else f"{seconds}s"

    tok_str = f"~{self._estimated_tokens // 1000}k" if self._estimated_tokens > 0 else "0"
    max_tok = cfg.max_tokens // 1000

    return f" {model} | tokens≈{tok_str}/{max_tok}k | tools:{self._tool_call_count} | session {session_str} | {api} "
```

---

## 五、欢迎屏简化

### 当前问题

ASCII art 占 12 行 + 信息表 4 行 + 提示 1 行 = 17 行。每次启动都滚一屏。

### 目标样式

```
Xcode v0.1.0 — terminal-native AI coding agent
Skills: none | API: ready | Project: D:\Xcode
Type normally to chat · / for commands · Tab to complete
```

3 行搞定。保留猫猫但缩小到 2 行（可选）。

### 实现方案

**`_render_welcome()` 重写：**

```python
def _render_welcome(self) -> None:
    rg_msg = ensure_ripgrep_installed()

    cfg = self.config_store.load()
    enabled = ", ".join(cfg.enabled_skills) if cfg.enabled_skills else "none"
    has_key = bool(cfg.api_key or os.getenv("XCODE_API_KEY") or os.getenv("OPENAI_API_KEY"))
    key_state = "ready" if has_key else "missing-key"

    self.console.print("[bold]Xcode[/bold] v0.1.0 — terminal-native AI coding agent")
    self.console.print(f"[dim]Skills:[/dim] {enabled} | [dim]API:[/dim] {key_state} | [dim]Project:[/dim] {self.cwd}")
    self.console.print("[dim]Type normally to chat · / for commands · Tab to complete[/dim]")

    if not rg_msg.startswith("ripgrep already installed"):
        self.console.print(f"[dim]{rg_msg}[/dim]")
```

如果用户喜欢猫猫，可以保留 2 行极简版：

```python
self.console.print("[bold]Xcode[/bold] v0.1.0  /\\_/\\")
self.console.print("terminal-native AI agent  (•.•)  ")
```

---

## 六、工具结果错误展示

### 当前问题

所有工具结果都用 `[dim]` 展示，包括错误。用户不容易注意到出错。

### 目标

- 成功：`[dim]  → done (N chars)[/dim]` 一行
- 错误：`[bold red]  Error: ...[/bold red]` 醒目展示
- 文件操作成功：`[green]  → Edited {path} (N replacements)[/green]`

---

## 七、Claude Code 对比：工具调用显示

Claude Code 会展示每个工具调用——这是透明性的核心。用户始终知道 Agent 在做什么：

```
assistant ▸ 让我读取这个文件。

## tool.Read
   path: src/main.py
   offset: 0
   limit: 50

  → 50 lines read

assistant ▸ 这个文件定义了 CLI 入口…

## tool.Edit
   path: src/main.py
   old_string: "    parser.add_argument('--debug')"
   new_string: "    parser.add_argument('--debug', action='store_true')"
   Diff · src/main.py
   ──────────────────
   -    parser.add_argument('--debug')
   +    parser.add_argument('--debug', action='store_true')

   Allow? [Y/n]: y
   → Edited src/main.py (1 replacement)

assistant ▸ 已修改，将 --debug 改为 store_true。
```

用户看到完整链路：**说了什么 → 调了什么工具 → 工具结果 → 继续推理**。工具调用不隐藏，反而用 `## tool.Name` 标记突出。

---

## 八、6 个需补充的改进

### 8.1 用户输入双重打印问题

**问题**：当前 `prompt_toolkit` 输入行在用户打字时已显示 `you ▸` 前缀，回车后 `_print_user_bubble()` 又用 Panel 包裹打印一遍。同一段输入出现两次，浪费空间且混乱。

**Claude Code 行为**：用户输入只在上方保留一行记录（无 Panel），与 assistant 回复之间有空行分隔。

**修复方案**：

```python
def _print_user_bubble(self, text: str) -> None:
    # 不重复打印用户输入——prompt_toolkit 已处理
    # 仅作为对话历史标记，用 subtle 样式一行带过
    self.console.print(f"[dim]▸ {text}[/dim]")
```

关键是**不带 Panel**，且用 dim 样式区分"已过去的用户输入"和"即将的助理回复"。

### 8.2 多轮 LLM 调用的视觉连续性

**问题**：一个用户消息可能触发多轮 LLM（对话 → 工具调用 → LLM 继续 → 工具调用 → ...）。当前只在 `_run_llm_loop` 入口打印一次 `assistant ▸`，工具调用和后续回复之间缺少层级关系。

**Claude Code 行为**：工具调用和结果视觉上缩进，助理文本保持左对齐。用户能清楚区分"助理说的话"和"系统做的事"。

**修复方案**：

```
assistant ▸
好的，我来修改这个函数。                    ← 助理说的话（左对齐）

  ## tool.Edit                              ← 工具调用（缩进 2 空格）
     path: src/main.py
     ...
  [Diff preview]

  → Edited (1 replacement)                  ← 工具结果（缩进 2 空格）

在这个改动中...                             ← 助理继续说话（左对齐）
```

关键规则：助理文本左对齐，工具调用/结果统一缩进 2 格。多轮 LLM 调用时不重复打印 `assistant ▸` 标签。

### 8.3 权限询问界面升级

**问题**：`permissions.py:45-58` 用裸 `input()` 做权限确认：

```python
value = input(f"Allow tool '{tool_name}'? [y/N]: ")
```

这在 Rich 渲染的上下文中显得突兀，且对 `edit_file`/`write_file` 来说，diff 已经展示了却还要多一步确认。

**Claude Code 行为**：diff 展示后，用结构性提示询问 `Allow? [Y/n]`，权限确认和 diff 在同一个视觉上下文内。

**修复方案**：统一用 prompt_toolkit 的输入行处理确认（和 plan 审批一样），不用 `input()`：

```python
# 不用 input()，而用 prompt_toolkit 的下一个 prompt 行
# 用户输入 "y" / "approve" / "同意" → 批准
# 用户输入 "n" / "deny" / "拒绝" → 拒绝
# 其他任意输入 → 默认拒绝
```

或者至少把 `input()` 换成 Rich Console 的输入方式，保持视觉一致。

### 8.4 Streaming 模式下的代码块双重显示

**问题**：`streaming_plus_final_render` 模式下：

```
streaming: LLM token → 用户看到 ```python\nprint("hello")\n```  (raw text)
final:       → _print_assistant_bubble() → 用户再次看到 Syntax 高亮版
```

同一段代码显示两次——第一次 raw markdown，第二次 Rich 渲染。

**修复方案**：streaming 时检测到代码块开始 ` ``` ` 后，切换为 buffer 模式——代码块内容缓存不输出，等代码块结束 ` ``` ` 后由 Rich Syntax 一次性渲染。或者更简单——代码块检测后标记"已通过 Rich 渲染"，跳过二次渲染。

### 8.5 中断/取消的 UI 反馈

**问题**：用户 Ctrl+C 中断长时间运行的工具时，UI 没有任何反馈——Rich 可能残留半截输出，状态混乱。

**Claude Code 行为**：Ctrl+C 后显示 `[dim]Interrupted.[/dim]`，中断信息作为 tool result 返回 LLM。

**修复方案**：

```python
# _run_llm_loop() 中工具执行部分
try:
    result = self.tools.execute(tc.name, tc.args)
except KeyboardInterrupt:
    self.console.print("[dim]Interrupted.[/dim]")
    result = "Error: user interrupted the operation"
```

中断信息作为 tool result 传给 LLM，LLM 可以据此调整策略（换个方法、拆分操作等）。

### 8.6 状态栏费用估算（可选）

**问题**：状态栏设计有 token 计数但不含费用。Xcode 支持多模型（openai / deepseek 等），价格差异大，费用信息对用户有参考价值。

**Claude Code 行为**：`/context` 中展示 token 用量分类。

**建议**：在底部状态栏加 `cost≈$0.03`（基于模型定价表做简单估算）。这是锦上添花，放到后期做。

简单实现：在 Config 或一个常量表中定义常见模型的每 1k token 价格，乘以估算 token 数。

---

## 九、改动文件清单

| 文件 | 改动内容 |
|------|---------|
| `agent.py` | `_print_user_bubble()` 重写、`_render_tool_call()` 新增、`_run_llm_loop()` 重构工具执行流程（先 diff 后执行）、`_bottom_toolbar()` 增强、`_render_welcome()` 简化 |
| `renderer.py` | `render()` 去掉 Panel header、错误时红色高亮 |
| `permissions.py` | `prompt_user()` 可选增加 diff 展示参数（或由 agent.py 调用前自行展示） |

---

## 十、依赖关系

本方案不引入新依赖，全部基于已有的 Rich + prompt-toolkit 能力：
- `Panel` / `Syntax` / `Markdown` / `Table` — 已在用
- `Console.print(end="")` — 已在用
- `difflib.unified_diff` — 已在用

---

## 十一、与 ROADMAP 的关系

本文件是 Phase 4 Task 4.2（UI 升级）的扩展设计。不引入新依赖，全部基于已有的 Rich + prompt_toolkit。

## 十二、实施顺序

本文件是 Phase 4 Task 4.2（UI 升级）的扩展设计。实现时按以下顺序：

1. **对话气泡重构**（renderer.py + agent.py）— 解决双重打印 + Panel 冗余，最基础
2. **工具调用展示**（agent.py）— 提升工具可见性 + 多轮 LLM 视觉连续性
3. **先审后执行**（agent.py _run_llm_loop 重构）— 核心交互改进 + 权限界面升级
4. **中断/取消反馈**（agent.py）— 小改动，大体验提升
5. **Streaming 双重渲染修复**（agent.py）— 消除 raw → Rich 重复显示
6. **状态栏增强**（agent.py）— 锦上添花
7. **欢迎屏简化**（agent.py）— 最小改动
8. **费用估算**（agent.py）— 可选，后期

---

## 十三、验收标准

- [ ] 对话中不再出现 `Panel.fit("assistant")` header
- [ ] 用户消息用 `[dim]▸ text[/dim]` 一行记录，不用 Panel 包裹，不重复打印
- [ ] `edit_file` / `write_file` 执行前展示 diff
- [ ] diff 展示后用户可 approve/deny，deny 则跳过写入（权限确认用 prompt_toolkit 而非裸 input()）
- [ ] `run_shell` 执行前展示命令内容（当权限为 ask 时）
- [ ] 工具调用展示参数摘要（key: value 格式），左缩进 2 格
- [ ] 工具结果：成功显示一行确认，错误显示红色高亮
- [ ] 多轮 LLM 调用时不重复打印 `assistant ▸`，助理文本左对齐、工具调用缩进 2 格
- [ ] Streaming 模式下代码块不会 raw markdown + Rich 渲染双重显示
- [ ] Ctrl+C 中断工具时显示 `[dim]Interrupted.[/dim]`
- [ ] 底部状态栏显示 token 估算、工具调用次数、会话时长
- [ ] 欢迎屏不超过 4 行
- [ ] 可选：状态栏含 cost≈$0.00 费用估算

---

