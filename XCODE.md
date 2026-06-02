# Xcode 项目记忆

## 项目概述
- **定位**：终端原生AI编码代理，类似Cloud Code，支持任何OpenAI兼容API
- **技术栈**：Python >= 3.10，Typer + Rich + OpenAI API
- **数据目录**：`~/.xcode/`（Windows: `%USERPROFILE%/.xcode/`）

## 开发状态
- **版本**：v0.1.0+
- **进度**：Phase 1-4.5 全部完成，Session Resume、Memory自管理、AgentRuntime重构完成
- **当前重点**：补齐费用估算、原生Windows验收，继续第二轮结构收口
- **源码**：`src/xcode_cli/`

## 核心组件
- `core/agent.py` - 主REPL循环（第二轮重构待继续拆分）
- `core/llm.py` - API客户端（流式+工具调用）
- `core/memory.py` - 三重记忆系统（Project/User/Auto Memory）
- `core/planning.py` - 计划模式（/plan命令）
- `core/permissions.py` - 三级权限（session > project > global）
- `core/context.py` - 上下文管理（token估算、自动压缩、动态max_tokens）
- `core/session_store.py` - 会话持久化（UUID session、JSONL transcript）
- `core/config.py` - 配置系统（项目级覆盖全局）
- `core/commands/slash.py` - 斜杠命令和自动补全
- `core/ui/shell.py` - 欢迎屏、工具栏、基础输出
- `core/ui/env_dashboard.py` - /env TUI仪表盘（5项参数管理）
- `core/ui/streaming.py` - 流式输出状态管理
- `core/conversation/resume.py` - /resume命令（方向键选择）
- `core/conversation/compaction.py` - /compact压缩（Live进度显示）
- `core/tooling/approval.py` - 工具审批菜单（TTY/非TTY fallback）
- `core/tooling/execution.py` - 工具执行、diff预览、memory自动允许

## 已完成功能
1. **协议与工具升级** - OpenAI function calling、ToolDef/ToolRegistry、edit_file/grep/glob工具
2. **Agent架构升级** - 子Agent（EXPLORE/PLAN/GENERAL）、任务追踪（task_create/update/list）
3. **计划与记忆** - /plan模式、三层记忆模型（Project XCODE.md + User XCODE.md + Auto Memory）
4. **安全与体验** - 权限系统、Rich Markdown渲染、语法高亮、工具审批UI
5. **上下文管理** - token估算、自动压缩、动态max_tokens、/env配置
6. **会话恢复** - UUID session、JSONL transcript、/resume方向键选择、/compact Live进度
7. **Memory自管理** - memory-scoped写入免审、普通文件保持审批
8. **AgentRuntime模块化** - 第一轮拆分完成（命令、UI、会话、工具审批、执行）

## 遗留阻塞项
| 项目 | 状态 | 说明 |
|------|------|------|
| CLI --resume/--continue | 延后 | 当前只做交互内/resume |
| /context cost | 未实现 | 只有token估算，无价格估算 |
| 工具调用UI折叠 | 基础完成 | Ctrl+O展开未做 |
| 原生Windows E2E | 未完成 | 需在cmd.exe/PowerShell验证完整交互 |
| agent.py第二轮重构 | 待继续 | command handlers待拆到core/commands/ |

## 开发原则
1. 不用asyncio，同步+ThreadPoolExecutor
2. 工具异常全部捕获
3. 编辑优先用edit_file
4. 中文界面，英文标识符
5. memory写入免审，普通文件保持审批
6. 项目级配置覆盖全局配置
7. 默认采用 SDD：Spec -> Plan -> Implementation -> Review -> Progress Tracking
8. 不默认采用 TDD；测试作为验收和回归保护，只有用户或计划明确要求时才严格执行 TDD

## 记忆
- Xcode的名字是小米
- Codex 默认担任架构/review/文档管理角色，优先写 spec、plan、coding brief，再 review coding agent 实现
