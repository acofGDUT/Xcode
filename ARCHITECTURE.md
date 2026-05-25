# Xcode 架构文档

> 面向接手开发的 Agent（人类或 AI）。ROADMAP.md 是需求文档，本文档是设计实现说明。
> 阅读顺序：先 ROADMAP.md 了解「要做什么」，再本文档了解「怎么做的」。

---

## 1. 组件关系图

```
main.py (Typer CLI 入口)
  ├── xcode chat        → AgentRuntime.run_chat()
  ├── xcode dashboard   → Dashboard().run()
  ├── xcode tool run    → 直接调用 tools/
  └── xcode skill ...   → SkillManager

AgentRuntime (agent.py)
  ├── LLMClient (llm.py)          ← OpenAI 兼容 API，流式 + tool calling
  ├── ToolRegistry (tool_registry.py) ← 工具注册、Schema 生成、执行分发
  │     ├── tools/files.py        ← read_file / write_file / edit_file
  │     ├── tools/search.py       ← grep (rg) / glob
  │     ├── tools/shell.py        ← run_shell
  │     └── tools/agent_tool.py   ← dispatch_agent (工厂函数)
  ├── TaskTracker (task_tracker.py)   ← Task CRUD + 依赖管理
  ├── PlanMode (planning.py)          ← 计划模式状态机
  ├── MemoryManager (memory.py)       ← XCODE.md 双文件 + auto_memory
  ├── ContextManager (context.py)     ← Token 估算 + 对话压缩
  ├── PermissionManager (permissions.py) ← 三级权限 (session > project > global)
  ├── OutputRenderer (ui/renderer.py) ← Rich Markdown/Diff 渲染
  ├── ConfigStore (config.py)         ← ~/.xcode/config.json
  ├── SessionStore (session.py)       ← JSONL 会话日志
  ├── SkillManager (skills/manager.py) ← 技能安装/启用
  ├── project_root.py                 ← 项目根目录检测
  └── bootstrap.py                    ← ripgrep 自动下载（Windows）
```

## 2. 核心数据流

### 2.1 用户消息处理流程

```
用户输入
  │
  ├─ 以 / 开头 → _handle_slash_command()
  │     ├── /plan    → _handle_plan_command()
  │     ├── /memory  → _handle_memory_command()
  │     ├── /env     → _handle_env_command()
  │     ├── /skill   → _handle_skill_command()
  │     └── ...
  │
  ├─ plan_mode.pending_approval → _handle_plan_approval_input()
  │
  └─ 普通消息:
      1. build_system_prompt()  → BASE + skills + XCODE.md memory context
         或 plan_mode.get_system_prompt()（计划模式）
      2. _run_llm_loop(history, system_prompt)
         ├── ContextManager.should_compress() → 必要时压缩历史
         ├── llm.complete(stream=True) → 流式输出 + on_token/on_reasoning_token
         ├── 无 tool_calls → 返回文本
         └── 有 tool_calls:
               ├── PermissionManager.check() → 权限检查
               ├── AgentRuntime._prompt_tool_approval() → ask 级别内联确认
               ├── tools.execute() → 执行工具
               ├── edit_file/write_file 前 → OutputRenderer.render_diff()
               └── 追加 assistant + tool 消息到 history，继续循环
```

### 2.2 System Prompt 构建优先级

```
build_system_prompt() 拼接顺序：
  1. BASE_SYSTEM_PROMPT          (prompting.py, 基础行为规范)
  2. Working directory           (当前工作目录)
  3. Enabled skills              (各技能 SKILL.md 原文注入)
  4. Memory context              (MemoryManager.get_context_for_prompt)
       ├── Project XCODE.md      (上限 2000 chars)
       ├── User XCODE.md         (上限 2000 chars)
       └── Auto memory           (上限 1200 chars, 总计 5000)
```

### 2.3 记忆系统数据流

**auto memory 存储格式**：

- 文件位置：`~/.xcode/projects/<project>/memory/memory.md`
- 单条格式：`- type: <user|feedback|project|reference> | note: <content>`
- 写入方式：LLM 调用 `write_file(path=memory.md, content="...", append=true)`

```
写入:
  Agent 判断应记住某事
    │
    ├─ 项目级长期记忆 → edit_file <project>/XCODE.md (append under ## Project)
    ├─ 用户级长期记忆 → edit_file ~/.xcode/XCODE.md (append under ## User)
    └─ 自动记忆 → write_file(path=memory.md, content="- type: X | note: Y", append=true)
         │
         └─ 所有「何时存/存什么/存什么类型/不存什么」的判断由 BASE_SYSTEM_PROMPT 驱动
            MemoryManager 不参与写入，不做事后过滤

读取（自动注入）:
  每次 build_system_prompt() →
    MemoryManager.get_context_for_prompt(cfg)
      ├─ Project XCODE.md (截断 2000)
      ├─ User XCODE.md (截断 2000)
      └─ read_auto_memory_context(limit=5)
           ├─ read_auto_memory_entries() 解析 memory.md 中所有有效条目
           ├─ 取最后 N 条（默认 5）
           └─ 拼成多行文本 (截断 1200, 仅 auto_memory=True)
```

