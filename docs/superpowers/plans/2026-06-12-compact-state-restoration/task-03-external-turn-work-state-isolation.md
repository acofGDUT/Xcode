# Task 3: External Turn Work-State Isolation

**Risk layer:** P0

**Goal:** Ensure QQchat/external conversations do not share local REPL work state or each other's work state.

**Files:**
- Modify: `src/xcode_cli/core/external_turn.py`
- Modify: `src/xcode_cli/core/agent.py`
- Modify: `tests/test_external_turn.py`

- [ ] **Step 1: Write failing isolation tests**

Cover two cases:

```python
def test_external_turns_do_not_share_local_work_state(...):
    ...

def test_external_conversations_have_separate_work_state(...):
    ...
```

The first test should seed local `AgentRuntime.work_state` and assert a QQ turn does not receive it. The second should run two external conversation keys with different read files and assert their snapshots differ.

- [ ] **Step 2: Extend external state**

Add a `work_state` field to the per-conversation state in `ExternalTurnRunner`, or add a small `work_state_for_session_id()` callback. Prefer keeping state beside the existing external `history` and `session_id`.

- [ ] **Step 3: Pass external work state into headless loop**

Extend `_run_external_llm_loop()` and `_run_llm_loop()` with optional `work_state`. Local calls default to `self.work_state`; external calls pass the conversation-specific tracker.

- [ ] **Step 4: Verify task**

Run:

```powershell
pytest tests/test_external_turn.py tests/test_agent_tool_loop.py -q
```

Expected: external state isolation passes and local tool-loop behavior remains unchanged.
