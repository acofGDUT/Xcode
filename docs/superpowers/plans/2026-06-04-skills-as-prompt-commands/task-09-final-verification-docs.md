# Task 9: 最终回归和文档收口

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/DEVNOTES.md`

- [ ] **Step 1: 运行编译检查**

Run:

```powershell
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/commands/registry.py src/xcode_cli/core/commands/skill.py src/xcode_cli/core/commands/slash.py src/xcode_cli/core/turn.py src/xcode_cli/skills/model.py src/xcode_cli/skills/loader.py src/xcode_cli/skills/prompt.py src/xcode_cli/skills/validation.py
```

Expected: no output and exit code 0。

- [ ] **Step 2: 运行 focused tests**

Run:

```powershell
pytest tests/test_skill_loader.py tests/test_skill_prompt.py tests/test_skill_validation.py tests/test_skill_command_registry.py tests/test_skill_prompt_command_flow.py tests/test_skill_allowed_tools.py tests/test_init_command.py tests/test_slash_dispatcher.py tests/test_agent_user_turn.py -q
```

Expected: PASS。

- [ ] **Step 3: 运行全量测试**

Run:

```powershell
pytest -q
```

Expected: PASS。

- [ ] **Step 4: diff 检查**

Run:

```powershell
git diff --check
```

Expected: no trailing whitespace errors。

- [ ] **Step 5: 更新文档**

文档必须说明：

- Phase 1 skills 已改为 `.xcode/skills/<name>/SKILL.md`。
- skills 是目录包，supporting files 按需读取，不自动注入上下文。
- 旧 `skill.json` / `enabled_skills` / system prompt 全量注入已移除。
- skill 是 prompt command，不是独立 runtime 分支。
- `allowed-tools` 是当前 turn 临时工具白名单，但不自动提升权限。
- resume 会恢复 skill 的 hidden/model prompt，而不只恢复 `/skill args` 展示文本。
- Phase 2 才做 SkillTool 和模型主动调用。

- [ ] **Step 6: 提交**

```powershell
git add docs/current/ARCHITECTURE.md docs/current/ROADMAP.md docs/current/PROGRESS.md docs/current/DEVNOTES.md
git commit -m "docs: document skills as prompt commands"
```
