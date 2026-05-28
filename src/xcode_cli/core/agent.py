from __future__ import annotations

import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from xcode_cli.core.permissions import PermissionManager
from xcode_cli.core.commands.slash import SlashCompleter
from xcode_cli.core.config import ConfigStore
from xcode_cli.core.conversation.compaction import ConversationCompactor
from xcode_cli.core.conversation.resume import ResumeCommandService
from xcode_cli.core.tooling.approval import ToolApprovalController
from xcode_cli.core.tooling.display import ToolCallDisplay, ToolDisplayState
from xcode_cli.core.tooling.execution import ToolCallExecutor
from xcode_cli.core.ui.shell import ShellUI
from xcode_cli.core.ui.streaming import StreamingTurnRenderer
from xcode_cli.core.context import ContextManager
from xcode_cli.core.dashboard import Dashboard
from xcode_cli.core.llm import LLMClient
from xcode_cli.core.memory import MemoryManager
from xcode_cli.core.planning import PlanMode, write_plan_file
from xcode_cli.core.prompting import build_system_prompt
from xcode_cli.core.project_root import resolve_project_root
from xcode_cli.core.runtime_status import RuntimeStatusStore
from xcode_cli.core.session import SessionStore
from xcode_cli.core.task_tracker import TaskTracker, create_task_tools
from xcode_cli.core.tool_registry import ToolDef, ToolRegistry
from xcode_cli.core.tools import ALL_TOOLS
from xcode_cli.core.tools.agent_tool import create_dispatch_agent_tool
from xcode_cli.skills.manager import SkillManager


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
        self.prompt = PromptSession(completer=SlashCompleter(), auto_suggest=AutoSuggestFromHistory())
        self.approval = ToolApprovalController(self.console, self._session_auto_approve)
        self.compactor = ConversationCompactor(self.context, self.llm, self.sessions, self.console)
        self.resume_service = ResumeCommandService(self.sessions, self.context, self.console, self.prompt)
        self.shell_ui = ShellUI(
            self.console,
            self.config_store,
            self.context,
            session_start_getter=lambda: self._session_start,
            tool_count_getter=lambda: self._tool_call_count,
            token_getter=lambda: self._estimated_tokens,
            cwd=self.cwd,
        )
        self.tools = ToolRegistry()
        for t in ALL_TOOLS:
            self.tools.register(t)
        self.tools.register(create_dispatch_agent_tool(self.llm, self.config_store))
        for task_tool in create_task_tools(self.task_tracker):
            self.tools.register(task_tool)
        for extra_tool in self._create_plan_memory_tools():
            self.tools.register(extra_tool)
        self.tool_display_state = ToolDisplayState(expanded=False)
        self.tool_display = ToolCallDisplay(self.tool_display_state)
        self.tool_executor = ToolCallExecutor(
            self.console,
            self.tools,
            self.permissions,
            self.approval,
            self.memory,
            self.config_store,
            self._session_auto_approve,
            tool_display=self.tool_display,
        )

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
        self.shell_ui.render_welcome()

    def _show_command_suggestions(self) -> None:
        self.shell_ui.show_command_suggestions()

    def _bottom_toolbar(self) -> str:
        return self.shell_ui.bottom_toolbar()

    def _print_user_bubble(self, text: str) -> None:
        self.shell_ui.print_user_bubble(text)

    def _print_assistant_bubble(self, text: str) -> None:
        self.shell_ui.print_assistant_bubble(text)

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
        result = self.resume_service.run()
        if result is not None:
            self._history[:] = result.history
            self._session_id = result.session_id
            self._runtime_status.update_session_id(result.session_id)

    def _find_previous_summary(self, history: list[dict[str, Any]]) -> str:
        return self.compactor.find_previous_summary(history)

    def _handle_compact_command(self) -> None:
        if len(self._history) < 4:
            self.console.print("Nothing to compact.")
            return

        outcome = self.compactor.compact_history(self._history)
        if outcome is None:
            self.console.print("Nothing to compact.")
            return

        self._history[:] = outcome.messages
        saved_tokens = max(outcome.before_tokens - outcome.after_tokens, 0)

        self.compactor.write_checkpoint(self._session_id, outcome)

        self.console.print(
            f"[dim]Context compacted: {outcome.before_messages} -> {outcome.after_messages} messages, "
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

    def _render_assistant_prefix(self) -> None:
        self.shell_ui.render_assistant_prefix()

    def _run_llm_loop(self, history: list[dict[str, Any]], system_prompt: str) -> str:
        cfg = self.config_store.load()
        render_mode = cfg.response_render_mode
        assistant_turn_started = False

        renderer = StreamingTurnRenderer(
            self.console,
            render_mode=render_mode,
            render_markdown=lambda text: self._print_assistant_bubble(text),
        )

        while True:
            if self.context.should_compress(history):
                outcome = self.compactor.compact_history(history)
                if outcome is not None:
                    before_messages = outcome.before_messages
                    after_messages = outcome.after_messages
                    history[:] = outcome.messages
                    saved_tokens = max(outcome.before_tokens - outcome.after_tokens, 0)
                    self.console.print(
                        f"[dim]Context compressed: {before_messages} -> {after_messages} messages, "
                        f"saved ~{saved_tokens} tokens.[/dim]"
                    )
                    if self._session_id:
                        self.compactor.write_checkpoint(self._session_id, outcome)

            content_buffer: list[str] = []
            reasoning_buffer: list[str] = []
            start_time = time.monotonic()
            first_text_token_elapsed_ms: float | None = None
            assistant_prefix_printed = False

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
                if not assistant_prefix_printed:
                    if not assistant_turn_started:
                        self._render_assistant_prefix()
                        assistant_turn_started = True
                    assistant_prefix_printed = True
                renderer.on_text_token(token)

            def on_reasoning_token(token: str) -> None:
                reasoning_buffer.append(token)
                renderer.on_reasoning_token(token)

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
                first_text_ms = int(first_text_token_elapsed_ms or total_ms)
                response_ms = max(int(total_ms - first_text_ms), 0)
                self.console.print(f"[dim](思考 {first_text_ms}ms / 回复 {response_ms}ms)[/dim]")

            if not response.tool_calls:
                final_text = response.content or ""
                turn_result = renderer.finish(final_text)
                if final_text and turn_result.needs_final_render:
                    if not assistant_turn_started:
                        self._render_assistant_prefix()
                        assistant_turn_started = True
                    if render_mode == "buffer_then_render":
                        self._print_assistant_bubble(final_text)
                if not final_text:
                    return "No response."
                return final_text

            tool_result = self.tool_executor.execute(response)
            self._tool_call_count += tool_result.executed_count
            history.append(tool_result.assistant_message)
            history.extend(tool_result.tool_messages)

            if self._session_id:
                self.sessions.append_message(self._session_id, tool_result.assistant_message)
                for tm in tool_result.tool_messages:
                    self.sessions.append_message(self._session_id, tm)
