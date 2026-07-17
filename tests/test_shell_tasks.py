from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from xcode_cli.core.shell_tasks import ShellTaskManager, ShellTaskTimeout


def _python_command(code: str) -> str:
    args = [sys.executable, "-u", "-c", code]
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def _wait_for_status(
    manager: ShellTaskManager,
    task_id: str,
    expected: set[str],
    timeout: float = 5.0,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot, _ = manager.get_output(task_id)
        if snapshot.status in expected:
            return snapshot
        time.sleep(0.02)
    snapshot, _ = manager.get_output(task_id)
    raise AssertionError(f"task {task_id} stayed in {snapshot.status}")


def _wait_for_port(port: int, *, listening: bool, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            available = probe.connect_ex(("127.0.0.1", port)) == 0
        if available is listening:
            return
        time.sleep(0.02)
    raise AssertionError(f"port {port} listening={available}, expected {listening}")


@pytest.fixture
def manager(tmp_path: Path):
    value = ShellTaskManager(base_dir=tmp_path / "shell-tasks")
    try:
        yield value
    finally:
        value.shutdown()


def test_fast_command_returns_output_and_exit_code(manager: ShellTaskManager) -> None:
    result = manager.run(
        _python_command("print('hello from shell')"),
        timeout_ms=5000,
    )

    assert result.background_reason is None
    assert result.task.status == "completed"
    assert result.task.exit_code == 0
    assert "hello from shell" in result.output


def test_explicit_background_returns_without_restarting_process(manager: ShellTaskManager) -> None:
    started = time.monotonic()
    result = manager.run(
        _python_command("import time; print('ready', flush=True); time.sleep(0.6)"),
        timeout_ms=5000,
        run_in_background=True,
    )

    assert time.monotonic() - started < 0.5
    assert result.background_reason == "explicit"
    assert result.task.status == "running"
    assert result.task.backgrounded is True
    assert len(manager.list_tasks()) == 1
    assert manager.list_tasks()[0].pid == result.task.pid

    completed = _wait_for_status(manager, result.task.task_id, {"completed"})
    assert completed.exit_code == 0


def test_wait_budget_transitions_same_process_to_background(manager: ShellTaskManager) -> None:
    result = manager.run(
        _python_command("import time; print('started', flush=True); time.sleep(0.5)"),
        timeout_ms=50,
    )

    assert result.background_reason == "timeout"
    assert result.task.status == "running"
    assert result.task.backgrounded is True
    assert manager.list_tasks()[0].pid == result.task.pid

    completed = _wait_for_status(manager, result.task.task_id, {"completed"})
    assert completed.exit_code == 0


def test_background_output_continues_after_run_returns(manager: ShellTaskManager) -> None:
    result = manager.run(
        _python_command(
            "import time; print('first', flush=True); time.sleep(0.15); print('second', flush=True)"
        ),
        run_in_background=True,
    )

    completed = _wait_for_status(manager, result.task.task_id, {"completed"})
    snapshot, output = manager.get_output(result.task.task_id)

    assert completed.status == "completed"
    assert snapshot.exit_code == 0
    assert "first" in output
    assert "second" in output
    assert Path(snapshot.output_file).read_bytes()


def test_output_is_bounded_but_pipe_is_drained(tmp_path: Path) -> None:
    manager = ShellTaskManager(base_dir=tmp_path / "shell-tasks", max_output_bytes=64)
    try:
        result = manager.run(
            _python_command("import sys; sys.stdout.write('x' * 4096); sys.stdout.flush()"),
            timeout_ms=5000,
        )
        snapshot, output = manager.get_output(result.task.task_id, max_chars=1000)

        assert snapshot.status == "completed"
        assert snapshot.output_truncated is True
        assert len(output.encode("utf-8")) <= 64
        assert Path(snapshot.output_file).stat().st_size <= 64
    finally:
        manager.shutdown()


def test_stop_task_is_idempotent(manager: ShellTaskManager) -> None:
    result = manager.run(
        _python_command("import time; print('ready', flush=True); time.sleep(30)"),
        run_in_background=True,
    )

    stopped = manager.stop_task(result.task.task_id)
    stopped_again = manager.stop_task(result.task.task_id)

    assert stopped.status == "stopped"
    assert stopped_again.status == "stopped"
    assert _wait_for_status(manager, result.task.task_id, {"stopped"}).status == "stopped"


def test_stop_task_releases_child_listening_port(manager: ShellTaskManager) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    result = manager.run(
        _python_command(
            "import http.server; "
            f"server = http.server.ThreadingHTTPServer(('127.0.0.1', {port}), "
            "http.server.SimpleHTTPRequestHandler); "
            "print('listening', flush=True); server.serve_forever()"
        ),
        run_in_background=True,
    )
    _wait_for_port(port, listening=True)

    stopped = manager.stop_task(result.task.task_id)
    _wait_for_port(port, listening=False)

    assert stopped.status == "stopped"
    with socket.socket() as rebound:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            rebound.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        rebound.bind(("127.0.0.1", port))


def test_shutdown_stops_all_running_tasks_and_is_idempotent(tmp_path: Path) -> None:
    manager = ShellTaskManager(base_dir=tmp_path / "shell-tasks")
    first = manager.run(
        _python_command("import time; time.sleep(30)"),
        run_in_background=True,
    )
    second = manager.run(
        _python_command("import time; time.sleep(30)"),
        run_in_background=True,
    )

    manager.shutdown()
    manager.shutdown()

    statuses = {task.task_id: task.status for task in manager.list_tasks()}
    assert statuses[first.task.task_id] == "stopped"
    assert statuses[second.task.task_id] == "stopped"


def test_shutdown_starts_process_tree_stops_concurrently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = ShellTaskManager(base_dir=tmp_path / "shell-tasks")
    first = manager.run(_python_command("import time; time.sleep(30)"), run_in_background=True)
    second = manager.run(_python_command("import time; time.sleep(30)"), run_in_background=True)
    original_request_stop = manager._request_stop
    barrier = threading.Barrier(2)

    def coordinated_stop(task, deadline):
        barrier.wait(timeout=1.0)
        original_request_stop(task, deadline)

    monkeypatch.setattr(manager, "_request_stop", coordinated_stop)
    try:
        manager.shutdown()
        statuses = {task.task_id: task.status for task in manager.list_tasks()}

        assert statuses[first.task.task_id] == "stopped"
        assert statuses[second.task.task_id] == "stopped"
    finally:
        monkeypatch.setattr(manager, "_request_stop", original_request_stop)
        manager.shutdown()


def test_unknown_task_id_is_controlled_error(manager: ShellTaskManager) -> None:
    with pytest.raises(KeyError, match="missing"):
        manager.get_output("missing")
    with pytest.raises(KeyError, match="missing"):
        manager.stop_task("missing")


def test_hard_timeout_stops_process_instead_of_backgrounding(manager: ShellTaskManager) -> None:
    started = time.monotonic()

    with pytest.raises(ShellTaskTimeout):
        manager.run(
            _python_command("import time; time.sleep(30)"),
            timeout_ms=50,
            background_on_timeout=False,
        )

    assert time.monotonic() - started < 3.0
    assert manager.list_tasks()[0].status == "stopped"


def test_default_output_directory_is_lazy_and_uses_runtime_xcode_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    manager = ShellTaskManager()

    assert not (xcode_dir / "shell_tasks").exists()

    try:
        result = manager.run(_python_command("print('ok')"), timeout_ms=5000)
        output_path = Path(result.task.output_file)

        assert output_path.is_relative_to(xcode_dir / "shell_tasks")
        assert output_path.exists()
    finally:
        manager.shutdown()

    assert not output_path.parent.exists()


def test_root_only_stop_fallback_does_not_report_stopped(
    manager: ShellTaskManager,
    monkeypatch,
) -> None:
    result = manager.run(
        _python_command("import time; time.sleep(30)"),
        run_in_background=True,
    )
    original_terminate = manager._terminate_process_tree

    def root_only_fallback(task, deadline):
        task.process.kill()
        task.process.wait(timeout=1.0)
        return False, True, True

    monkeypatch.setattr(manager, "_terminate_process_tree", root_only_fallback)
    with pytest.raises(RuntimeError, match="only the root process was terminated"):
        manager.stop_task(result.task.task_id)

    assert manager.list_tasks()[0].status != "stopped"
    monkeypatch.setattr(manager, "_terminate_process_tree", original_terminate)
