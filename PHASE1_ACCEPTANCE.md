# Phase 1 验收报告

**日期**：2026-05-23
**状态**：全部通过

---

## 验收概览

| # | 验收项 | 状态 | 对应 Task |
|---|--------|------|-----------|
| 1 | ToolRegistry 工具注册中心 | PASS | 1.1 |
| 2 | 6 个工具实现 | PASS | 1.2 |
| 3 | LLM Client 原生 tool calling + 流式输出 | PASS | 1.3 |
| 4 | System Prompt 更新 | PASS | 1.4 |
| 5 | Agent 多轮工具调用循环 | PASS | 1.5 |
| 6 | CLI 入口兼容 | PASS | 1.6 |
| 7 | ripgrep Bootstrap | PASS | - |

---

## 逐项验证

### 1. ToolRegistry（Task 1.1）

**文件**：`src/xcode_cli/core/tool_registry.py`

- `ToolDef` dataclass：`name` / `description` / `parameters` / `required` / `execute` / `is_read_only` — 全部字段正确
- `get_openai_schemas()` 输出格式符合 OpenAI API 规范：`{"type": "function", "function": {"name": ..., "parameters": {"type": "object", "properties": ..., "required": [...]}}}`
- `execute()` 捕获所有异常转为字符串，未知工具返回友好错误
- `list_names()` 返回所有注册工具名

**验证输出**：
```
6 tools registered: read_file, write_file, edit_file, grep, glob, run_shell
All schemas: type=function, params.type=object
```

### 2. 六个工具（Task 1.2）

#### 2.1 read_file

- 分页读取（offset + limit），行号从 0 开始
- 文件不存在 → `Error: file not found`
- 二进制/图片文件 → `Error: cannot read binary file`
- 截断时末尾标注 `## Total lines: {total}`

**测试通过**：
```
read_file (offset=1, limit=2): 行号正确 + 截断提示
read_file (nonexist): Error: file not found
```

#### 2.2 write_file

- 自动创建父目录
- 写入后返回路径确认

#### 2.3 edit_file

这是 Phase 1 最核心的新工具，所有边界条件通过：

| 场景 | 预期 | 结果 |
|------|------|------|
| 唯一匹配 | 替换 1 次 | PASS |
| 多处匹配（replace_all=false） | 报错并告知出现次数 | PASS |
| replace_all=true | 替换所有匹配 | PASS |
| old_string 找不到 | 报错并附文件内容 | PASS |
| new_string == old_string | 报错提示必须不同 | PASS |

#### 2.4 grep

- `content` 模式：显示匹配行（带文件路径 + 行号）
- `files_with_matches` 模式：仅文件路径
- `count` 模式：每个文件的匹配计数
- 无匹配：`No matches found for pattern: ...`
- 路径优先级：`~/.xcode/bin/rg.exe` > 系统 PATH

#### 2.5 glob

- 返回绝对路径，按 mtime 降序
- 最多 500 条，超出截断提示
- 无匹配友好提示

#### 2.6 run_shell

- 基础命令执行正常
- 错误命令返回 exit_code
- 超时保护（`subprocess.run(timeout=...)`）

### 3. LLM Client（Task 1.3）

**文件**：`src/xcode_cli/core/llm.py`

**数据结构**：
- `ToolCall(id, name, args)` — dataclass
- `LLMResponse(content, tool_calls)` — dataclass

**`complete()` 方法签名**：
```python
def complete(self, system_prompt, messages, tool_schemas, on_text_token=None) -> LLMResponse
```

**关键实现**：
- `tools=tool_schemas` + `tool_choice="auto"` + `stream=True` — 原生 function calling
- 流式遍历：`delta.content` → `on_text_token` 回调；`delta.tool_calls` → 按 index 累积
- 缺失 API key 返回 `LLMResponse("Missing API key...")`，不抛异常
- **已删除** `_maybe_parse_tool_call()` — 不再手动解析 JSON

