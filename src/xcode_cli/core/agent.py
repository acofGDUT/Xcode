from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.shortcuts import radiolist_dialog
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.table import Table

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
from xcode_cli.core.session import SessionStore
from xcode_cli.core.task_tracker import TaskTracker, create_task_tools
from xcode_cli.core.tool_registry import ToolDef, ToolRegistry
from xcode_cli.core.tools import ALL_TOOLS
from xcode_cli.core.tools.agent_tool import create_dispatch_agent_tool
from xcode_cli.skills.manager import SkillManager


COMMANDS = {
    "/help": "Show available commands",
    "/dashboard": "Open API configuration dashboard",
    "/skill": "Manage skills (list/install/enable/disable)",
    "/env": "Manage API env for current process",
    "/plan": "Plan mode controls (enter/show/approve/reject)",
    "/memory": "Memory status and auto-memory toggle",
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
                ("/env edit", "Open ~/.xcode/config.json in default editor"),
            ]:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")
            return

        for cmd, desc in COMMANDS.items():
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display=f"{cmd} — {desc}")


class AgentRuntime:
    def __init__(self) -> None:
        self.console = Console()
        self.sessions = SessionStore()
        self.skills = SkillManager()
        self.config_store = ConfigStore()
        self.llm = LLMClient()
        self.context = ContextManager()
        self.cwd = str(resolve_project_root(os.getcwd()))
        self.task_tracker = TaskTracker()
        self.memory = MemoryManager(cwd=self.cwd)
        self.permissions = PermissionManager(cwd=self.cwd)
        self.plan_mode = PlanMode()
        self._session_start = time.monotonic()
        self._tool_call_count = 0
        self._estimated_tokens = 0
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
        session_id = self.sessions.new_session_id()
        self._render_welcome()

        history: list[dict[str, Any]] = []

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

            self.sessions.append(session_id, "user", user_input)
            self._print_user_bubble(user_input)
            history.append({"role": "user", "content": user_input})

            if self.plan_mode.is_active:
                system_prompt = self.plan_mode.get_system_prompt()
            else:
                system_prompt = build_system_prompt(self.config_store.load(), self.skills, self.cwd)
            final_text = self._run_llm_loop(history=history, system_prompt=system_prompt)

            is_llm_error = final_text.startswith("[v0] LLM request failed:")
            is_missing_key = final_text.startswith("[v0] Missing API key")
            is_missing_pkg = final_text.startswith("[v0] openai package not installed")

            if is_llm_error or is_missing_key or is_missing_pkg:
                self.console.print(f"[bold red]{final_text}[/bold red]")
                continue

            self.sessions.append(session_id, "assistant", final_text)
            history.append({"role": "assistant", "content": final_text})

            if self.plan_mode.pending_approval:
                self._show_plan_and_ask_approval()

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
        OutputRenderer.render(self.console, text)

    def _handle_slash_command(self, command: str) -> None:
        parts = command.split()
        head = parts[0].lower()

        if head == "/help":
            self._show_command_suggestions()
            self.console.print("/skill list|install <path>|enable <name>|disable <name>")
            self.console.print("/env show|set <api_key>|unset")
            self.console.print("/memory | /memory auto on|off")
            self.console.print("/dashboard")
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
            self.console.print("/env show | /env set <api_key> | /env unset | /env edit")
            return
        action = parts[1].lower()
        if action == "show":
            key = os.getenv("XCODE_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not key:
                self.console.print("API key is not set.")
            else:
                masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "(set)"
                self.console.print(f"API key: {masked}")
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

        self.console.print("Usage: /env show|set <api_key>|unset|base-url <url>|model <name>|edit")

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
        return None

    def _prompt_tool_approval(self, tool_name: str) -> str:
        choice = radiolist_dialog(
            title="Tool Approval",
            text=f"Review complete. Allow tool call now? ({tool_name})",
            values=[
                ("yes", "Yes"),
                ("yes_all", "Yes, for this conversation"),
                ("no", "No"),
            ],
            default="yes",
        ).run()
        if choice is None:
            return "no"
        return choice

    def _run_llm_loop(self, history: list[dict[str, Any]], system_prompt: str) -> str:
        max_tool_rounds = 10
        cfg = self.config_store.load()
        render_mode = cfg.response_render_mode
        stream_text = render_mode == "streaming_plus_final_render"


        for _ in range(max_tool_rounds):
            if self.context.should_compress(history):
                history[:] = self.context.compress(history, self.llm)
                self.console.print("[dim]Context compressed to avoid token overflow.[/dim]")

            content_buffer: list[str] = []
            reasoning_buffer: list[str] = []
            start_time = time.monotonic()
            first_text_token_elapsed_ms: float | None = None
            self.console.print("[dim]Thinking...[/dim]")
            assistant_prefix_printed = False

            stream_state = {"in_code_block": False, "fence_ticks": 0}

            def on_token(token: str) -> None:
                nonlocal first_text_token_elapsed_ms, assistant_prefix_printed
                if first_text_token_elapsed_ms is None:
                    elapsed = time.monotonic() - start_time
                    first_text_token_elapsed_ms = elapsed * 1000
                content_buffer.append(token)
                if not stream_text:
                    return
                if not assistant_prefix_printed:
                    self.console.print("[magenta]assistant[/magenta] ▸ ", end="")
                    assistant_prefix_printed = True
                # stream plain text, but buffer code blocks to avoid double-render
                for ch in token:
                    if ch == "`":
                        stream_state["fence_ticks"] += 1
                    else:
                        stream_state["fence_ticks"] = 0
                    if stream_state["fence_ticks"] == 3:
                        stream_state["in_code_block"] = not stream_state["in_code_block"]
                        stream_state["fence_ticks"] = 0
                    if not stream_state["in_code_block"]:
                        self.console.print(ch, end="", markup=False)

            def on_reasoning_token(token: str) -> None:
                reasoning_buffer.append(token)

            response = self.llm.complete(
                system_prompt=system_prompt,
                messages=history,
                tool_schemas=self.tools.get_openai_schemas(),
                on_text_token=on_token,
                on_reasoning_token=on_reasoning_token,
            )
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
                        self._print_assistant_bubble(final_text)
                else:
                    if final_text and ("```" in final_text or "|" in final_text or "\n#" in final_text):
                        self.console.print()
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
                        except FileNotFoundError:
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
                        OutputRenderer.render_diff(self.console, old_text, new_text, file_path)

                if scope and self._session_auto_approve.get(scope):
                    self.console.print("  [dim]approval: auto-yes (this conversation)[/dim]")
                elif level == "ask":
                    if tc.name == "run_shell":
                        cmd = str(tc.args.get("command", ""))
                        self.console.print("  [dim]Review: command preview before approval[/dim]")
                        self.console.print(f"  [bold yellow]$ {cmd}[/bold yellow]")
                    approval = self._prompt_tool_approval(tc.name)
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
                    self.console.print(f"  [dim]→ done ({len(result_str)} chars)[/dim]")

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

        return "Reached maximum tool call rounds."
