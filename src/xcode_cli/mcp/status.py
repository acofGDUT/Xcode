from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


MCPServerState = Literal["connected", "failed", "untrusted", "disabled"]


@dataclass
class MCPToolStatus:
    original_name: str
    registered_name: str
    read_only: bool


@dataclass
class MCPServerStatus:
    name: str
    status: MCPServerState
    fingerprint: str
    tool_count: int = 0
    error_summary: str = ""
    warnings: list[str] = field(default_factory=list)
    tools: list[MCPToolStatus] = field(default_factory=list)
