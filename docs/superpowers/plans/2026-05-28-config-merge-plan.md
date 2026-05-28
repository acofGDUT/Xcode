# 项目级配置合并 + 统一参数口径 + /env 仪表盘

## 目标

按 `docs/superpowers/specs/2026-05-28-config-merge-design.md` 实现两项改动：

1. Config 系统升级：补全 `max_summary_chars` 字段，实现项目级 `.xcode/config.json` 覆盖，统一压缩参数口径
2. `/env` 重写为全屏 TUI 配置仪表盘

## 前置约束

- Python >= 3.10，同步模型，不引入 asyncio
- prompt_toolkit 在 Git Bash/mingw 有已知限制，关键交互需在 cmd.exe/PowerShell 验收
- 工具异常全部捕获，不能打崩主循环
- 不引入不必要的抽象
- 所有用户界面字符串使用中文，代码标识符使用英文
- `/env` 仪表盘复用 `approval.py:read_key()` 做键盘读取

---

## 功能一：Config 系统升级

### 1.1 Config dataclass 新增字段

**文件**：`src/xcode_cli/core/config.py`

在 `Config` dataclass 末尾添加：

```python
max_summary_chars: int = 6000
```

### 1.2 ConfigStore.load() — 项目级 merge

**文件**：`src/xcode_cli/core/config.py`

在 `load()` 方法中，构造 Config 对象后，检查并 merge 项目级配置：

```python
def load(self) -> Config:
    # ... 现有逻辑构造 Config 对象 cfg ...
    
    # 新增：项目级 config merge
    project_config_path = Path.cwd() / ".xcode" / "config.json"
    if project_config_path.exists():
        try:
            project_data = json.loads(project_config_path.read_text(encoding="utf-8"))
            if isinstance(project_data, dict):
                # 仅覆盖项目文件中显式存在的字段
                for field_name in [
                    "enabled_skills", "api_key", "base_url", "model", "provider",
                    "auto_memory", "max_tokens", "response_render_mode", "syntax_theme",
                    "max_summary_chars",
                ]:
                    if field_name in project_data:
                        setattr(cfg, field_name, project_data[field_name])
        except (json.JSONDecodeError, OSError) as exc:
            # warning 打印，不崩
            import sys
            print(f"[warning] Failed to read project config {project_config_path}: {exc}", file=sys.stderr)
    
    return cfg
```

注意：`Path.cwd()` 获取当前工作目录。`ConfigStore` 不持有 `cwd`，但如果需要可以添加 `cwd` 参数（不强制——用 `os.getcwd()` 作为 fallback，保持向后兼容）。

**设计决策**：项目级 config 文件的字段名和类型与全局完全一致，不需要单独解析逻辑。直接用 `setattr` 赋值而不是逐个手动解析，因为 `Config` 字段类型已知且简单。

### 1.3 ConfigStore.save() — `max_summary_chars` 序列化

**文件**：`src/xcode_cli/core/config.py`

在 `save()` 的 `payload` 中添加：

```python
"max_summary_chars": config.max_summary_chars,
```

### 1.4 ContextManager — 删除 prompt 词数软约束

**文件**：`src/xcode_cli/core/context.py`

修改两处 prompt：

```python
# 首次摘要：把 "under 300 words" 改为下面的格式
summary_prompt = (
    "Summarize the following conversation. Preserve key requirements, "
    "completed actions, pending items, constraints, file changes, errors, "
    "user preferences, current work, and next steps. "
    f"Output only the summary text, under {self.max_summary_chars} characters."
)

# 累积摘要：把 "under 400 words" 改为下面的格式
summary_prompt = (
    "Below is a previous conversation summary and new conversation content since that summary. "
    "Produce an updated cumulative summary that merges old and new information. "
    "The new summary must preserve key decisions, constraints, file changes, errors, "
    "user preferences, pending items, current work, and next steps from BOTH the old summary "
    "and the new content. "
    f"Output only the cumulative summary text, under {self.max_summary_chars} characters."
)
```

这样 `max_summary_chars` 从 Config 传入后，prompt 的字符上限与代码硬截断保持一致。

如果 `max_summary_chars` 为 0 或 None，prompt 中不写字符上限（LLM 自由决定长度），代码层截断也跳过。

### 1.5 agent.py — ContextManager 初始化补传参数

**文件**：`src/xcode_cli/core/agent.py`

```python
# 原来 (line 55)
self.context = ContextManager(max_tokens=cfg.max_tokens)
# 改为
self.context = ContextManager(max_tokens=cfg.max_tokens, max_summary_chars=cfg.max_summary_chars)
```

### 1.6 测试

**文件**：`tests/test_config.py`

新增测试：

- `test_max_summary_chars_default`：Config 默认值 6000
- `test_max_summary_chars_serialization`：save/load 循环不丢失
- `test_project_config_merge`：项目级 config 字段覆盖全局
- `test_project_config_not_exists`：项目文件不存在时全用全局
- `test_project_config_malformed`：损坏的项目文件不崩，打印 warning

