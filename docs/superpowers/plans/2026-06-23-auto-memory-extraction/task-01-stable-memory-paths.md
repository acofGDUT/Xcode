# Task 01: Stable Auto Memory Paths

**Risk layer:** P0

## Goal

Make auto memory use the same stable project key as sessions, while retaining read-only compatibility with the old `<cwd.name>` memory directory.

## Suggested Files

- Create: `src/xcode_cli/core/project_key.py`
- Modify: `src/xcode_cli/core/session.py`
- Modify: `src/xcode_cli/core/memory.py`
- Modify: `src/xcode_cli/core/prompting.py`
- Modify: `src/xcode_cli/core/agent.py`
- Test: `tests/test_memory.py`
- Test: `tests/test_prompting_memory.py`
- Test: `tests/test_agent_memory_command.py`

## Constraints

- New auto memory writes must target `~/.xcode/projects/<project_key>/memory/`.
- Existing `~/.xcode/projects/<cwd.name>/memory/MEMORY.md` must remain readable if stable index is absent.
- Do not move or delete legacy memory files.
- Do not change `Project XCODE.md` or `User XCODE.md` semantics.
- Keep Windows invalid path regression behavior intact.

## Steps

- [x] **Step 1: Add failing stable project-key tests**

Append to `tests/test_memory.py`:

```python
def test_auto_memory_path_uses_stable_project_key(tmp_path: Path, monkeypatch) -> None:
    import xcode_cli.paths
    from xcode_cli.core.memory import MemoryManager
    from xcode_cli.core.session import SessionStore

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    first = tmp_path / "a" / "repo"
    second = tmp_path / "b" / "repo"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    first_memory = MemoryManager(cwd=str(first))
    second_memory = MemoryManager(cwd=str(second))

    assert first_memory.memory_dir_path().parent.name == SessionStore(cwd=str(first)).project_key()
    assert second_memory.memory_dir_path().parent.name == SessionStore(cwd=str(second)).project_key()
    assert first_memory.memory_dir_path() != second_memory.memory_dir_path()


def test_legacy_auto_memory_index_is_read_when_stable_index_missing(tmp_path: Path, monkeypatch) -> None:
    import xcode_cli.paths
    from xcode_cli.core.memory import MemoryManager
    from xcode_cli.core.config import Config

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    memory = MemoryManager(cwd=str(project_dir))
    legacy_dir = memory.legacy_memory_dir_path()
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "MEMORY.md").write_text("- [Old](old.md) - old hook\n", encoding="utf-8")

    context = memory.get_context_for_prompt(Config(auto_memory=True))

    assert "Old" in context
    assert memory.memory_index_path().exists() is False
```

- [x] **Step 2: Run tests to verify failure**

Run:

```text
pytest tests/test_memory.py::test_auto_memory_path_uses_stable_project_key tests/test_memory.py::test_legacy_auto_memory_index_is_read_when_stable_index_missing -q
```

Expected:

- First test fails because `MemoryManager` still uses `cwd.name`.
- Second test fails because `legacy_memory_dir_path()` is not implemented.

- [x] **Step 3: Add shared project-key helper**

Create `src/xcode_cli/core/project_key.py`:

```python
from __future__ import annotations

import os


def project_key_for_path(cwd: str) -> str:
    path = os.path.abspath(cwd)
    key = path.replace(":", "").replace("\\", "--").replace("/", "--")
    while key.startswith("-"):
        key = key[1:]
    return key or "default"
```

Modify `src/xcode_cli/core/session.py`:

```python
from xcode_cli.core.project_key import project_key_for_path
```

Replace `SessionStore.project_key()` body with:

```python
    def project_key(self) -> str:
        return project_key_for_path(self._cwd)
```

- [x] **Step 4: Update MemoryManager stable and legacy paths**

Modify `src/xcode_cli/core/memory.py` imports:

```python
from xcode_cli.core.project_key import project_key_for_path
```

Replace the auto memory path setup in `MemoryManager.__init__` with:

```python
        project_key = project_key_for_path(str(self.cwd))
        legacy_project_name = self.cwd.name or "default"
        self.memory_dir = self.xcode_home / "projects" / project_key / "memory"
        self.legacy_memory_dir = self.xcode_home / "projects" / legacy_project_name / "memory"
        self.memory_index = self.memory_dir / "MEMORY.md"
        self.legacy_memory_index = self.legacy_memory_dir / "MEMORY.md"
```

Add helpers:

```python
    def legacy_memory_dir_path(self) -> Path:
        return self.legacy_memory_dir

    def legacy_memory_index_path(self) -> Path:
        return self.legacy_memory_index
```

Replace `read_memory_index()` with:

```python
    def read_memory_index(self) -> str:
        path = self.memory_index
        if not path.exists() and self.legacy_memory_index.exists():
            path = self.legacy_memory_index
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()
```

- [x] **Step 5: Update `/memory` status display**

Modify `_handle_memory_command()` in `src/xcode_cli/core/agent.py` so it prints legacy status when present:

```python
            legacy_dir = self.memory.legacy_memory_dir_path()
            if legacy_dir.exists() and legacy_dir != self.memory.memory_dir_path():
                self.console.print(f"Legacy memory dir: {legacy_dir} (read fallback)")
```

- [x] **Step 6: Update prompt path tests if needed**

If `tests/test_prompting_memory.py::test_resolved_memory_paths_in_prompt` asserts the old path shape, update it to compare against `MemoryManager.memory_dir_path()` instead of hard-coded `<cwd.name>`.

- [x] **Step 7: Run focused tests**

Run:

```text
pytest tests/test_memory.py tests/test_prompting_memory.py tests/test_agent_memory_command.py -q
```

Expected:

- All tests pass.
- Existing invalid Windows path regression still passes.

- [x] **Step 8: Stop for review**

Do not continue into manifest scanning until this task is reviewed. If the user asks for commits, use:

```text
git add src/xcode_cli/core/project_key.py src/xcode_cli/core/session.py src/xcode_cli/core/memory.py src/xcode_cli/core/prompting.py src/xcode_cli/core/agent.py tests/test_memory.py tests/test_prompting_memory.py tests/test_agent_memory_command.py
git commit -m "feat: stabilize auto memory paths"
```

