from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from xcode_cli.core.permissions import PermissionManager
from xcode_cli.ui.renderer import OutputRenderer

from xcode_cli.core.bootstrap import ensure_ripgrep_installed
from xcode_cli.core.config import ConfigStore
from xcode_cli.core.context import ContextManager
from xcode_cli.core.dashboard import Dashboard
from xcode_cli.core.llm import LLMClient
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.planning import PlanMode, write_plan_file
from xcode_cli.core.prompting import build_system_prompt
from xcode_cli.core.project_root import resolve_project_root
from xcode_cli.core.runtime_status import RuntimeStatusStore
from xcode_cli.core.session import SessionStore
from xcode_cli.core.session_resume import SessionResumeBuilder
from xcode_cli.core.task_tracker import TaskTracker, create_task_tools
from xcode_cli.core.tool_registry import ToolDef, ToolRegistry
from xcode_cli.core.tools import ALL_TOOLS
from xcode_cli.core.tools.agent_tool import create_dispatch_agent_tool
from xcode_cli.skills.manager import SkillManager


COMMANDS = {
    "/help": "Show available commands",
    "/context": "Show token usage and context budget",
    "/dashboard": "Open API configuration dashboard",
    "/skill": "Manage skills (list/install/enable/disable)",
    "/env": "Manage API env for current process",
    "/plan": "Plan mode controls (enter/show/approve/reject)",
    "/memory": "Memory status and auto-memory toggle",
    "/resume": "List and resume previous sessions",
    "/compact": "Compress current conversation context",
    "/exit": "Exit chat",
}


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        if text.startswith("/dashboard"):
            yield Completion(
                "/dashboard",
                start_position=-len(text),
                display="/dashboard — Open API configuration dashboard",
            )
            return

        if text.startswith("/skill"):
            for cmd, desc in [
                ("/skill list", "List installed skills"),
                ("/skill install ", "Install skill from local path"),
                ("/skill enable ", "Enable an installed skill"),
                ("/skill disable ", "Disable an installed skill"),
            ]:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")
            return

        if text.startswith("/env"):
            for cmd, desc in [
                ("/env show", "Show current API key status"),
                ("/env set ", "Set and persist API key"),
                ("/env unset", "Unset API key from process and config"),
                ("/env base-url ", "Set provider base URL"),
                ("/env model ", "Set model name"),
                ("/env theme ", "Set syntax highlight theme"),
                ("/env max-tokens ", "Set max token budget for context compression"),
                ("/env edit", "Open ~/.xcode/config.json in default editor"),
            ]:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")
            return

        if text.startswith("/resume"):
            yield Completion("/resume", start_position=-len(text), display="/resume — List and resume previous sessions")
            return

        if text.startswith("/compact"):
            yield Completion("/compact", start_position=-len(text), display="/compact — Compress current conversation context")
            return

        for cmd, desc in COMMANDS.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")


