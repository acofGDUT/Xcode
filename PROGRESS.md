# Xcode 项目进度表

> 最后更新：2026-05-23

---

## 总览

| Phase | 名称 | 状态 | 验收报告 |
|-------|------|:---:|------|
| Phase 1 | 协议与工具升级 | ✅ 完成 | PHASE1_ACCEPTANCE.md |
| Phase 2 | Agent 架构升级 | ✅ 完成 | PHASE2_ACCEPTANCE.md |
| Phase 3 | 计划与记忆 | ✅ 完成 | PHASE3_ACCEPTANCE.md |
| Phase 4 | 安全与体验 | ⚠️ 2/4 通过，2 项待修复 | PHASE4_ACCEPTANCE.md |
| Phase 5 | 生态扩展 | 🔲 未开始 | — |

---

## Phase 1：协议与工具升级

| Task | 内容 | 状态 |
|------|------|:---:|
| 1.1 | 工具注册表 + Schema 定义 | ✅ |
| 1.2 | 重构现有工具 + 新增 edit/grep/glob | ✅ |
| 1.3 | LLM Client 重写（tool calling + streaming） | ✅ |
| 1.4 | 更新 System Prompt | ✅ |
| 1.5 | Agent 适配新协议 + 流式输出 | ✅ |
| 1.6 | CLI 入口更新 + pyproject.toml | ✅ |

---

## Phase 2：Agent 架构升级

| Task | 内容 | 状态 |
|------|------|:---:|
| 2.1 | 定义 Agent 类型和消息协议 | ✅ |
| 2.2 | 子 Agent 执行器 | ✅ |
| 2.3 | Agent 派发工具 | ✅ |
| 2.4 | 并行 Agent 执行 | ✅ |
| 2.5 | 任务追踪系统 | ✅ |

---

## Phase 3：计划与记忆

| Task | 内容 | 状态 |
|------|------|:---:|
| 3.1 | 计划模式（EnterPlanMode / ExitPlanMode） | ✅ |
| 3.2 | 记忆系统（XCODE.md 双文件 + auto_memory） | ✅ |
| 3.3 | Config 扩展 + /memory 命令 | ✅ |

---

## Phase 4：安全与体验

| Task | 内容 | 状态 | 文件 |
|------|------|:---:|------|
| 4.1 | 权限系统 | ✅ 通过 | `permissions.py` |
| 4.2 | UI 升级（Markdown/Diff 渲染） | ❌ 未完成（render 未集成） | `ui/renderer.py` |
| 4.3 | 上下文管理（Token 压缩） | ⚠️ MAX_TOKENS 硬编码 200k | `context.py` |
| 4.4 | 流式思考展示与耗时统计 | ✅ 通过 | `llm.py` + `agent.py` |

---

## Phase 5：生态扩展

| Task | 内容 | 状态 |
|------|------|:---:|
| 5.1 | WebFetch 工具 | 🔲 |
| 5.2 | WebSearch 工具 | 🔲 |
| 5.3 | 定时任务（Cron） | 🔲 |
| 5.4 | Git 集成工具 | 🔲 |
| 5.5 | Hooks 系统 | 🔲 |
| 5.6 | 项目级配置 | ⚠️ 部分完成 (`project_root.py` 已实现，ConfigStore merge 未做) |

---

## 当前工具清单（13 个）

| 工具 | Phase | 文件 |
|------|:---:|------|
| `read_file` | 1 | `tools/files.py` |
| `write_file` | 1 | `tools/files.py` |
| `edit_file` | 1 | `tools/files.py` |
| `grep` | 1 | `tools/search.py` |
| `glob` | 1 | `tools/search.py` |
| `run_shell` | 1 | `tools/shell.py` |
| `dispatch_agent` | 2 | `tools/agent_tool.py` |
| `task_create` | 2 | `task_tracker.py` |
| `task_update` | 2 | `task_tracker.py` |
| `task_list` | 2 | `task_tracker.py` |
| `enter_plan_mode` | 3 | `agent.py` |
| `write_plan` | 3 | `agent.py` |
| `exit_plan_mode` | 3 | `agent.py` |

---

## 斜杠命令清单

| 命令 | Phase | 功能 |
|------|:---:|------|
| `/help` | v0 | 显示可用命令 |
| `/dashboard` | v0 | API 配置 TUI |
| `/skill` | v0 | 技能管理 |
| `/env` | v0 | API 环境配置 |
| `/exit` | v0 | 退出 |
| `/plan` | 3 | 计划模式控制 |
| `/memory` | 3 | 记忆状态 + auto 开关 |

---

## 下一步

1. **验收 Phase 4**：权限/UI/上下文/思考展示已全部集成，需要端到端测试
2. **Phase 5**：按需选择 WebFetch / Git / Hooks 等功能实现
3. **Prompt 完善**：记忆系统的 BASE_SYSTEM_PROMPT 规则需要落地到 `prompting.py`
