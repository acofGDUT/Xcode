from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    required: list[str]
    execute: Callable[..., str]
    is_read_only: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get_openai_schemas(self, allowed_tools: list[str] | None = None) -> list[dict]:
        allowed = set(allowed_tools) if allowed_tools is not None else None
        schemas: list[dict] = []
        for tool in self._tools.values():
            if allowed is not None and tool.name not in allowed:
                continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": tool.parameters,
                            "required": tool.required,
                        },
                    },
                }
            )
        return schemas

    def execute(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            return tool.execute(**args)
        except Exception as exc:
            return f"Tool error: {exc}"

    def is_read_only(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.is_read_only if tool else False

    def list_names(self) -> list[str]:
        return list(self._tools.keys())
