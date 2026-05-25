# Xcode 开发笔记

> 记录开发中遇到的问题、已知边界情况、设计取舍。ROADMAP.md 说「做什么」, ARCHITECTURE.md 说「怎么做的」，本文档说「为什么这样做 / 坑在哪」。

---

## 已知问题

### 0. radiolist_dialog 全屏遮挡 diff（2026-05-24，Cursor Opus 4.7）

**现象**：`_prompt_tool_approval()` 使用 `prompt_toolkit.shortcuts.radiolist_dialog`，它是全屏模态弹窗——清空终端后只显示 "Yes / Yes All / No" 三个选项。用户在审批时**完全看不到刚才的 diff**，只能凭记忆决定。

**影响**：先审后执行的核心价值被抵消——diff 展示了但用户看不到，审批变成盲操作。`write_file`/`edit_file`/`run_shell` 全部受影响。

**根因**：`radiolist_dialog` 是为独立 CLI 工具设计的对话框，不适合嵌入持续的对话式交互。它启动独立的 event loop，接管整个终端渲染。

**修复方向**：换成内联审批——diff 保持显示不滚动，审批区直接在当前上下文里渲染，而不是弹出全屏对话框。详见 `UI_APPROVAL_FIX.md`。

**状态**：✅ 已修复（V3，2026-05-25）。`radiolist_dialog` 已删除，TTY 环境下改为内联三选项菜单：

- `Yes`
- `No`
- `Yes, for this conversation`

支持 `↑/↓` 和 `Enter` 选择，也保留 `y/n/a` 快捷键；仅在非 TTY fallback 场景下才退回单行 `input()`。

---

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

### 5. auto_memory 现为 prompt 驱动的索引模型

**现状**：当前实现不再由 `MemoryManager` 用关键词分类、解析或过滤 auto memory。类型判断、slug 命名、frontmatter 结构、索引维护规则都由 `BASE_SYSTEM_PROMPT` 驱动，`MemoryManager` 只负责：

- 暴露 `memory/` 目录与 `MEMORY.md` 索引路径
- 在 prompt 中注入项目 XCODE、用户 XCODE 和 `MEMORY.md` 索引内容

**当前模型**：

- 单条记忆：`~/.xcode/projects/<project>/memory/<slug>.md`
- 索引文件：`~/.xcode/projects/<project>/memory/MEMORY.md`
- 注入方式：只自动注入 `MEMORY.md` 索引；需要细节时，Agent 再自行 `read_file` 对应记忆文件

**影响**：智能判断几乎全部在 prompt 层，不在 `memory.py` 里。这让代码更简单，但也意味着 prompt 文档和实现模型必须始终保持一致。

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

### 9. Phase 4.5 Batch 1 review closure：`max_tokens` 与测试基线已收口（2026-05-25，Codex review）

**结果**：`ContextManager` 已改为实例级 `max_tokens`，`/env max-tokens` 已落地，`/context` 展示与压缩阈值现在统一使用 runtime 的 `self.context.max_tokens`。

**测试补强**：`tests/test_agent_env.py` 已直接覆盖 `AgentRuntime._handle_env_command()` 的真实命令路径，包括：

- 合法值更新 runtime 与持久化 config
- 非法值报错且不污染状态
- `/env show` 包含 `max-tokens`

**结论**：Phase 4.5 Batch 1 的两个 review follow-up 已关闭。后续工作不再是这批的一致性收口，而是继续推进会话恢复、费用估算和原生 Windows 端到端验收。

---

### 10. Phase 4.5 Batch 2 review closure：记忆模型验证与 Windows 路径回归已收口（2026-05-25，Codex review）

**结果**：当前 memory 模型已补齐一轮真实测试基线，覆盖 `MemoryManager` 路径与读写、`build_system_prompt()` 的 memory 集成，以及 `AgentRuntime._handle_memory_command()` 的真实命令路径。

**已补充的测试**：
- `tests/test_memory.py`
- `tests/test_prompting_memory.py`
- `tests/test_agent_memory_command.py`
- `tests/test_agent_memory_bug.py`

**实现收口**：
- `build_system_prompt()` 现在会显式注入当前项目的 resolved memory paths，减少模型在 Windows 下自行拼接 `%USERNAME%` 或把 `<project>` 误替换成完整工作目录的概率
- `agent.py` 中 `write_file` / `edit_file` 的 diff preview 读取目标文件时，已将 `OSError` 视为可恢复预览失败，不再因为非法路径把主循环打崩

**结论**：Phase 4.5 Batch 2 的 memory 校验与回归修复已关闭。后续与 memory 相关的工作不再是“补当前模型测试基线”，而是更高层的能力扩展，例如会话恢复、费用估算和原生 Windows 端到端验收。

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

### 为什么 auto memory 用“单条记忆文件 + MEMORY.md 索引”而不是内联格式

**两种方案**：

| | 路径 A（内联格式） | 路径 B（write_file + append） |
|---|---|---|
| 机制 | LLM 在回复中夹带 `- type: X \| note: Y`，代码正则抓取 | LLM 显式创建 `<slug>.md` 并维护 `MEMORY.md` 索引 |
| 触发 | `_try_persist_auto_memory` 只在无 tool_calls 时触发 | 任何时刻 LLM 都可以调用工具 |
| 可见性 | 用户看不到（被系统消费） | 对话中显示为工具调用，可审计 |
| memory.py | ~190 行（解析、过滤、去重、写入） | ~120 行（路径管理 + 索引读取 + 注入） |
| 判断逻辑 | 代码层 `_is_durable_note` 关键词过滤 | prompt 驱动，LLM 自行判断 |

**选择路径 B 的理由**：
- 路径 A 的触发窗口太窄（`agent.py:523` 只在 `not response.tool_calls` 时触发），多轮工具调用中的记忆会丢失
- 路径 A 依赖 LLM 在自然语言中严格输出格式行，不可靠
- 路径 B 中 LLM 显式调工具，行为有审计记录
- 路径 B 让 `memory.py` 退化到路径管理和注入层，所有智能在 prompt 里——改 prompt 不改变代码
- 路径 B 允许“索引先提示、需要时再读详情”的两段式记忆访问，减少 prompt 膨胀

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
6. **`/context` 费用估算**：当前 `/context` 已能显示 token 用量分类，但还没有按模型定价做 approximate cost 估算。后续可以在 `Config` 或定价表中维护 per-1k token 价格，并接入 `/context` 与底部状态栏。
7. **对话历史恢复**：当前 `SessionStore` 会写 JSONL 会话记录，但 CLI 还没有 `resume` / `continue` 入口，退出后无法直接继续上一轮会话。后续可以在 `main.py` 和 `AgentRuntime` 中接入“继续最近一次会话”和“按 session id 恢复”。
8. **原生 Windows 端到端验收**：当前 v3 的大部分验证来自编译、局部冒烟和非原生 console 环境下的间接检查。由于 `prompt_toolkit` 在非原生控制台下有 `NoConsoleScreenBufferError` 这类已知限制，仍需要在原生 `cmd.exe` 或 PowerShell 中跑一轮 `xcode chat` 端到端验收。
