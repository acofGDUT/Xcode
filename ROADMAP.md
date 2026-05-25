# Xcode 开发路线图

> **阅读对象**：此文档面向接手的 coding agent（人类或 AI）。每个 Phase 的子任务按依赖顺序排列，包含具体文件路径、数据结构定义、函数签名、关键逻辑描述和验证方法。先读完对应 Phase 全部内容再动手。

---

## 项目概览

- **语言**：Python >= 3.10
- **CLI 框架**：Typer（入口 `src/xcode_cli/main.py`，app 对象）
- **终端 UI**：Rich（Panel/Table/Console） + prompt-toolkit（REPL）
- **LLM 客户端**：openai>=1.40.0（OpenAI 兼容 API）
- **数据目录**：`~/.xcode/`（Windows: `%USERPROFILE%/.xcode/`）
- **源码根目录**：`src/xcode_cli/`

### 关键文件当前状态速查

| 文件 | 职责 | 行数 |
|------|------|------|
| `core/agent.py` | REPL 循环、斜杠命令、工具执行 | 324 |
| `core/llm.py` | OpenAI API 调用、文本解析工具调用 | 74 |
| `core/tools.py` | read_file / write_file / run_shell 实现 | 33 |
| `core/prompting.py` | 系统提示构建 + 技能注入 | 39 |
| `core/config.py` | Config dataclass + ConfigStore JSON 读写 | 45 |
| `core/dashboard.py` | API 配置 TUI | 294 |
| `core/session.py` | JSONL 会话持久化 | 31 |
| `skills/manager.py` | 技能安装/列表 | 60 |
| `paths.py` | ~/.xcode/ 目录初始化 | 14 |
| `main.py` | Typer CLI 入口 | 106 |

---

## Phase 1：协议与工具升级（地基）

**目标**：将工具调用从"文本解析 JSON"升级为 LLM 原生 function calling；新增 edit/grep/glob 三个核心工具；支持流式输出。Phase 1 完成后，Xcode 的工具系统从原型级升级到可用级。

**总预计改动**：约 6 个文件，新增约 400 行，修改约 200 行。

---

### Task 1.1 — 工具注册表 + Schema 定义

**目的**：建立一套工具定义标准，每个工具自带 OpenAI function calling 所需的 JSON Schema。后续新增工具只需按规范添加即可，无需改动 LLM 调用代码。

**文件**：新建 `src/xcode_cli/core/tool_registry.py`

**设计要求**：

1. 定义 `ToolDef` dataclass：
```python
@dataclass
class ToolDef:
    name: str                              # 函数名，如 "read_file"
    description: str                       # 给 LLM 看的功能描述
    parameters: dict                       # JSON Schema properties 部分
    required: list[str]                    # 必填参数名列表
    execute: Callable[..., str]            # 实际执行函数
    is_read_only: bool = True              # 是否只读（权限系统用）
```

2. 定义 `ToolRegistry` 类：
```python
class ToolRegistry:
    def __init__(self): ...
    def register(self, tool: ToolDef) -> None: ...
    def get_openai_schemas(self) -> list[dict]: ...  # 转成 OpenAI tools 参数格式
    def execute(self, name: str, args: dict) -> str: ...  # 按名称执行工具
    def list_names(self) -> list[str]: ...
```

3. `get_openai_schemas()` 的输出格式必须严格按照 OpenAI API 规范：
```python
# 返回 list，每个元素：
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": { ... },
            "required": ["path"],
        },
    },
}
```

4. `execute()` 方法需要：
   - 查找 `name` 对应的 `ToolDef`
   - 如果 name 不存在，返回 `"Error: unknown tool '{name}'"`
   - 调用 `tool.execute(**args)`，捕获所有异常并返回 `"Tool error: {exc}"`

**验证**：单独 import ToolRegistry，注册一个假工具，调用 `get_openai_schemas()` 检查输出格式。

---

### Task 1.2 — 重构现有工具 + 新增 edit/grep/glob

**目的**：把 `tools.py` 中的 3 个函数改为符合 ToolDef 规范的工具模块，同时新增 3 个工具。

**文件**：拆分 `src/xcode_cli/core/tools.py` → 新建 `src/xcode_cli/core/tools/` 包

**新目录结构**：
```
src/xcode_cli/core/tools/
    __init__.py          # 导出 ALL_TOOLS list
    files.py             # read_file / write_file / edit_file
    search.py            # grep / glob
    shell.py             # run_shell
```

**`tools/__init__.py`**：汇总所有 ToolDef，导出 `ALL_TOOLS: list[ToolDef]`，方便 registry 初始化。

---

#### `tools/files.py` — 3 个文件工具

**read_file（改进）**：

当前实现一次读整个文件，大文件会撑爆上下文。改进为支持分页：

```python
def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """
    读取文件内容。
    path: 绝对路径
    offset: 起始行号（0-indexed），默认从第 0 行开始
    limit: 最多读取行数，默认 2000
    返回格式：每行带 "行号\t内容" 前缀（类似 cat -n）
    如果文件不存在返回 "Error: file not found: {path}"
    如果是二进制文件/图片，返回 "Error: cannot read binary file: {path}"
    """
```

实现要点：
- 用 `Path(path).read_text(encoding="utf-8")` 
- 如果 UnicodeDecodeError，尝试作为图片读取（PIL/Pillow），能打开则返回 "This is an image file..." 的描述
- 按 `\n` 分割，取 `[offset : offset + limit]` 切片
- 每行前面加 `{line_number}\t`（行号从 offset+1 开始递增）
- 末尾加 `"## Total lines: {total}"` 如果文件被截断

**write_file（不变）**：保持现有实现，仅包装为 ToolDef。

**edit_file（新增——这是 Phase 1 最核心的新工具）**：

```python
def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """
    精确字符串替换。这是安全编辑文件的核心工具。
    
    path: 要编辑的文件绝对路径
    old_string: 要被替换的字符串（必须在文件中唯一存在，除非 replace_all=True）
    new_string: 替换后的新字符串（必须与 old_string 不同）
    replace_all: 是否替换所有匹配项。默认 False，此时 old_string 必须唯一。
    
    行为规则：
    1. 读取文件全部内容（文本模式）
    2. 如果 replace_all=False：
       - 统计 old_string 出现次数
       - 0 次 → 返回 Error 并列出文件内容让 LLM 看到实际文本
       - >1 次 → 返回 Error 说明出现次数，要求提供更大上下文使匹配唯一
       - ==1 次 → 执行替换
    3. 如果 replace_all=True → 替换所有匹配
    4. 如果 new_string == old_string → 返回 Error（必须不同）
    5. 写入文件并返回 "Successfully edited {path} (N replacements)"
    
    返回值示例：
    - 成功： "Edited D:/foo/bar.py: replaced 1 occurrence(s)"
    - 找不到： "Error: old_string not found in file. File content:\n{前2000行}"
    - 不唯一： "Error: old_string found 3 times in file. Use more context to make it unique, or set replace_all=true"
    """
```

