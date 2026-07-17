from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import BinaryIO, Literal


ShellTaskStatus = Literal["running", "completed", "failed", "stopped"]
BackgroundReason = Literal["explicit", "timeout"]

_DEFAULT_WAIT_TIMEOUT_MS = 120_000
_DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
_DEFAULT_MAX_OUTPUT_CHARS = 20_000
_READ_CHUNK_BYTES = 64 * 1024
_DEFAULT_STOP_TIMEOUT_SECONDS = 2.0


class ShellTaskTimeout(TimeoutError):
    """Raised when a foreground wait budget expires and backgrounding is disabled."""

    def __init__(self, task: ShellTaskSnapshot, timeout_ms: int) -> None:
        self.task = task
        self.task_id = task.task_id
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Shell task {task.task_id} timed out after {timeout_ms}ms; stop was requested"
        )


@dataclass(frozen=True)
class ShellTaskSnapshot:
    """Immutable public view of a managed shell process."""

    task_id: str
    command: str
    cwd: str | None
    pid: int
    status: ShellTaskStatus
    backgrounded: bool
    background_reason: BackgroundReason | None
    exit_code: int | None
    output_file: str
    output_truncated: bool
    started_at: float
    ended_at: float | None
    error: str | None = None

    @property
    def root_pid(self) -> int:
        return self.pid


@dataclass(frozen=True)
class ShellRunResult:
    """Result of the foreground portion of a shell task."""

    task: ShellTaskSnapshot
    output: str
    background_reason: BackgroundReason | None


@dataclass
class _ShellTask:
    task_id: str
    command: str
    cwd: str | None
    process: subprocess.Popen[bytes]
    output_path: Path
    started_at: float
    status: ShellTaskStatus = "running"
    backgrounded: bool = False
    background_reason: BackgroundReason | None = None
    exit_code: int | None = None
    output_truncated: bool = False
    ended_at: float | None = None
    error: str | None = None
    output_buffer: bytearray = field(default_factory=bytearray, repr=False)
    output_file_bytes: int = 0
    total_output_bytes: int = 0
    stop_confirmed: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    stop_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    drain_done: threading.Event = field(default_factory=threading.Event, repr=False)
    monitor_thread: threading.Thread | None = field(default=None, repr=False)


