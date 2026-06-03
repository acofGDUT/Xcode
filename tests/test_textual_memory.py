"""Tests for Textual memory full migration (Tasks 1-6)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from xcode_cli.core.config import Config, ConfigStore
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.runtime.services import RuntimeServices
from xcode_cli.core.ui.commands import RunSlashCommandCommand, SubmitUserInputCommand
from xcode_cli.core.ui.events import (
    PermissionRequestEvent,
    SystemNoticeAdded,
    UICommandFailed,
    UserMessageAdded,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_memory_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create temp project and xcode_home with memory files.

    Returns (project_dir, xcode_home).
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    xcode_home = tmp_path / ".xcode"
    xcode_home.mkdir()

    # Project XCODE.md
    (project_dir / "XCODE.md").write_text(
        "# Project Memory\nUse tabs not spaces.\n", encoding="utf-8"
    )
    # User XCODE.md
    (xcode_home / "XCODE.md").write_text(
        "# User Profile\nPrefers Chinese.\n", encoding="utf-8"
    )
    # Auto memory index
    memory_dir = xcode_home / "projects" / project_dir.name / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text(
        "- [Test Memory](test.md) — a test entry\n", encoding="utf-8"
    )
    (memory_dir / "test.md").write_text(
        "---\nname: test\ndescription: test entry\n---\nTest content.\n",
        encoding="utf-8",
    )
    return project_dir, xcode_home


def _make_services(
    project_dir: Path,
    xcode_home: Path,
    *,
    auto_memory: bool = True,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> RuntimeServices:
    """Create RuntimeServices with temp paths."""
    if monkeypatch is not None:
        monkeypatch.setattr(
            "xcode_cli.paths.ensure_xcode_home", lambda: xcode_home
        )
        monkeypatch.setattr(
            "xcode_cli.core.memory.ensure_xcode_home", lambda: xcode_home
        )
        monkeypatch.setattr(
            "xcode_cli.core.config.ensure_xcode_home", lambda: xcode_home
        )

    # Write config with desired auto_memory to the expected location
    cfg = Config(auto_memory=auto_memory)
    config_store = ConfigStore()
    config_store.save(cfg)

    return RuntimeServices.create(cwd=str(project_dir))


def _make_controller_with_services(
    project_dir: Path,
    xcode_home: Path,
    *,
    auto_memory: bool = True,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> tuple[RuntimeController, RuntimeServices]:
    """Create controller and services with temp paths."""
    services = _make_services(
        project_dir, xcode_home, auto_memory=auto_memory, monkeypatch=monkeypatch
    )
    controller = services.create_textual_controller(headless=True)
    return controller, services


# ---------------------------------------------------------------------------
# Task 1: Textual system prompt memory parity
# ---------------------------------------------------------------------------


class TestSystemPromptMemoryParity:
    """Verify Textual path uses the same memory injection as legacy."""

    def test_system_prompt_includes_resolved_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(project_dir, xcode_home, monkeypatch=monkeypatch)

        prompt = services.system_prompt()

        assert "Resolved memory paths for this project" in prompt
        assert str(project_dir / "XCODE.md") in prompt
        assert str(xcode_home / "XCODE.md") in prompt
        assert "Auto memory dir:" in prompt
        assert "Auto memory index:" in prompt

    def test_system_prompt_includes_project_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(project_dir, xcode_home, monkeypatch=monkeypatch)

        prompt = services.system_prompt()

        assert "## Project Memory (XCODE.md)" in prompt
        assert "Use tabs not spaces" in prompt

    def test_system_prompt_includes_user_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(project_dir, xcode_home, monkeypatch=monkeypatch)

        prompt = services.system_prompt()

        assert "## User Memory (XCODE.md)" in prompt
        assert "Prefers Chinese" in prompt

    def test_system_prompt_includes_auto_memory_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(
            project_dir, xcode_home, auto_memory=True, monkeypatch=monkeypatch
        )

        prompt = services.system_prompt()

        assert "## Auto Memory Index" in prompt
        assert "Test Memory" in prompt

    def test_system_prompt_excludes_auto_memory_index_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(
            project_dir, xcode_home, auto_memory=False, monkeypatch=monkeypatch
        )

        prompt = services.system_prompt()

        # Project/User memory still present
        assert "## Project Memory (XCODE.md)" in prompt
        assert "## User Memory (XCODE.md)" in prompt
        # Auto memory index NOT present
        assert "## Auto Memory Index" not in prompt
        assert "Test Memory" not in prompt

    def test_controller_system_prompt_includes_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When controller submits a turn, the system_prompt_provider includes memory."""
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )
        # The system_prompt_provider is set; invoke it
        prompt = controller._system_prompt_provider()

        assert "## Project Memory (XCODE.md)" in prompt
        assert "## User Memory (XCODE.md)" in prompt
        assert "Resolved memory paths" in prompt


