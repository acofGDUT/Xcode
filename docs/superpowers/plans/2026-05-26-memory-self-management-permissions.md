# Memory 自管理权限实现计划

> **给 Coding Agent：** 使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 按任务执行。本文只要求你写代码和测试；项目主文档由 Codex review 后统一收口。

**目标：** 让 Xcode 写入和编辑自己解析出来的 memory 文件时不再反复要求用户审核，同时保持普通文件写入仍受现有审批保护。

**架构：** 增加一个严格的 memory 路径级免审判断。`MemoryManager` 负责判断目标路径是否属于 resolved memory 写入范围；`AgentRuntime` 在 `write_file` / `edit_file` 审批前调用该判断，只对 memory-scoped 写入跳过用户审批。不要修改 `PermissionManager` 对 `write_file` / `edit_file` 的默认权限。

**技术栈：** Python 3.10+、pytest、现有同步 `AgentRuntime`、`PermissionManager`、`MemoryManager`。

---

## 背景

当前行为：

- `PermissionManager._default_level("write_file"|"edit_file")` 返回 `ask`。
- `_run_llm_loop()` 先调用 `self.permissions.check(tc.name)`，当 level 为 `ask` 时再走 `_prompt_tool_approval()`。
- memory 路径已经由 `MemoryManager` 解析：
  - project memory：`<project>/XCODE.md`
  - user memory：`~/.xcode/XCODE.md`
  - auto memory dir：`~/.xcode/projects/<project>/memory/`
  - auto memory index：`~/.xcode/projects/<project>/memory/MEMORY.md`
- prompt 会要求模型通过 `write_file` 写 auto memory，所以当前 memory 写入也会触发普通写文件审批。

目标行为：

- `write_file` / `edit_file` 命中 resolved memory 路径时，不要求用户手动审批。
- 普通项目文件仍然要求审批。
- 形如 `C:\Users\%USERNAME%\.xcode\projects\D:\Xcode\memory\...` 的错误 Windows 路径不能被误判为 memory。
- UI 仍需可审计，例如打印 `approval: memory auto-allow`。

不做的事：

- 不新增 `memory_save` / `memory_delete` 专用工具。
- 不允许所有 `~/.xcode` 写入。
- 不把 `write_file` / `edit_file` 默认权限改成 `allow`。
- 不重构整个 `agent.py`，只做最小审批路径改动。
- 不更新主项目文档；实现完成后只在交付总结里说明需要 Codex 更新哪些文档。

---

## 涉及文件

- 修改：`src/xcode_cli/core/memory.py`
  - 增加 resolved memory 写入目标判断 helper。

- 修改：`src/xcode_cli/core/agent.py`
  - 在 `write_file` / `edit_file` 审批前判断是否为 memory 写入目标。
  - 只对 memory 目标绕过用户审批。

- 测试：`tests/test_memory.py`
  - 覆盖 memory 路径判断。

- 新增测试：`tests/test_agent_memory_permissions.py`
  - 覆盖 AgentRuntime 审批行为。

---

## Task 1：增加 memory 路径判断

**文件：**
- 修改：`src/xcode_cli/core/memory.py`
- 测试：`tests/test_memory.py`

- [ ] **Step 1：先写失败测试**

在 `tests/test_memory.py` 末尾追加：

```python
class TestMemoryWriteTargets:
    def test_project_xcode_is_memory_write_target(self, tmp_path: Path, monkeypatch) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        assert mm.is_memory_write_target(str(mm.project_memory_path())) is True

    def test_user_xcode_is_memory_write_target(self, tmp_path: Path, monkeypatch) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        assert mm.is_memory_write_target(str(mm.user_memory_path())) is True

    def test_auto_memory_file_is_memory_write_target(self, tmp_path: Path, monkeypatch) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        target = mm.memory_dir_path() / "project_tech_stack.md"
        assert mm.is_memory_write_target(str(target)) is True

    def test_memory_index_is_memory_write_target(self, tmp_path: Path, monkeypatch) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        assert mm.is_memory_write_target(str(mm.memory_index_path())) is True

    def test_non_memory_project_file_is_not_memory_write_target(self, tmp_path: Path, monkeypatch) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        target = mm.cwd / "src" / "app.py"
        assert mm.is_memory_write_target(str(target)) is False

    def test_sibling_of_memory_dir_is_not_memory_write_target(self, tmp_path: Path, monkeypatch) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        target = mm.memory_dir_path().parent / "memory_notes.md"
        assert mm.is_memory_write_target(str(target)) is False

    def test_invalid_windows_memory_like_path_is_not_memory_write_target(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        mm = _make_memory_manager(tmp_path, monkeypatch, project_name="demo")
        bad_path = r"C:\Users\%USERNAME%\.xcode\projects\D:\Xcode\memory\project_tech_stack.md"
        assert mm.is_memory_write_target(bad_path) is False
```

- [ ] **Step 2：确认测试失败**

运行：

```powershell
pytest tests/test_memory.py::TestMemoryWriteTargets -q
```

预期：失败，原因是 `MemoryManager.is_memory_write_target` 还不存在。

- [ ] **Step 3：实现最小功能**

