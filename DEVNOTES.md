# Xcode 开发笔记

> 记录开发中遇到的问题、已知边界情况、设计取舍。ROADMAP.md 说「做什么」, ARCHITECTURE.md 说「怎么做的」，本文档说「为什么这样做 / 坑在哪」。

---

## 已知问题

### 1. prompt_toolkit 在非 Windows 控制台下无法启动

**现象**：在 bash/cygwin/mingw 终端中运行 `xcode chat`，`PromptSession()` 抛出 `NoConsoleScreenBufferError`。

**原因**：prompt_toolkit 的 `Win32Output` 要求原生 Windows 控制台。Git Bash 等终端模拟的是 POSIX 行为。

**影响**：无法在 bash 中做 Agent 集成测试，只能做静态/单元测试。

**临时方案**：在 `cmd.exe` 或 PowerShell 中启动，或用 `winpty` 包装。

---

### 2. ripgrep Bootstrap 仅 Windows

**现象**：`bootstrap.py` 的 `ensure_ripgrep_installed()` 在 Linux/macOS 上返回 `"not implemented yet"`。

**影响**：Linux/macOS 上 `grep` 工具回退到系统 PATH 中的 `rg`。如果系统没装 ripgrep，grep 工具报错。

**优先级**：低。当前开发环境是 Windows。

---

### 3. PowerShell glob 展开

**现象**：在 PowerShell 中 `xcode tool glob --pattern "*.py"` 可能被 shell 先展开再传给程序。

**解决方案**：`main.py` 提供了 `--literal-pattern` 和 `--stdin-pattern` 参数作为变通。CLI 方式使用无此问题。

---

### 4. ConfigStore 不支持项目级配置合并

**现象**：Phase 5 Task 5.6 只实现了 `project_root.py`（项目根检测），但 `ConfigStore.load()` 仍只读 `~/.xcode/config.json`，未合并项目 `.xcode/settings.json`。

**影响**：权限系统的 project 级别规则已可通过 `PermissionManager._load_project_rules()` 独立加载，但其他 Config 字段不支持项目级覆盖。

---

### 5. auto_memory 分类逻辑基于关键词匹配

**现象**：`MemoryManager._classify_auto_memory_type()` 用硬编码的关键词列表判断记忆类型。

**局限**：中英文关键词各覆盖不完全，可能漏分类或误分类。当前覆盖了常见模式，但边缘 case 存在。

**改进方向**：改为 prompt 驱动——在 BASE_SYSTEM_PROMPT 中定义四种类型的语义和示例，让 LLM 自行判断类型。参考 `prompts/memory_system_prompt.md`。

**当前存储格式已到位**：`- type: <user|feedback|project|reference> | note: <content>`，单文件 `memory.md`，解析 + 去重逻辑完整。问题只在「谁来判断类型」——是函数还是 LLM。

---

### 6. 多 tool_calls 合并为单条 assistant 消息

**现象**：Phase 1 早期版本中，每个 tool_call 独立追加一条 assistant 消息，OpenAI API 报错。

**修复**：`_run_llm_loop()` 中所有同轮 tool_calls 合并为一条 `"role": "assistant"` 消息，`tool_calls` 字段是列表。符合 OpenAI API 要求。

---

### 7. LLM 流式输出 token 含 `[...]` 导致 Rich markup 注入崩溃

**现象**：Agent 在流式输出 LLM 回复时，`MarkupError: closing tag '[/dim]' at position 0 doesn't match any open tag`。

**原因**：`agent.py` 的 `on_token` 和 `on_reasoning_token` 回调中用 `console.print(token)` 和 `console.print(f"[dim]{token}[/dim]")` 打印 LLM token，但没禁用 Rich markup 解析。LLM 输出中可能包含 `[xxx]` 或 `[/xxx]` 字符串（如代码示例、markdown 链接引用等），Rich 把它们当样式标签解析，但找不到对应的开/闭标签就崩溃。

**修复**：两处 `console.print()` 都加 `markup=False`，`on_reasoning_token` 用 `style="dim"` 替代手动 `[dim]` 包装：
```python
# on_token (line 501)
self.console.print(token, end="", markup=False)

# on_reasoning_token (line 505)
self.console.print(token, end="", markup=False, style="dim")
```

---

### 8. 这正是你说的“流式 vs 富渲染冲突”的典型折中方案。
如果你想更干净，我建议下一步做成可配置模式：