实现要点：
- 这是整个工具系统最关键的工具，实现质量直接影响用户体验
- `replace_all=False` 时的唯一性检查是**安全机制**——防止误改
- 如果 `old_string` 找不到，返回错误时**附带文件内容**（前 2000 行），这样 LLM 可以看到文件实际内容并修正
- 所有字符串比较用原始文本，不要 strip/trim
- 文件编码统一 utf-8

---

#### `tools/search.py` — 2 个搜索工具

**grep（新增）**：

```python
def grep(
    pattern: str,
    path: str = ".",
    glob_filter: str | None = None,
    output_mode: str = "content",
    head_limit: int = 250,
    offset: int = 0,
    case_insensitive: bool = False,
) -> str:
    """
    基于 ripgrep 的内容搜索。实际调用 `rg` 命令行。
    
    pattern: 正则表达式（ripgrep 语法，非 Python re）
    path: 搜索目录，默认当前工作目录
    glob_filter: 文件名过滤，如 "*.py" 或 "*.{ts,tsx}"
    output_mode: "content"（显示匹配行）、"files_with_matches"（只显示文件路径）、"count"（计数）
    head_limit: 最多返回行数，默认 250
    offset: 跳过前 N 条结果
    case_insensitive: 是否忽略大小写
    
    返回：
    - rg 的 stdout 输出
    - 如果 rg 未安装 → "Error: rg (ripgrep) is not installed. Install it from https://github.com/BurntSushi/ripgrep"
    - 如果无匹配 → "No matches found for pattern: {pattern}"
    """
```

实现要点：
- 使用 `subprocess.run(["rg", ...])`，**不使用 shell=True**（安全 + 避免转义问题）
- 构建参数列表：`["rg", "--no-heading", "-n", pattern, path]`
- `output_mode == "files_with_matches"` → 加 `-l`
- `output_mode == "count"` → 加 `-c`
- `case_insensitive` → 加 `-i`
- `glob_filter` → 加 `--glob={glob_filter}`
- 注意：`path` 和 `pattern` 可能包含空格，直接作为 list 元素传入（subprocess 自动处理）

**glob（新增）**：

```python
def glob(pattern: str, path: str = ".") -> str:
    """
    文件模式匹配。使用 Python pathlib.Path.glob()。
    
    pattern: glob 模式，如 "**/*.py"、"src/**/*.ts"
    path: 搜索根目录
    
    返回格式：每行一个匹配的文件路径（按修改时间降序排列）
    最多返回 500 个结果，超出则在末尾显示截断提示
    """
```

实现要点：
- `sorted(Path(path).glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)`
- 只返回文件，跳过目录
- 路径转为绝对路径字符串
- 取前 500 条
- 如果 0 条，返回 `"No files matched pattern: {pattern}"`

---

#### `tools/shell.py` — 1 个 Shell 工具

**run_shell（改进）**：

```python
def run_shell(command: str, cwd: str | None = None, timeout: int = 120000) -> str:
    """
    执行 shell 命令。
    command: 要执行的命令
    cwd: 工作目录，默认当前目录
    timeout: 超时时间（毫秒），默认 120000（2 分钟）
    
    返回：stdout + stderr + exit_code
    超时时返回 "Error: command timed out after {timeout}ms"
    """
```

改进点：
- 用 `subprocess.run(..., timeout=timeout/1000)` 替代当前的无限等待
- 捕获 `subprocess.TimeoutExpired` 异常
- 返回格式保持现有风格（stdout + stderr + exit_code）
- **不要轻易去掉 `shell=True`**——当前用 shell=True 是刻意的，这让 LLM 可以写管道、重定向等复杂命令。但要意识到安全风险，等 Phase 4 权限系统来管控。

---

### Task 1.3 — LLM Client 重写（tool calling + streaming）

**目的**：将 `llm.py` 从"文本解析"模式改为原生 function calling；新增流式回调支持。

**文件**：重写 `src/xcode_cli/core/llm.py`

**当前问题**：`_maybe_parse_tool_call()` 用正则匹配 JSON——LLM 输出格式稍有偏差就失败。

**新设计**：

```python
@dataclass
class ToolCall:
    id: str              # OpenAI 返回的 tool_call_id
    name: str            # 工具名
    args: dict           # 参数

@dataclass  
class LLMResponse:
    content: str                      # 文本内容（可能为空，如果纯 tool call）
    tool_calls: list[ToolCall]        # 工具调用列表（可能为空）
```

**`LLMClient` 类改动**：

1. 构造函数不变（仍从 ConfigStore + 环境变量读配置）

2. 新增 `complete()` 方法签名：

```python
def complete(
    self,
    system_prompt: str,
    messages: list[dict[str, str]],
    tool_schemas: list[dict],          # 从 ToolRegistry.get_openai_schemas() 传入
    on_text_token: Callable[[str], None] | None = None,  # 流式回调
) -> LLMResponse:
```

3. 方法内部逻辑：

```
1. 构建 messages: [{"role":"system","content":system_prompt}, *history]
2. 调用 client.chat.completions.create(
       model=...,
       messages=messages,
       tools=tool_schemas,        # 传入工具定义
       tool_choice="auto",        # LLM 自行决定是否调用工具
       temperature=0.2,
       stream=True,               # 开启流式
   )
3. 遍历 stream chunks:
   - 遇到 delta.content → 累积到 content_parts，同时调用 on_text_token(token) 
   - 遇到 delta.tool_calls → 累积 tool_call 信息
4. 构建 LLMResponse(content=全量文本, tool_calls=解析出的工具调用列表)
5. 如果 api_key 为空 → 返回带错误消息的 LLMResponse（不抛异常）
```

4. 流式遍历的实现细节：

```python
content_parts: list[str] = []
tool_calls_acc: dict[int, dict] = {}  # index → {"id":..., "name":..., "args":...}

for chunk in stream:
    delta = chunk.choices[0].delta
    
    # 文本流
    if delta.content:
        content_parts.append(delta.content)
        if on_text_token:
            on_text_token(delta.content)
    
    # 工具调用流
    if delta.tool_calls:
        for tc in delta.tool_calls:
            idx = tc.index
            if idx not in tool_calls_acc:
                tool_calls_acc[idx] = {"id": "", "name": "", "args": ""}
            if tc.id:
                tool_calls_acc[idx]["id"] = tc.id
            if tc.function and tc.function.name:
                tool_calls_acc[idx]["name"] = tc.function.name
            if tc.function and tc.function.arguments:
                tool_calls_acc[idx]["args"] += tc.function.arguments

# 构建返回
tool_calls = []
for tc_dict in tool_calls_acc.values():
    try:
        args = json.loads(tc_dict["args"])
    except json.JSONDecodeError:
        args = {}
    tool_calls.append(ToolCall(id=tc_dict["id"], name=tc_dict["name"], args=args))
```

5. **删除** `_maybe_parse_tool_call()` 方法——不再需要手动解析。

**验证**：设置好 API key，调用 `complete()` 传入简单的 tools schema（如 read_file），发一条 "读一下 README.md"，检查返回的 `LLMResponse.tool_calls` 是否非空且格式正确。

---

### Task 1.4 — 更新 System Prompt