## 3. 关键设计决策

### 3.1 不引入 asyncio

所有 LLM 调用和子 Agent 执行使用同步代码。并行场景用 `concurrent.futures.ThreadPoolExecutor`。理由：异步会传染整个调用链，对当前规模不划算。

### 3.2 工具注册使用工厂函数

`dispatch_agent` 和 `task_create/update/list` 使用工厂函数而非直接定义，因为需要闭包捕获 `LLMClient` 和 `TaskTracker` 实例。在 `AgentRuntime.__init__()` 中调用工厂并注册。

### 3.3 记忆系统无专用 CRUD 工具

对标 Claude Code，不使用 `memory_save/list/get/delete` 工具。Agent 通过 `write_file`/`edit_file` 直接操作 `XCODE.md` 文件。`MemoryManager` 仅负责 context 注入和 auto_memory 质量过滤。

### 3.4 权限系统三级优先级

`session > project (.xcode/settings.json) > global (~/.xcode/settings.json) > default`。
默认策略：shell/write/edit 为 `ask`，read/grep/glob 为 `allow`。

### 3.5 计划模式不自动触发

保留手动 `/plan enter` 或 LLM 调用 `enter_plan_mode` 工具进入。不要求 Agent 自动判断任务复杂度，提供更高可控性。

### 3.6 子 Agent 工具白名单

EXPLORE/PLAN 子 Agent 仅注册 `{read_file, grep, glob}`，通过 `SubAgentExecutor.__init__()` 中的白名单控制，不是事后权限检查。

### 3.7 工具异常全部捕获

`ToolRegistry.execute()` 是最外层保护——所有工具异常被捕获并转为 `"Tool error: {exc}"`，不会让 Agent 循环崩溃。

### 3.8 上下文预算采用 runtime 单一来源

Phase 4.5 Batch 1 后，`ContextManager` 持有实例级 `max_tokens`，由 `AgentRuntime` 初始化时传入，并在 `/env max-tokens <value>` 时同步更新。

`/context` 展示和 `should_compress()` 压缩阈值都统一读取 `self.context.max_tokens`，避免显示预算和执行预算分叉。

## 4. 文件组织

```
src/xcode_cli/
  main.py                  # Typer 入口
  paths.py                 # ~/.xcode 目录初始化
  core/
    agent.py               # AgentRuntime: REPL 循环 + 命令处理 + 工具注册
    llm.py                 # LLMClient: OpenAI API + 流式 + tool calling
    tool_registry.py       # ToolDef + ToolRegistry
    prompting.py           # BASE_SYSTEM_PROMPT + build_system_prompt()
    config.py              # Config + ConfigStore
    memory.py              # MemoryManager: XCODE.md + auto_memory
    planning.py            # PlanMode 状态机
    task_tracker.py        # Task + TaskTracker + 工具工厂
    sub_agent.py           # SubAgentExecutor
    agent_types.py         # AgentType 枚举
    context.py             # ContextManager: token 估算 + 压缩
    permissions.py         # PermissionManager: 三级权限
    project_root.py        # 项目根目录检测
    session.py             # JSONL 会话持久化
    bootstrap.py           # ripgrep 自动下载
    dashboard.py           # API 配置 TUI
    tools/
      __init__.py          # ALL_TOOLS 导出
      files.py             # read_file / write_file / edit_file
      search.py            # grep (rg) / glob
      shell.py             # run_shell
      agent_tool.py        # dispatch_agent 工厂
  skills/
    manager.py             # 技能安装/列表
  ui/
    renderer.py            # Rich Markdown/Diff 渲染

~/.xcode/                   # 用户数据目录
  config.json              # API key + model + auto_memory + max_tokens + render config
  XCODE.md                 # 用户记忆
  settings.json            # 权限配置
  projects/<name>/memory/
    memory.md              # 自动记忆
  plans/                   # 计划文件
  sessions/                # 聊天日志
  skills/                  # 已安装技能
  bin/                     # ripgrep 等外部二进制
```

## 5. 总代码量

| 目录 | 行数 |
|------|------|
| `core/` | ~2,000 |
| `core/tools/` | ~350 |
| `ui/` | ~37 |
| `skills/` | ~60 |
| 根 (`main.py` + `paths.py`) | ~176 |
| **总计** | **~2,400** |
