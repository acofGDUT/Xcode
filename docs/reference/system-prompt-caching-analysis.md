# System Prompt 缓存策略分析

> 分析日期：2026-05-26
> 用途：为 Xcode 性能优化提供设计参考

---

## 一、问题

`AgentRuntime.run_chat()` 每轮循环都调用 `build_system_prompt()`，每次重读 config.json、MEMORY.md、所有 memory 文件、skill 文件、然后字符串拼接。即使用户连续输入 10 条消息、什么都没变，以上步骤重复 10 次。

---

## 二、为什么 Xcode 比 Claude Code 慢

Claude Code 的策略是**启动时拼一次、缓存复用**：

```
Session 启动
    │
    ▼
读取所有注入源（config、memory、skills、CLAUDE.md 等）
    │
    ▼
拼接成完整 system prompt → 缓存到 self._cached_system_prompt
    │
    ▼
每轮对话：直接用缓存，零 I/O、零拼接
    │
    ▼
仅在特定事件失效重建：
  /compact、--resume、/env 修改、写新 memory、/skill enable/disable
```

Xcode 当前的做法是**每轮重建**：

```
每轮 run_chat() 循环
    │
    ▼
build_system_prompt()
    │
    ├── open() 读 config.json
    ├── open() 读 MEMORY.md
    ├── open() 读所有 memory 文件
    ├── open() 读所有 skill 文件
    └── 字符串拼接
    │
    ▼
返回 system prompt → 用完丢弃
    │
    ▼
下一轮重复以上全部步骤
```

**开销对比（单轮）**：

| | Claude Code | Xcode |
|---|---|---|
| 文件 I/O | 0 次 | N 次（N = config + memory + skill 文件数） |
| 字符串拼接 | 0 次 | 1 次完整拼接 |
| 内存分配 | 引用缓存对象 | 每次新建大字符串 |

Xcode 用的是远程 API（deepseek-v4-pro），网络延迟本身 ~1-3s。每轮再加几十次文件 I/O + 字符串拼接，延迟累加明显。Claude Code 的缓存策略让每轮只支付网络延迟，本地开销几乎为零。

---

## 三、缓存失效策略

在 `AgentRuntime` 里加 `self._cached_system_prompt: str | None = None` 和 `self._prompt_dirty: bool = True`。

`_get_system_prompt()` 方法检查 dirty 标记，仅在 dirty 时重建并缓存。

| 事件 | 需重建 |
|------|--------|
| Session 启动 | 是（首次构建） |
| /compact | 是（summary checkpoint 变了） |
| --resume | 是（恢复的 session 上下文不同） |
| /env 修改配置 | 是（config 变了） |
| 写新 memory | 是（memory 内容变了） |
| /skill enable/disable | 是（skill 列表变了） |
| 普通用户输入 | 否（直接用缓存） |
| 工具调用结果返回 | 否（直接用缓存） |

---

## 四、实现要点

```python
class AgentRuntime:
    def __init__(self, ...):
        self._cached_system_prompt: str | None = None
        self._prompt_dirty: bool = True

    def _get_system_prompt(self) -> str:
        if self._prompt_dirty or self._cached_system_prompt is None:
            self._cached_system_prompt = build_system_prompt(...)
            self._prompt_dirty = False
        return self._cached_system_prompt

    def invalidate_system_prompt(self) -> None:
        self._prompt_dirty = True
```

所有触发重建的地方调用 `self.invalidate_system_prompt()` 即可。
