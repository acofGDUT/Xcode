# Task 2: Record Work State From Tool Execution

**Risk layer:** P0

**Goal:** Feed tool results into `WorkStateTracker` without changing model-visible tool messages.

**Files:**
- Modify: `src/xcode_cli/core/tooling/execution.py`
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `tests/test_agent_tool_loop.py`

- [ ] **Step 1: Write failing integration test**

Add a test where the fake LLM calls `read_file`; after `_run_llm_loop()`, assert local `agent.work_state.snapshot().active_file` points to the file. Also assert the `tool` message content in history is unchanged.

- [ ] **Step 2: Add optional work_state parameter**

Change `ToolCallExecutor.execute(...)` to accept:

```python
work_state: WorkStateTracker | None = None
```

After each `ToolOutput` is produced, call:

```python
if work_state is not None:
    work_state.record_tool_result(tc.name, tc.args, output.content, audit_metadata=output.audit_metadata)
```

Wrap the call in `try/except Exception` and ignore tracker failures.

- [ ] **Step 3: Wire local AgentRuntime state**

In `AgentRuntime.__init__`, create:

```python
self.work_state = WorkStateTracker()
```

Pass it from `_run_llm_loop()` when the loop is local. Do not attach work-state metadata to model messages.

- [ ] **Step 4: Verify task**

Run:

```powershell
pytest tests/test_work_state.py tests/test_agent_tool_loop.py -q
```

Expected: work-state unit tests and tool-loop integration tests pass.