class ShellTaskManager:
    """Owns shell processes and exposes a synchronous, thread-safe task API."""

    def __init__(
        self,
        *,
        base_dir: str | os.PathLike[str] | None = None,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
        max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
        stop_timeout_seconds: float = _DEFAULT_STOP_TIMEOUT_SECONDS,
    ) -> None:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be greater than zero")
        if max_output_chars <= 0:
            raise ValueError("max_output_chars must be greater than zero")
        if stop_timeout_seconds <= 0:
            raise ValueError("stop_timeout_seconds must be greater than zero")

        self._base_dir_override = (
            Path(base_dir).expanduser().resolve() if base_dir is not None else None
        )
        self._base_dir: Path | None = None
        self._runtime_id = uuid.uuid4().hex
        self._max_output_bytes = int(max_output_bytes)
        self._max_output_chars = int(max_output_chars)
        self._stop_timeout_seconds = float(stop_timeout_seconds)
        self._tasks: dict[str, _ShellTask] = {}
        self._lock = threading.RLock()
        self._shutdown = False

    def run(
        self,
        command: str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        timeout_ms: int = _DEFAULT_WAIT_TIMEOUT_MS,
        run_in_background: bool = False,
        background_on_timeout: bool = True,
    ) -> ShellRunResult:
        """Spawn once, then return on drain completion or background transition."""

        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        if timeout_ms < 0:
            raise ValueError("timeout_ms must not be negative")

        background_reason: BackgroundReason | None = (
            "explicit" if run_in_background else None
        )
        task = self._spawn_task(command, cwd, background_reason)

        if run_in_background:
            snapshot, output = self._output_for_task(task, self._max_output_chars)
            return ShellRunResult(snapshot, output, "explicit")

        if task.drain_done.wait(timeout_ms / 1000):
            snapshot, output = self._output_for_task(task, self._max_output_chars)
            return ShellRunResult(snapshot, output, None)

        if background_on_timeout:
            with task.lock:
                if task.status == "running":
                    task.backgrounded = True
                    task.background_reason = "timeout"
                    background_reason = "timeout"
                else:
                    background_reason = None
            snapshot, output = self._output_for_task(task, self._max_output_chars)
            return ShellRunResult(snapshot, output, background_reason)

        try:
            snapshot = self.stop_task(task.task_id)
        except Exception as exc:
            snapshot = self._snapshot(task)
            raise ShellTaskTimeout(snapshot, timeout_ms) from exc
        raise ShellTaskTimeout(snapshot, timeout_ms)

    def get_output(
        self,
        task_id: str,
        *,
        max_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
    ) -> tuple[ShellTaskSnapshot, str]:
        task = self._get_task(task_id)
        requested_chars = self._clamp_max_chars(max_chars)
        return self._output_for_task(task, requested_chars)

    def list_tasks(self) -> list[ShellTaskSnapshot]:
        with self._lock:
            tasks = list(self._tasks.values())
        return [self._snapshot(task) for task in tasks]

    def stop_task(self, task_id: str) -> ShellTaskSnapshot:
        task = self._get_task(task_id)
        deadline = time.monotonic() + self._stop_timeout_seconds
        self._request_stop(task, deadline)

        remaining = max(0.0, deadline - time.monotonic())
        if not task.drain_done.wait(remaining):
            raise RuntimeError(
                f"Shell task {task.task_id} did not finish draining after stop"
            )

        snapshot = self._snapshot(task)
        if snapshot.status == "running":
            raise RuntimeError(f"Shell task {task.task_id} is still running")
        return snapshot

    def shutdown(self) -> None:
        """Stop all live tasks, then wait boundedly for drains before cleanup."""

        with self._lock:
            self._shutdown = True
            tasks = list(self._tasks.values())

        # Stop tasks concurrently so every process tree receives the same bounded
        # shutdown budget instead of later tasks inheriting an expired deadline.
        stop_deadline = time.monotonic() + self._stop_timeout_seconds
        stop_threads: list[threading.Thread] = []

        def request_stop(task: _ShellTask) -> None:
            try:
                self._request_stop(task, stop_deadline)
            except Exception:
                # Shutdown is best effort; a failed stop remains visibly non-terminal.
                pass

        for task in tasks:
            thread = threading.Thread(
                target=request_stop,
                args=(task,),
                name=f"xcode-shell-stop-{task.task_id}",
                daemon=True,
            )
            stop_threads.append(thread)
            thread.start()

        for thread in stop_threads:
            remaining = max(0.0, stop_deadline - time.monotonic())
            if remaining == 0:
                break
            thread.join(remaining)

        drain_deadline = time.monotonic() + self._stop_timeout_seconds
        for task in tasks:
            remaining = max(0.0, drain_deadline - time.monotonic())
            task.drain_done.wait(remaining)

        for task in tasks:
            thread = task.monitor_thread
            if thread is not None and task.drain_done.is_set():
                thread.join(timeout=0.05)

        base_dir = self._base_dir
        if base_dir is not None and all(task.drain_done.is_set() for task in tasks):
            shutil.rmtree(base_dir, ignore_errors=True)

    def _spawn_task(
        self,
        command: str,
        cwd: str | os.PathLike[str] | None,
        background_reason: BackgroundReason | None,
    ) -> _ShellTask:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("ShellTaskManager has been shut down")

        task_id = f"shell-{uuid.uuid4().hex}"
        output_path = self._ensure_base_dir() / f"{task_id}.log"
        output_path.touch(exist_ok=False)
        cwd_value = os.fspath(cwd) if cwd is not None else None

        popen_kwargs: dict[str, object] = {
            "shell": True,
            "cwd": cwd_value,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "bufsize": 0,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(command, **popen_kwargs)  # type: ignore[arg-type]
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

        task = _ShellTask(
            task_id=task_id,
            command=command,
            cwd=cwd_value,
            process=process,
            output_path=output_path,
            started_at=time.time(),
            backgrounded=background_reason is not None,
            background_reason=background_reason,
        )
        with self._lock:
            if self._shutdown:
                # A concurrent shutdown won the race after spawn. Register so the
                # process remains visible, then stop it below.
                self._tasks[task_id] = task
                should_stop = True
            else:
                self._tasks[task_id] = task
                should_stop = False

        thread = threading.Thread(
            target=self._monitor_task,
            args=(task,),
            name=f"xcode-shell-{task_id}",
            daemon=True,
        )
        task.monitor_thread = thread
        thread.start()

        if should_stop:
            try:
                self.stop_task(task_id)
            finally:
                raise RuntimeError("ShellTaskManager has been shut down")
        return task

    def _monitor_task(self, task: _ShellTask) -> None:
        output_file: BinaryIO | None = None
        monitor_error: str | None = None
        try:
            try:
                output_file = task.output_path.open("ab", buffering=0)
            except OSError as exc:
                monitor_error = f"failed to open task output: {exc}"

            stream = task.process.stdout
            if stream is None:
                raise RuntimeError("shell process stdout pipe is unavailable")

            while True:
                # Fixed-size binary reads keep draining commands with no newlines.
                chunk = stream.read(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                write_error = self._record_output(task, chunk, output_file)
                if write_error is not None and monitor_error is None:
                    monitor_error = write_error
        except Exception as exc:
            if monitor_error is None:
                monitor_error = f"shell output monitor failed: {exc}"
            self._stop_after_monitor_failure(task)
        finally:
            try:
                if task.process.stdout is not None:
                    task.process.stdout.close()
            except Exception:
                pass
            if output_file is not None:
                try:
                    output_file.close()
                except Exception as exc:
                    if monitor_error is None:
                        monitor_error = f"failed to close task output: {exc}"

        try:
            exit_code = task.process.wait()
        except Exception as exc:
            exit_code = task.process.poll()
            if monitor_error is None:
                monitor_error = f"failed to wait for shell process: {exc}"

        # Serialize terminal publication with stop_task so a natural-exit/stop
        # race cannot overwrite a confirmed stop or report a failed kill as stopped.
        with task.stop_lock:
            with task.lock:
                task.exit_code = exit_code
                task.ended_at = time.time()
                if task.stop_confirmed:
                    task.status = "stopped"
                elif monitor_error is not None:
                    task.status = "failed"
                    task.error = monitor_error
                elif exit_code == 0:
                    task.status = "completed"
                else:
                    task.status = "failed"
        task.drain_done.set()

    def _record_output(
        self,
        task: _ShellTask,
        chunk: bytes,
        output_file: BinaryIO | None,
    ) -> str | None:
        with task.lock:
            task.total_output_bytes += len(chunk)

            task.output_buffer.extend(chunk)
            if len(task.output_buffer) > self._max_output_bytes:
                del task.output_buffer[: len(task.output_buffer) - self._max_output_bytes]

            remaining = self._max_output_bytes - task.output_file_bytes
            to_write = chunk[: max(0, remaining)]
            if len(to_write) < len(chunk):
                task.output_truncated = True
            task.output_file_bytes += len(to_write)

        if not to_write:
            return None
        if output_file is None:
            with task.lock:
                task.output_truncated = True
            return "task output file is unavailable"
        try:
            output_file.write(to_write)
        except OSError as exc:
            with task.lock:
                task.output_truncated = True
            return f"failed to write task output: {exc}"
        return None

    def _stop_after_monitor_failure(self, task: _ShellTask) -> None:
        deadline = time.monotonic() + self._stop_timeout_seconds
        with task.stop_lock:
            self._terminate_process_tree(task, deadline)

    def _request_stop(self, task: _ShellTask, deadline: float) -> None:
        with task.stop_lock:
            with task.lock:
                if task.status != "running":
                    return

            if task.process.poll() is not None:
                # The process won the race naturally. Let the monitor publish its
                # real completed/failed status after it drains the remaining pipe.
                return

            tree_kill_succeeded, exited, root_fallback_used = (
                self._terminate_process_tree(task, deadline)
            )
            if not exited:
                raise RuntimeError(
                    f"Failed to stop shell task {task.task_id}: process is still running"
                )
            if root_fallback_used:
                raise RuntimeError(
                    f"Failed to stop shell task {task.task_id}: process-tree stop "
                    "failed; only the root process was terminated"
                )
            if tree_kill_succeeded:
                with task.lock:
                    task.stop_confirmed = True

    def _terminate_process_tree(
        self,
        task: _ShellTask,
        deadline: float,
    ) -> tuple[bool, bool, bool]:
        process = task.process
        if process.poll() is not None:
            return False, True, False

        tree_kill_succeeded = False
        root_fallback_used = False
        if os.name == "nt":
            remaining = max(0.01, deadline - time.monotonic())
            try:
                completed = subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=remaining,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                tree_kill_succeeded = completed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                tree_kill_succeeded = False
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                tree_kill_succeeded = True
            except (OSError, ProcessLookupError):
                tree_kill_succeeded = False

        if process.poll() is None and not tree_kill_succeeded:
            root_fallback_used = True
            try:
                process.kill()
            except OSError:
                pass

        if process.poll() is None:
            remaining = max(0.0, deadline - time.monotonic())
            if remaining > 0:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    pass
        return tree_kill_succeeded, process.poll() is not None, root_fallback_used

    def _output_for_task(
        self,
        task: _ShellTask,
        max_chars: int,
    ) -> tuple[ShellTaskSnapshot, str]:
        with task.lock:
            data = bytes(task.output_buffer)
            snapshot = self._snapshot_locked(task)

        output = data.decode("utf-8", errors="replace")
        view_truncated = len(output) > max_chars
        if max_chars == 0:
            output = ""
        elif view_truncated:
            output = output[-max_chars:]
        if view_truncated and not snapshot.output_truncated:
            snapshot = replace(snapshot, output_truncated=True)
        return snapshot, output

    def _snapshot(self, task: _ShellTask) -> ShellTaskSnapshot:
        with task.lock:
            return self._snapshot_locked(task)

    @staticmethod
    def _snapshot_locked(task: _ShellTask) -> ShellTaskSnapshot:
        return ShellTaskSnapshot(
            task_id=task.task_id,
            command=task.command,
            cwd=task.cwd,
            pid=task.process.pid,
            status=task.status,
            backgrounded=task.backgrounded,
            background_reason=task.background_reason,
            exit_code=task.exit_code,
            output_file=str(task.output_path),
            output_truncated=task.output_truncated,
            started_at=task.started_at,
            ended_at=task.ended_at,
            error=task.error,
        )

    def _get_task(self, task_id: str) -> _ShellTask:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown shell task: {task_id}")
        return task

    def _ensure_base_dir(self) -> Path:
        with self._lock:
            if self._base_dir is None:
                if self._base_dir_override is not None:
                    base_dir = self._base_dir_override
                else:
                    # Read through the module at first spawn so test/runtime
                    # monkeypatches of XCODE_DIR are respected.
                    from xcode_cli import paths as xcode_paths

                    base_dir = (
                        Path(xcode_paths.XCODE_DIR)
                        / "shell_tasks"
                        / self._runtime_id
                    ).expanduser().resolve()
                base_dir.mkdir(parents=True, exist_ok=True)
                self._base_dir = base_dir
            return self._base_dir

    def _clamp_max_chars(self, max_chars: int) -> int:
        try:
            requested = int(max_chars)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_chars must be an integer") from exc
        return min(self._max_output_chars, max(0, requested))


# Backwards-compatible descriptive alias for integrations that prefer the longer name.
ShellTaskRunResult = ShellRunResult
