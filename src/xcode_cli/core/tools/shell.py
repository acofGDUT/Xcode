from __future__ import annotations

import json
from dataclasses import asdict

from xcode_cli.core.shell_tasks import ShellRunResult, ShellTaskManager, ShellTaskTimeout
from xcode_cli.core.tool_registry import ToolDef


MAX_TASK_OUTPUT_CHARS = 20000


def _format_run_result(result: ShellRunResult) -> str:
    if result.background_reason is not None:
        task = result.task
        headline = (
            "Command is running in background."
            if task.status == "running"
            else "Command finished while being registered as a background task."
        )
        return "\n".join(
            [
                headline,
                f"task_id={task.task_id}",
                f"pid={task.pid}",
                f"status={task.status}",
                f"background_reason={result.background_reason}",
                f"output_file={task.output_file}",
            ]
        )

    parts: list[str] = []
    output = result.output.strip()
    if output:
        parts.append(output)
    if result.task.output_truncated:
        parts.append("[output truncated]")
    parts.append(f"exit_code={result.task.exit_code}")
    return "\n".join(parts)


def run_shell(command: str, cwd: str | None = None, timeout: int = 120000) -> str:
    """Run one command without leaving an unmanaged background task.

    The interactive AgentRuntime registers manager-bound tools instead. This
    compatibility entry point is also used by ``xcode tool run shell`` and
    therefore treats ``timeout`` as a hard deadline.
    """
    manager = ShellTaskManager()
    try:
        result = manager.run(
            command,
            cwd=cwd,
            timeout_ms=timeout,
            background_on_timeout=False,
        )
        return _format_run_result(result)
    except ShellTaskTimeout:
        return f"Error: command timed out after {timeout}ms"
    except Exception as exc:
        return f"Error: failed to run command: {exc}"
    finally:
        manager.shutdown()


def create_shell_tools(manager: ShellTaskManager) -> list[ToolDef]:
    def managed_run_shell(
        command: str,
        cwd: str | None = None,
        timeout: int = 120000,
        run_in_background: bool = False,
    ) -> str:
        try:
            result = manager.run(
                command,
                cwd=cwd,
                timeout_ms=timeout,
                run_in_background=run_in_background,
                background_on_timeout=True,
            )
        except Exception as exc:
            return f"Error: failed to run command: {exc}"
        return _format_run_result(result)

    def shell_task_output(task_id: str, max_chars: int = 20000) -> str:
        try:
            bounded_chars = max(0, min(int(max_chars), MAX_TASK_OUTPUT_CHARS))
            snapshot, output = manager.get_output(task_id, max_chars=bounded_chars)
        except KeyError:
            return f"Error: shell task not found: {task_id}"
        except Exception as exc:
            return f"Error: failed to read shell task '{task_id}': {exc}"

        parts = [
            f"task_id={snapshot.task_id}",
            f"status={snapshot.status}",
            f"pid={snapshot.pid}",
            f"exit_code={snapshot.exit_code}",
            f"output_truncated={str(snapshot.output_truncated).lower()}",
            f"output_file={snapshot.output_file}",
        ]
        if output:
            parts.extend(["output:", output])
        return "\n".join(parts)

    def shell_task_list() -> str:
        try:
            tasks = [asdict(task) for task in manager.list_tasks()]
        except Exception as exc:
            return f"Error: failed to list shell tasks: {exc}"
        return json.dumps(tasks, ensure_ascii=False)

    def shell_task_stop(task_id: str) -> str:
        try:
            snapshot = manager.stop_task(task_id)
        except KeyError:
            return f"Error: shell task not found: {task_id}"
        except Exception as exc:
            return f"Error: failed to stop shell task '{task_id}': {exc}"
        return "\n".join(
            [
                f"task_id={snapshot.task_id}",
                f"status={snapshot.status}",
                f"pid={snapshot.pid}",
                f"exit_code={snapshot.exit_code}",
            ]
        )

    return [
        ToolDef(
            name="run_shell",
            description=(
                "Execute a shell command. Set run_in_background=true for servers, watchers, "
                "and commands that do not exit by themselves. Run the target command directly; "
                "do not wrap it in start, Start-Process, or another detach mechanism. When the "
                "foreground wait budget expires, the same process continues as a managed task."
            ),
            parameters={
                "command": {"type": "string", "description": "Shell command to execute."},
                "cwd": {"type": "string", "description": "Optional working directory."},
                "timeout": {
                    "type": "integer",
                    "description": "Foreground wait budget in milliseconds before automatic backgrounding.",
                    "default": 120000,
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Return a managed task ID immediately without waiting for process exit.",
                    "default": False,
                },
            },
            required=["command"],
            execute=managed_run_shell,
            is_read_only=False,
        ),
        ToolDef(
            name="shell_task_output",
            description="Read bounded output and current status for a managed shell task.",
            parameters={
                "task_id": {"type": "string", "description": "Managed shell task ID."},
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum output characters to return.",
                    "default": 20000,
                },
            },
            required=["task_id"],
            execute=shell_task_output,
            is_read_only=True,
        ),
        ToolDef(
            name="shell_task_list",
            description="List managed shell tasks for the current local runtime.",
            parameters={},
            required=[],
            execute=shell_task_list,
            is_read_only=True,
        ),
        ToolDef(
            name="shell_task_stop",
            description="Stop a managed shell task and its process tree.",
            parameters={
                "task_id": {"type": "string", "description": "Managed shell task ID."},
            },
            required=["task_id"],
            execute=shell_task_stop,
            is_read_only=False,
        ),
    ]


RUN_SHELL_TOOL = ToolDef(
    name="run_shell",
    description="Execute a shell command with a hard timeout in a one-shot context.",
    parameters={
        "command": {"type": "string", "description": "Shell command to execute."},
        "cwd": {"type": "string", "description": "Optional working directory."},
        "timeout": {"type": "integer", "description": "Hard timeout in milliseconds.", "default": 120000},
    },
    required=["command"],
    execute=run_shell,
    is_read_only=False,
)
