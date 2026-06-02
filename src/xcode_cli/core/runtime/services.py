"""Shared runtime service assembly for interactive agent UIs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from xcode_cli.core.config import ConfigStore
from xcode_cli.core.context import ContextManager
from xcode_cli.core.llm import LLMClient
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.planning import PlanMode, write_plan_file
from xcode_cli.core.project_root import resolve_project_root
from xcode_cli.core.prompting import build_system_prompt
from xcode_cli.core.runtime.controller import RuntimeController
from xcode_cli.core.session import SessionStore
from xcode_cli.core.task_tracker import TaskTracker, create_task_tools
from xcode_cli.core.tool_registry import ToolDef, ToolRegistry
from xcode_cli.core.tools import ALL_TOOLS
from xcode_cli.core.tools.agent_tool import create_dispatch_agent_tool
from xcode_cli.skills.manager import SkillManager


@dataclass
class RuntimeServices:
    """Container for services shared by terminal UI runtimes."""

    cwd: str
    config_store: ConfigStore
    llm_client: LLMClient
    skills: SkillManager
    task_tracker: TaskTracker
    memory: MemoryManager
    permissions: PermissionManager
    plan_mode: PlanMode
    context: ContextManager
    sessions: SessionStore
    session_id: str = ""
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)

    @classmethod
    def create(cls, cwd: str | None = None) -> "RuntimeServices":
        """Create runtime services using the same defaults as legacy chat."""
        resolved_cwd = str(resolve_project_root(cwd or os.getcwd()))
        config_store = ConfigStore()
        llm_client = LLMClient()
        cfg = config_store.load()
        sessions = SessionStore(cwd=resolved_cwd)
        services = cls(
            cwd=resolved_cwd,
            config_store=config_store,
            llm_client=llm_client,
            skills=SkillManager(),
            task_tracker=TaskTracker(),
            memory=MemoryManager(cwd=resolved_cwd),
            permissions=PermissionManager(cwd=resolved_cwd),
            plan_mode=PlanMode(),
            context=ContextManager(
                max_tokens=cfg.max_tokens,
                max_summary_chars=cfg.max_summary_chars,
            ),
            sessions=sessions,
            session_id=sessions.new_session_id(),
        )
        services._register_default_tools()
        return services

    def system_prompt(self) -> str:
        """Build the current system prompt from dynamic config and skills."""
        return build_system_prompt(self.config_store.load(), self.skills, self.cwd)

    def create_textual_controller(self, *, headless: bool = False) -> RuntimeController:
        """Create a RuntimeController wired to the shared services."""
        return RuntimeController(
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
            permission_manager=self.permissions,
            memory_manager=self.memory,
            task_tracker=self.task_tracker,
            session_store=self.sessions,
            context_manager=self.context,
            plan_mode=self.plan_mode,
            config_store=self.config_store,
            system_prompt_provider=self.system_prompt,
            session_id=self.session_id,
            headless=headless,
        )

    def _register_default_tools(self) -> None:
        """Register built-in tools and runtime tools."""
        for tool in ALL_TOOLS:
            self.tool_registry.register(tool)
        self.tool_registry.register(
            create_dispatch_agent_tool(self.llm_client, self.config_store)
        )
        for task_tool in create_task_tools(self.task_tracker):
            self.tool_registry.register(task_tool)
        for extra_tool in self._create_plan_tools():
            self.tool_registry.register(extra_tool)

    def _create_plan_tools(self) -> list[ToolDef]:
        """Create plan mode tools."""
        def write_plan(content: str) -> str:
            path = write_plan_file(content)
            self.plan_mode.plan_path = path
            return f"Plan written to: {path}"

        def exit_plan_mode(plan_summary: str) -> str:
            if not self.plan_mode.is_active:
                return "Error: not in planning mode"
            return self.plan_mode.exit(plan_summary)

        return [
            ToolDef(
                name="write_plan",
                description="Write plan markdown content to ~/.xcode/plans and return path.",
                parameters={
                    "content": {
                        "type": "string",
                        "description": "Full plan markdown content.",
                    }
                },
                required=["content"],
                execute=write_plan,
                is_read_only=False,
            ),
            ToolDef(
                name="exit_plan_mode",
                description="Finish planning and request user approval.",
                parameters={
                    "plan_summary": {
                        "type": "string",
                        "description": "Short summary of the plan.",
                    }
                },
                required=["plan_summary"],
                execute=exit_plan_mode,
                is_read_only=True,
            ),
        ]
