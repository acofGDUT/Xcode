# Task 7: 文档和最终验证

> Parent plan: [2026-06-05-model-invocable-skills-plan.md](../2026-06-05-model-invocable-skills-plan.md)
> Spec: [2026-06-05-model-invocable-skills-design.md](../../specs/2026-06-05-model-invocable-skills-design.md)

**Files:**
- Modify: `docs/current/ARCHITECTURE.md`
- Modify: `docs/current/ROADMAP.md`
- Modify: `docs/current/PROGRESS.md`
- Modify: `docs/current/DEVNOTES.md`

- [ ] **Step 1: 更新 ARCHITECTURE**

在 skills 章节记录 Phase 2 数据流：

```text
SkillLoader
  -> SkillCatalog
  -> SkillListingFormatter -> system prompt Available Skills
  -> SkillInvocationService
       -> SlashCommandDispatcher for user invocation
       -> SkillTool for model invocation
```

明确：

- SkillTool 不依赖 slash command registry。
- `user-invocable` 和 `disable-model-invocation` 是独立开关。
- listing 只包含 name/description/when_to_use。
- allowed-tools 只收窄工具，不提权。

- [ ] **Step 2: 更新 ROADMAP**

将 Skills Phase 2 状态更新为完成，并记录不包含：

- fork
- hooks
- remote skills
- skill search

- [ ] **Step 3: 更新 PROGRESS**

新增 Phase 2 验收记录，包含：

```text
- compact skill listing 注入 system prompt
- SkillTool 支持 skill,args
- SkillTool 成功加载后，本 user turn 后续 tool schemas 不再包含 skill，避免递归调用
- user-invocable=false 但 model invocation enabled 的 skill 可调用
- disable-model-invocation=true 和 context=fork 被拒绝
- allowed-tools 在 SkillTool 后续 turn 生效且不绕过 PermissionManager
- session/resume/compact 保留 loaded skill marker 和 invocation audit metadata
- skill_invocation audit event 不包含完整 model_content
- pytest focused + full pytest 结果
```

- [ ] **Step 4: 更新 DEVNOTES**

新增开发约束：

- 新 skill 入口必须走 `SkillInvocationService`。
- SkillTool 成功加载 skill 后必须通过 blocked-tools 机制禁用后续 SkillTool 递归调用。
- SkillTool 的 audit metadata 不能包含完整 skill prompt；完整 prompt 只放在模型可见 tool message 中。
- 不要让模型工具调用 `SlashCommandDispatcher`。
- 新增 SkillTool 相关测试时，优先测真实 loader/catalog/service/tool 链路。
- listing 测试必须证明完整 body 不进入 system prompt。

- [ ] **Step 5: 编译检查**

Run:

```powershell
python -m py_compile src/xcode_cli/skills/catalog.py src/xcode_cli/skills/listing.py src/xcode_cli/skills/invocation.py src/xcode_cli/core/tools/skill_tool.py src/xcode_cli/core/tool_registry.py src/xcode_cli/core/tooling/execution.py src/xcode_cli/core/commands/registry.py src/xcode_cli/core/commands/dispatcher.py src/xcode_cli/core/prompting.py src/xcode_cli/core/agent.py
```

Expected: exit code 0。

- [ ] **Step 6: 聚焦测试**

Run:

```powershell
pytest tests/test_skill_catalog.py tests/test_skill_listing.py tests/test_skill_invocation_service.py tests/test_skill_tool.py tests/test_model_invocable_skill_flow.py tests/test_prompting_skills.py tests/test_skill_prompt_command_flow.py tests/test_skill_allowed_tools.py tests/test_resume.py tests/test_compaction.py -q
```

Expected: PASS。

- [ ] **Step 7: 全量测试**

Run:

```powershell
pytest -q
```

Expected: PASS。

- [ ] **Step 8: diff 检查**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors。Windows LF/CRLF warning 不算失败。

- [ ] **Step 9: 提交**

```powershell
git add docs/current/ARCHITECTURE.md docs/current/ROADMAP.md docs/current/PROGRESS.md docs/current/DEVNOTES.md
git commit -m "docs: document model-invocable skills"
```