---

## 功能二：/env 仪表盘

### 2.1 新建 EnvDashboard

**文件**：`src/xcode_cli/core/ui/env_dashboard.py`（新建）

参考 `Dashboard` 的 TUI 模式（`console.clear()`、Panel、Table、`read_key()`），实现一个全屏配置仪表盘：

```python
class EnvDashboard:
    def __init__(self, config_store, console) -> None:
        self.config_store = config_store
        self.console = console
        self.cfg = config_store.load()  # 编辑中的副本
        self.selected: int = 0           # 当前选中行索引
        self.params: list[ParamDef] = [] # 参数定义列表
    
    def run(self) -> None:
        """入口：清屏 → 主循环 → 返回到调用者"""
```

### 2.2 参数定义

仪表盘管理的 5 个参数：

```python
@dataclass
class ParamDef:
    key: str           # Config 字段名
    label: str         # 显示名称
    description: str   # 说明文字
    type: str          # "int" | "str" | "bool" | "choice"
    choices: list[str] | None  # type="choice" 时的合法值
```

参数列表：

```python
self.params = [
    ParamDef("max_tokens", "Max Tokens", "上下文 token 预算上限，超出 80% 触发自动压缩", "int", None),
    ParamDef("max_summary_chars", "Summary Chars", "压缩摘要最大字符数，0 关闭硬截断", "int", None),
    ParamDef("response_render_mode", "渲染模式", "streaming_plus_final_render: 逐 token 流式 / buffer_then_render: 完成后渲染", "choice", ["streaming_plus_final_render", "buffer_then_render"]),
    ParamDef("syntax_theme", "语法主题", "代码高亮配色方案", "str", None),
    ParamDef("auto_memory", "自动记忆", "关闭后不再自动写入项目记忆文件", "bool", None),
]
```

### 2.3 主循环

```python
def run(self) -> None:
    self.console.clear()
    self._print_banner()
    
    while True:
        self._render_params()
        self._render_help()
        
        key = read_key()
        if key in {"up", "k"}:
            self.selected = (self.selected - 1) % len(self.params)
        elif key in {"down", "j"}:
            self.selected = (self.selected + 1) % len(self.params)
        elif key == "enter":
            self._edit_param(self.params[self.selected])
        elif key == "s":
            self.config_store.save(self.cfg)
            self.console.print("\n[green]配置已保存到[/green] " + str(self.config_store.path))
            self.console.print("[dim]部分参数（max_tokens、response_render_mode）在下次启动时生效。[/dim]")
            return
        elif key in {"q", "escape"}:
            self.console.print("\n[dim]未保存，已退出。[/dim]")
            return
```

### 2.4 渲染方法

`_render_params()` 输出每个参数的当前值和说明：

```python
def _render_params(self) -> None:
    # 重新渲染前先清屏（或用 ANSI 刷新，参考 approval._refresh_options）
    self.console.clear()
    self._print_banner()
    
    # 分区标题
    self.console.print("\n  [bold]Context[/bold]")
    self._print_param_row(0)  # max_tokens
    self._print_param_row(1)  # max_summary_chars
    self.console.print("\n  [bold]输出[/bold]")
    self._print_param_row(2)  # response_render_mode
    self._print_param_row(3)  # syntax_theme
    self.console.print("\n  [bold]记忆[/bold]")
    self._print_param_row(4)  # auto_memory

def _print_param_row(self, idx: int) -> None:
    param = self.params[idx]
    value = getattr(self.cfg, param.key)
    if isinstance(value, bool):
        display_value = "开启" if value else "关闭"
    else:
        display_value = str(value)
    
    prefix = ">" if idx == self.selected else " "
    style = "bold cyan" if idx == self.selected else ""
    # 注意：带样式输出时，说明文字用 dim
    label_col_width = 20
    self.console.print(
        f"  {prefix} {param.label:<{label_col_width}} {display_value:<20} [dim]{param.description}[/dim]",
        style=style,
    )
```

由于参数少（5 个），每次按方向键后整个清屏重新渲染即可，不需要 `_refresh_params` 的 ANSI 局部刷新逻辑。

### 2.5 编辑方法

