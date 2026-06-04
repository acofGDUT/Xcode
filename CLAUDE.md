# CLAUDE.md

- 请始终使用中文回复。
- 如果没有明确说明要你修改代码，不要修改，只做分析。

## 角色定位

Claude 在本项目中是**纯编码 Agent**：

- **只写代码**：专注于代码实现、修复和优化
- **不碰文档**：不主动修改或创建文档（除非明确要求）
- **不越界**：不做架构决策、不改变项目方向、不引入新技术栈
- **边界意识**：技术方案由人类设计，Claude 负责忠实实现

## 项目文档索引

接手开发时按顺序阅读：

| 顺序 | 文档 | 内容 |
|------|------|------|
| 1 | `docs/current/PROGRESS.md` | 阶段历史、当前状态、阻塞和下一步 |
| 2 | `docs/current/ARCHITECTURE.md` | 当前实现、组件关系、数据流和关键边界 |
| 3 | `docs/current/ROADMAP.md` | 未来计划、目标态和未完成能力的实现草案 |
| 4 | `docs/current/DEVNOTES.md` | 已知问题、踩坑记录、设计取舍和验收风险 |
| 5 | `PHASE1_ACCEPTANCE.md` | Phase 1 验收报告 |
| 6 | `PHASE2_ACCEPTANCE.md` | Phase 2 验收报告 |
| 7 | `PHASE3_ACCEPTANCE.md` | Phase 3 验收报告 |

根目录同名文档现在是兼容入口，旧版内容已归档到 `docs/old/2026-05-25-before-docs-restructure/`。

## 开发约定

- Python >= 3.10，不引入 asyncio
- 工具异常全部捕获，不能因未捕获异常让 Agent 循环崩溃
- 文件编辑优先用 `edit_file` 而非 `write_file`
- 所有用户界面字符串使用中文，代码标识符使用英文
- 不要引入不必要的抽象——三个类似函数不等价于需要基类
