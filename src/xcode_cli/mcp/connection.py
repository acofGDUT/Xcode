from __future__ import annotations

import asyncio
import threading
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xcode_cli.mcp.config import MCPConfig, MCPServerConfig
from xcode_cli.mcp.status import MCPServerStatus
from xcode_cli.mcp.trust import MCPTrustStore, compute_server_fingerprint

_CANCEL_CLEANUP_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class MCPDiscoveredTool:
    server_name: str
    name: str
    description: str
    input_schema: object


@dataclass
class _ConnectionRecord:
    server: MCPServerConfig
    session: Any
    tools: list[MCPDiscoveredTool] = field(default_factory=list)


class MCPConnectionManager:
    def __init__(
        self,
        *,
        config: MCPConfig,
        trust_store: MCPTrustStore,
        project_key: str,
        client_factory: Any | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.config = config
        self.trust_store = trust_store
        self.project_key = project_key
        self.client_factory = client_factory or SDKStdioClientFactory()
        self.timeout_seconds = timeout_seconds
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="xcode-mcp", daemon=True)
        self._thread.start()
        self._records: dict[str, _ConnectionRecord] = {}
        self._statuses: dict[str, MCPServerStatus] = {}
        self._shutdown = False

    def start_trusted_servers(self) -> None:
        for server in self.config.servers:
            fingerprint = compute_server_fingerprint(self.project_key, server)
            if not server.enabled:
                self._statuses[server.name] = MCPServerStatus(name=server.name, status="disabled", fingerprint=fingerprint)
                continue
            if not self.trust_store.is_trusted(self.project_key, server):
                self._statuses[server.name] = MCPServerStatus(name=server.name, status="untrusted", fingerprint=fingerprint)
                continue
            try:
                self._run_sync(self._connect_server(server))
            except FutureTimeoutError:
                self._statuses[server.name] = MCPServerStatus(
                    name=server.name,
                    status="failed",
                    fingerprint=fingerprint,
                    error_summary=f"MCP server '{server.name}' connection timed out.",
                )
            except Exception as exc:
                self._statuses[server.name] = MCPServerStatus(
                    name=server.name,
                    status="failed",
                    fingerprint=fingerprint,
                    error_summary=str(exc),
                )

    def list_connected_tools(self) -> list[MCPDiscoveredTool]:
        tools: list[MCPDiscoveredTool] = []
        for record in self._records.values():
            tools.extend(record.tools)
        return tools

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: dict) -> object:
        record = self._records.get(server_name)
        if record is None:
            return _tool_error(f"MCP server '{server_name}' is not connected.")
        try:
            return self._run_sync(self._call_tool(record.session, tool_name, arguments))
        except FutureTimeoutError:
            return _tool_error(f"Tool error: MCP tool '{server_name}.{tool_name}' timed out.")
        except Exception as exc:
            return _tool_error(f"Tool error: {exc}")

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        try:
            self._run_sync(self._shutdown_async())
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1.0)

    def statuses(self) -> list[MCPServerStatus]:
        return [self._statuses[name] for name in self._statuses]

    async def _connect_server(self, server: MCPServerConfig) -> None:
        fingerprint = compute_server_fingerprint(self.project_key, server)
        session = await _maybe_await(self.client_factory.connect(server))
        try:
            raw_tools = await _call_method(session, "list_tools")
            tools = [_coerce_discovered_tool(server.name, item) for item in _extract_tools(raw_tools)]
        except Exception:
            with suppress(Exception):
                await _close_session(session)
            raise
        self._records[server.name] = _ConnectionRecord(server=server, session=session, tools=tools)
        self._statuses[server.name] = MCPServerStatus(
            name=server.name,
            status="connected",
            fingerprint=fingerprint,
            tool_count=len(tools),
        )

    async def _call_tool(self, session: Any, tool_name: str, arguments: dict) -> object:
        return await _call_method(session, "call_tool", tool_name, arguments)

    async def _shutdown_async(self) -> None:
        for record in list(self._records.values()):
            await _close_session(record.session)
        self._records.clear()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_sync(self, coro):
        cleanup_done = threading.Event()
        future = asyncio.run_coroutine_threadsafe(_signal_when_done(coro, cleanup_done), self._loop)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            cleanup_done.wait(timeout=_CANCEL_CLEANUP_TIMEOUT_SECONDS)
            with suppress(FutureCancelledError, FutureTimeoutError):
                future.result(timeout=0)
            raise


class SDKStdioClientFactory:
    async def connect(self, server: MCPServerConfig) -> Any:
        return await SDKStdioSession.open(server)


class SDKStdioSession:
    def __init__(self, stack: AsyncExitStack, session: Any) -> None:
        self._stack = stack
        self._session = session

    @classmethod
    async def open(cls, server: MCPServerConfig) -> "SDKStdioSession":
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:
            raise RuntimeError(f"MCP SDK is not available: {exc}") from exc

        stack = AsyncExitStack()
        params = StdioServerParameters(
            command=server.command,
            args=list(server.args),
            cwd=str(server.cwd),
            env=dict(server.env) if server.env else None,
        )
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            return cls(stack, session)
        except BaseException:
            await stack.aclose()
            raise

    async def list_tools(self) -> object:
        return await self._session.list_tools()

    async def call_tool(self, name: str, arguments: dict) -> object:
        return await self._session.call_tool(name, arguments)

    async def close(self) -> None:
        await self._stack.aclose()


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


async def _signal_when_done(coro, event: threading.Event) -> Any:
    try:
        return await coro
    finally:
        event.set()


async def _call_method(obj: Any, method_name: str, *args) -> Any:
    method = getattr(obj, method_name)
    return await _maybe_await(method(*args))


async def _close_session(session: Any) -> None:
    close = getattr(session, "close", None)
    if close is not None:
        await _maybe_await(close())


def _extract_tools(raw_tools: object) -> list[object]:
    if isinstance(raw_tools, list):
        return raw_tools
    tools = getattr(raw_tools, "tools", None)
    if isinstance(tools, list):
        return tools
    if isinstance(raw_tools, dict) and isinstance(raw_tools.get("tools"), list):
        return raw_tools["tools"]
    return []


def _coerce_discovered_tool(server_name: str, raw_tool: object) -> MCPDiscoveredTool:
    name = _get(raw_tool, "name", "")
    description = _get(raw_tool, "description", "")
    input_schema = _get(raw_tool, "inputSchema", _get(raw_tool, "input_schema", {}))
    return MCPDiscoveredTool(
        server_name=server_name,
        name=str(name),
        description=str(description or ""),
        input_schema=input_schema,
    )


def _get(value: object, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _tool_error(message: str) -> dict[str, object]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}