**目的**：去掉当前 system prompt 中手写 JSON 格式的段落。改用原生 tool calling 后，LLM 从 `tools` 参数获取工具信息，不再需要在 prompt 里描述协议。

**文件**：修改 `src/xcode_cli/core/prompting.py`

**具体改动**：

`BASE_SYSTEM_PROMPT` 从当前内容改为：

```python
BASE_SYSTEM_PROMPT = """You are Xcode, a local coding CLI agent. You help users with software engineering tasks.

Guidelines:
- Be concise, clear, and action-oriented.
- Use the provided tools to read files, search code, edit files, and run shell commands.
- Prefer using the edit_file tool over write_file for modifying existing files — it's safer and shows exactly what changed.
- Use grep and glob to search the codebase before asking the user where things are.
- Read files to understand context before making changes. Do not guess.
- When you don't know something about the codebase, search for it rather than asking the user.
- Default to no comments in code. Only add comments when the WHY is non-obvious.
- Write short, focused responses. Don't narrate your process unless asked.
"""
```

关键变化：**删除了** "output a single JSON action in this format: ..." 以及 "Tool args: read: {...}" 的全部内容。

---

### Task 1.5 — Agent 适配新协议 + 流式输出

**目的**：修改 `agent.py`，接入 ToolRegistry + 新 LLMClient + 流式输出。这是 Phase 1 的集成点，将所有新组件连接起来。

**文件**：修改 `src/xcode_cli/core/agent.py`

**具体改动**：

1. **构造函数**：新增初始化 ToolRegistry 并注册所有工具

```python
from xcode_cli.core.tool_registry import ToolRegistry
from xcode_cli.core.tools import ALL_TOOLS

class AgentRuntime:
    def __init__(self):
        self.console = Console()
        self.sessions = SessionStore()
        self.skills = SkillManager()
        self.config_store = ConfigStore()
        self.llm = LLMClient()
        self.tools = ToolRegistry()
        for t in ALL_TOOLS:
            self.tools.register(t)
        self.prompt = PromptSession(
            completer=SlashCompleter(),
            auto_suggest=AutoSuggestFromHistory()
        )
```

2. **`run_chat()` 主循环**中的 LLM 调用逻辑需要改为处理多轮 tool calling：

```python
# 当前逻辑（一轮）：
#   llm_res = self.llm.complete(...)
#   if llm_res.tool_call: 执行工具 → 再调一次 LLM

# 新逻辑（支持多轮 + 流式）：
#   调用 _run_llm_loop(history) → 内部处理流式输出和多轮 tool calling
```

3. **新增 `_run_llm_loop()` 方法**——处理流式输出 + 工具调用循环：

```python
def _run_llm_loop(self, history: list[dict], system_prompt: str) -> str:
    """
    调用 LLM，流式打印文本，执行工具调用，循环直到 LLM 返回纯文本。
    返回最终的文本响应。
    """
    max_tool_rounds = 10  # 防止无限循环
    
    for round_num in range(max_tool_rounds):
        # 流式回调：实时打印 token
        content_buffer = []
        def on_token(token: str):
            content_buffer.append(token)
            self.console.print(token, end="")
        
        response = self.llm.complete(
            system_prompt=system_prompt,
            messages=history,
            tool_schemas=self.tools.get_openai_schemas(),
            on_text_token=on_token,
        )
        
        # 如果有文本内容，先打印换行
        if content_buffer:
            self.console.print()
        
        # 如果无工具调用 → 返回文本
        if not response.tool_calls:
            return response.content
        
        # 执行所有工具调用
        for tc in response.tool_calls:
            self.console.print(f"[dim]## tool.{tc.name}[/dim]")
            result = self.tools.execute(tc.name, tc.args)
            self.console.print(f"[dim]{result[:200]}[/dim]")  # 截断显示
            
            # 将 tool call 和 result 追加到 history
            history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.args)}
                }]
            })
            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    
    return "Reached maximum tool call rounds."
```

4. **消息格式注意**：OpenAI 的 tool call 消息格式与普通文本消息不同：
   - assistant 带 tool_calls：`{"role": "assistant", "content": null, "tool_calls": [...]}`
   - tool 结果：`{"role": "tool", "tool_call_id": "...", "content": "..."}`

5. **流式输出的用户体验**：
   - 先打印 `assistant ▸ ` 前缀（紫色），然后流式追加文本
   - 文本打印完成后换行
   - 再打印工具调用信息（dim 样式，低调）

**验证**：启动 `xcode chat`，输入"读一下 README.md 前 20 行"。应看到：
1. 流式输出 LLM 的文字回复
2. 出现 `## tool.read_file` 提示
3. 返回文件内容
4. LLM 基于内容给出最终回复

---

### Task 1.6 — CLI 入口更新 + pyproject.toml 依赖

**文件**：修改 `src/xcode_cli/main.py`

**改动**：`tool run` 命令需要支持新的 edit/grep/glob 工具：

```python
@tool_app.command("run")
def tool_run(
    kind: str = typer.Argument(..., help="Tool type: read|write|edit|shell|grep|glob"),
    ...
):
```

参数处理逻辑保持不变，增加 `edit/grep/glob` 的分支即可。

**文件**：修改 `pyproject.toml`

依赖不变（ripgrep 是外部二进制，通过 `subprocess` 调用，不是 Python 包）。可选：添加 `Pillow>=10.0.0` 用于图片检测。

---

### Phase 1 完成标准

- [ ] `xcode chat` 启动正常
- [ ] 流式输出：LLM 回复逐字打印，不等完整响应
- [ ] 工具调用：LLM 正确触发 read_file / write_file / edit_file / grep / glob / run_shell
- [ ] `edit_file` 唯一性检查：相同字符串出现 2 次时报错，1 次时正常替换
- [ ] `grep` 在无 ripgrep 时给出友好错误提示
- [ ] `glob` 返回匹配文件列表
- [ ] 多轮工具调用：LLM 可以连续调用多个工具后再回复
- [ ] 回退兼容：旧的 `/skill` `/env` `/dashboard` `/exit` 斜杠命令仍正常工作

---

## Phase 2：Agent 架构升级

**目标**：支持子 Agent 派发、后台任务执行、任务追踪。主 Agent 可以将独立任务分派给子 Agent。

**依赖**：Phase 1 全部完成。本 Phase 大部分代码是新增文件，对现有代码侵入小。

---

### Task 2.1 — 定义 Agent 类型和消息协议

**新建文件**：`src/xcode_cli/core/agent_types.py`

```python
from dataclasses import dataclass
from enum import Enum

class AgentType(Enum):
    GENERAL = "general"        # 通用 Agent（读写代码）
    EXPLORE = "explore"        # 只读探索 Agent（仅 read/grep/glob）
    PLAN = "plan"              # 设计 Agent（不做代码修改）

@dataclass
class AgentTask:
    task_id: str               # UUID
    agent_type: AgentType
    prompt: str                # 子 Agent 的初始 prompt
    result: str | None = None  # 执行结果（完成后填充）
    status: str = "pending"    # pending / running / done / error
```

---

### Task 2.2 — 子 Agent 执行器

