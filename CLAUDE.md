# CLAUDE.md

- 请始终使用中文回复。
- 如果没有明确说明要你修改代码，不要修改，只做分析。

## 项目文档索引

接手开发时按顺序阅读：

| 顺序 | 文档 | 内容 |
|------|------|------|
| 1 | `PROGRESS.md` | 项目进度表，各 Phase/Task 完成状态 |
| 2 | `ROADMAP.md` | 完整需求文档，每个 Task 的函数签名和数据结构 |
| 3 | `ARCHITECTURE.md` | 组件关系、数据流、设计决策 |
| 4 | `DEVNOTES.md` | 已知问题、踩坑记录、设计取舍 |
| 5 | `PHASE1_ACCEPTANCE.md` | Phase 1 验收报告 |
| 6 | `PHASE2_ACCEPTANCE.md` | Phase 2 验收报告 |
| 7 | `PHASE3_ACCEPTANCE.md` | Phase 3 验收报告 |

## 开发约定

- Python >= 3.10，不引入 asyncio
- 工具异常全部捕获，不能因未捕获异常让 Agent 循环崩溃
- 新工具必须注册 `is_read_only` 字段
- 文件编辑优先用 `edit_file` 而非 `write_file`
- 所有用户界面字符串使用中文，代码标识符使用英文
- 不要引入不必要的抽象——三个类似函数不等价于需要基类
