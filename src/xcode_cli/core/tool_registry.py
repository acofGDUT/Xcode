from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ToolOutput:
    content: str
    metadata: dict[str, object] = field(default_factory=dict)
    audit_metadata: dict[str, object] = field(default_factory=dict)
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] = field(default_factory=list)


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    required: list[str]
    execute: Callable[..., str | ToolOutput]
    is_read_only: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get_openai_schemas(
        self,
        allowed_tools: list[str] | None = None,
        blocked_tools: set[str] | list[str] | None = None,
    ) -> list[dict]:
        allowed = set(allowed_tools) if allowed_tools is not None else None
        blocked = set(blocked_tools or [])
        schemas: list[dict] = []
        for tool in self._tools.values():
            if allowed is not None and tool.name not in allowed:
                continue
            if tool.name in blocked:
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

    def execute(self, name: str, args: dict) -> ToolOutput:
        tool = self._tools.get(name)
        if not tool:
            return ToolOutput(content=f"Error: unknown tool '{name}'")
        try:
            result = tool.execute(**args)
            if isinstance(result, ToolOutput):
                return result
            return ToolOutput(content=str(result))
        except Exception as exc:
            return ToolOutput(content=f"Tool error: {exc}")

    def is_read_only(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.is_read_only if tool else False

    def list_names(self) -> list[str]:
        return list(self._tools.keys())