**新建文件**：`src/xcode_cli/core/sub_agent.py`

**核心类**：`SubAgentExecutor`

```python
class SubAgentExecutor:
    """
    独立运行一个 LLM Agent 会话。
    拥有自己的 LLMClient、ToolRegistry（仅限该类型允许的工具）、对话历史。
    """
    def __init__(self, agent_type: AgentType, llm_client: LLMClient):
        ...
    
    def run(self, prompt: str) -> str:
        """
        同步执行——启动一个完整的 Agent 循环：
        1. 构建 system prompt（根据 agent_type 不同）
        2. 发送 prompt 作为首条 user 消息
        3. 循环：LLM → 工具调用 → 工具执行 → 追加结果 → 直到 LLM 返回纯文本
        4. 返回最终文本
        """
```

**不同类型 Agent 的工具限制**：
- EXPLORE：只能使用 read_file / grep / glob（不注册 write_file / edit_file / run_shell）
- PLAN：只能使用 read_file / grep / glob（和 EXPLORE 一样，只读）
- GENERAL：全部工具

**不同类型的 system prompt**：
- EXPLORE：强调"只搜索和阅读代码，不做修改，输出精简"
- PLAN：强调"分析代码并设计方案，输出结构化的计划"
- GENERAL：同主 Agent

**关键约束**：
- `run()` 是同步阻塞调用——调用方需要等它执行完
- 子 Agent 不打印任何 UI 输出——所有结果通过返回值传递
- 子 Agent 的最大工具调用轮数限制为 15 轮

---

### Task 2.3 — Agent 派发工具

**新建文件**：`src/xcode_cli/core/tools/agent_tool.py`

这是一个特殊的工具，让主 Agent 可以派发子 Agent：

```python
def dispatch_agent(agent_type: str, prompt: str) -> str:
    """
    派发一个子 Agent 执行独立任务。子 Agent 是独立的 LLM 会话，互不干扰。
    
    agent_type: "explore" | "plan" | "general"
    prompt: 子 Agent 的任务描述（要完整自包含，子 Agent 看不到主会话上下文）
    
    返回：子 Agent 的完整执行结果文本
    """
```

注册到 ToolRegistry 时，`is_read_only` 取决于 agent_type——explore/plan 为 True，general 为 False。

**注意**：这个工具有一个循环依赖问题——`dispatch_agent` 需要访问 `LLMClient` 实例。解决方案是用闭包或工厂函数：

```python
def create_dispatch_agent_tool(llm_client: LLMClient, config_store: ConfigStore) -> ToolDef:
    def dispatch_agent(agent_type: str, prompt: str) -> str:
        executor = SubAgentExecutor(AgentType(agent_type), llm_client, config_store)
        return executor.run(prompt)
    
    return ToolDef(
        name="dispatch_agent",
        description="...",
        parameters={...},
        required=["agent_type", "prompt"],
        execute=dispatch_agent,
        is_read_only=False,
    )
```

在 `AgentRuntime.__init__()` 中调用此工厂函数，将返回的 ToolDef 注册到 ToolRegistry。

---

### Task 2.4 — 并行 Agent 执行

**目的**：当主 Agent 一次性调用多个 `dispatch_agent`（在上一步 LLM 响应中返回多个 tool_calls），这些调用应该并行执行。

**改动位置**：`agent.py` 的 `_run_llm_loop()` 方法

当 `len(response.tool_calls) > 1` 且所有 tool_calls 都是 `dispatch_agent` 时，使用 `concurrent.futures.ThreadPoolExecutor` 并行执行：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# 在 _run_llm_loop 中，执行工具调用时：
if all(tc.name == "dispatch_agent" for tc in response.tool_calls):
    with ThreadPoolExecutor(max_workers=len(response.tool_calls)) as executor:
        futures = {
            executor.submit(self.tools.execute, tc.name, tc.args): tc 
            for tc in response.tool_calls
        }
        for future in as_completed(futures):
            tc = futures[future]
            result = future.result()
            # 追加到 history...
else:
    # 顺序执行
    for tc in response.tool_calls:
        result = self.tools.execute(tc.name, tc.args)
        # ...
```

**不用 asyncio**——当前项目是同步代码，ThreadPoolExecutor 对 I/O 密集型任务（LLM API 调用）足够好，不会引入异步传染。

---

### Task 2.5 — 任务追踪系统

**新建文件**：`src/xcode_cli/core/task_tracker.py`

```python
@dataclass
class Task:
    id: str
    subject: str          # 简短标题
    description: str      # 详细描述
    status: str           # pending / in_progress / completed / deleted
    blocked_by: list[str] # 依赖的任务 ID 列表
    blocks: list[str]     # 被此任务阻塞的任务 ID 列表

class TaskTracker:
    def __init__(self): ...
    def create(self, subject: str, description: str) -> Task: ...
    def update(self, task_id: str, status: str) -> Task: ...
    def list_all(self) -> list[Task]: ...
    def add_dependency(self, task_id: str, blocked_by_id: str) -> None: ...
```

对应的 3 个工具（注册到 ToolRegistry）：
- `task_create(subject, description)` → 创建任务
- `task_update(task_id, status)` → 更新状态
- `task_list()` → 列出所有任务

这些工具注册为 `is_read_only=False`。

---

### Phase 2 完成标准

- [ ] `dispatch_agent(agent_type="explore", prompt="找到所有定义 API 路由的地方")` 能正常执行并返回结果
- [ ] 主 Agent 在一次回复中派发 2 个 explore 子 Agent，它们并行执行
- [ ] TaskCreate/TaskUpdate/TaskList 工具可用
- [ ] 子 Agent 不能调用 write_file/edit_file/run_shell（如果是 explore 类型）

---

## Phase 3：计划与记忆

**目标**：增加”先计划再执行”的工作流和跨会话记忆系统。

**依赖**：Phase 1 完成。Phase 2 可选（不强制依赖）。

**设计原则**：
- 极简优先：只保留高频、可解释、可审计的能力
- 文件可见：所有长期记忆可直接打开编辑（markdown）
- 跨会话稳定：新会话自动注入记忆，不依赖人工重复输入
- 自然语言优先：Agent 通过自然表达即可触发写入，不要求记忆专用命令

---

### Task 3.1 — 计划模式（EnterPlanMode / ExitPlanMode）

**核心理念**：用户通过 `/plan enter` 或 LLM 调用 `enter_plan_mode` 工具进入计划模式，Agent 探索代码、设计方案、写入计划文件、等用户审批。

**新建文件**：`src/xcode_cli/core/planning.py`

**`PlanMode` 状态机**：

```
普通模式 ──enter_plan_mode──→ 计划模式（system prompt 切换为只读探索）
                                     │
                                LLM 调用 write_plan 写方案
                                     │
                                LLM 调用 exit_plan_mode
                                     │
                                等待用户审批（pending_approval=True）
                                     │
                          approve ←┴→ reject
                            │              │
                      按计划执行      回到普通模式