streaming_plain：只流式，不最终重渲（最快）
streaming_plus_final_render：先流式，再富渲染（当前）
buffer_then_render：不流式，完整后一次渲染（最美观）
你如果同意，我可以直接把这个开关加到 settings.json 里并接到运行时逻辑。

---


## 设计取舍

### 为什么 memory 工具被完全移除

旧设计有 4 个专用 memory 工具（list/get/save/delete）。重构后全部删除，Agent 用 `write_file`/`edit_file` 直接操作 XCODE.md。

**理由**：
- 每个工具都是一个 API 契约，需要维护 Schema 和行为语义
- 文件操作工具已经能覆盖所有记忆操作
- 专用工具增加了 LLM 的选择负担（14 个工具 vs 13 个）
- 对齐 Claude Code 的无专用工具模式

**代价**：LLM 需要自行判断何时存、存到哪个文件，prompt 中的规则指引变得更重要。

### 为什么 plan_mode 不自动触发

ROADMAP 原设计期望 Agent 自动判断任务复杂度并进入计划模式。实现时改为手动 + LLM 自主调用。

**理由**：
- 自动判断的误触发成本高（简单任务进入计划模式打断流程）
- Skills 系统已能承担部分规划职责
- `/plan enter` 提供显式控制

### 为什么 sub_agent 不递归派发

`SubAgentExecutor` 初始化时，即使 GENERAL 类型也不注册 `dispatch_agent` 工具。

**理由**：防止无限递归——子 Agent 再派发子 Agent，消耗和延迟不可控。

### 为什么不用 asyncio

并行场景只用 `ThreadPoolExecutor`。

**理由**：
- I/O 密集型（LLM API 调用）用线程池足够
- 异步会传染 `complete()` → `_run_llm_loop()` → `run_chat()` 整个调用链
- 当前代码量 ~2400 行，不值得引入异步复杂度

### 为什么 auto memory 用 write_file + append 而不是内联格式

**两种方案**：

| | 路径 A（内联格式） | 路径 B（write_file + append） |
|---|---|---|
| 机制 | LLM 在回复中夹带 `- type: X \| note: Y`，代码正则抓取 | LLM 显式调用 `write_file(append=true)` |
| 触发 | `_try_persist_auto_memory` 只在无 tool_calls 时触发 | 任何时刻 LLM 都可以调用工具 |
| 可见性 | 用户看不到（被系统消费） | 对话中显示为工具调用，可审计 |
| memory.py | ~190 行（解析、过滤、去重、写入） | ~120 行（只读取 + 注入） |
| 判断逻辑 | 代码层 `_is_durable_note` 关键词过滤 | prompt 驱动，LLM 自行判断 |

**选择路径 B 的理由**：
- 路径 A 的触发窗口太窄（`agent.py:523` 只在 `not response.tool_calls` 时触发），多轮工具调用中的记忆会丢失
- 路径 A 依赖 LLM 在自然语言中严格输出格式行，不可靠
- 路径 B 中 LLM 显式调工具，行为有审计记录
- 路径 B 让 memory.py 退化到纯 I/O，所有智能在 prompt 里——改 prompt 不改变代码
- 代价：`write_file` 需要增加 `append` 参数（+8 行）

**决策日期**：2026-05-24

---

## 测试策略

| 层级 | 方式 | 覆盖 |
|------|------|------|
| 语法验证 | `py_compile` | 所有 .py 文件 |
| 单元测试 | Python 脚本直接 import + assert | 数据类、API、状态机 |
| 集成测试 | 模拟 AgentRuntime 初始化（跳过 PromptSession） | 工具注册、权限、记忆 |
| LLM 测试 | 实际 API 调用 + 断言工具调用链 | 工具触发、多轮对话 |
| 端到端 | `xcode chat` 实际对话 | 仅 cmd.exe/PowerShell |

---

## 后续改进方向

1. **Prompt 完善**：记忆系统规则（何时存/不存什么）需要落地到 BASE_SYSTEM_PROMPT
2. **Linux/macOS bootstrap**：`ensure_ripgrep_installed()` 的非 Windows 实现
3. **Config 合并**：项目 `.xcode/settings.json` 覆盖全局 `~/.xcode/config.json`
4. **auto_memory 三态**：`on | off | ask`，当前仅 bool
5. **XCODE.md 模板**：首次创建时提供结构化模板