# ---------------------------------------------------------------------------
# Task 2: Textual tool registry memory tool exposure
# ---------------------------------------------------------------------------


class TestToolRegistryMemoryTools:
    """Verify Textual path exposes file tools, not memory CRUD."""

    def test_tool_registry_exposes_file_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(project_dir, xcode_home, monkeypatch=monkeypatch)

        tool_names = services.tool_registry.list_names()

        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit_file" in tool_names

    def test_tool_registry_no_memory_crud(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(project_dir, xcode_home, monkeypatch=monkeypatch)

        tool_names = services.tool_registry.list_names()

        for forbidden in ("memory_save", "memory_list", "memory_get", "memory_delete"):
            assert forbidden not in tool_names, f"{forbidden} should not be registered"


# ---------------------------------------------------------------------------
# Task 3: Textual memory permission parity
# ---------------------------------------------------------------------------


class TestMemoryPermissions:
    """Verify memory-scoped auto-allow, explicit deny wins, ordinary file asks."""

    def test_memory_write_auto_allow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """write_file targeting memory path skips approval."""
        from xcode_cli.core.runtime.cancellation import CancellationToken

        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, services = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )
        memory_target = str(project_dir / "XCODE.md")

        # Register a fake write_file that records invocation
        executed = []
        from xcode_cli.core.tool_registry import ToolDef

        def fake_write_file(path: str, content: str, append: bool = False) -> str:
            executed.append(path)
            return "OK"

        services.tool_registry.register(
            ToolDef(
                name="write_file",
                description="Write file.",
                parameters={"path": {"type": "string"}, "content": {"type": "string"}},
                required=["path", "content"],
                execute=fake_write_file,
                is_read_only=False,
            )
        )

        # Simulate a tool call in the controller's execute path
        from xcode_cli.core.llm import ToolCall

        tc = ToolCall(
            id="tc_1",
            name="write_file",
            args={"path": memory_target, "content": "new content"},
        )
        results = controller._execute_tools_in_turn(
            [tc], turn_id="turn_1", cancellation=CancellationToken()
        )

        # Tool should execute without permission request
        assert len(executed) == 1
        assert executed[0] == memory_target

    def test_explicit_deny_wins_over_memory_auto_allow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit session deny blocks memory write."""
        from xcode_cli.core.runtime.cancellation import CancellationToken

        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, services = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )
        memory_target = str(project_dir / "XCODE.md")

        from xcode_cli.core.tool_registry import ToolDef

        executed = []

        def fake_write_file(path: str, content: str, append: bool = False) -> str:
            executed.append(path)
            return "OK"

        services.tool_registry.register(
            ToolDef(
                name="write_file",
                description="Write file.",
                parameters={"path": {"type": "string"}, "content": {"type": "string"}},
                required=["path", "content"],
                execute=fake_write_file,
                is_read_only=False,
            )
        )

        # Set explicit deny
        controller._permission_manager.set_session_rule("write_file", "deny")

        from xcode_cli.core.llm import ToolCall

        tc = ToolCall(
            id="tc_2",
            name="write_file",
            args={"path": memory_target, "content": "new content"},
        )
        results = controller._execute_tools_in_turn(
            [tc], turn_id="turn_2", cancellation=CancellationToken()
        )

        # Tool should NOT execute
        assert len(executed) == 0
        assert any("denied" in r[1].lower() for r in results)

    def test_ordinary_file_still_requires_approval(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """write_file targeting a non-memory path emits permission request."""
        from xcode_cli.core.runtime.cancellation import CancellationTokenSource

        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, services = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )
        ordinary_target = str(project_dir / "main.py")

        from xcode_cli.core.tool_registry import ToolDef

        executed = []

        def fake_write_file(path: str, content: str, append: bool = False) -> str:
            executed.append(path)
            return "OK"

        services.tool_registry.register(
            ToolDef(
                name="write_file",
                description="Write file.",
                parameters={"path": {"type": "string"}, "content": {"type": "string"}},
                required=["path", "content"],
                execute=fake_write_file,
                is_read_only=False,
            )
        )

        from xcode_cli.core.llm import ToolCall

        tc = ToolCall(
            id="tc_3",
            name="write_file",
            args={"path": ordinary_target, "content": "print('hi')"},
        )

        cancellation = CancellationTokenSource()
        result_holder: list[Any] = []

        def worker() -> None:
            result_holder.extend(
                controller._execute_tools_in_turn(
                    [tc], turn_id="turn_3", cancellation=cancellation.token
                )
            )

        thread = threading.Thread(target=worker)
        thread.start()
        try:
            deadline = time.time() + 2
            permission_events = []
            while time.time() < deadline:
                events = controller.drain_events()
                permission_events.extend(
                    event for event in events if isinstance(event, PermissionRequestEvent)
                )
                if permission_events:
                    break
                time.sleep(0.01)

            assert permission_events
            assert permission_events[0].tool_name == "write_file"
            assert permission_events[0].tool_call_id == "tc_3"
            assert len(executed) == 0
        finally:
            cancellation.cancel()
            thread.join(timeout=1)

        assert not thread.is_alive()
        assert len(executed) == 0
        assert result_holder
        assert "denied" in result_holder[0][1].lower()


# ---------------------------------------------------------------------------
# Task 4: /memory slash parity
# ---------------------------------------------------------------------------


class TestMemorySlashParity:
    """Verify /memory shows full status and supports auto on|off."""

    def test_memory_shows_full_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory"))
        events = controller.drain_events()
        notice = next(e for e in events if isinstance(e, SystemNoticeAdded))

        assert "auto_memory: on" in notice.content
        assert "project_memory:" in notice.content
        assert "user_memory:" in notice.content

    def test_memory_auto_off(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory auto off"))
        events = controller.drain_events()

        # Should have a notice about the change
        notices = [e for e in events if isinstance(e, SystemNoticeAdded)]
        assert any("off" in n.content.lower() for n in notices)

        # Config should be persisted
        cfg = controller._config_store.load()
        assert cfg.auto_memory is False

    def test_memory_auto_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, auto_memory=False, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory auto on"))
        events = controller.drain_events()

        notices = [e for e in events if isinstance(e, SystemNoticeAdded)]
        assert any("on" in n.content.lower() for n in notices)

        cfg = controller._config_store.load()
        assert cfg.auto_memory is True

    def test_memory_auto_invalid_arg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory auto maybe"))
        events = controller.drain_events()

        notices = [e for e in events if isinstance(e, SystemNoticeAdded)]
        # Should show usage hint
        assert any("usage" in n.content.lower() or "auto" in n.content.lower() for n in notices)

    def test_memory_status_reflects_exists_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Memory status shows exists/missing for project/user memory."""
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory"))
        events = controller.drain_events()
        notice = next(e for e in events if isinstance(e, SystemNoticeAdded))

        # Both exist in setup
        assert "exists" in notice.content.lower()

    def test_memory_status_shows_files_and_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Memory status shows file count and index entries."""
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory"))
        events = controller.drain_events()
        notice = next(e for e in events if isinstance(e, SystemNoticeAdded))

        # Should mention memory files and index entries
        assert "memory files:" in notice.content.lower() or "files:" in notice.content.lower()


# ---------------------------------------------------------------------------
# Task 5: Write memory then next prompt reflects it
# ---------------------------------------------------------------------------


class TestWriteMemoryThenPrompt:
    """Verify write_file to memory target → next system_prompt includes it."""

    def test_write_memory_then_prompt_includes_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(project_dir, xcode_home, monkeypatch=monkeypatch)

        marker = "textual-memory-marker-xyz"

        # Write to project XCODE.md
        (project_dir / "XCODE.md").write_text(
            f"# Project\n{marker}\n", encoding="utf-8"
        )

        # Next system prompt should include the marker
        prompt = services.system_prompt()
        assert marker in prompt

    def test_write_auto_memory_then_prompt_includes_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(
            project_dir, xcode_home, auto_memory=True, monkeypatch=monkeypatch
        )

        marker = "auto-memory-marker-abc"
        memory_dir = xcode_home / "projects" / project_dir.name / "memory"
        (memory_dir / "MEMORY.md").write_text(
            f"- [Marker Entry](marker.md) — {marker}\n", encoding="utf-8"
        )

        prompt = services.system_prompt()
        assert marker in prompt

    def test_write_auto_memory_disabled_then_prompt_excludes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        services = _make_services(
            project_dir, xcode_home, auto_memory=False, monkeypatch=monkeypatch
        )

        marker = "should-not-appear"
        memory_dir = xcode_home / "projects" / project_dir.name / "memory"
        (memory_dir / "MEMORY.md").write_text(
            f"- [Marker](marker.md) — {marker}\n", encoding="utf-8"
        )

        prompt = services.system_prompt()
        assert marker not in prompt


# ---------------------------------------------------------------------------
# Task 6: /memory auto affects subsequent prompt
# ---------------------------------------------------------------------------


class TestMemoryAutoAffectsPrompt:
    """Verify /memory auto on|off actually changes prompt injection."""

    def test_auto_off_excludes_auto_memory_from_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, services = _make_controller_with_services(
            project_dir, xcode_home, auto_memory=True, monkeypatch=monkeypatch
        )

        # Initially included
        prompt_before = services.system_prompt()
        assert "## Auto Memory Index" in prompt_before

        # Toggle off
        controller.dispatch(RunSlashCommandCommand(raw="/memory auto off"))
        controller.drain_events()

        # Now system prompt should exclude auto memory
        prompt_after = services.system_prompt()
        assert "## Auto Memory Index" not in prompt_after
        # Project/User memory still present
        assert "## Project Memory (XCODE.md)" in prompt_after

    def test_auto_on_includes_auto_memory_in_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, services = _make_controller_with_services(
            project_dir, xcode_home, auto_memory=False, monkeypatch=monkeypatch
        )

        # Initially excluded
        prompt_before = services.system_prompt()
        assert "## Auto Memory Index" not in prompt_before

        # Toggle on
        controller.dispatch(RunSlashCommandCommand(raw="/memory auto on"))
        controller.drain_events()

        # Now system prompt should include auto memory
        prompt_after = services.system_prompt()
        assert "## Auto Memory Index" in prompt_after

    def test_memory_status_reflects_auto_toggle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After /memory auto off, /memory shows 'off'."""
        project_dir, xcode_home = _setup_memory_files(tmp_path)
        controller, _ = _make_controller_with_services(
            project_dir, xcode_home, auto_memory=True, monkeypatch=monkeypatch
        )

        controller.dispatch(RunSlashCommandCommand(raw="/memory auto off"))
        controller.drain_events()

        controller.dispatch(RunSlashCommandCommand(raw="/memory"))
        events = controller.drain_events()
        notice = next(e for e in events if isinstance(e, SystemNoticeAdded))

        assert "off" in notice.content.lower()