```

**3 个工具**（注册到 ToolRegistry）：

| 工具 | is_read_only | 说明 |
|------|:---:|------|
| `enter_plan_mode` | True | 进入计划模式，system prompt 切换 |
| `write_plan(content)` | False | 写入计划文件到 `~/.xcode/plans/` |
| `exit_plan_mode(plan_summary)` | True | 完成计划，等待用户审批 |

**用户命令**：`/plan enter` `/plan show` `/plan approve` `/plan reject`

**审批输入**：支持 `approve`/`同意`/`批准`/`通过` 和 `reject`/`拒绝`/`驳回`

**Agent 改动**（`agent.py`）：

在 `run_chat()` 中增加模式切换：
```python
if self.plan_mode.is_active:
    system_prompt = self.plan_mode.get_system_prompt()
else:
    system_prompt = build_system_prompt(...)

final_text = self._run_llm_loop(history, system_prompt)

if self.plan_mode.pending_approval:
    self._show_plan_and_ask_approval()
```

---

### Task 3.2 — 记忆系统（XCODE.md 双文件模型）

**核心理念**：废弃旧的多文件索引体系，统一为 `XCODE.md` 双文件模型，对标 Claude Code 记忆系统——无专用 memory 工具，Agent 通过自然语言判断何时写入，记忆自动注入 system prompt。

**数据目录结构**：

```
~/.xcode/
  XCODE.md                              # 用户记忆（长期，跨项目共享）
  projects/<project>/memory/
    memory.md                           # 自动记忆（单文件，每行一条分类条目）

<project_root>/
  XCODE.md                              # 项目记忆（项目内约束、约定、决策）
```

**auto memory 条目格式**：`- type: <user|feedback|project|reference> | note: <content>`

**与 Claude Code 记忆系统的对标**：

| 特性 | Claude Code | Phase 3 重构后 |
|------|-------------|----------------|
| 项目级指令 | `CLAUDE.md` / `.claude/CLAUDE.md` | `<project>/XCODE.md` |
| 用户级记忆 | `~/.claude/projects/<name>/memory/` | `~/.xcode/XCODE.md` |
| 自动记忆 | Agent 自主写入 `.md` 文件 | Agent 自主写入 `~/.xcode/projects/<project>/memory/memory.md` |
| 专用 CRUD 工具 | 无（用 Write/Read 工具） | 无（用 write_file/read_file 工具） |
| 注入方式 | 每次会话自动注入 system prompt | 每次会话自动注入 system prompt |
| 开关控制 | 系统指令控制 | `auto_memory` 配置 + `/memory auto on/off` |

**`MemoryManager` 类**（重写 `memory.py`）：

```python
class MemoryManager:
    def __init__(self, cwd: str | None = None):
        # cwd 用于定位项目 XCODE.md

    # ── 路径与存在性 ──
    def user_memory_path(self) -> Path: ...       # ~/.xcode/XCODE.md
    def project_memory_path(self) -> Path: ...     # {cwd}/XCODE.md
    def has_user_memory(self) -> bool: ...
    def has_project_memory(self) -> bool: ...

    # ── 读取 ──
    def read_user_memory(self) -> str: ...
    def read_project_memory(self) -> str: ...

    # ── 写入（默认追加） ──
    def write_user_memory(self, content: str, append: bool = True) -> None: ...
    def write_project_memory(self, content: str, append: bool = True) -> None: ...

    # ── auto-memory 写入（由 LLM 通过 write_file 工具完成，MemoryManager 不参与）──
    def is_auto_memory_enabled(self, cfg: Config) -> bool: ...

    # ── auto-memory 读取（供 prompt 注入用）──
    def read_auto_memory_entries(self) -> list[tuple[str, str]]:
        """解析 memory.md 返回 [(type, note), ...]. 仅内部使用."""
    def read_auto_memory_context(self, limit: int = 5) -> str:
        """取最后 limit 条，拼成多行文本返回."""

    # ── prompt 注入（核心方法） ──
    def get_context_for_prompt(self, cfg: Config) -> str:
        “””
        拼接记忆上下文，注入优先级：
        1. Project XCODE.md  （上限 2000 chars）
        2. User XCODE.md     （上限 2000 chars）
        3. Auto memory       （上限 1200 chars，仅 auto_memory=True 时）
        总上限 5000 chars
        “””
```

**删除内容**：
- `MemoryEntry` dataclass
- `MEMORY.md` 索引文件
- 4 个专用 memory 工具（`memory_list` / `memory_get` / `memory_save` / `memory_delete`）
- frontmatter 解析逻辑

**Agent 如何操作记忆**：Agent 使用已有的 `write_file` / `edit_file` 工具直接操作记忆文件。Auto memory 写入使用 `write_file(path=memory.md, content=”...”, append=true)`，长期记忆写入使用 `edit_file` 追加到 XCODE.md。system prompt 中描述完整的类型定义、负面清单、读写规则和验证步骤。

**设计决策（2026-05-24）**：auto memory 写入从「内联格式 + 代码正则抓取」（路径 A）改为「write_file + append 工具调用」（路径 B）。理由：
- 路径 A 要求 LLM 在自然语言中夹带格式行，不可靠；_try_persist_auto_memory 只在无 tool_calls 时触发，窗口太窄
- 路径 B 中 LLM 显式调用工具，行为可审计（对话中可见工具调用），触发时机不受限
- memory.py 从 236 行精简到 ~120 行，只保留读取 + 注入，所有智能判断由 prompt 驱动

---

### Task 3.3 — Project Root 统一解析 + 检索安全边界（修复跨盘检索 bug）

**问题背景**：
当前 `grep/glob` 默认 `path="."`，实际搜索根目录取决于进程启动时工作目录（CWD）。在 Windows 上如果会话从 `D:\` 或 `C:\` 等位置启动，Agent 可能把“项目检索”扩展到整个盘符，导致误检索、慢检索。

**改造目标**：
1. 引入统一项目根解析器 `ProjectRootResolver`（可先用函数实现）
2. 统一 `AgentRuntime.cwd`、`MemoryManager`、`grep/glob` 的默认根目录来源
3. 增加安全保护：禁止默认在文件系统根目录（Windows 盘符根 / POSIX `/`）执行检索
4. 启动时明确展示 `Project Root`，便于用户感知当前检索范围

**建议优先级**：
- `--project-root` 显式参数（后续可加）
- 环境变量 `XCODE_PROJECT_ROOT`
- 启动目录向上查找项目标记（`.git` / `pyproject.toml` / `package.json`）
- fallback 到当前目录

**实现涉及**：
- 新增：`src/xcode_cli/core/project_root.py`
- 修改：`agent.py`（`self.cwd` 由 resolver 提供，不再裸用 `os.getcwd()`）
- 修改：`tools/search.py`（当 path 为默认值时使用 project root；根目录搜索拦截）
- 修改：欢迎信息增加 `Project Root` 行

---

### Task 3.4 — Config 扩展 + /memory 命令

**Config 新增字段**（`config.py`）：

```python
@dataclass
class Config:
    ...
    auto_memory: bool = True  # 默认开启自动记忆
