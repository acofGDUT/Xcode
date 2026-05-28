# 项目级配置合并 + 统一参数口径

## 目标

1. 实现 `.xcode/config.json` 项目级配置覆盖全局 `~/.xcode/config.json`（字段级 merge）
2. 补全 Config 中代码已引用但不可配的字段（`max_summary_chars`、`response_render_mode`、`auto_memory`）
3. 统一压缩参数口径——去掉 prompt 中的 300/400 词软约束，只保留 `max_summary_chars` 硬截断
4. `/env` 重新设计为全屏 TUI 配置仪表盘（参考 `Dashboard` 风格），覆盖所有非 API 配置项

## 数据结构变更

### Config dataclass

新增字段：

```python
@dataclass
class Config:
    enabled_skills: list[str] = field(default_factory=list)
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    provider: str = "openai-compatible"
    auto_memory: bool = True
    max_tokens: int = 128000
    response_render_mode: str = "buffer_then_render"
    syntax_theme: str = "monokai"
    max_summary_chars: int = 6000       # 新增
```

### ConfigStore.load() — 项目级 merge

加载顺序：

1. 读 `~/.xcode/config.json` → 构造 Config 对象
2. 检查 `<project>/.xcode/config.json` 是否存在
3. 存在 → 字段级浅覆盖（项目文件显式写的字段覆盖全局值，未写的保持原值）
4. 不存在 → 跳过，全用全局

约束：

- 项目文件不要求完整 schema，可以是部分字段
- 项目文件格式错误 → 打印 warning，忽略，用全局值
- `api_key`、`base_url`、`model` 也在 merge 范围内（项目可绑定专用 key/模型）
- `save()` 只写全局文件，项目级 config 由用户手动创建/编辑

### ConfigStore.save()

只写 `~/.xcode/config.json`，行为不变。

### context.py — 压缩参数收口

| 参数 | 当前写死位置 | 变更 |
|------|-------------|------|
| `max_tokens` | `__init__` 默认 128000 | 不变，已从 Config 传入 |
| `max_summary_chars` | `__init__` 默认 6000 | 从 Config 传入，`agent.py:55` 补传此参数 |
| `compression_threshold` (0.8) | `should_compress()` 硬编码 | 保持硬编码，不暴露 |
| `tail_count` (8) | `compress()` 局部变量 | 保持硬编码，不暴露 |
| 最小压缩消息数 (20) | `compress()` 开头 | 保持硬编码，不暴露 |
| 首次摘要 300 词 | prompt 字符串 | 删除词数限制，改为 `max_summary_chars` 字符上限提示 |
| 累积摘要 400 词 | prompt 字符串 | 同上 |

变更思路：删掉 prompt 里 `under 300 words` / `under 400 words` 字样，改为 `under {max_summary_chars} characters`。LLM 看到字符上限后自行控制摘要长度，代码层的 `max_summary_chars` 硬截断做最后兜底。

### agent.py — ContextManager 初始化收口

```python
# 原来
self.context = ContextManager(max_tokens=cfg.max_tokens)
# 改为
self.context = ContextManager(max_tokens=cfg.max_tokens, max_summary_chars=cfg.max_summary_chars)
```

## /env 仪表盘

### 入口

REPL 中输入 `/env` 进入配置仪表盘。现有 `/env show|set|unset|...` 子命令全部移除，统一为 TUI。

### 参数面板

仅展示非 API 配置（API Key / Base URL / Model 仍在 `xcode dashboard` 管理）：

```
╔══════════════════════════════════════════════╗
║        Xcode 配置中心                        ║
║        /env — 上下文 · 压缩 · 输出           ║
╚══════════════════════════════════════════════╝

  Context
  ├─ Max Tokens         128000        上下文 token 预算上限，超出 80% 触发自动压缩
  ├─ Summary Chars      6000          压缩摘要最大字符数，0 或空值关闭硬截断
  │
  输出
  ├─ 渲染模式           buffer_then_render   streaming_plus_final_render: 逐 token / buffer_then_render: 完成后渲染
  ├─ 语法主题           monokai              代码高亮配色方案 (monokai, dracula, one-dark 等)
  │
  记忆
  └─ 自动记忆          开启            关闭后不再自动写入项目记忆文件

  操作: ↑↓ 导航  Enter 编辑  s 保存  q 不保存退出
```

### 导航

- ↑/↓ 方向键在参数列表上下移动
- 当前选中行高亮
- Enter 进入当前参数的编辑模式

### 编辑模式

在选中行下方展开输入区域：

```
  编辑: Summary Chars ──────────────────────────
  │ 当前值: 6000                                 │
  │ 说明: 压缩摘要最大字符数，0 或空值关闭硬截断   │
  │ 新值 ████████                                │
  └──────────────────────────────────────────────
  按 Enter 确认，Esc 取消
```

- 布尔型（auto_memory）：显示 开启/关闭 切换按钮
- 枚举型（render_mode）：在合法值间循环
- 整数/字符串：文本输入，带类型校验
- Esc 取消编辑，回到参数列表
- 编辑后的值暂存在内存 Config，不立即写盘

### 保存与退出

- `s`：写入 `~/.xcode/config.json`，打印 "Config saved to <path>"，退出仪表盘，提示 "config 已更新，建议重启生效"
- `q`：丢弃所有编辑，不写盘，退出

### 键盘读取

复用 `approval.py:read_key()` 函数。TTY 检测：非 TTY 环境打印提示 "请使用 /env edit 编辑配置文件" 并退回 REPL。

### 提示重启

保存后显示：
```
配置已保存到 ~/.xcode/config.json
部分参数（max_tokens、response_render_mode）在下次启动时生效。
```

## 涉及文件

| 文件 | 改动 |
|------|------|
| `src/xcode_cli/core/config.py` | Config 加 `max_summary_chars`；ConfigStore.load() 加项目级 merge 逻辑 |
| `src/xcode_cli/core/context.py` | prompt 中去掉 300/400 词，改为字符上限；删除或注释废弃的软约束 |
| `src/xcode_cli/core/agent.py` | 删掉现有 `_handle_env_command` 所有分支；改为入口调用 `EnvDashboard.run()`；ContextManager 初始化补传 `max_summary_chars` |
| `src/xcode_cli/core/ui/env_dashboard.py` | **新文件**：EnvDashboard TUI 类，含渲染、导航、编辑、保存、键盘读取 |
| `tests/test_config.py` | 新增项目级 merge 测试、`max_summary_chars` 序列化测试 |
| `tests/test_env_dashboard.py` | 新增仪表盘 TUI 逻辑测试（渲染、导航、编辑） |

## 验收标准

- `pytest` 全量通过
- `xcode chat` → `/env` → 展示 5 项参数面板，方向键可用，Enter 编辑，s 保存 q 退出
- 编辑后保存：`~/.xcode/config.json` 中对应字段已更新
- 项目目录下创建 `.xcode/config.json`（部分字段），启动 xcode，对应 Config 被覆盖
- `/env` 编辑 max_summary_chars=0，触发压缩后摘要不做硬截断
- 原生 PowerShell/cmd.exe 手工验收仪表盘交互
- `py_compile` 所有改动文件通过
