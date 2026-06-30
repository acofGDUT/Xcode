# Task 06: Docs And Final Verification

状态：未实现；自动化回归未执行；PowerShell/cmd.exe 原生 PTY 手工验收未执行。

**风险层级：** P1/P2

## 目标

在 recall v2 代码和自动化回归完成后，同步当前事实文档，跑完整验证矩阵，并明确保留或关闭原生 PTY 手工验收缺口。

## 建议文件

- 修改：`docs/current/ARCHITECTURE.md`
- 修改：`docs/current/PROGRESS.md`
- 修改：`docs/current/ROADMAP.md`
- 修改：`docs/current/DEVNOTES.md`
- 修改：`docs/superpowers/plans/2026-06-23-auto-memory-recall-v2-claude-like-plan.md`
- 修改：本 task 及已完成 task 状态

## 约束

- 只有真实运行过的命令才能写成“通过”。
- `ARCHITECTURE.md` 只描述已实现的当前机制，不写未实现后续设想。
- `PROGRESS.md` 记录证据和 review 结论，不维护 backlog。
- `ROADMAP.md` 只保留未完成能力和手工验收缺口。
- 修改中文文档使用 `apply_patch`，并做 UTF-8 磁盘级抽样验证。

## 步骤

- [ ] **Step 1: 更新 task 状态**

把已完成 task 顶部状态从“未实现”改为真实状态，例如：

```text
状态：代码实现和自动化回归已完成；PowerShell/cmd.exe 原生 PTY 手工验收未执行、未记录。
```

不要把未执行的手工验收写成已完成。

- [ ] **Step 2: 更新总 plan 状态**

在总 plan 顶部写明真实完成度：

- 代码实现是否完成。
- 自动化回归是否完成。
- PowerShell/cmd.exe 原生 PTY 手工验收是否完成。
- QQchat/external/headless 隔离是否只由自动化覆盖，还是有真实平台记录。

- [ ] **Step 3: 更新 `ARCHITECTURE.md`**

只在实现完成后追加/调整 memory 相关章节：

- `MEMORY.md` 短索引常驻 prompt。
- v2 manifest selector 默认读取顶层 `type`。
- no-tool selector + recent successful tool names。
- bounded topic read + point-in-time system reminder。
- session surfaced/touched 去重和 local REPL state 边界。

- [ ] **Step 4: 更新 `PROGRESS.md`**

记录真实证据：

- 聚焦测试命令和结果。
- `python -m compileall -q src` 结果。
- 全量 `pytest -q` 结果。
- `git diff --check` 结果。
- 手工验收是否执行。

- [ ] **Step 5: 更新 `ROADMAP.md`**

如果代码和自动化完成但手工验收未做：

- 从“未实现”移到“代码实现和自动化回归完成；手工验收未执行/未记录”。
- 保留 PowerShell/cmd.exe 原生 PTY 和 external/headless 隔离验收缺口。

如果全部完成，则从近期未实现项移除，只在验收缺口表保留真实未完成部分。

- [ ] **Step 6: 更新 `DEVNOTES.md`**

记录仍有效 review 边界：

- 不要把 topic 正文常驻 base system prompt。
- 不要让 stale prefetch 污染后续 turn。
- 不要让 recent tools 泄漏 args/path/output。
- 不要让 QQchat/external/headless 共享本地 REPL recall state。

- [ ] **Step 7: 运行最终验证**

运行：

```text
pytest tests/test_memory_manifest_v2.py -q
pytest tests/test_memory_recall_v2.py -q
pytest tests/test_agent_memory_recall_v2.py -q
pytest tests/test_prompting_memory_v2.py -q
python -m compileall -q src
pytest -q
git diff --check
```

将真实输出摘要写入 `PROGRESS.md`，不要预填结果。

- [ ] **Step 8: 做中文文档 UTF-8 抽样验证**

运行类似命令抽样读取新增中文段落：

```text
python -X utf8 -c "from pathlib import Path; paths=[Path('docs/current/ROADMAP.md'), Path('docs/current/PROGRESS.md'), Path('docs/current/ARCHITECTURE.md')]; [print(p, p.read_text(encoding='utf-8').splitlines()[0]) for p in paths]"
```

必要时再抽样总 plan 和 task 文件标题，确认磁盘内容不是乱码。

- [ ] **Step 9: 停止 final review**

Review 检查：

- 完成结论是否都跟在证据之后。
- ROADMAP、PROGRESS、ARCHITECTURE、DEVNOTES 是否没有状态漂移。
- spec/plan/task checkbox 是否反映真实状态。

