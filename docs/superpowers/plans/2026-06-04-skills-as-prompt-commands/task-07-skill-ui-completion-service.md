# Task 7: UI、completion 和 `/skill` 服务改为新模型

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Modify: `src/xcode_cli/core/commands/slash.py`
- Modify: `src/xcode_cli/core/ui/shell.py`
- Modify: `src/xcode_cli/core/commands/skill.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_skill_command_service.py`
- Test: `tests/test_init_command.py`

- [ ] **Step 1: 更新 `/skill` 行为测试**

`/skill` Phase 1 建议支持：

```text
/skill list
/skill show <name>
/skill validate
```

测试要覆盖：

```python
def test_skill_list_uses_project_skill_loader(tmp_path):
    from io import StringIO
    from rich.console import Console
    from xcode_cli.core.commands.skill import SkillCommandService
    from xcode_cli.skills.loader import SkillLoader

    skill_dir = tmp_path / ".xcode" / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: Review code\n---\nReview $ARGUMENTS",
        encoding="utf-8",
    )
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    loader = SkillLoader(tmp_path)

    svc = SkillCommandService(loader, console)
    svc.list_project_skills()
    assert "review" in output.getvalue()
    assert "Review code" in output.getvalue()
```

- [ ] **Step 2: 修改 SkillCommandService**

`SkillCommandService` 不再依赖 `ConfigStore` 和旧 `SkillManager`，改为依赖 `SkillLoader`：

```python
class SkillCommandService:
    def __init__(self, loader: SkillLoader, console: Console) -> None:
        self._loader = loader
        self._console = console
```

`run(parts)` 支持 list/show/validate；旧 install/enable/disable 输出迁移提示：

```text
Skills are now loaded from .xcode/skills/<name>/SKILL.md.
```

`/skill validate` 应合并 loader notices 和 validation notices，至少展示：

- frontmatter parse error
- description missing fallback
- built-in command conflict
- unknown allowed tool
- `context: fork` 当前 unsupported
- hooks parsed but not executed

- [ ] **Step 3: 修改 completion**

`SlashCompleter` 应接收动态 commands，或由 `AgentRuntime` 构造时传入 registry。user-invocable skills 显示：

```text
/review — Review code [path]
```

- [ ] **Step 4: 修改 ShellUI help**

`show_command_suggestions()` 接收动态 visible commands，展示 built-in 命令和 skill 命令。`user-invocable: false` 不显示。

- [ ] **Step 5: 运行聚焦测试**

Run:

```powershell
pytest tests/test_skill_command_service.py tests/test_init_command.py tests/test_slash_dispatcher.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/xcode_cli/core/commands/slash.py src/xcode_cli/core/ui/shell.py src/xcode_cli/core/commands/skill.py src/xcode_cli/core/agent.py tests/test_skill_command_service.py tests/test_init_command.py tests/test_slash_dispatcher.py
git commit -m "feat: surface project skills in slash command UI"
```
