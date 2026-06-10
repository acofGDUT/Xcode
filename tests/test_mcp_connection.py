from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from xcode_cli.mcp.config import MCPConfig, MCPServerConfig
from xcode_cli.mcp.connection import MCPConnectionManager, SDKStdioSession
from xcode_cli.mcp.trust import MCPTrustStore


class FakeSession:
    def __init__(self, *, tools=None, calls=None, list_error: Exception | None = None, call_delay: float = 0) -> None:
        self.tools = tools or []
        self.calls = calls or {}
        self.list_error = list_error
        self.call_delay = call_delay
        self.closed = False

    async def list_tools(self):
        if self.list_error:
            raise self.list_error
        return self.tools

    async def call_tool(self, name: str, arguments: dict):
        if self.call_delay:
            await asyncio.sleep(self.call_delay)
        value = self.calls.get(name)
        if isinstance(value, Exception):
            raise value
        return value or {"content": [{"type": "text", "text": "ok"}]}

    async def close(self):
        self.closed = True


class FakeClientFactory:
    def __init__(self, sessions: dict[str, FakeSession]) -> None:
        self.sessions = sessions
        self.started: list[str] = []

    async def connect(self, server: MCPServerConfig) -> FakeSession:
        self.started.append(server.name)
        value = self.sessions[server.name]
        if isinstance(value, Exception):
            raise value
        return value


class SlowConnectFactory:
    def __init__(self) -> None:
        self.cleanup_finished = False

    async def connect(self, server: MCPServerConfig) -> FakeSession:
        try:
            await asyncio.sleep(10)
        finally:
            await asyncio.sleep(0)
            self.cleanup_finished = True


def _server(name: str = "filesystem", enabled: bool = True) -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        type="stdio",
        command="python",
        args=("server.py",),
        cwd=Path.cwd(),
        env={},
        enabled=enabled,
    )


def test_untrusted_server_does_not_connect(tmp_path: Path) -> None:
    server = _server()
    factory = FakeClientFactory({server.name: FakeSession()})
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(server,)),
        trust_store=MCPTrustStore(tmp_path / "trust.json"),
        project_key="project",
        client_factory=factory,
    )

    manager.start_trusted_servers()

    assert factory.started == []
    assert manager.statuses()[0].status == "untrusted"
    manager.shutdown()


def test_trusted_server_connects_and_lists_tools(tmp_path: Path) -> None:
    server = _server()
    trust = MCPTrustStore(tmp_path / "trust.json")
    trust.trust("project", server)
    session = FakeSession(tools=[{"name": "read_file", "description": "Read", "inputSchema": {}}])
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(server,)),
        trust_store=trust,
        project_key="project",
        client_factory=FakeClientFactory({server.name: session}),
    )

    manager.start_trusted_servers()

    assert manager.statuses()[0].status == "connected"
    assert manager.statuses()[0].tool_count == 1
    assert manager.list_connected_tools()[0].name == "read_file"
    manager.shutdown()


def test_start_failure_sets_failed_status(tmp_path: Path) -> None:
    server = _server()
    trust = MCPTrustStore(tmp_path / "trust.json")
    trust.trust("project", server)
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(server,)),
        trust_store=trust,
        project_key="project",
        client_factory=FakeClientFactory({server.name: RuntimeError("spawn failed")}),
    )

    manager.start_trusted_servers()

    status = manager.statuses()[0]
    assert status.status == "failed"
    assert "spawn failed" in status.error_summary
    manager.shutdown()


def test_tools_list_failure_sets_failed_without_affecting_other_server(tmp_path: Path) -> None:
    bad = _server("bad")
    good = _server("good")
    trust = MCPTrustStore(tmp_path / "trust.json")
    trust.trust("project", bad)
    trust.trust("project", good)
    bad_session = FakeSession(list_error=RuntimeError("list failed"))
    good_session = FakeSession(tools=[{"name": "ok", "inputSchema": {}}])
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(bad, good)),
        trust_store=trust,
        project_key="project",
        client_factory=FakeClientFactory(
            {
                "bad": bad_session,
                "good": good_session,
            }
        ),
    )

    manager.start_trusted_servers()

    statuses = {status.name: status for status in manager.statuses()}
    assert statuses["bad"].status == "failed"
    assert statuses["good"].status == "connected"
    assert bad_session.closed is True
    assert good_session.closed is False
    manager.shutdown()


def test_shutdown_closes_connected_sessions(tmp_path: Path) -> None:
    server = _server()
    trust = MCPTrustStore(tmp_path / "trust.json")
    trust.trust("project", server)
    session = FakeSession()
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(server,)),
        trust_store=trust,
        project_key="project",
        client_factory=FakeClientFactory({server.name: session}),
    )
    manager.start_trusted_servers()

    manager.shutdown()
    manager.shutdown()

    assert session.closed


def test_call_tool_timeout_returns_tool_error(tmp_path: Path) -> None:
    server = _server()
    trust = MCPTrustStore(tmp_path / "trust.json")
    trust.trust("project", server)
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(server,)),
        trust_store=trust,
        project_key="project",
        client_factory=FakeClientFactory({"filesystem": FakeSession(call_delay=0.2)}),
        timeout_seconds=0.01,
    )
    manager.start_trusted_servers()

    result = manager.call_tool_sync("filesystem", "read_file", {})

    assert isinstance(result, dict)
    assert result["isError"] is True
    assert "Tool error:" in result["content"][0]["text"]
    manager.shutdown()


def test_connect_timeout_waits_for_cancellation_cleanup(tmp_path: Path) -> None:
    server = _server()
    trust = MCPTrustStore(tmp_path / "trust.json")
    trust.trust("project", server)
    factory = SlowConnectFactory()
    manager = MCPConnectionManager(
        config=MCPConfig(servers=(server,)),
        trust_store=trust,
        project_key="project",
        client_factory=factory,
        timeout_seconds=0.01,
    )

    manager.start_trusted_servers()

    status = manager.statuses()[0]
    assert status.status == "failed"
    assert "timed out" in status.error_summary
    assert factory.cleanup_finished is True
    manager.shutdown()


def test_sdk_stdio_open_closes_partial_stack_when_initialize_is_cancelled(monkeypatch) -> None:
    closed: list[str] = []

    class FakeStdioContext:
        async def __aenter__(self):
            return "read", "write"

        async def __aexit__(self, exc_type, exc, tb):
            closed.append("stdio")

    class FakeClientSession:
        def __init__(self, read, write) -> None:
            self.read = read
            self.write = write

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            closed.append("session")

        async def initialize(self) -> None:
            raise asyncio.CancelledError

    fake_mcp = types.ModuleType("mcp")
    fake_client = types.ModuleType("mcp.client")
    fake_stdio = types.ModuleType("mcp.client.stdio")
    fake_mcp.StdioServerParameters = lambda **kwargs: kwargs
    fake_mcp.ClientSession = FakeClientSession
    fake_stdio.stdio_client = lambda params: FakeStdioContext()
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", fake_client)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", fake_stdio)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(SDKStdioSession.open(_server()))
    assert closed == ["session", "stdio"]