```

**`/memory` 命令**（`agent.py`）：

| 命令 | 功能 |
|------|------|
| `/memory` | 显示 auto-memory 状态 + 项目/用户 XCODE.md 路径与存在性 |
| `/memory auto on` | 开启自动记忆，持久化到 config.json |
| `/memory auto off` | 关闭自动记忆，持久化到 config.json |

---

### Phase 3 完成标准

- [ ] `/plan enter` 进入计划模式，system prompt 切换为只读探索
- [ ] `write_plan` + `exit_plan_mode` 完整流程可走通
- [ ] 用户可通过 `approve`/`reject` 审批计划
- [ ] `~/.xcode/XCODE.md` 用户记忆跨会话持久化
- [ ] `<project>/XCODE.md` 项目记忆在新会话中自动注入 system prompt
- [ ] `/memory` 命令显示状态，`/memory auto on/off` 持久化
- [ ] Project Root 解析统一生效（Agent / Memory / Search 使用同一根目录）
- [ ] `grep/glob` 默认检索不再依赖随机 CWD，不会跨盘误扫
- [ ] 默认拒绝在文件系统根目录执行检索（除非用户显式指定更窄 path）
- [ ] 启动欢迎信息展示当前 `Project Root`
- [ ] 旧 memory 工具（list/get/save/delete）已完全下线
- [ ] 注入长度自动截断保护（单段 2000 chars，总计 5000 chars）

> 说明：不再要求”Agent 自动判断复杂任务并自动进入计划模式”，保留手动 `/plan enter` 提供更高可控性与更低误触发成本。记忆操作不使用专用工具，由 Agent 通过 write_file/edit_file 直接操作 XCODE.md 文件。

---

## Phase 4：安全与体验

**目标**：权限控制 + UI 升级 + 上下文管理。让 Xcode 从"能用"变成"好用且安全"。

**依赖**：Phase 1 完成。Phase 2-3 可选。

---

### Task 4.1 — 权限系统

**新建文件**：`src/xcode_cli/core/permissions.py`

**设计**：

```python
@dataclass
class ToolPermission:
    tool_name: str
    level: str  # "allow" | "deny" | "ask"

class PermissionManager:
    def __init__(self, config: Config): ...
    def check(self, tool_name: str) -> str: ...  # 返回 allow/deny/ask
    def prompt_user(self, tool_name: str, args: dict) -> bool: ...  # 交互式询问
```

**权限规则优先级**（从高到低）：
1. 会话中用户显式设置的规则
2. 项目级 `.xcode/config.json` 中的 rules
3. 全局 `~/.xcode/config.json` 中的 rules
4. 默认：run_shell → ask，write_file/edit_file → ask，read_file/grep/glob → allow

**Agent 改动**（`agent.py` 的 `_run_llm_loop()`）：
在 `self.tools.execute()` 之前插入权限检查：

```python
for tc in response.tool_calls:
    level = self.permissions.check(tc.name)
    if level == "deny":
        result = f"Permission denied for tool: {tc.name}"
        # 记录一条 tool result 后继续下一个，避免执行工具
        continue

    if level == "ask":
        approved = self.permissions.prompt_user(tc.name, tc.args)
        if not approved:
            result = f"User denied tool: {tc.name}"
            # 记录一条 tool result 后继续下一个，避免执行工具
            continue

    # allow 或 ask 且用户已批准
    result = self.tools.execute(tc.name, tc.args)
    ...
```

**配置文件**：新建 `~/.xcode/settings.json` 支持：

```json
{
    "permissions": {
        "run_shell": "ask",
        "write_file": "allow",
        "edit_file": "allow"
    }
}
```

---

### Task 4.2 — UI 升级

**目标**：更好的 Markdown 渲染、代码块语法高亮、内联 diff。

**详细设计**：见 `UI_REDESIGN.md`（对话气泡重构、先审后执行、工具展示、状态栏增强、欢迎屏简化）。

**新建文件**：`src/xcode_cli/ui/renderer.py`

```python
class OutputRenderer:
    """封装 Rich 渲染逻辑，统一输出风格"""
    
    @staticmethod
    def render(text: str) -> None:
        """
        用 Rich 渲染 markdown 文本。
        - 代码块：用 pygments 语法高亮 + Panel 包裹
        - 标题：Rich 的 Rule/Header
        - 列表/表格：对应 Rich 组件
        """
    
    @staticmethod
    def render_diff(old: str, new: str, file_path: str) -> None:
        """
        用 Rich 渲染 diff（类似 git diff）。
        使用 Python difflib 生成差异，红色表示删除行，绿色表示新增行。
        """
```

**Agent 改动**：`_print_assistant_bubble()` 改用 `OutputRenderer.render()` 替代简单的 `Panel(text)`。

**新增依赖**：`pygments>=2.17.0`（语法高亮）

---

### Task 4.3 — 上下文管理

**目的**：当对话历史超过 token 限制时，自动压缩/截断旧消息，避免 API 调用失败。

**状态**：已在 Phase 4.5 Batch 1 完成并通过 review（2026-05-25）。

**文件**：`src/xcode_cli/core/context.py`（新建）、`src/xcode_cli/core/config.py`（修改）、`src/xcode_cli/core/agent.py`（修改）

#### 4.3.1 核心逻辑

```python
class ContextManager:
    """
    管理对话历史的 token 用量。
    
    策略：
    1. 粗略估算 token 数（英文：~4 字符/token，中文：~1.5 字符/token）
    2. 当预估 token 超过 max_tokens 的 80% 时触发压缩
    3. 压缩方式：保留 system prompt + 最近 N 轮完整对话，中间的对话用 LLM 做摘要
    """
    
    def __init__(self, max_tokens: int = 128000) -> None:
        self.max_tokens = max_tokens
    
    def estimate_tokens(self, messages: list[dict]) -> int: ...
    def should_compress(self, messages: list[dict]) -> bool: ...
    def compress(self, messages: list[dict], llm_client) -> list[dict]:
        """
        压缩策略：
        1. 保留首条 user 消息（用户初始需求）
        2. 保留最后 8 轮完整对话
        3. 中间部分：调用 LLM 生成一段摘要
        4. 将摘要作为 system 消息插入
        """
```

#### 4.3.2 MAX_TOKENS 动态化（2026-05-24 设计）

**问题**：当前 `MAX_TOKENS = 200000` 硬编码，`should_compress()` 阈值 = 200k × 0.8 = 160k。默认模型 `gpt-4o-mini` 上下文窗口仅 128k，压缩永远不会触发，API 在到达阈值前就返回 "context length exceeded"。

**方案**：

**Step 1 — Config 增加 `max_tokens` 字段**（`config.py`）：

```python
@dataclass
class Config:
    # ... 现有字段 ...
    max_tokens: int = 128000  # 默认匹配 gpt-4o-mini/4o 的 128k 窗口
