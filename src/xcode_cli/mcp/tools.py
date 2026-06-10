from __future__ import annotations

from xcode_cli.core.tool_registry import ToolDef, ToolOutput
from xcode_cli.mcp.config import MCPConfig, MCPServerConfig
from xcode_cli.mcp.connection import MCPConnectionManager, MCPDiscoveredTool
from xcode_cli.mcp.naming import detect_tool_name_conflicts
from xcode_cli.mcp.result import render_mcp_tool_result
from xcode_cli.mcp.schema import convert_input_schema


def create_mcp_tool_defs(
    *,
    connection_manager: MCPConnectionManager,
    config: MCPConfig,
    existing_names: set[str] | None = None,
) -> tuple[list[ToolDef], list[str]]:
    server_configs = {server.name: server for server in config.servers}
    warnings: list[str] = list(config.warnings)
    grouped: dict[str, list[MCPDiscoveredTool]] = {}
    for tool in connection_manager.list_connected_tools():
        grouped.setdefault(tool.server_name, []).append(tool)

    tool_defs: list[ToolDef] = []
    used_names = set(existing_names or set())
    for server_name, tools in grouped.items():
        server = server_configs.get(server_name)
        if server is None:
            warnings.append(f"Skipped MCP tools for unknown server '{server_name}'.")
            continue

        visible_tools = [_tool for _tool in tools if _is_tool_enabled(server, _tool.name)]
        accepted, naming_warnings = detect_tool_name_conflicts(
            server_name=server_name,
            tool_names=[tool.name for tool in visible_tools],
            existing_names=used_names,
        )
        warnings.extend(naming_warnings)

        for tool in visible_tools:
            registered_name = accepted.get(tool.name)
            if registered_name is None:
                continue
            schema = convert_input_schema(tool.input_schema)
            warnings.extend(f"MCP tool '{tool.name}': {warning}" for warning in schema.warnings)
            if schema.parameters is None:
                warnings.append(f"Skipped MCP tool '{tool.name}' because its inputSchema is invalid.")
                continue
            used_names.add(registered_name)
            tool_defs.append(
                ToolDef(
                    name=registered_name,
                    description=tool.description or f"MCP tool {tool.name} from server {server_name}.",
                    parameters=schema.parameters,
                    required=schema.required,
                    execute=_make_execute(connection_manager, server_name, tool.name, config.max_mcp_output_chars),
                    is_read_only=tool.name in server.read_only_tools,
                )
            )

    return tool_defs, warnings


def _is_tool_enabled(server: MCPServerConfig, tool_name: str) -> bool:
    if server.tool_allowlist and tool_name not in server.tool_allowlist:
        return False
    if tool_name in server.tool_blocklist:
        return False
    return True


def _make_execute(connection_manager: MCPConnectionManager, server_name: str, tool_name: str, max_chars: int):
    def execute(**kwargs) -> ToolOutput:
        raw_result = connection_manager.call_tool_sync(server_name, tool_name, kwargs)
        return ToolOutput(content=render_mcp_tool_result(raw_result, max_chars=max_chars))

    return execute
