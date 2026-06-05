# Task 1: 移除旧 skill 壳子并锁定新边界

> Parent plan: [2026-06-04-skills-as-prompt-commands-plan.md](../2026-06-04-skills-as-prompt-commands-plan.md)
> Spec: [2026-06-04-skills-as-prompt-commands-design.md](../../specs/2026-06-04-skills-as-prompt-commands-design.md)


**Files:**
- Modify: `src/xcode_cli/core/config.py`
- Modify: `src/xcode_cli/core/prompting.py`
- Modify: `src/xcode_cli/skills/manager.py`
- Modify: `tests/test_prompting_memory.py`
- Modify: `tests/test_skill_command_service.py`

- [ ] **Step 1: 写失败测试，证明 system prompt 不再注入 enabled skills**

在 `tests/test_prompting_memory.py` 增加：

```python
def test_build_system_prompt_does_not_inject_enabled_skill_files(tmp_path):
    from xcode_cli.core.config import Config
    from xcode_cli.core.prompting import build_system_prompt

    cfg = Config()
    assert not hasattr(cfg, "enabled_skills")

    prompt = build_system_prompt(cfg, cwd=str(tmp_path))

    assert "Enabled skills:" not in prompt
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
pytest tests/test_prompting_memory.py::test_build_system_prompt_does_not_inject_enabled_skill_files -q
```

Expected: FAIL，因为当前 `Config` 仍有 `enabled_skills` 或 `build_system_prompt()` 仍接收 `SkillManager`。

- [ ] **Step 3: 修改 Config，删除 `enabled_skills`**

在 `src/xcode_cli/core/config.py` 中删除 `enabled_skills` 字段；保留旧配置文件兼容读取时忽略未知字段，不要因为用户已有旧配置而崩溃。

实现要求：

```python
allowed_fields = {f.name for f in fields(Config)}
data = {k: v for k, v in data.items() if k in allowed_fields}
```

- [ ] **Step 4: 修改 prompting，移除 skill 注入**

将 `build_system_prompt()` 签名改为：

```python
def build_system_prompt(config: Config, cwd: str = "") -> str:
```

删除读取 `config.enabled_skills`、`skill_manager.list_installed()`、`SKILL.md` 注入的整段逻辑。

- [ ] **Step 5: 修改调用方**

在 `src/xcode_cli/core/agent.py` 中把：

```python
build_system_prompt(self.config_store.load(), self.skills, self.cwd)
```

改为：

```python
build_system_prompt(self.config_store.load(), self.cwd)
```

- [ ] **Step 6: 运行聚焦测试**

Run:

```powershell
pytest tests/test_prompting_memory.py tests/test_config.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add src/xcode_cli/core/config.py src/xcode_cli/core/prompting.py src/xcode_cli/core/agent.py tests/test_prompting_memory.py tests/test_config.py
git commit -m "refactor: remove legacy enabled skills prompt injection"
```
