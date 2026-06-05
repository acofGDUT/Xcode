from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from xcode_cli.core.llm import LLMResponse
from xcode_cli.core.tool_registry import ToolOutput
from xcode_cli.core.tooling.display import ToolCallDisplay, ToolDisplayState
from xcode_cli.ui.renderer import OutputRenderer


@dataclass
class ToolExecutionResult:
    assistant_message: dict[str, Any]
    tool_messages: list[dict[str, Any]]
    executed_count: int
    activated_allowed_tools: list[str] | None = None
    blocked_tools: list[str] = field(default_factory=list)
    skill_invocations: list[dict[str, object]] = field(default_factory=list)


class ToolCallExecutor:
    def __init__(
        self,
        console,
        tools,
        permissions,
        approval,
        memory,
        config_store,
        auto_approve: dict[str, bool],
        tool_display: ToolCallDisplay | None = None,
    ) -> None:
        self.console = console
        self.tools = tools
        self.permissions = permissions
        self.approval = approval
        self.memory = memory
        self.config_store = config_store
        self.auto_approve = auto_approve
        self.tool_display = tool_display or ToolCallDisplay(ToolDisplayState(expanded=True))

    def execute(self, response: LLMResponse, allowed_tools: list[str] | None = None) -> ToolExecutionResult:
        executed_calls: list[tuple[Any, ToolOutput]] = []
        executed_count = 0
        allowed = set(allowed_tools) if allowed_tools is not None else None
        activated_allowed_tools: list[str] | None = None
        blocked_tools: list[str] = []
        skill_invocations: list[dict[str, object]] = []

        self._render_tool_calls(response.tool_calls)

        for tc in response.tool_calls:
            if allowed is not None and tc.name not in allowed:
                result = f"Tool error: tool '{tc.name}' is not allowed by the current skill."
                self.console.print(f"  [bold red]{result}[/bold red]")
                executed_calls.append((tc, ToolOutput(content=result)))
                continue

            level = self.permissions.check(tc.name, is_read_only=self.tools.is_read_only(tc.name))
            if level == "deny":
                result = f"Permission denied for tool: {tc.name}"
                self.console.print(f"  [bold red]{result}[/bold red]")
                executed_calls.append((tc, ToolOutput(content=result)))
                continue

            scope = self.approval.scope_for_tool(tc.name)
            is_memory_write = self._is_memory_write_tool_call(tc.name, tc.args)

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

            if is_memory_write and level != "deny":
                self.console.print("  [dim]approval: memory auto-allow[/dim]")
            elif scope and self.auto_approve.get(scope):
                self.console.print("  [dim]approval: auto-yes (this conversation)[/dim]")
            elif level == "ask":
                if tc.name == "run_shell":
                    cmd = str(tc.args.get("command", ""))
                    self.console.print("  [dim]Review: command preview before approval[/dim]")
                    self.console.print(f"  [bold yellow]$ {cmd}[/bold yellow]")
                approval_result = self.approval.prompt(tc.name, scope)
                if approval_result == "no":
                    result = f"User denied tool: {tc.name}"
                    self.console.print(f"  [dim]{result}[/dim]")
                    executed_calls.append((tc, ToolOutput(content=result)))
                    continue
                if approval_result == "yes_all" and scope:
                    self.auto_approve[scope] = True

            try:
                output = self.tools.execute(tc.name, tc.args)
            except KeyboardInterrupt:
                self.console.print("  [dim]Interrupted.[/dim]")
                output = ToolOutput(content="Error: user interrupted the operation")

            executed_count += 1
            if output.content.startswith("Error:"):
                self.console.print(f"  [bold red]{output.content}[/bold red]")
            else:
                summary = self._summarize_tool_result(tc.name, tc.args, output.content)
                self.console.print(f"  [dim]→ {summary}[/dim]")

            if output.audit_metadata.get("kind") == "skill_invocation":
                skill_invocations.append(dict(output.audit_metadata))
            if output.allowed_tools is not None:
                activated_allowed_tools = output.allowed_tools
            for tool_name in output.blocked_tools:
                if tool_name not in blocked_tools:
                    blocked_tools.append(tool_name)

            executed_calls.append((tc, output))

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

        tool_messages: list[dict[str, Any]] = []
        for tc, output in executed_calls:
            tool_messages.append({"role": "tool", "tool_call_id": tc.id, "content": output.content})

        return ToolExecutionResult(
            assistant_message=assistant_msg,
            tool_messages=tool_messages,
            executed_count=executed_count,
            activated_allowed_tools=activated_allowed_tools,
            blocked_tools=blocked_tools,
            skill_invocations=skill_invocations,
        )

    def _render_tool_calls(self, tool_calls: list[Any]) -> None:
        lines = self.tool_display.render_calls(tool_calls)
        for line in lines:
            self.console.print(f"  {line}")

    def _render_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        self.console.print(f"  [bold cyan]## tool.{tool_name}[/bold cyan]")
        for key, value in args.items():
            val_str = str(value)
            if len(val_str) > 120:
                val_str = val_str[:120] + "..."
            self.console.print(f"    [dim]{key}:[/dim] {val_str}")

    def _is_memory_write_tool_call(self, tool_name: str, args: dict[str, Any]) -> bool:
        if tool_name not in {"write_file", "edit_file"}:
            return False
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            return False
        return self.memory.is_memory_write_target(path)

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
        if tool_name == "skill":
            name = str(args.get("skill", "")).strip().lstrip("/")
            return f"loaded skill {name}" if name else "loaded skill"
        if tool_name == "edit_file":
            return result
        if tool_name == "write_file":
            path = args.get("path", "")
            action = "appended" if args.get("append") else "wrote"
            return f"{action} {path}"
        return f"done ({len(result)} chars)"