```

`ConfigStore.load()` / `save()` 同步读写该字段。

**Step 2 — ContextManager 从 Config 读取**（`context.py`）：

- 移除类常量 `MAX_TOKENS = 200000`
- `__init__(self, max_tokens: int = 128000)` 接收 runtime token budget
- `should_compress()` 用 `self.max_tokens` 替代硬编码值

**Step 3 — Agent 传入 Config**（`agent.py`）：

```python
# 构造时传入
self.context = ContextManager(max_tokens=self.config_store.load().max_tokens)
```

**Step 4 — 用户可手动覆盖**（可选，`/env max-tokens <value>`）：

在 `_handle_env_command()` 中增加 `max-tokens` 子命令，允许用户切换模型后手动调整上下文窗口大小。

**实现补充**：

- `/context` 展示当前 runtime `max_tokens` 和压缩阈值
- `tests/test_context.py`、`tests/test_config.py`、`tests/test_agent_env.py` 提供本批次测试基线

**后期可选增强**：根据 model 名称自动推断（如 `gpt-4o-mini` → 128k, `deepseek-chat` → 64k, `claude-3.5-sonnet` → 200k），但当前手动配置已覆盖需求。

#### 4.3.3 摘要提示词英文化

`compress()` 中的中文摘要提示词改为英文，与 `BASE_SYSTEM_PROMPT` 风格一致：

```python
# 当前（中文，不一致）
summary_prompt = "请将以下对话压缩为 200 字以内摘要，保留关键需求、已完成操作、未完成事项、约束条件。"

# 改为（英文，与 system prompt 一致）
summary_prompt = (
    "Summarize the following conversation in under 200 words. "
    "Keep: key requirements, completed actions, pending items, constraints."
)
```

#### 4.3.4 改动文件清单

| 文件 | 改动 |
|------|------|
| `config.py` | Config 增加 `max_tokens: int = 128000`；ConfigStore 读写该字段 |
| `context.py` | 移除 `MAX_TOKENS` 常量；`__init__` 接收 Config；摘要提示词改英文 |
| `agent.py` | `ContextManager(config=...)` 构造传参；可选 `/env max-tokens` 命令 |

---

### Task 4.4 — 流式思考展示与耗时统计

**目的**：在模型思考期间给用户可感知的反馈——不等、不黑屏、知道 LLM 在动。

**三个阶段**：

**阶段 1 — 等待指示**（第一个 token 到达前）

在 `_run_llm_loop()` 中，调用 `self.llm.complete()` 之前启动计时，在首个 token 到达前显示 `[dim]Thinking...[/dim]`，首个 token 到达后擦除或覆盖。

```python
# agent.py _run_llm_loop() 伪代码
start_time = time.monotonic()
thinking_shown = False

def on_token(token: str) -> None:
    nonlocal thinking_shown
    if not thinking_shown:
        elapsed = time.monotonic() - start_time
        # 擦除 "Thinking..." 行，打印耗时
        self.console.print(f"[dim]({elapsed:.1f}s)[/dim] ", end="")
        thinking_shown = True
    content_buffer.append(token)
    self.console.print(token, end="")
```

**阶段 2 — reasoning 流式展示**

`llm.py` 新增 `on_reasoning_token` 回调，与现有的 `on_text_token` 对称。`agent.py` 收到后以折叠或 dim 样式实时打印思考内容。

```python
# llm.py complete() 签名新增参数
def complete(
    self,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tool_schemas: list[dict],
    on_text_token: Callable[[str], None] | None = None,
    on_reasoning_token: Callable[[str], None] | None = None,   # 新增
) -> LLMResponse:
```

```python
# agent.py _run_llm_loop() 中
def on_reasoning_token(token: str) -> None:
    self.console.print(f"[dim]{token}[/dim]", end="")
    reasoning_buffer.append(token)
```

**阶段 3 — 耗时总结**

每轮 LLM 调用结束时，打印 `[dim](思考 {reasoning_ms}ms / 回复 {response_ms}ms)[/dim]`。这对排查性能问题和用户感知模型快慢都有用。

```python
# 在 complete() 返回后
response_time = (time.monotonic() - start_time) * 1000
self.console.print(f"[dim]({response_time:.0f}ms)[/dim]")
```

**改进后用户体验对比**：

```
# 当前：黑屏等到第一个 token
assistant ▸ [等 3 秒...] 这段代码的作用是...

# 改进后：
assistant ▸ Thinking... (3.2s)
[dim]用户询问的是...[/dim]  # reasoning 实时流出
这段代码的作用是...         # 正式回复
(dim 思考 3200ms / 回复 1500ms)
```

**涉及文件**：
- `src/xcode_cli/core/llm.py` — `complete()` 新增 `on_reasoning_token` 回调；流式循环中触发
- `src/xcode_cli/core/agent.py` — `_run_llm_loop()` 增加计时 + reasoning 回调 + 耗时总结

**新增依赖**：无（全部用标准库 `time` + 已有 Rich dim 样式）。

---

### Phase 4 完成标准

- [x] shell 命令需要用户确认才能执行（如果权限设为 ask）
- [x] Markdown 代码块有语法高亮
- [x] edit_file 执行后展示 diff 对比
- [x] 长对话自动压缩，压缩阈值根据 Config.max_tokens 动态计算（不再硬编码 200k）
- [x] `/env max-tokens <value>` 可手动调整上下文窗口大小
- [x] 压缩摘要提示词与 BASE_SYSTEM_PROMPT 语言一致（英文）
- [x] 等待首个 token 时显示 Thinking... 指示
- [x] 思考模型（DeepSeek R1 等）的推理过程以 dim 样式流式展示
- [x] 每轮 LLM 调用完成后显示耗时

---

## Phase 5：生态扩展

**目标**：WebFetch/WebSearch、定时任务、Git 集成、Hooks 系统。这些功能彼此独立，可任意顺序实现。

**依赖**：Phase 1。其余 Phase 不强制依赖。

---

### Task 5.1 — WebFetch 工具

**新建文件**：`src/xcode_cli/core/tools/web.py`

```python
def web_fetch(url: str, prompt: str) -> str:
    """
    抓取网页内容并用小型模型处理。
    
    实现：
    1. requests.get(url, timeout=15)
    2. 用 BeautifulSoup 提取正文（去除 script/style/nav 等）
    3. 将 HTML 转为纯文本（截断为 8000 字符）
    4. 如果有 prompt，用 LLM（轻量模型）按 prompt 要求总结/提取
    5. 返回处理后的文本
    """
```

**新增依赖**：`requests>=2.31.0`, `beautifulsoup4>=4.12.0`

**安全约束**：
- 仅允许 HTTP/HTTPS URL
- 禁止访问 localhost / 127.0.0.1 / 内网 IP 段
- 超时 15 秒
- 返回内容截断为 10000 字符

---

### Task 5.2 — WebSearch 工具

```python
def web_search(query: str) -> str:
    """
    网络搜索。使用 DuckDuckGo Instant Answer API（免费，无需 key）。
    
    实现：
    1. requests.get("https://api.duckduckgo.com/?q={query}&format=json")
    2. 解析 Abstract + RelatedTopics
    3. 返回格式化的搜索结果
    """
```

如果不依赖外部 API，可以调用 `https://html.duckduckgo.com/html/?q={query}` 解析搜索结果页。

---

### Task 5.3 — 定时任务

**新建文件**：`src/xcode_cli/core/scheduler.py`

支持两种模式：

