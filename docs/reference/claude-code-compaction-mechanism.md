# Claude Code 压缩与恢复机制（参考分析）

> 分析日期：2026-05-25
> 用途：为 Xcode Phase 5 `--resume` 功能提供设计参考

---

## 一、触发

上下文接近上限时，Claude Code 调一次 LLM 生成摘要。这是一次性的 token 消耗（几千 token 换后续无限轮）。

---

## 二、压缩过程

```
当前 LLM 上下文                当前 JSONL
┌──────────────────┐          ┌──────────────────┐
│ msg 1            │          │ msg 1            │
│ msg 2            │          │ msg 2            │
│ ...              │          │ ...              │
│ msg 500          │          │ msg 500          │
│ msg 501          │          │ msg 501          │
│ msg 502          │          │ msg 502          │
└──────────────────┘          └──────────────────┘

            LLM 压缩（调 API）
                 │
                 ▼
         结构化摘要（9 段）
         Primary Request / Key Concepts /
         Files / Errors / Problems /
         User Messages / Pending /
         Current Work / Next Step
```

### JSONL 中

全量保留所有消息，插入一条特殊 user 消息作为 checkpoint：

```
Line 500: assistant: 原来的最后一条回复
Line 501: ...
Line 639: system (turn_duration)
                        ← 新插入 ↓
Line 640: user: "This session is being continued from a
                previous conversation... Summary: ..."
Line 641: user: <command-name>/compact</command-name>
Line 642: user: Compacted (ctrl+o to see full summary)
                        ← 标记结束 ↑
Line 643: user: 你接下来要做什么？  ← 新对话从这里开始
Line 644: assistant: 好的...
```

### LLM 上下文中

旧消息全部替换为摘要，新消息继续追加：

```
┌──────────────────────────────────────┐
│ system prompt                         │
│ +                                     │
│ user: "This session is being          │
│        continued... Summary: ..."     │  ← 代表全部历史
│ +                                     │
│ user: 你接下来要做什么？              │  ← 新消息
│ assistant: 好的...                    │
│ ...（继续增长）                       │
└──────────────────────────────────────┘
```

### 终端展示

用户只看到一行 dim 文字 `Compacted (ctrl+o to see full summary)`，按 Ctrl+O 展开完整摘要。

---

## 三、与 Xcode 压缩策略的对比

| | Claude Code `/compact` | Xcode `ContextManager.compress()` |
|---|---|---|
| 压缩范围 | 全部历史 | 只压缩中间 |
| 尾部处理 | 也纳入摘要，不保留原始 | 保留尾 8 条原始消息 |
| 首条处理 | 纳入摘要 | 保留首条 user 原始 |
| LLM 看到 | 摘要 + 之后的新对话 | 首条 user + 摘要 + 尾 8 条 |

没有重复的对话。Claude Code 更激进——全部压缩，Xcode 更保守——保留头尾原始消息。

---

## 四、Session 关闭

session 退出时，最后一条压缩标记（JSONL 末尾附近）的状态被记录。

一个 session 可能被压缩多次，每次都是一条新的 user 消息 checkpoint：

```
JSONL:
  1-100:  早期对话
  101:    user: "This session is being continued... Summary-1"
  102:    user: /compact
  103-500: 继续对话
  501:    user: "This session is being continued... Summary-2"
  502:    user: /compact
  503-800: 继续对话（session 结束）
```

> **注意：多次压缩时早期摘要会丢失。** Summary-1 覆盖对话 1-100，Summary-2 只覆盖对话 103-500（两次压缩之间的内容），并不包含 Summary-1 的内容。Resume 只读最后一条压缩标记（Summary-2），Summary-1 中记录的关键决策、上下文等信息永久丢失——除非每次压缩时 LLM 被要求做"累积总结"而非"增量总结"。实测 Claude Code 的行为确认了这一点：多次压缩后 `--resume` 只能看到最后一条摘要。

---

## 五、Resume 恢复

```
新 session 启动（--resume 或自动检测）
         │
         ▼
读上一个 JSONL 文件
         │
         ▼
找最后一条 "This session is being continued..." user 消息
  → 读到 Summary-2
         │
         ▼
作为 <system-reminder> 注入新 session 的 system prompt
         │
         ▼
┌──────────────────────────────────────────┐
│ system prompt                             │
│ +                                         │
│ <system-reminder>                         │
│ This session is being continued...        │
│ Summary: ...（Summary-2 的内容）          │
│ </system-reminder>                        │
│ +                                         │
│ user: 你的第一条新消息                    │
└──────────────────────────────────────────┘
```

**不调 LLM、不耗 token、纯本地读取**。摘要在上次压缩时已经生成并持久化在 JSONL 中，resume 只读最后一条压缩标记，不需要解析整份 transcript。加载快是因为只读 JSONL 尾部。

---

## 六、Session 存储结构

### 完整对话记录

**位置**：`~/.claude/projects/<项目名>/<session-uuid>.jsonl`

每个 session 一个文件，按 UUID 命名。JSONL 格式，每一行是一次事件——用户输入、工具调用、工具结果、thinking、hook 触发、权限检查、assistant 回复等，全量记录。

### 命令历史

**位置**：`~/.claude/history.jsonl`

只存用户输入文本 + 时间戳 + sessionId，供按 ↑ 翻历史用。

```json
{"display": "你好", "timestamp": 1779447643035, "project": "D:\\Xcode", "sessionId": "2a9da52c-..."}
```

### 会话状态

**位置**：`~/.claude/sessions/<pid>.json`

```json
{
  "pid": 220512,
  "sessionId": "9c462299-...",
  "cwd": "D:\\Xcode",
  "status": "busy",
  "updatedAt": 1779717903772
}
```

用途：
- **崩溃恢复**：重启后读到上次在哪个项目、哪个 session，可提示 `--resume`
- **实例互斥**：同项目下已有 `status: busy` 进程时阻止第二个实例
- **调试**：通过 pid 找到进程 kill，或判断假死（updatedAt 长时间不更新）

### 写入时机

Transcript JSONL 是实时增量写入的。每发生一个事件立刻追加一行，不是对话结束后才一次性写。即使崩溃，已发生的对话不丢失。

---

## 七、对 Xcode Phase 5 的启示

Xcode 现在已有的：
- `ContextManager.compress()` — 运行时 LLM 压缩
- `SessionStore.append()` — 实时写入 JSONL

Xcode 还需要做的（Phase 5 `--resume`）：

1. 压缩时将摘要作为特殊消息写入 session JSONL（对应 Claude Code 的 `<command-name>/compact</command-name>` user 消息）
2. 启动时检测上一个 session 的最后压缩标记
3. 将摘要注入 system prompt（对应 Claude Code 的 `<system-reminder>`）
4. 提供 `--resume` / `--continue` CLI 入口