```python
def _edit_param(self, param: ParamDef) -> None:
    current = getattr(self.cfg, param.key)
    
    self.console.print()
    self.console.print(f"  [bold]编辑: {param.label}[/bold]")
    self.console.print(f"  当前值: {current}")
    self.console.print(f"  [dim]{param.description}[/dim]")
    
    if param.type == "bool":
        # 布尔值：直接 toggle
        new_value = not current
        setattr(self.cfg, param.key, new_value)
        self.console.print(f"  [green]-> {'开启' if new_value else '关闭'}[/green]")
        time.sleep(0.5)  # 短暂显示结果后刷新
        return
    
    if param.type == "choice":
        # 枚举值：在 choices 中循环
        current_idx = param.choices.index(current) if current in param.choices else 0
        new_value = param.choices[(current_idx + 1) % len(param.choices)]
        setattr(self.cfg, param.key, new_value)
        self.console.print(f"  [green]-> {new_value}[/green]")
        time.sleep(0.5)
        return
    
    # int / str：文本输入
    try:
        if not sys.stdin.isatty():
            raw = input("  新值: ").strip()
        else:
            self.console.print("  新值: ", end="")
            raw = input().strip()
    except (EOFError, KeyboardInterrupt):
        self.console.print("  [dim]已取消[/dim]")
        time.sleep(0.3)
        return
    
    if not raw:
        self.console.print("  [dim]保持原值[/dim]")
        time.sleep(0.3)
        return
    
    if param.type == "int":
        try:
            value = int(raw)
        except ValueError:
            self.console.print(f"  [red]无效整数: {raw}[/red]")
            time.sleep(0.5)
            return
        if param.key == "max_tokens" and value <= 0:
            self.console.print(f"  [red]max_tokens 必须 > 0[/red]")
            time.sleep(0.5)
            return
        if param.key == "max_summary_chars" and value < 0:
            self.console.print(f"  [red]max_summary_chars 必须 >= 0[/red]")
            time.sleep(0.5)
            return
        setattr(self.cfg, param.key, value)
    
    if param.type == "str":
        setattr(self.cfg, param.key, raw.strip())
    
    self.console.print(f"  [green]-> {getattr(self.cfg, param.key)}[/green]")
    time.sleep(0.5)
```

### 2.6 编辑模式简化说明

按 spec 设计，编辑不需要展开输入区域在当前选中行下方。由于参数只有 5 个，在控制台底部显示编辑提示行即可：

```
  操作: ↑↓ 导航  Enter 编辑  s 保存  q 不保存退出
  编辑: Summary Chars  当前值: 6000  说明: 压缩摘要最大字符数，0 关闭硬截断  新值> █
```

Enter 进入编辑后，底部出现 `新值> ` 提示，用户输入后回车确认，立即更新内存中的 Config 值并刷新面板。`read_key()` 在编辑模式下不生效——用 `input()` 获取文本输入。

**简化实现**：不对每个参数类型搞复杂的编辑 UI。统一方案——Enter 后底部行变成输入行，用户 input 回车，校验后更新。

### 2.7 agent.py — 替换 _handle_env_command

**文件**：`src/xcode_cli/core/agent.py`

删除整个 `_handle_env_command` 方法（lines 258-353），替换为：

```python
def _handle_env_command(self, parts: list[str]) -> None:
    from xcode_cli.core.ui.env_dashboard import EnvDashboard
    dashboard = EnvDashboard(self.config_store, self.console)
    dashboard.run()
    # 仪表盘退出后，同步关键字段到运行中的 ContextManager
    cfg = self.config_store.load()
    self.context.max_tokens = cfg.max_tokens
    self.context.max_summary_chars = cfg.max_summary_chars
```

### 2.8 非 TTY 处理

在 `EnvDashboard.__init__` 或 `run()` 开头检测 TTY：

```python
if not sys.stdin.isatty():
    self.console.print("当前终端不支持交互式仪表盘。")
    self.console.print(f"请手动编辑配置文件: {self.config_store.path}")
    return
```

### 2.9 测试

**文件**：`tests/test_env_dashboard.py`（新建）

- `test_dashboard_init`：EnvDashboard 初始化后 cfg 包含正确默认值
- `test_dashboard_toggle_bool`：auto_memory 布尔值切换
- `test_dashboard_choice_cycle`：response_render_mode 在合法值间循环
- `test_dashboard_int_input`：max_tokens 整数输入，校验 <=0 拒绝
- `test_dashboard_save`：调用 save 后重读 Config 一致
- `test_dashboard_quit_no_save`：退出不保存时原 config 未变

---

## 实施顺序

1. Config 系统升级（`config.py`）：补字段 + 项目级 merge + max_summary_chars 序列化
2. ContextManager 收口（`context.py`）：prompt 词数 → 字符上限
3. agent.py 收口（`agent.py`）：ContextManager 补传 max_summary_chars
4. EnvDashboard 新建（`core/ui/env_dashboard.py`）
5. agent.py 替换 `_handle_env_command`
6. 补测试
7. `pytest` 全量 + `py_compile` 验证
8. 原生 PowerShell/cmd.exe 手工验收仪表盘

---

## 验收标准

- `pytest` 全量通过
- `xcode chat` → `/env` → 展示 5 项参数面板，方向键可用，Enter 编辑，s 保存 q 退出
- 编辑后保存，`~/.xcode/config.json` 中 `max_summary_chars` 等字段已更新
- 项目目录下创建 `.xcode/config.json`（部分字段），启动 xcode，对应 Config 被覆盖
- `/compact` 触发压缩时 prompt 使用字符上限而非词数
- `max_summary_chars=0` 时关闭摘要硬截断
- 非 TTY 环境打印引导提示，不崩
- `py_compile` 所有改动文件通过
