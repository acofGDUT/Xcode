# Textual UI Rendering Design

> 来源：UI Agent 设计稿，经 Codex 整理为可交给 Coding Agent 的设计依据。本文只定义 UI 交互与视觉行为，不包含 Python 实现代码。

## 1. 信息架构

Textual UI 分为三个核心区域，明确区分“持久化历史”和“当前动态状态”。

### Transcript 区域（长期历史流）

显示对用户和后续审计有长期价值的最终证据块：

- 用户完整输入。
- Assistant 最终回复。
- 工具执行后的简短摘要。
- 工具错误和用户拒绝记录。
- 收起后的工具组摘要，例如 `[ok] Searched 3 files`。

约束：

- 不被 thinking delta、shell progress tick、stdout chunk 污染。
- 不显示每一个动态进度事件。
- 不写入 UI-only state 到 transcript JSONL。

### Current Turn 区域（当前活跃区）

承载当前交互回合的动态 view state：

- thinking streaming 状态。
- 当前工具参数预览。
- diff preview。
- approval surface。
- shell tail output 和进度信息。
- 当前运行工具或工具组。

生命周期：

- turn 结束后，动态状态被销毁或折叠。
- 只把简短摘要、错误、拒绝等证据写入长期 transcript。

### Bottom Area / Status Bar

输入框上方显示简要任务状态；最底部状态栏显示当前 turn、approval、message count、viewport、任务摘要等已有运行态信息。

注意：当前项目没有 CPU/RAM 指标来源，不在本轮新增系统资源监控。

## 2. 显示密度规范

引入三种显示密度：

- `compact`：高度合并摘要，例如 `Read 5 files, searched 3 patterns`。
- `normal`：每个独立工具或工具组显示为单行或短块，例如 `read_file README.md`。
- `expanded`：显示参数、输出、stderr、耗时和完整结果。

默认策略：

- `read_file` / `grep` / `glob` 默认 `compact`，允许合并。
- `edit_file` / `write_file` 默认 `normal`，不能隐藏 diff 和 approval。
- `run_shell` 默认 `normal`，执行中显示 tail output 和计数。
- 错误和拒绝默认独立显示，不被普通折叠吞掉。

交互建议：

- 支持纯键盘。
- 展开 key 使用 `tool_call_id` 或 group id。
- tool use 和 tool result 必须同步展开。
- `Up/Down/Enter` 可能与输入框、resume selector、approval selector 冲突；实现时应先设计 focus/selection 状态，不能直接全局抢键。
- 第一批实现可先支持状态模型和渲染，不强制实现完整键盘展开。

## 3. Thinking UI

Streaming 时：

```text
Thinking... (2.3s)
```

完成后默认折叠为：

```text
Thought for 4.5s
```

Expanded 时：

- 展示完整 Markdown thinking 内容。
- 使用简洁缩进或左侧竖线区分普通对话。
- 旧 thinking 不应长期铺满 transcript。

实现约束：

- 当前 `RuntimeController` 尚未完整暴露 reasoning/thinking UI event。本功能可以作为后续 Batch C 实现。
- 不要把每个 thinking delta 追加成 `MessageBlock`。

## 4. Tool UI

### Read/Search Group

连续只读工具可组合。

未展开：

```text
[+] Analyzed 3 files (read_file, grep)
```

展开后：

```text
read_file src/main.py
grep "def auth" src/
glob **/*.py
```

### Edit/Write Diff + Approval

编辑和写入操作不可与只读工具混组。

Current Turn 中显示：

```text
edit_file src/main.py
- def old_function():
+ def new_function():

Waiting for approval: Yes / No / Yes, this conversation
```

完成后长期 transcript 只保留简短摘要，例如：

```text
[ok] Edited src/main.py
```

### Shell Progress

执行中显示：

```text
shell pytest tests/
elapsed 12.5s | 145 lines | 4.2 KB
last output:
  ...
```

约束：

- 默认只显示最后 3-5 行。
- 记录 line count、byte count、elapsed。
- 完整输出只在 expanded 模式显示。
- stdout/stderr chunk 不应逐行变成长期 `MessageBlock`。

### Error / Rejection

错误和拒绝需要作为长期证据保留。

示例：

```text
[rejected] write_file src/main.py
[error] run_shell pytest: command timed out after 30000ms
```

### Agent / Subtask

子 Agent 或 task 类工具显示为层级摘要：

```text
sub-agent CodeReview: running
  read_file ...
  grep ...
```

第一版可只做摘要，不展示子 Agent 内部完整工具树。

## 5. Task UI

Task UI 从 `Tasks: N active` 升级为可扫描 checklist。

ASCII 优先状态：

```text
[ ] Pending task
[-] In progress task
[x] Completed task
[!] Failed task
[~] Canceled task
```

Current task / next task：

```text
Current: Refactor ViewState | Next: Implement grouping
```

约束：

- 默认使用 ASCII，避免 Windows 字体不支持复杂符号。
- 可在后续主题/配置中引入 Unicode 图标，但不是本轮默认要求。

## 6. 场景示例

### read + grep + edit

```text
Assistant: Let me check the code and make the update.

[+] Analyzed 2 files (read_file, grep) 0.5s

edit_file src/main.py
- def old_function():
+ def new_function():

Waiting for approval: y/n/a
```

### shell 长输出

```text
shell npm install (running)
... 150 lines hidden ...
fetch metadata ...
fetch metadata ...
fetch metadata ...
elapsed 18s | 153 lines | 12 KB
```

### task_create / task_update

```text
Tasks
[x] 1. Setup project
[-] 2. Build task UI
[ ] 3. Write tests
```

### thinking + final answer

```text
Thought for 3.2s (expand for details)

The issue is caused by missing view state normalization...
```

## 7. Windows 终端约束

- cmd.exe / PowerShell 窄窗口下不能溢出。
- 长文本必须 wrap 或截断。
- 按钮文案不能挤爆边框。
- 不依赖鼠标。
- 所有审批和折叠/展开必须有键盘路径。
- 默认符号采用 ASCII；Unicode/emoji 仅作为未来可选增强。

