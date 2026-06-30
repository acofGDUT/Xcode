# Task 03: Bounded Read And Point-In-Time Reminders

状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工验收未执行、未记录。

**风险层级：** P1

## 目标

升级选中 topic 的 bounded read 和 system reminder 渲染：每个 memory 都带 age warning 和 point-in-time verification 提醒，截断时给出 auto memory scope 内的完整读取路径提示。

## 建议文件

- 修改：`src/xcode_cli/core/memory_recall.py`
- 创建/修改：`tests/test_memory_recall_v2.py`

## 约束

- 每轮最多 5 个 topic。
- 每个 topic 最多 4096 bytes 或 200 行。
- session 累计 surfaced 上限默认 60 KiB。
- reminder 不泄漏 selector prompt、manifest 全量列表、recent tool args 或 secret。
- memory 是 point-in-time observation；涉及代码行为、路径、行号、依赖版本、日程或当前状态时必须提醒按当前代码/文档验证。

## 步骤

- [x] **Step 1: 添加 bounded read 测试**

覆盖：

- 超过 4096 bytes 的 topic 被截断。
- 超过 200 行的 topic 被截断。
- 截断正文末尾追加提示：可用 `read_file` 查看 auto memory scope 内完整文件。
- 读取失败只进入 warnings，不影响其他 memory 注入。

- [x] **Step 2: 添加 reminder 格式测试**

覆盖：

- `render_system_reminder()` 使用 `<system-reminder>` 或等价明确边界。
- 每个 memory 包含 `Memory: <path>:`。
- 不足一天显示 `saved recently`，超过一天显示天数。
- 包含 point-in-time / verify current code/docs 提醒。
- 多个 memory 可以合并为一条 system message，但必须 bounded 且可测试。

- [x] **Step 3: 添加 surfaced bytes 测试**

覆盖：

- 注入前再次检查 `surfaced_paths`、`touched_paths` 和 `surfaced_bytes`。
- 达到 session cap 时停止读取后续 memory。
- `surfaced_bytes` 使用 UTF-8 byte length，而不是 Python 字符数。

- [x] **Step 4: 让测试先失败**

运行：

```text
pytest tests/test_memory_recall_v2.py -q
```

预期：旧 `Relevant auto memories:` 简单格式和无截断提示相关测试失败。

- [x] **Step 5: 实现 `SurfacedMemory` 字段补充**

按需给 `SurfacedMemory` 增加：

- `filename`
- `mtime_ms`
- `truncated`
- `byte_count`
- `line_count`

保持旧测试可小幅迁移，避免把数据模型做成通用文档 AST。

- [x] **Step 6: 实现 reminder 渲染**

渲染要求：

- 每个 memory 块有 age warning。
- 明确 memory 是历史观察，不是实时状态。
- 正文保留原 v2 frontmatter 和 body。
- 截断提示只给 auto memory scope 内 path。

- [x] **Step 7: 运行聚焦测试**

运行：

```text
pytest tests/test_memory_recall_v2.py tests/test_memory_recall.py -q
```

预期：

- v2 reminder 渲染通过。
- 原有 selection、dedupe、fail-closed 行为不回归。

- [x] **Step 8: 停止 review**

Review 检查：

- reminder 是否可能过长或重复注入。
- 截断提示是否可能暴露 memory scope 外路径。
- point-in-time 文案是否足够明确，避免模型把旧记忆当实时事实。