class AgentRuntime:
    def __init__(self) -> None:
        self.console = Console()
        self.cwd = str(resolve_project_root(os.getcwd()))
        self.sessions = SessionStore(cwd=self.cwd)
        self._runtime_status = RuntimeStatusStore()
        self.skills = SkillManager()
        self.config_store = ConfigStore()
        self.llm = LLMClient()
        cfg = self.config_store.load()
        self.context = ContextManager(max_tokens=cfg.max_tokens)
        self.task_tracker = TaskTracker()
        self.memory = MemoryManager(cwd=self.cwd)
        self.permissions = PermissionManager(cwd=self.cwd)
        self.plan_mode = PlanMode()
        self._session_start = time.monotonic()
        self._tool_call_count = 0
        self._estimated_tokens = 0
        self._history: list[dict[str, Any]] = []
        self._session_id: str = ""
        self._session_auto_approve: dict[str, bool] = {"write": False, "shell": False}
        self.tools = ToolRegistry()
        for t in ALL_TOOLS:
            self.tools.register(t)
        self.tools.register(create_dispatch_agent_tool(self.llm, self.config_store))
        for task_tool in create_task_tools(self.task_tracker):
            self.tools.register(task_tool)
        for extra_tool in self._create_plan_memory_tools():
            self.tools.register(extra_tool)
        self.prompt = PromptSession(completer=SlashCompleter(), auto_suggest=AutoSuggestFromHistory())

    def run_chat(self) -> None:
        self._session_id = self.sessions.new_session_id()
        self._runtime_status.create(self._session_id, self.cwd)
        self._render_welcome()

        self._history: list[dict[str, Any]] = []

        try:
            while True:
                user_input = self.prompt.prompt(ANSI("\x1b[96myou\x1b[0m ▸ "), bottom_toolbar=self._bottom_toolbar).strip()
                if not user_input:
                    continue
                if user_input in {"/exit", "exit", "quit"}:
                    self.console.print("Goodbye.")
                    break

                if user_input == "/":
                    self._show_command_suggestions()
                    continue

                if user_input.startswith("/"):
                    self._handle_slash_command(user_input)
                    continue

                if self.plan_mode.pending_approval and self._handle_plan_approval_input(user_input):
                    continue

                self.sessions.append_message(self._session_id, {"role": "user", "content": user_input})
                self.sessions.append_user_history(self._session_id, user_input)
                self._print_user_bubble(user_input)
                self._history.append({"role": "user", "content": user_input})

                if self.plan_mode.is_active:
                    system_prompt = self.plan_mode.get_system_prompt()
                else:
                    system_prompt = build_system_prompt(self.config_store.load(), self.skills, self.cwd)

                self._runtime_status.update("busy")
                try:
                    final_text = self._run_llm_loop(history=self._history, system_prompt=system_prompt)
                finally:
                    self._runtime_status.update("idle")

                is_llm_error = final_text.startswith("[v0] LLM request failed:")
                is_missing_key = final_text.startswith("[v0] Missing API key")
                is_missing_pkg = final_text.startswith("[v0] openai package not installed")

                if is_llm_error or is_missing_key or is_missing_pkg:
                    self.console.print(f"[bold red]{final_text}[/bold red]")
                    continue

                self.sessions.append_message(self._session_id, {"role": "assistant", "content": final_text})
                self._history.append({"role": "assistant", "content": final_text})

                if self.plan_mode.pending_approval:
                    self._show_plan_and_ask_approval()
        finally:
            self._runtime_status.delete()

    def _render_welcome(self) -> None:
        ensure_ripgrep_installed()

        cfg = self.config_store.load()
        enabled = ", ".join(cfg.enabled_skills) if cfg.enabled_skills else "none"
        has_key = bool(cfg.api_key or os.getenv("XCODE_API_KEY") or os.getenv("OPENAI_API_KEY"))
        key_state = "ready" if has_key else "missing-key"

        self.console.print("[bold]Xcode[/bold] v0.1.0  /\\_/\\")
        self.console.print("terminal-native AI agent  (•.•)")
        self.console.print(f"[dim]Skills:[/dim] {enabled} | [dim]API:[/dim] {key_state} | [dim]Project:[/dim] {self.cwd}")
        self.console.print("[dim]Type normally to chat · / for commands · Tab to complete[/dim]")

    def _show_command_suggestions(self) -> None:
        table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
        table.add_column("Command", style="green")
        table.add_column("Description", style="white")
        table.add_row("/help", "Show available commands")
        table.add_row("/context", "Show token usage and context budget")
        table.add_row("/dashboard", "Open API configuration dashboard")
        table.add_row("/skill", "Manage skills")
        table.add_row("/env", "Configure API and model settings")
        table.add_row("/memory", "Show memory status and toggle auto-memory")
        table.add_row("/exit", "Exit chat")
        self.console.print(Panel(table, title="Slash Commands", border_style="cyan"))

    def _bottom_toolbar(self) -> str:
        cfg = self.config_store.load()
        model = cfg.model or os.getenv("XCODE_MODEL", "gpt-4o-mini")
        has_key = bool(cfg.api_key or os.getenv("XCODE_API_KEY") or os.getenv("OPENAI_API_KEY"))
        api = "ready" if has_key else "missing-key"
        elapsed = int(time.monotonic() - self._session_start)
        minutes, seconds = divmod(elapsed, 60)
        session_str = f"{minutes}m{seconds}s" if minutes else f"{seconds}s"
        tok_k = self._estimated_tokens // 1000 if self._estimated_tokens else 0
        max_tok_k = max((cfg.max_tokens or 0) // 1000, 1)
        return f" {model} | tokens≈{tok_k}k/{max_tok_k}k | tools:{self._tool_call_count} | session {session_str} | {api} "

    def _print_user_bubble(self, text: str) -> None:
        self.console.print(f"[dim]▸ {text}[/dim]")

    def _print_assistant_bubble(self, text: str) -> None:
        OutputRenderer.render(self.console, text, syntax_theme=self.config_store.load().syntax_theme)

    def _handle_slash_command(self, command: str) -> None:
        parts = command.split()
        head = parts[0].lower()

        if head == "/help":
            self._show_command_suggestions()
            self.console.print("/skill list|install <path>|enable <name>|disable <name>")
            self.console.print("/env show|set <api_key>|unset|base-url <url>|model <name>|theme <name>|max-tokens <value>")
            self.console.print("/context")
            self.console.print("/memory | /memory auto on|off")
            self.console.print("/dashboard")
            return

        if head == "/context":
            self._handle_context_command()
            return

        if head == "/dashboard":
            Dashboard().run()
            return

        if head == "/skill":
            self._handle_skill_command(parts)
            return

        if head == "/env":
            self._handle_env_command(parts)
            return

        if head == "/plan":
            self._handle_plan_command(parts)
            return

        if head == "/memory":
            self._handle_memory_command(parts)
            return

        if head == "/resume":
            self._handle_resume_command()
            return

        if head == "/compact":
            self._handle_compact_command()
            return

        self.console.print(f"Unknown command: {command}. Try /help")

    def _handle_skill_command(self, parts: list[str]) -> None:
        if len(parts) == 1:
            self.console.print("/skill list | /skill install <path> | /skill enable <name> | /skill disable <name>")
            return
        action = parts[1].lower()
        if action == "list":
            cfg = self.config_store.load()
            enabled = set(cfg.enabled_skills)
            skills = self.skills.list_installed()
            if not skills:
                self.console.print("No skills installed.")
                return
            for s in skills:
                status = "enabled" if s.name in enabled else "disabled"
                self.console.print(f"- {s.name} [{status}] - {s.description}")
            return
        if action == "install" and len(parts) >= 3:
            installed = self.skills.install(" ".join(parts[2:]))
            self.console.print(f"Installed skill: [bold]{installed.name}[/bold] -> {installed.path}")
            return
        if action == "enable" and len(parts) >= 3:
            name = " ".join(parts[2:])
            cfg = self.config_store.load()
            if name not in cfg.enabled_skills:
                cfg.enabled_skills.append(name)
                self.config_store.save(cfg)
            self.console.print(f"Enabled skill: {name}")
            return
        if action == "disable" and len(parts) >= 3:
            name = " ".join(parts[2:])
            cfg = self.config_store.load()
            cfg.enabled_skills = [s for s in cfg.enabled_skills if s != name]
            self.config_store.save(cfg)
            self.console.print(f"Disabled skill: {name}")
            return
        self.console.print("Usage: /skill list|install <path>|enable <name>|disable <name>")

    def _handle_env_command(self, parts: list[str]) -> None:
        if len(parts) == 1:
            self.console.print(
                "/env show | /env set <api_key> | /env unset | /env base-url <url> | "
                "/env model <name> | /env theme <name> | /env max-tokens <value> | /env edit"
            )
            return
        action = parts[1].lower()
        if action == "show":
            cfg = self.config_store.load()
            key = os.getenv("XCODE_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not key:
                self.console.print("API key is not set.")
            else:
                masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "(set)"
                self.console.print(f"API key: {masked}")
            self.console.print(f"model: {cfg.model or os.getenv('XCODE_MODEL', 'gpt-4o-mini')}")
            self.console.print(f"base_url: {cfg.base_url or '(default)'}")
            self.console.print(f"max-tokens: {cfg.max_tokens}")
            self.console.print(f"syntax theme: {cfg.syntax_theme}")
            return
        if action == "set" and len(parts) >= 3:
            key = " ".join(parts[2:])
            cfg = self.config_store.load()
            cfg.api_key = key
            self.config_store.save(cfg)
            os.environ["XCODE_API_KEY"] = key
            self.console.print("API key saved and persisted.")
            self.console.print(f"Config file: {self.config_store.path}")
            return

        if action == "unset":
            cfg = self.config_store.load()
            cfg.api_key = ""
            self.config_store.save(cfg)
            os.environ.pop("XCODE_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            self.console.print("API key removed from process and config file.")
            self.console.print(f"Config file: {self.config_store.path}")
            return

        if action == "base-url" and len(parts) >= 3:
            cfg = self.config_store.load()
            cfg.base_url = " ".join(parts[2:])
            self.config_store.save(cfg)
            self.console.print(f"base_url saved to {self.config_store.path}")
            return

        if action == "model" and len(parts) >= 3:
            cfg = self.config_store.load()
            cfg.model = " ".join(parts[2:])
            self.config_store.save(cfg)
            self.console.print(f"model saved to {self.config_store.path}")
            return

        if action == "theme" and len(parts) >= 3:
            cfg = self.config_store.load()
            cfg.syntax_theme = " ".join(parts[2:]).strip() or "monokai"
            self.config_store.save(cfg)
            self.console.print(f"syntax theme saved to {self.config_store.path}")
            return

        if action == "max-tokens" and len(parts) >= 3:
            value_str = " ".join(parts[2:])
            try:
                value = int(value_str)
            except ValueError:
                self.console.print(f"[bold red]Invalid value: '{value_str}'. max-tokens must be a positive integer.[/bold red]")
                return
            if value <= 0:
                self.console.print(f"[bold red]Invalid value: {value}. max-tokens must be a positive integer.[/bold red]")
                return
            cfg = self.config_store.load()
            cfg.max_tokens = value
            self.config_store.save(cfg)
            self.context.max_tokens = value
            self.console.print(f"max-tokens set to {value} and saved to {self.config_store.path}")
            return

        if action == "edit":
            config_path = self.config_store.path
            self.console.print(f"Config file: {config_path}")
            try:
                if os.name == "nt":
                    os.startfile(str(config_path))  # type: ignore[attr-defined]
                elif os.name == "posix":
                    subprocess.Popen(["xdg-open", str(config_path)])
                else:
                    self.console.print("Auto-open is not supported on this OS. Open the file path manually.")
                    return
                self.console.print("Opened config file in your default editor.")
            except Exception as exc:
                self.console.print(f"Failed to open config file automatically: {exc}")
            return

        self.console.print("Usage: /env show|set <api_key>|unset|base-url <url>|model <name>|theme <name>|max-tokens <value>|edit")

    def _create_plan_memory_tools(self) -> list[ToolDef]:
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
                parameters={"content": {"type": "string", "description": "Full plan markdown content."}},
                required=["content"],
                execute=write_plan,
                is_read_only=False,
            ),
            ToolDef(
                name="exit_plan_mode",
                description="Finish planning and request user approval.",
                parameters={"plan_summary": {"type": "string", "description": "Short summary of the plan."}},
                required=["plan_summary"],
                execute=exit_plan_mode,
                is_read_only=True,
            ),
        ]

    def _handle_memory_command(self, parts: list[str]) -> None:
        cfg = self.config_store.load()
        if len(parts) == 1:
            auto_state = "on" if cfg.auto_memory else "off"
            project_path = self.memory.project_memory_path()
            user_path = self.memory.user_memory_path()
            project_state = "exists" if self.memory.has_project_memory() else "missing"
            user_state = "exists" if self.memory.has_user_memory() else "missing"

            self.console.print(f"Auto-memory: {auto_state}")
            self.console.print(f"Project memory: {project_path} ({project_state})")
            self.console.print(f"User memory: {user_path} ({user_state})")
            memory_files = list(self.memory.memory_dir_path().glob("*.md"))
            memory_index = self.memory.read_memory_index()
            index_entries = memory_index.count("\n") + 1 if memory_index else 0
            self.console.print(f"Memory dir: {self.memory.memory_dir_path()}")
            self.console.print(f"Memory files: {len(memory_files)} (index: {index_entries} entries)")
            return

        if len(parts) == 3 and parts[1].lower() == "auto" and parts[2].lower() in {"on", "off"}:
            value = parts[2].lower() == "on"
            cfg.auto_memory = value
            self.config_store.save(cfg)
            self.console.print(f"Auto-memory set to {'on' if value else 'off'}")
            return

        self.console.print("Usage: /memory | /memory auto on|off")

    def _handle_resume_command(self) -> None:
        sessions = self.sessions.list_sessions()
        if not sessions:
            self.console.print("No recent sessions found for this project.")
            return

        self.console.print("Recent sessions:")
        for i, s in enumerate(sessions, 1):
            ts = datetime.utcfromtimestamp(s.updated_at).strftime("%Y-%m-%d %H:%M")
            preview = s.last_user_input[:60] if s.last_user_input else "(empty)"
            cp_mark = " \\[checkpoint]" if s.has_checkpoint else ""
            self.console.print(f"  {i}. {s.session_id[:8]}...  {ts}  {preview}{cp_mark}")

        choice = self.prompt.prompt(
            ANSI("\x1b[96mSelect session number (empty to cancel)\x1b[0m ▸ ")
        ).strip()

        if not choice:
            self.console.print("Cancelled.")
            return

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(sessions):
                self.console.print("Invalid selection.")
                return
        except ValueError:
            self.console.print("Invalid selection.")
            return

        selected = sessions[idx]
        resume_budget = int(self.context.max_tokens * 0.6)
        builder = SessionResumeBuilder(self.context, resume_budget)
        result = builder.build(selected.path)
        if not result.history:
            self.console.print("Failed to load session history.")
            return

        self._history[:] = result.history
        self._session_id = selected.session_id
        self._runtime_status.update_session_id(selected.session_id)
        self.console.print(f"Resumed session {selected.session_id}")
        self.console.print(f"Restored from checkpoint: {'yes' if result.restored_from_checkpoint else 'no'}")
        self.console.print(f"Restored messages: {result.message_count}")
        self.console.print(f"Estimated context: ~{result.estimated_tokens} tokens")
        if selected.last_user_input:
            self.console.print(f"Latest user input: {selected.last_user_input[:100]}")

    @staticmethod
    def _find_previous_summary(history: list[dict[str, Any]]) -> str:
        for msg in reversed(history):
            if msg.get("role") == "system":
                content = str(msg.get("content", ""))
                if "Conversation summary checkpoint:" in content:
                    return content.split("Conversation summary checkpoint:\n", 1)[-1].strip()
        return ""

    def _handle_compact_command(self) -> None:
        if len(self._history) < 4:
            self.console.print("Nothing to compact.")
            return

        before_messages = len(self._history)
        before_tokens = self.context.estimate_tokens(self._history)
        previous_summary = self._find_previous_summary(self._history)
        result = self.context.compress(self._history, self.llm, previous_summary)

        if not result.checkpoint_message:
            self.console.print("Nothing to compact.")
            return

        after_messages = len(result.messages)
        after_tokens = self.context.estimate_tokens(result.messages)
        self._history[:] = result.messages
        saved_tokens = max(before_tokens - after_tokens, 0)

        self.sessions.append_message(self._session_id, result.checkpoint_message)
        self.sessions.append_event(self._session_id, {
            "type": "compaction_checkpoint",
            "summary": result.summary,
            "summary_format": "xcode.v1",
            "source_message_count": before_messages,
            "source_token_estimate": before_tokens,
            "remaining_message_count": after_messages,
        })

        self.console.print(
            f"[dim]Context compacted: {before_messages} -> {after_messages} messages, "
            f"saved ~{saved_tokens} tokens.[/dim]"
        )

    def _handle_plan_command(self, parts: list[str]) -> None:
        if len(parts) == 1:
            self.console.print("/plan enter | /plan show | /plan approve | /plan reject")
            return
        action = parts[1].lower()
        if action == "enter":
            msg = self.plan_mode.enter()
            self.console.print(msg)
            return
        if action == "show":
            if not self.plan_mode.plan_path:
                self.console.print("当前还没有计划文件。")
                return
            self.console.print(f"当前计划文件: {self.plan_mode.plan_path}")
            return
        if action == "approve":
            self.console.print(self.plan_mode.approve())
            return
        if action == "reject":
            self.console.print(self.plan_mode.reject())
            return
        self.console.print("Usage: /plan enter|show|approve|reject")

    def _show_plan_and_ask_approval(self) -> None:
        summary = self.plan_mode.plan_summary or "(无摘要)"
        self.console.print("\n[bold cyan]计划已生成，等待审批[/bold cyan]")
        if self.plan_mode.plan_path:
            self.console.print(f"计划文件: {self.plan_mode.plan_path}")
        self.console.print(f"摘要: {summary}")
        self.console.print("可先编辑计划文件后再确认，或直接输入：approve / reject")

    def _handle_plan_approval_input(self, user_input: str) -> bool:
        normalized = user_input.strip().lower()
        approve_set = {"approve", "同意", "批准", "通过", "/plan approve"}
        reject_set = {"reject", "拒绝", "驳回", "/plan reject"}

        if normalized in approve_set:
            self.console.print(self.plan_mode.approve())
            return True
        if normalized in reject_set:
            self.console.print(self.plan_mode.reject())
            return True
        return False

    def _current_system_prompt(self) -> str:
        if self.plan_mode.is_active:
            return self.plan_mode.get_system_prompt()
        return build_system_prompt(self.config_store.load(), self.skills, self.cwd)

    def _handle_context_command(self) -> None:
        cfg = self.config_store.load()
        system_prompt = self._current_system_prompt()
        system_message = {"role": "system", "content": system_prompt}
        system_tokens = self.context.estimate_tokens([system_message])
        role_groups: dict[str, list[dict[str, Any]]] = {
            "user": [],
            "assistant": [],
            "tool": [],
            "system": [],
            "other": [],
        }
        for message in self._history:
            role = str(message.get("role", "other"))
            if role not in role_groups:
                role = "other"
            role_groups[role].append(message)

        role_tokens = {role: self.context.estimate_tokens(messages) for role, messages in role_groups.items()}
        history_tokens = sum(role_tokens.values())
        total_tokens = system_tokens + history_tokens
        max_tokens = self.context.max_tokens
        remaining_tokens = max(max_tokens - total_tokens, 0)
        compression_threshold = int(self.context.max_tokens * 0.8)

        table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
        table.add_column("Item", style="green")
        table.add_column("Value", style="white")
        table.add_row("model", cfg.model or os.getenv("XCODE_MODEL", "gpt-4o-mini"))
        table.add_row("max tokens", str(max_tokens))
        table.add_row("render mode", cfg.response_render_mode)
        table.add_row("syntax theme", cfg.syntax_theme)
        table.add_row("messages", str(len(self._history)))
        table.add_row("system prompt", f"~{system_tokens} tokens")
        table.add_row("user", f"{len(role_groups['user'])} msg / ~{role_tokens['user']} tokens")
        table.add_row("assistant", f"{len(role_groups['assistant'])} msg / ~{role_tokens['assistant']} tokens")
        table.add_row("tool", f"{len(role_groups['tool'])} msg / ~{role_tokens['tool']} tokens")
        if role_groups["system"]:
            table.add_row("history system", f"{len(role_groups['system'])} msg / ~{role_tokens['system']} tokens")
        if role_groups["other"]:
            table.add_row("other", f"{len(role_groups['other'])} msg / ~{role_tokens['other']} tokens")
        table.add_row("chat history", f"~{history_tokens} tokens")
        table.add_row("total", f"~{total_tokens} / {max_tokens}")
        table.add_row("free", f"~{remaining_tokens}")
        table.add_row("compression threshold", f"~{compression_threshold}")
        table.add_row("auto-memory", "on" if cfg.auto_memory else "off")
        self.console.print(Panel(table, title="Context", border_style="cyan"))

    def _render_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        self.console.print(f"  [bold cyan]## tool.{tool_name}[/bold cyan]")
        for key, value in args.items():
            val_str = str(value)
            if len(val_str) > 120:
                val_str = val_str[:120] + "..."
            self.console.print(f"    [dim]{key}:[/dim] {val_str}")

    def _approval_scope_for_tool(self, tool_name: str) -> str | None:
        if tool_name in {"edit_file", "write_file"}:
            return "write"
        if tool_name == "run_shell":
            return "shell"
        return tool_name

    def _read_approval_key(self) -> str:
        if os.name == "nt":
            import msvcrt

            ch = msvcrt.getwch()
            if ch in {"\x00", "\xe0"}:
                second = msvcrt.getwch()
                if second == "H":
                    return "up"
                if second == "P":
                    return "down"
                return ""
            if ch == "\r":
                return "enter"
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch.lower()

        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                rest = sys.stdin.read(2)
                if rest == "[A":
                    return "up"
                if rest == "[B":
                    return "down"
                return "escape"
            if ch in {"\r", "\n"}:
                return "enter"
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _render_approval_options(self, tool_name: str, scope: str, selected: int) -> None:
        options = [
            "Yes",
            "No",
            "Yes, for this conversation",
        ]
        self.console.print(f"  [bold]Apply {tool_name} for {scope}?[/bold] [dim](↑/↓, Enter)[/dim]")
        for idx, label in enumerate(options):
            prefix = ">" if idx == selected else " "
            style = "bold cyan" if idx == selected else "dim"
            self.console.print(f"  {prefix} {label}", style=style)

    def _refresh_approval_options(self, tool_name: str, scope: str, selected: int) -> None:
        sys.stdout.write("\x1b[4A")
        for _ in range(4):
            sys.stdout.write("\x1b[2K")
            sys.stdout.write("\x1b[1B")
        sys.stdout.write("\x1b[4A")
        sys.stdout.flush()
        self._render_approval_options(tool_name, scope, selected)

    def _prompt_tool_approval(self, tool_name: str, scope: str | None) -> str:
        if scope and self._session_auto_approve.get(scope):
            return "yes"

        approval_scope = scope or tool_name
        if not sys.stdin.isatty():
            try:
                value = input(f"  Apply {tool_name} for {approval_scope}? [Y]es / [n]o / [a]ll: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "no"
            if not value or value in {"y", "yes"}:
                return "yes"
            if value in {"a", "all", "yes_all"}:
                return "yes_all"
            return "no"

        selected = 0
        try:
            self._render_approval_options(tool_name, approval_scope, selected)
            while True:
                key = self._read_approval_key()
                if key in {"up", "k"}:
                    selected = (selected - 1) % 3
                    self._refresh_approval_options(tool_name, approval_scope, selected)
                elif key in {"down", "j"}:
                    selected = (selected + 1) % 3
                    self._refresh_approval_options(tool_name, approval_scope, selected)
                elif key in {"enter", " "}:
                    self.console.print()
                    return ["yes", "no", "yes_all"][selected]
                elif key in {"y"}:
                    self.console.print()
                    return "yes"
                elif key in {"n", "escape"}:
                    self.console.print()
                    return "no"
                elif key in {"a"}:
                    self.console.print()
                    return "yes_all"
        except (EOFError, KeyboardInterrupt):
            return "no"

    def _render_assistant_prefix(self) -> None:
        self.console.print("[magenta]assistant[/magenta] ▸ ", end="")

    def _summarize_tool_result(self, tool_name: str, args: dict[str, Any], result: str) -> str:
        if result.startswith("Error:"):
            return result

        if tool_name == "read_file":
            line_count = len([line for line in result.splitlines() if line.strip()])
            return f"read {line_count} line(s)"
        if tool_name == "grep":
            if result.startswith("No matches found"):
                return "no matches"
            return f"found {len(result.splitlines())} match line(s)"
        if tool_name == "glob":
            if result.startswith("No files matched"):
                return "no files matched"
            return f"matched {len(result.splitlines())} file(s)"
        if tool_name == "run_shell":
            exit_line = next((line for line in reversed(result.splitlines()) if line.startswith("exit_code=")), "")
            return exit_line or "command finished"
        if tool_name == "edit_file":
            return result
        if tool_name == "write_file":
            path = args.get("path", "")
            action = "appended" if args.get("append") else "wrote"
            return f"{action} {path}"
        return f"done ({len(result)} chars)"

    def _run_llm_loop(self, history: list[dict[str, Any]], system_prompt: str) -> str:
        max_tool_rounds = 10
        cfg = self.config_store.load()
        render_mode = cfg.response_render_mode
        stream_text = render_mode == "streaming_plus_final_render"
        assistant_turn_started = False


        for _ in range(max_tool_rounds):
            if self.context.should_compress(history):
                before_messages = len(history)
                before_tokens = self.context.estimate_tokens(history)
                previous_summary = self._find_previous_summary(history)
                result = self.context.compress(history, self.llm, previous_summary)
                after_messages = len(result.messages)
                after_tokens = self.context.estimate_tokens(result.messages)
                history[:] = result.messages
                saved_tokens = max(before_tokens - after_tokens, 0)
                self.console.print(
                    f"[dim]Context compressed: {before_messages} -> {after_messages} messages, "
                    f"saved ~{saved_tokens} tokens.[/dim]"
                )
                if self._session_id and result.checkpoint_message:
                    self.sessions.append_message(self._session_id, result.checkpoint_message)
                    self.sessions.append_event(self._session_id, {
                        "type": "compaction_checkpoint",
                        "summary": result.summary,
                        "summary_format": "xcode.v1",
                        "source_message_count": before_messages,
                        "source_token_estimate": before_tokens,
                        "remaining_message_count": after_messages,
                    })

            content_buffer: list[str] = []
            reasoning_buffer: list[str] = []
            start_time = time.monotonic()
            first_text_token_elapsed_ms: float | None = None
            assistant_prefix_printed = False

            stream_state = {"fence_ticks": 0}
            thinking_stop = threading.Event()
            thinking_thread: threading.Thread | None = None
            thinking_live = Live(
                Text("Thinking (0.0s)...", style="dim"),
                console=self.console,
                refresh_per_second=8,
                transient=True,
            )
            thinking_stopped = False

            def thinking_loop() -> None:
                while not thinking_stop.is_set():
                    elapsed = time.monotonic() - start_time
                    thinking_live.update(Text(f"Thinking ({elapsed:.1f}s)...", style="dim"))
                    time.sleep(0.1)

            def stop_thinking() -> None:
                nonlocal thinking_stopped
                if thinking_stopped:
                    return
                thinking_stopped = True
                thinking_stop.set()
                if thinking_thread is not None:
                    thinking_thread.join(timeout=0.2)
                thinking_live.stop()

            def on_token(token: str) -> None:
                nonlocal first_text_token_elapsed_ms, assistant_prefix_printed, assistant_turn_started
                if first_text_token_elapsed_ms is None:
                    elapsed = time.monotonic() - start_time
                    first_text_token_elapsed_ms = elapsed * 1000
                    stop_thinking()
                content_buffer.append(token)
                if not stream_text:
                    return
                if not assistant_prefix_printed:
                    if not assistant_turn_started:
                        self._render_assistant_prefix()
                        assistant_turn_started = True
                    assistant_prefix_printed = True
                for ch in token:
                    if ch == "`":
                        stream_state["fence_ticks"] += 1
                    else:
                        stream_state["fence_ticks"] = 0
                    if stream_state["fence_ticks"] >= 3:
                        stream_state["fence_ticks"] = 0
                    self.console.print(ch, end="", markup=False)

            def on_reasoning_token(token: str) -> None:
                reasoning_buffer.append(token)

            thinking_live.start()
            thinking_thread = threading.Thread(target=thinking_loop, daemon=True)
            thinking_thread.start()

            try:
                response = self.llm.complete(
                    system_prompt=system_prompt,
                    messages=history,
                    tool_schemas=self.tools.get_openai_schemas(),
                    on_text_token=on_token,
                    on_reasoning_token=on_reasoning_token,
                )
            except KeyboardInterrupt:
                stop_thinking()
                self.console.print("[dim]Interrupted.[/dim]")
                return "Interrupted."
            finally:
                stop_thinking()
            self._estimated_tokens = self.context.estimate_tokens(history)

            total_ms = (time.monotonic() - start_time) * 1000

            if content_buffer or reasoning_buffer:
                if stream_text:
                    self.console.print()
                first_text_ms = int(first_text_token_elapsed_ms or total_ms)
                response_ms = max(int(total_ms - first_text_ms), 0)
                self.console.print(f"[dim](思考 {first_text_ms}ms / 回复 {response_ms}ms)[/dim]")

            if not response.tool_calls:
                final_text = response.content or ""
                if render_mode == "buffer_then_render":
                    if final_text:
                        self.console.print()
                        if not assistant_turn_started:
                            self._render_assistant_prefix()
                            assistant_turn_started = True
                        self._print_assistant_bubble(final_text)
                else:
                    if final_text and ("```" in final_text or "|" in final_text or "\n#" in final_text):
                        self.console.print()
                        if not assistant_turn_started:
                            self._render_assistant_prefix()
                            assistant_turn_started = True
                        self._print_assistant_bubble(final_text)
                return final_text

            executed_calls: list[tuple[Any, str]] = []
            for tc in response.tool_calls:
                self._render_tool_call(tc.name, tc.args)

                level = self.permissions.check(tc.name)
                if level == "deny":
                    result = f"Permission denied for tool: {tc.name}"
                    self.console.print(f"  [bold red]{result}[/bold red]")
                    executed_calls.append((tc, result))
                    continue

                scope = self._approval_scope_for_tool(tc.name)

                if tc.name in {"edit_file", "write_file"}:
                    file_path = str(tc.args.get("path", ""))
                    old_text = ""
                    if file_path:
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                old_text = f.read()
                        except (FileNotFoundError, OSError):
                            old_text = ""

                    if tc.name == "write_file":
                        new_text = str(tc.args.get("content", ""))
                    else:
                        old_string = str(tc.args.get("old_string", ""))
                        new_string = str(tc.args.get("new_string", ""))
                        replace_all = bool(tc.args.get("replace_all", False))
                        count = -1 if replace_all else 1
                        new_text = old_text.replace(old_string, new_string, count)

                    if file_path:
                        self.console.print("  [dim]Review: diff preview before approval[/dim]")
                        OutputRenderer.render_diff(
                            self.console,
                            old_text,
                            new_text,
                            file_path,
                            syntax_theme=self.config_store.load().syntax_theme,
                            line_numbers=True,
                        )

                if scope and self._session_auto_approve.get(scope):
                    self.console.print("  [dim]approval: auto-yes (this conversation)[/dim]")
                elif level == "ask":
                    if tc.name == "run_shell":
                        cmd = str(tc.args.get("command", ""))
                        self.console.print("  [dim]Review: command preview before approval[/dim]")
                        self.console.print(f"  [bold yellow]$ {cmd}[/bold yellow]")
                    approval = self._prompt_tool_approval(tc.name, scope)
                    if approval == "no":
                        result = f"User denied tool: {tc.name}"
                        self.console.print(f"  [dim]{result}[/dim]")
                        executed_calls.append((tc, result))
                        continue
                    if approval == "yes_all" and scope:
                        self._session_auto_approve[scope] = True

                try:
                    result = self.tools.execute(tc.name, tc.args)
                except KeyboardInterrupt:
                    self.console.print("  [dim]Interrupted.[/dim]")
                    result = "Error: user interrupted the operation"

                result_str = str(result)
                self._tool_call_count += 1
                if result_str.startswith("Error:"):
                    self.console.print(f"  [bold red]{result_str}[/bold red]")
                else:
                    summary = self._summarize_tool_result(tc.name, tc.args, result_str)
                    self.console.print(f"  [dim]→ {summary}[/dim]")

                executed_calls.append((tc, result_str))

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                    }
                    for tc, _ in executed_calls
                ],
            }
            if response.reasoning_content:
                assistant_msg["reasoning_content"] = response.reasoning_content
            history.append(assistant_msg)

            for tc, result in executed_calls:
                history.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            if self._session_id:
                self.sessions.append_message(self._session_id, assistant_msg)
                for tc, result in executed_calls:
                    self.sessions.append_message(self._session_id, {"role": "tool", "tool_call_id": tc.id, "content": result})

        return "Reached maximum tool call rounds."
