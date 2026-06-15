from __future__ import annotations

from pathlib import Path

from xcode_cli.core.work_state import WorkStateTracker


def test_read_file_result_records_bounded_excerpt_and_hash(tmp_path: Path) -> None:
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir()
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    tracker = WorkStateTracker(cwd=str(tmp_path), max_file_excerpt_chars=20)

    tracker.record_tool_call(
        "read_file",
        {"path": str(target), "offset": 1, "limit": 2},
        "one\ntwo\nthree\n",
    )

    snapshot = tracker.snapshot()
    assert snapshot.active_file == str(target)
    assert len(snapshot.recent_files) == 1
    recent = snapshot.recent_files[0]
    assert recent.path == str(target)
    assert recent.line_start == 1
    assert recent.line_end == 2
    assert recent.sha256.startswith("sha256:")
    assert "one" in recent.excerpt


def test_write_file_records_path_and_hash_without_written_content(tmp_path: Path) -> None:
    target = tmp_path / "secret.txt"
    target.write_text("client_secret = should-not-render\n", encoding="utf-8")
    tracker = WorkStateTracker(cwd=str(tmp_path))

    tracker.record_tool_call(
        "write_file",
        {"path": str(target), "content": "client_secret = should-not-render"},
        "wrote file",
    )

    rendered = tracker.render_restored_context()
    assert str(target) in rendered
    assert "should-not-render" not in rendered


def test_run_shell_records_test_failures_and_redacts_secrets(tmp_path: Path) -> None:
    tracker = WorkStateTracker(cwd=str(tmp_path))
    output = (
        "FAILED tests/test_context.py::test_manual_compact\n"
        "Authorization: Bearer very-secret-token\n"
        "src/foo.py:42: error: broken\n"
        "exit_code=1"
    )

    tracker.record_tool_call("run_shell", {"command": "pytest tests -q"}, output)

    snapshot = tracker.snapshot()
    assert snapshot.latest_test is not None
    assert "tests/test_context.py::test_manual_compact" in snapshot.latest_test.failed_tests
    rendered = tracker.render_restored_context()
    assert "very-secret-token" not in rendered
    assert "[REDACTED]" in rendered
    assert "src/foo.py:42 error: broken" in rendered


def test_run_shell_diagnostics_preserve_windows_absolute_path(tmp_path: Path) -> None:
    tracker = WorkStateTracker(cwd=str(tmp_path))
    output = r"D:\Xcode\src\foo.py:42:13: error: broken"

    tracker.record_tool_call("run_shell", {"command": "python -m compileall src"}, output)

    diagnostic = tracker.snapshot().diagnostics[0]
    assert diagnostic.path == r"D:\Xcode\src\foo.py"
    assert diagnostic.line == 42
    assert diagnostic.column == 13
    rendered = tracker.render_restored_context()
    assert r"D:\Xcode\src\foo.py:42:13 error: broken" in rendered


def test_restored_context_budget_omits_low_priority_sections(tmp_path: Path) -> None:
    tracker = WorkStateTracker(cwd=str(tmp_path), max_restored_context_chars=260)
    for index in range(8):
        target = tmp_path / f"file{index}.py"
        target.write_text("x" * 100, encoding="utf-8")
        tracker.record_tool_call("read_file", {"path": str(target)}, "x" * 100)
    tracker.record_tool_call("skill", {"skill": "review"}, "<xcode_loaded_skill name=\"review\" />")

    rendered = tracker.render_restored_context()

    assert rendered.startswith("Compact restored context:")
    assert "omitted" in rendered
    assert len(rendered) <= 260
