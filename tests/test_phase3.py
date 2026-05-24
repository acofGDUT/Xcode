from pathlib import Path

from xcode_cli.core.config import Config
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.planning import PlanMode


def test_plan_mode_state_transitions() -> None:
    mode = PlanMode()
    assert mode.enter() == "已进入计划模式。"
    assert mode.is_active is True

    msg = mode.exit("summary")
    assert "等待用户审批" in msg
    assert mode.pending_approval is True

    assert "批准" in mode.approve()
    assert mode.is_active is False
    assert mode.pending_approval is False


def test_memory_xcode_md_context_and_auto_memory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)

    mm = MemoryManager(cwd=str(project_root))
    mm.write_project_memory("project rule")
    mm.write_user_memory("user preference")

    ctx = mm.get_context_for_prompt(Config(auto_memory=False))
    assert "## Project Memory (XCODE.md)" in ctx
    assert "project rule" in ctx
    assert "## User Memory (XCODE.md)" in ctx
    assert "user preference" in ctx
    assert "## Auto Memory" not in ctx

    mm.save_auto_memory("auto learned")
    ctx_with_auto = mm.get_context_for_prompt(Config(auto_memory=True))
    assert "## Auto Memory" in ctx_with_auto
    assert "auto learned" in ctx_with_auto
