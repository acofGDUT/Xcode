# Memory Model Validation Task Brief

Date: 2026-05-25
Project: Xcode
Owner role: Coding Agent implementation brief
Reviewer role: Codex architecture/review agent

Status: completed and accepted on 2026-05-25.

## 1. Goal

This batch does not redesign the memory system.

The memory model is already decided by current implementation and project docs:

- project memory: `<project>/XCODE.md`
- user memory: `~/.xcode/XCODE.md`
- auto memory: `~/.xcode/projects/<project>/memory/`
- auto memory index: `MEMORY.md`
- one auto memory topic per `<slug>.md` file

The Coding Agent should only strengthen the implementation around this existing model:

- restore a real test baseline for memory behavior
- verify slash-command behavior for `/memory`
- make only minimal code changes if tests expose real mismatches

## 2. Source of Truth

Use current code as the primary source of truth:

- `src/xcode_cli/core/memory.py`
- `src/xcode_cli/core/prompting.py`
- `src/xcode_cli/core/agent.py`
- `src/xcode_cli/core/config.py`

Project docs have been updated to match this model. Do not revert to the old single-file `memory.md` design.

## 3. In Scope

### 3.1 MemoryManager test baseline

Status: completed.

Expected test file:

- `tests/test_memory.py`

Minimum coverage:

- `user_memory_path()` and `project_memory_path()` resolve correctly
- `memory_dir_path()` and `memory_index_path()` point to `~/.xcode/projects/<project>/memory/`
- `write_user_memory(..., append=True)` appends correctly
- `write_project_memory(..., append=True)` appends correctly
- `read_memory_index()` returns empty string when missing
- `get_context_for_prompt()` injects:
  - project XCODE block
  - user XCODE block
  - auto memory index block only when `auto_memory=True`
- truncation behavior still holds

### 3.2 Prompt integration test baseline

Status: completed.

Expected test file:

- `tests/test_prompting_memory.py`

Minimum coverage:

- `build_system_prompt()` includes memory context when files exist
- enabled skills still compose correctly with memory context
- project cwd is passed into `MemoryManager`
- auto memory block is index-only, not individual memory file body injection

### 3.3 `/memory` real command path tests

Status: completed.

Expected test file:

- `tests/test_agent_memory_command.py`

Minimum coverage:

- `/memory` prints:
  - auto-memory on/off
  - project memory path
  - user memory path
  - memory dir path
- `/memory auto on` persists `Config.auto_memory=True`
- `/memory auto off` persists `Config.auto_memory=False`
- tests run against temporary Xcode home, not the real user directory

## 4. Out of Scope

Do not do any of the following in this batch:

- redesign memory model
- reintroduce dedicated memory CRUD tools
- add resume/continue
- add `/context` cost estimate
- add project config merge
- change Phase 5 scope

If you discover a deeper design problem, note it in the handoff instead of expanding scope.

## 5. Implementation Constraints

- Keep the current prompt-driven model
- Do not add code that parses or classifies auto memory entries inside `MemoryManager`
- Do not make `MemoryManager` responsible for creating or maintaining individual auto memory files
- If code changes are needed, they should be minimal and directly justified by failing tests
- Preserve Chinese user-facing UI strings where touched

## 6. Acceptance Criteria

The batch is acceptable only if all of the following are true:

- memory tests are real, not simulated-only placeholders
- tests are isolated from real `~/.xcode`
- `/memory` command behavior is covered through real `AgentRuntime` command-path tests
- current docs remain accurate for the final implementation
- no old `memory.md` single-file assumptions are reintroduced

## 7. Validation Commands

Before handoff, the Coding Agent must run and report:

```powershell
python -m py_compile src\xcode_cli\core\memory.py
python -m py_compile src\xcode_cli\core\prompting.py
python -m py_compile src\xcode_cli\core\agent.py
pytest
python -c "from xcode_cli.core.memory import MemoryManager; print('memory import ok')"
python -c "from xcode_cli.core.prompting import build_system_prompt; print('prompting import ok')"
```

If `pytest` scope is narrowed, explain why and include the exact command used.

## 8. Expected Deliverable

The Coding Agent handoff should include:

- files changed
- tests added
- commands run
- whether any code changes were needed beyond tests
- residual risks or follow-up notes

## 9. Review Focus For Codex

I will review this batch primarily for:

- whether tests actually exercise current memory behavior
- whether the current memory model stays prompt-driven
- whether `/memory` behavior is validated through real command paths
- whether any implementation change stays within the existing model