在 `src/xcode_cli/core/memory.py` 的 `MemoryManager` 中增加：

```python
    def is_memory_write_target(self, path: str | Path) -> bool:
        try:
            target = Path(path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            return False

        exact_targets = {
            self.user_memory.resolve(strict=False),
            self.project_memory.resolve(strict=False),
            self.memory_index.resolve(strict=False),
        }
        if target in exact_targets:
            return True

        memory_root = self.memory_dir.resolve(strict=False)
        try:
            return target.is_relative_to(memory_root) and target.suffix.lower() == ".md"
        except ValueError:
            return False
```

注意：

- 使用 `strict=False`，因为目标 memory 文件可能还不存在。
- auto memory 只允许 `memory_dir` 内的 `.md` 文件。
- 不要用字符串包含 `memory` 这种方式判断路径。

- [ ] **Step 4：跑 focused tests**

运行：

```powershell
pytest tests/test_memory.py::TestMemoryWriteTargets -q
```

预期：全部通过。

---

## Task 2：只对 memory 写入跳过用户审批

**文件：**
- 修改：`src/xcode_cli/core/agent.py`
- 新增：`tests/test_agent_memory_permissions.py`

- [ ] **Step 1：写 AgentRuntime 审批行为测试**

新建 `tests/test_agent_memory_permissions.py`，覆盖：

- `write_file` 到 auto memory 文件时不调用 `_prompt_tool_approval()`。
- `edit_file` 到 project `XCODE.md` 时不调用 `_prompt_tool_approval()`。
- `write_file` 到普通项目文件时仍调用 `_prompt_tool_approval()`。
- 错误 Windows memory-like path 仍调用 `_prompt_tool_approval()`。

测试可以参考当前 `tests/test_agent_resume_command.py` 的 AgentRuntime mock 方式，必须 mock `PromptSession`，避免测试环境卡在真实交互。

- [ ] **Step 2：确认测试失败**

运行：

```powershell
pytest tests/test_agent_memory_permissions.py -q
```

预期：memory 写入测试失败，因为当前仍会调用审批。

- [ ] **Step 3：增加 AgentRuntime helper**

在 `src/xcode_cli/core/agent.py` 中 `_approval_scope_for_tool()` 附近增加：

```python
    def _is_memory_write_tool_call(self, tool_name: str, args: dict[str, Any]) -> bool:
        if tool_name not in {"write_file", "edit_file"}:
            return False
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            return False
        return self.memory.is_memory_write_target(path)
```

- [ ] **Step 4：接入审批流程**

在 `_run_llm_loop()` 中，拿到 `scope = self._approval_scope_for_tool(tc.name)` 后增加：

```python
                is_memory_write = self._is_memory_write_tool_call(tc.name, tc.args)
```

把原来的审批判断：

```python
                if scope and self._session_auto_approve.get(scope):
                    self.console.print("  [dim]approval: auto-yes (this conversation)[/dim]")
                elif level == "ask":
```

改为：

```python
                if is_memory_write and level != "deny":
                    self.console.print("  [dim]approval: memory auto-allow[/dim]")
                elif scope and self._session_auto_approve.get(scope):
                    self.console.print("  [dim]approval: auto-yes (this conversation)[/dim]")
                elif level == "ask":
```

必须保持：

- `level == "deny"` 的分支仍在这段逻辑之前。
- 不要设置 `_session_auto_approve["write"] = True`。
- 普通文件写入仍走原来的审批。

- [ ] **Step 5：跑审批测试**

运行：

```powershell
pytest tests/test_agent_memory_permissions.py -q
```

预期：全部通过。

---

## Task 3：最终验证

- [ ] **Step 1：跑相关测试**

```powershell
pytest tests/test_agent_memory_permissions.py tests/test_memory.py tests/test_agent_memory_bug.py -q
```

预期：全部通过。

- [ ] **Step 2：跑全量测试**

```powershell
pytest -q
```

预期：全部通过。

- [ ] **Step 3：编译关键文件**

```powershell
python -m py_compile src/xcode_cli/core/agent.py src/xcode_cli/core/memory.py src/xcode_cli/core/permissions.py
```

预期：无输出，退出码为 0。

- [ ] **Step 4：检查 diff**

```powershell
git diff --check
```

预期：没有 whitespace error。

- [ ] **Step 5：交付说明**

交付时说明：

- 修改了哪些代码文件。
- 增加了哪些测试。
- 哪些验证命令通过。
- 明确说明普通 `write_file` / `edit_file` 审批没有被放开。
- 不要自行更新 `README / ARCHITECTURE / DEVNOTES / PROGRESS / ROADMAP / 日期计划`，这些由 Codex review 后统一更新。

---

## Codex Review Checklist

Codex review 时重点检查：

- 是否有人把 `PermissionManager._default_level("write_file")` 改成了 `allow`。
- 是否放行了整个 `~/.xcode`。
- 是否用字符串包含 `memory` 来判断路径。
- 显式 `deny` 是否仍然挡住 memory 写入。
- 普通项目文件写入是否仍然需要审批。
- memory 免审是否污染了 `_session_auto_approve["write"]`。
- 是否有 `_run_llm_loop()` 级别测试，而不只是 helper 单测。