### 4. System Prompt（Task 1.4）

**文件**：`src/xcode_cli/core/prompting.py`

- `BASE_SYSTEM_PROMPT` 长度 764 字符
- **无** `"action":"tool"` 旧 JSON 格式
- **无** `tool_args` 残留
- 包含 edit_file / grep / glob 使用指导

### 5. Agent 集成（Task 1.5）

**文件**：`src/xcode_cli/core/agent.py`

**构造函数**初始化 ToolRegistry 并注册全部工具：
```python
self.tools = ToolRegistry()
for t in ALL_TOOLS:
    self.tools.register(t)
```

**`_run_llm_loop()` 方法**：
- 流式打印 LLM 文本回复（逐 token）
- 多轮工具调用循环（max 10 轮）
- **关键 bug 修复确认**：多个 tool_calls 合并为**一条** assistant 消息（不是每个 tool_call 一条），符合 OpenAI API 要求
- 工具调用信息以 dim 样式显示截断结果

### 6. CLI 入口（Task 1.6）

**文件**：`src/xcode_cli/main.py`

- `xcode chat` — 启动交互式会话
- `xcode dashboard` — API 配置 TUI
- `xcode skill install/list/enable/disable` — 技能管理
- `xcode tool run read/write/edit/shell/grep/glob` — 工具 CLI 子命令
- `xcode tool grep --pattern ... --path ...` — 专用子命令
- `xcode tool glob --pattern ... --literal-pattern ... --stdin-pattern` — 专用子命令（含 PowerShell 变通方案）

### 7. ripgrep Bootstrap

**文件**：`src/xcode_cli/core/bootstrap.py`

- 首次启动自动从 GitHub 下载 rg 15.1.0 到 `~/.xcode/bin/rg.exe`
- 二次启动幂等（"already installed"）
- `search.py` 的 `_resolve_rg_binary()` 优先使用 bundled 路径，fallback 系统 PATH
- 仅实现 Windows，Linux/macOS 返回 "not implemented yet"

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/xcode_cli/core/tool_registry.py` | 新建 | ToolDef + ToolRegistry |
| `src/xcode_cli/core/tools/__init__.py` | 新建 | 汇总 ALL_TOOLS |
| `src/xcode_cli/core/tools/files.py` | 新建 | read/write/edit_file |
| `src/xcode_cli/core/tools/search.py` | 新建 | grep/glob |
| `src/xcode_cli/core/tools/shell.py` | 新建 | run_shell |
| `src/xcode_cli/core/llm.py` | 重写 | 原生 tool calling + streaming |
| `src/xcode_cli/core/prompting.py` | 修改 | 删除旧 JSON 协议描述 |
| `src/xcode_cli/core/agent.py` | 修改 | 集成 ToolRegistry + 流式循环 |
| `src/xcode_cli/core/bootstrap.py` | 新建 | ripgrep 自动下载 |
| `src/xcode_cli/paths.py` | 修改 | 新增 XCODE_DIR + bin 目录 |
| `src/xcode_cli/main.py` | 修改 | tool run 支持 edit/grep/glob |

---

## 待改进项（非阻塞）

| 项目 | 说明 | 优先级 |
|------|------|--------|
| Linux/macOS bootstrap | 目前仅 Windows 实现，另外两个平台 fallback 系统 PATH | 低（Phase 5） |
| grep 懒加载下载 | 当前仅在欢迎界面触发下载，grep 首次调用不触发 | 低 |
| PowerShell glob 展开 | CLI 子命令的边缘问题，已提供 `--literal-pattern` 变通 | 低 |

---

## 结论

Phase 1 "协议与工具升级" **全部 8 项验收通过**。工具调用从文本解析 JSON 升级为原生 function calling，6 个工具均可用，流式输出正常，多轮工具调用循环正确，向后兼容完整。可以进入 Phase 2（Agent 架构升级）开发。