1. **Cron 定时**：用 Python `schedule` 库，指定 cron 表达式
2. **单次延时**：`threading.Timer` 实现

```python
@dataclass
class ScheduledJob:
    job_id: str
    cron: str          # "*/5 * * * *" 或 ISO timestamp
    prompt: str        # 到时间后执行什么
    recurring: bool
    durable: bool      # 是否持久化到磁盘

class Scheduler:
    def add(self, job: ScheduledJob) -> str: ...  # 返回 job_id
    def remove(self, job_id: str) -> None: ...
    def list_all(self) -> list[ScheduledJob]: ...
```

---

### Task 5.4 — Git 集成工具

**新建文件**：`src/xcode_cli/core/tools/git.py`

提供以下工具（每个都是对 git 命令的安全封装）：

- `git_status()` —— 读取 `git status --porcelain`
- `git_diff(staged: bool)` —— 读取 `git diff` 或 `git diff --staged`
- `git_log(n: int)` —— 读取 `git log --oneline -n {n}`
- `git_add(files: list[str])` —— `git add` 指定文件
- `git_commit(message: str)` —— `git commit -m`
- `git_create_branch(name: str)` —— `git checkout -b`
- `git_switch(branch: str)` —— `git checkout`

**安全约束**：
- 永远不执行 `git push --force` 或 `git reset --hard`（硬编码禁止）
- 永远不跳过 hooks（`--no-verify` 等）
- `git_commit` 使用 HEREDOC 方式传 message

---

### Task 5.5 — Hooks 系统

**新建文件**：`src/xcode_cli/core/hooks.py`

事件钩子机制：在特定时机执行用户配置的 shell 命令。

```python
class HookEvent(Enum):
    SESSION_START = "session_start"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    SESSION_END = "session_end"

class HookManager:
    def __init__(self, config: Config): ...
    def fire(self, event: HookEvent, context: dict) -> None:
        """执行所有注册在此事件上的 hooks"""
```

配置（`~/.xcode/settings.json`）：

```json
{
    "hooks": {
        "session_start": [
            "echo 'Xcode session started at $(date)' >> ~/.xcode/log"
        ],
        "pre_tool_use": [
            "echo 'About to run: {{tool_name}}' "
        ]
    }
}
```

**注意**：Hooks 的执行可能阻塞，需要设置超时（默认 10 秒）。如果 hook 超时或失败，打印警告但不阻止操作继续。

---

### Task 5.6 — 项目级配置

**目的**：支持项目级 `.xcode/settings.json`，让不同项目有不同的权限/技能配置。

**改动**：`ConfigStore` 增加加载优先级逻辑：

```
加载顺序（后者覆盖前者）：
1. ~/.xcode/config.json          （全局配置）
2. ./xcode/settings.json        （项目配置）
3. ./.xcode/settings.local.json （项目本地配置，不提交 git）
```

在 `AgentRuntime.__init__()` 中，`ConfigStore.load()` 改为 `ConfigStore.load_merged()`，自动检测当前工作目录下的 `.xcode/` 配置并合并。

---

## 附录 A：架构演进路线图

```
当前 (v0.1.0)：
  main.py → AgentRuntime(agent.py)
              ├── LLMClient(llm.py)       ← 文本解析 JSON
              ├── tools.py                 ← 3 个工具
              ├── prompting.py             ← 手写 JSON 协议
              ├── ConfigStore(config.py)
              ├── SessionStore(session.py)
              └── SkillManager(skills/manager.py)

Phase 1 后：
  main.py → AgentRuntime(agent.py)
              ├── LLMClient(llm.py)        ← 原生 tool calling + streaming
              ├── ToolRegistry(tool_registry.py)
              │     ├── tools/files.py     ← read/write/edit
              │     ├── tools/search.py    ← grep/glob
              │     └── tools/shell.py     ← run_shell
              ├── prompting.py             ← 简化（无 JSON 协议）
              ├── ConfigStore(config.py)
              ├── SessionStore(session.py)
              └── SkillManager(skills/manager.py)

Phase 2 后增加：
              ├── SubAgentExecutor(sub_agent.py)
              ├── tools/agent_tool.py      ← dispatch_agent
              └── TaskTracker(task_tracker.py)

Phase 3 后增加：
              ├── PlanMode(planning.py)
              ├── MemoryManager(memory.py)   ← XCODE.md 双文件
              │     ├── ~/.xcode/XCODE.md    ← 用户记忆
              │     ├── {cwd}/XCODE.md       ← 项目记忆
              │     └── memory/auto/         ← 自动记忆
              ├── /plan 命令 (enter/show/approve/reject)
              └── /memory 命令 (状态查看 + auto on/off)

Phase 4 后增加：
              ├── PermissionManager(permissions.py)
              ├── ContextManager(context.py)
              └── ui/renderer.py

Phase 5 后增加：
              ├── tools/web.py             ← webfetch/websearch
              ├── tools/git.py             ← git 操作
              ├── Scheduler(scheduler.py)
              └── HookManager(hooks.py)
```

## 附录 B：实现原则

1. **优先改核心协议，再加工具**。原生 tool calling（Task 1.3）是所有后续工作的基础，必须先做。
2. **每个 Task 完成后立即验证**——启动 `xcode chat` 实际对话测试，不要攒到最后。
3. **不要引入 asyncio**——当前同步代码足够好，ThreadPoolExecutor 覆盖并行场景。异步会传染整个调用链。
4. **新工具都要注册 `is_read_only`**——即使 Phase 4 权限系统还没做，先标记好，方便后续。
5. **文件编辑优先用 edit_file 而非 write_file**——edit_file 的精确替换更安全。system prompt 中要强调这一点。
6. **保持向后兼容**——原有的 `/skill` `/env` `/dashboard` `/exit` 命令、`xcode skill install` 子命令等要继续能用。
7. **不引入不必要的抽象**——三个类似的工具函数不需要立刻抽基类；先让代码工作，再考虑重构。
8. **所有异常必须捕获并转为字符串**——工具执行不能因为一个未捕获异常而让整个 Agent 循环崩溃。ToolRegistry.execute() 是最外层保护。
9. **中文注释和标识符**：项目所有用户界面字符串使用中文，代码标识符使用英文。

## 附录 C：关键数据结构速查

```python
# LLM 交互
@dataclass
class ToolCall:
    id: str
    name: str
    args: dict

@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]

# 工具系统
@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict       # JSON Schema properties
    required: list[str]
    execute: Callable[..., str]
    is_read_only: bool

# 配置
@dataclass
class Config:
    enabled_skills: list[str]
    api_key: str
    base_url: str
    model: str
    provider: str
    auto_memory: bool = True  # Phase 3 新增
    max_tokens: int = 128000  # Phase 4.3 新增 — 上下文窗口大小
    permissions: dict = {}     # Phase 4 新增
    response_render_mode: str = "buffer_then_render"  # Phase 4.2 新增

# 计划模式
@dataclass
class PlanMode:
    is_active: bool = False
    pending_approval: bool = False
    plan_path: str = ""
    plan_summary: str = ""

# 记忆（XCODE.md 双文件，无 MemoryEntry dataclass）
```
