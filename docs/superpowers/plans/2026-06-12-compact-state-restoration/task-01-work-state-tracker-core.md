# Task 1: WorkStateTracker Core

**Risk layer:** P0/P1

**Goal:** Build the bounded in-memory work-state tracker that later compact steps can consume.

**Files:**
- Create: `src/xcode_cli/core/work_state.py`
- Create: `tests/test_work_state.py`

- [ ] **Step 1: Write failing tests for file excerpts**

Add tests that record a `read_file` result with numbered lines and assert:

```python
def test_records_read_file_excerpt_with_hash(tmp_path):
    target = tmp_path / "LoginView.swift"
    target.write_text("\n".join(f"line {i}" for i in range(1, 121)), encoding="utf-8")
    output = "\n".join(f"{i}\tline {i}" for i in range(30, 81))

    tracker = WorkStateTracker(max_files=4, max_file_chars=4000)
    tracker.record_tool_result(
        tool_name="read_file",
        args={"path": str(target), "offset": 29, "limit": 51},
        content=output,
    )

    snapshot = tracker.snapshot()
    assert snapshot.active_file == str(target)
    assert snapshot.recent_files[0].line_start == 30
    assert snapshot.recent_files[0].line_end == 80
    assert snapshot.recent_files[0].sha256.startswith("sha256:")
```

- [ ] **Step 2: Write failing tests for command parsing and redaction**

Cover xcode/swift-style diagnostics, pytest failures, exit code parsing, and secret redaction:

```python
def test_records_shell_build_diagnostics_and_redacts_secret():
    tracker = WorkStateTracker()
    content = (
        "Sources/LoginView.swift:42:13: error: Cannot convert value\n"
        "Authorization: Bearer secret-token\n"
        "exit_code=65"
    )

    tracker.record_tool_result(
        tool_name="run_shell",
        args={"command": "xcodebuild test", "cwd": "D:\\Xcode"},
        content=content,
    )

    snapshot = tracker.snapshot()
    assert snapshot.latest_test is not None
    assert snapshot.latest_test.exit_code == 65
    assert snapshot.diagnostics[0].path.endswith("LoginView.swift")
    assert "secret-token" not in snapshot.latest_test.output_excerpt
```

- [ ] **Step 3: Implement dataclasses and bounded storage**

Implement `FileExcerpt`, `DiagnosticItem`, `CommandStatus`, `WorkStateSnapshot`, and `WorkStateTracker`. Keep storage in memory only. Use small helper functions:

```python
def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _redact(text: str) -> str:
    patterns = [
        r"Authorization:\s*(Bearer|QQBot|Basic|Token)\s+\S+",
        r"(?i)(client_secret|access_token|api_key|app_secret|qq_bot_client_secret)\s*[:=]\s*\S+",
        r"(?i)--(client-secret|access-token|api-key|app-secret)(\s+|=)\S+",
    ]
    ...
```

Catch `OSError` and `UnicodeDecodeError`; a tracker failure must never raise out of the tool loop.

- [ ] **Step 4: Implement restored-context renderer**

Add `render_restored_context(snapshot, max_chars=8000) -> tuple[str, list[str]]`. It must emit sections in priority order and return the included section names. When budget is exceeded, include an omission line rather than silently cutting through the middle of a file excerpt.

- [ ] **Step 5: Verify task**

Run:

```powershell
pytest tests/test_work_state.py -q
```

Expected: all new work-state tests pass.
