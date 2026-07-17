from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

from xcode_cli.core.agent_types import AgentType
from xcode_cli.core.shell_tasks import ShellTaskManager
from xcode_cli.core.sub_agent import SubAgentExecutor
from xcode_cli.core.tools.shell import create_shell_tools, run_shell


def _python_command(code: str) -> str:
    args = [sys.executable, "-u", "-c", code]
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def test_run_shell_fast_command_preserves_text_contract() -> None:
    result = run_shell(_python_command("print('ok')"), timeout=5000)


    assert result == "ok\nexit_code=0"


def test_run_shell_one_shot_timeout_is_bounded() -> None:
    started = time.monotonic()
    result = run_shell(_python_command("import time; time.sleep(30)"), timeout=50)

    assert result == "Error: command timed out after 50ms"
    assert time.monotonic() - started < 3.0


def test_create_shell_tools_exposes_background_protocol_and_permissions(tmp_path: Path) -> None:
    manager = ShellTaskManager(base_dir=tmp_path / "shell-tasks")
    try:
        tools = {tool.name: tool for tool in create_shell_tools(manager)}

        assert set(tools) == {
            "run_shell",
            "shell_task_output",
            "shell_task_list",
            "shell_task_stop",
        }
        assert tools["run_shell"].parameters["run_in_background"]["type"] == "boolean"
        assert tools["run_shell"].parameters["run_in_background"]["default"] is False
        assert tools["run_shell"].is_read_only is False
        assert tools["shell_task_output"].is_read_only is True
        assert tools["shell_task_list"].is_read_only is True
        assert tools["shell_task_stop"].is_read_only is False
    finally:
        manager.shutdown()


def test_background_tool_returns_task_id_and_management_tools_work(tmp_path: Path) -> None:
    manager = ShellTaskManager(base_dir=tmp_path / "shell-tasks")
    try:
        tools = {tool.name: tool for tool in create_shell_tools(manager)}
        result = tools["run_shell"].execute(
            command=_python_command("import time; print('ready', flush=True); time.sleep(30)"),
            run_in_background=True,
        )
        task_id = manager.list_tasks()[0].task_id

        assert f"task_id={task_id}" in result
        assert "background_reason=explicit" in result
        assert task_id in tools["shell_task_list"].execute()
        assert task_id in tools["shell_task_output"].execute(task_id=task_id)
        assert "status=stopped" in tools["shell_task_stop"].execute(task_id=task_id)
    finally:
        manager.shutdown()


def test_task_tool_unknown_id_returns_error(tmp_path: Path) -> None:
    manager = ShellTaskManager(base_dir=tmp_path / "shell-tasks")
    try:
        tools = {tool.name: tool for tool in create_shell_tools(manager)}

        assert tools["shell_task_output"].execute(task_id="missing").startswith("Error:")
        assert tools["shell_task_stop"].execute(task_id="missing").startswith("Error:")
    finally:
        manager.shutdown()


def test_general_sub_agent_does_not_receive_background_task_tools() -> None:
    executor = SubAgentExecutor(
        agent_type=AgentType.GENERAL,
        llm_client=MagicMock(),
        config_store=MagicMock(),
    )

    names = set(executor.tools.list_names())
    run_shell_schema = next(
        schema["function"]
        for schema in executor.tools.get_openai_schemas()
        if schema["function"]["name"] == "run_shell"
    )

    assert "run_shell" in names
    assert "run_in_background" not in run_shell_schema["parameters"]["properties"]
    assert {"shell_task_output", "shell_task_list", "shell_task_stop"}.isdisjoint(names)
