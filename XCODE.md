# Xcode 项目记忆

## 项目概述
- **定位**：终端原生AI编码代理，类似Cloud Code，支持任何OpenAI兼容API
- **技术栈**：Python >= 3.10，Typer + Rich + OpenAI API
- **数据目录**：`~/.xcode/`（Windows: `%USERPROFILE%/.xcode/`）

## 开发状态
- **版本**：v0.1.0
- **进度**：Phase 1-3 完成，Phase 4.3 待修复（上下文管理问题）
- **源码**：`src/xcode_cli/`

## 核心组件
- `core/agent.py` - REPL循环、工具执行
- `core/llm.py` - API客户端（流式+工具调用）
- `core/memory.py` - 三重记忆系统
- `core/planning.py` - 计划模式
- `core/permissions.py` - 三级权限

## 开发原则
1. 不用asyncio，同步+ThreadPoolExecutor
2. 工具异常全部捕获
3. 编辑优先用edit_file
4. 中文界面，英文标识符

## 记忆
- Xcode的名字是小米
