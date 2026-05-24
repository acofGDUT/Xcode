# Xcode 项目记忆文件

> 项目关键信息记录，供开发参考。

## 项目概述

- **项目名称**：Xcode - 终端原生AI编码代理
- **定位**：类似Cloud Code的本地CLI代理，支持任何OpenAI兼容API
- **核心特性**：13个内置工具、流式输出、子代理、计划模式、持久化记忆、权限系统
- **技术栈**：Python >= 3.10，Typer CLI框架，Rich终端UI，OpenAI API客户端
- **数据目录**：`~/.xcode/`（Windows: `%USERPROFILE%/.xcode/`）

## 开发状态

- **当前版本**：v0.1.0
- **完成阶段**：Phase 1-3已完成，Phase 4部分完成（3/4通过）
- **待修复**：Phase 4.3 上下文管理（MAX_TOKENS硬编码、Config无字段、摘要中文）
- **下一步**：修复Task 4.3，然后按需实现Phase 5功能

## 架构要点

- **源码目录**：`src/xcode_cli/`
- **核心组件**：
  - `core/agent.py` - REPL循环、工具执行、命令处理
  - `core/llm.py` - OpenAI兼容API客户端，支持流式输出和工具调用
  - `core/tool_registry.py` - 工具注册和Schema生成
  - `core/memory.py` - 双文件记忆系统（项目XCODE.md + 用户XCODE.md + 自动记忆）
  - `core/planning.py` - 计划模式状态机
  - `core/permissions.py` - 三级权限系统（session > project > global）
  - `ui/renderer.py` - Rich Markdown/Diff渲染

## 记忆系统

- **项目记忆**：`<project>/XCODE.md` - 项目约定、架构决策
- **用户记忆**：`~/.xcode/XCODE.md` - 用户偏好、全局设置
- **自动记忆**：`~/.xcode/projects/<project>/memory/memory.md` - 分类条目
- **注入方式**：每次会话自动注入system prompt，无需专用工具

## 工具清单（13个）

1. `read_file` - 读取文件内容（支持分页）
2. `write_file` - 写入文件内容
3. `edit_file` - 精确字符串替换（安全编辑）
4. `grep` - 基于ripgrep的内容搜索
5. `glob` - 文件模式匹配
6. `run_shell` - 执行shell命令
7. `dispatch_agent` - 派发子代理（explore/plan/general类型）
8. `task_create` - 创建任务
9. `task_update` - 更新任务状态
10. `task_list` - 列出所有任务
11. `enter_plan_mode` - 进入计划模式
12. `write_plan` - 写入计划文件
13. `exit_plan_mode` - 完成计划，等待审批

## 斜杠命令

- `/help` - 显示可用命令
- `/dashboard` - API配置TUI
- `/skill` - 技能管理
- `/env` - API环境配置
- `/plan` - 计划模式控制（enter/show/approve/reject）
- `/memory` - 记忆状态 + auto开关
- `/exit` - 退出

## 开发原则

1. **不引入asyncio** - 使用同步代码 + ThreadPoolExecutor处理并行
2. **工具异常全部捕获** - ToolRegistry.execute()是最外层保护
3. **编辑优先用edit_file** - 比write_file更安全
4. **保持向后兼容** - 原有命令和功能继续可用
5. **中文界面，英文标识符** - 用户界面字符串使用中文，代码标识符使用英文

## 记忆

- Xcode的名字是小米