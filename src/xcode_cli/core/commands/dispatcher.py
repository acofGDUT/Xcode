from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from rich.console import Console

from xcode_cli.core.commands.slash import PROMPT_COMMANDS


@dataclass(frozen=True)
class SlashDispatchResult:
    """斜杠命令分发结果。

    kind="prompt": text 是展开后的 prompt，应作为普通 user input 继续处理。
    kind="handled": 命令已由 side-effect handler 处理完毕，应回到输入循环。
    """
    kind: str
    text: str | None = None


class SlashCommandDispatcher:
    """将斜杠命令路由到对应 handler，返回统一的 dispatch result。

    不依赖 AgentRuntime；所有行为通过构造函数注入。
    """

    def __init__(
        self,
        console: Console,
        help_handler: Callable[[], None],
        context_handler: Callable[[], None],
        dashboard_handler: Callable[[], None],
        skill_handler: Callable[[list[str]], None],
        env_handler: Callable[[list[str]], None],
        plan_handler: Callable[[list[str]], None],
        memory_handler: Callable[[list[str]], None],
        resume_handler: Callable[[], None],
        compact_handler: Callable[[], None],
    ) -> None:
        self._console = console
        self._handlers: dict[str, Callable] = {
            "/help": lambda parts: help_handler(),
            "/context": lambda parts: context_handler(),
            "/dashboard": lambda parts: dashboard_handler(),
            "/skill": lambda parts: skill_handler(parts),
            "/env": lambda parts: env_handler(parts),
            "/plan": lambda parts: plan_handler(parts),
            "/memory": lambda parts: memory_handler(parts),
            "/resume": lambda parts: resume_handler(),
            "/compact": lambda parts: compact_handler(),
        }

    def dispatch(self, command: str) -> SlashDispatchResult:
        """分发一条斜杠命令，返回 dispatch result。

        Parameters
        ----------
        command : str
            完整的斜杠命令，如 "/help" 或 "/skill list"。
        """
        parts = command.split()
        head = parts[0].lower()

        # prompt command（如 /init）→ 展开为 prompt text，继续走普通 user turn
        prompt_cmd = PROMPT_COMMANDS.get(head)
        if prompt_cmd is not None:
            args = " ".join(parts[1:]) if len(parts) > 1 else ""
            return SlashDispatchResult(kind="prompt", text=prompt_cmd.handler(args))

        # side-effect command → 调用 handler，返回 handled
        handler = self._handlers.get(head)
        if handler is not None:
            handler(parts)
            return SlashDispatchResult(kind="handled")

        # 未知命令
        self._console.print(f"Unknown command: {command}. Try /help")
        return SlashDispatchResult(kind="handled")
