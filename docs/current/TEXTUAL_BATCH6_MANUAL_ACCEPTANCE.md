# Textual Batch 6 Manual Acceptance Checklist

> 本手册用于在 cmd.exe 和 PowerShell 中手动验收 Textual UI 的关键交互。
> 每项测试后请填写 Pass/Fail 和备注。

## 环境准备

```cmd
cd /d D:\Xcode
xcode chat --textual
```

PowerShell:

```powershell
cd D:\Xcode
xcode chat --textual
```

---

## 1. 启动和退出

### 1.1 正常启动

**步骤**: 运行 `xcode chat --textual`

**预期**: Textual UI 正常启动，显示输入框和状态栏

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

### 1.2 Ctrl+Q 退出

**步骤**: 按 `Ctrl+Q`

**预期**: 应用正常退出，无错误

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 2. 普通对话

### 2.1 发送普通消息

**步骤**: 输入普通问题（如 "What is Python?"）并按 Enter

**预期**: 看到 assistant 流式输出

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 3. Slash 命令

### 3.1 /help

**步骤**: 输入 `/help` 并按 Enter

**预期**: 显示命令列表，`/env` 描述为 "read-only"

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

### 3.2 /env

**步骤**: 输入 `/env` 并按 Enter

**预期**: 显示只读环境设置，包含 provider、base_url、model、api_key (脱敏)、max_tokens、max_summary_chars

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 4. /resume 交互

### 4.1 /resume 列表

**步骤**: 输入 `/resume` 并按 Enter

**预期**: 显示 session 列表，带 `>` 选中标记

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

### 4.2 /resume 导航

**步骤**: 按上/下方向键导航

**预期**: `>` 标记随按键移动

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

### 4.3 /resume 取消

**步骤**: 按 Esc 取消

**预期**: 选择器隐藏，显示 "Cancelled."

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 5. /compact 交互

### 5.1 /compact 执行

**步骤**: 输入 `/compact` 并按 Enter

**预期**: 压缩期间输入被阻塞，显示 "Compacting context... please wait."

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 6. 文件编辑审批

### 6.1 请求文件编辑

**步骤**: 请求 AI 编辑一个文件（如 "Edit the README to add a new section"）

**预期**: 显示 diff 预览和审批选项（Yes/No/Yes, this conversation）

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

### 6.2 上下键选择 + Enter 确认

**步骤**: 用上下键选择选项，按 Enter 确认

**预期**: 选项高亮移动，Enter 确认选择

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

### 6.3 n 拒绝

**步骤**: 按 `n` 拒绝工具调用

**预期**: 工具被拒绝，显示 rejected 结果

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 7. Shell 命令

### 7.1 请求 shell 命令

**步骤**: 请求 AI 执行 shell 命令（如 "Run `dir` to list files"）

**预期**: 显示命令预览，审批后 stdout/stderr 在 Textual UI 内显示

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 8. 窗口大小调整

### 8.1 缩窄终端

**步骤**: 将终端窗口缩窄到 60 列以下，重复文件编辑审批

**预期**: diff 预览被截断，审批选项仍然可见

**结果**: [ ] Pass  [ ] Fail

**备注**: _______________

---

## 总结

| 测试项 | cmd.exe | PowerShell |
|--------|---------|------------|
| 启动 | | |
| Ctrl+Q 退出 | | |
| 普通对话 | | |
| /help | | |
| /env | | |
| /resume 列表 | | |
| /resume 导航 | | |
| /resume 取消 | | |
| /compact | | |
| 文件编辑审批 | | |
| 上下键+Enter | | |
| n 拒绝 | | |
| Shell 命令 | | |
| 窗口缩窄 | | |

**验收人**: _______________

**验收日期**: _______________

**结论**: [ ] Pass  [ ] Fail  [ ] Partial

**备注**: _______________
