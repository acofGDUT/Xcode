# Task 1: MCP 配置与 trust store

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P0。配置和 trust gate 决定是否启动本地外部进程，任何绕过都会把 `.xcode/mcp.json` 变成命令执行入口。

**Files:**
- Modify: `pyproject.toml`
- Create: `src/xcode_cli/mcp/__init__.py`
- Create: `src/xcode_cli/mcp/config.py`
- Create: `src/xcode_cli/mcp/trust.py`
- Test: `tests/test_mcp_config.py`
- Test: `tests/test_mcp_trust.py`

## Goal

实现 `.xcode/mcp.json` 读取和本机 trust store。未信任或 hash 变化的 server 必须停在 untrusted 状态，不能启动进程。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_config.py`**

覆盖：

- 缺失 `.xcode/mcp.json` 返回空配置。
- `type` 缺失时默认为 `stdio`。
- 只接受 `stdio`，HTTP/SSE 配置进入 warning 或 invalid。
- `${workspace}` 展开为项目根。
- `${ENV_NAME}` 从传入 env 读取；缺失时变为空字符串并 warning。
- `max_mcp_output_chars` 缺失默认 20000，非法值回退默认。
- project config 中的 `env` 只能是字符串键值。

- [x] **Step 2: 写失败测试 `tests/test_mcp_trust.py`**

覆盖：

- trust fingerprint 包含 project_key、server name、type、command、args、resolved cwd、sorted env keys。
- env value 改变不改变 fingerprint，env key 改变会改变 fingerprint。
- command/args/cwd 改变会改变 fingerprint。
- trust store path 默认为 `~/.xcode/mcp_trust.json`。
- trust 后同 hash 返回 trusted。
- hash 变化后返回 untrusted。
- untrust 删除对应 project/server/hash record。

- [x] **Step 3: 添加 MCP 包和依赖**

在 `pyproject.toml` 增加官方 MCP Python SDK 依赖。实现阶段如需锁版本，由 Coding Agent 先确认本地包名和导入路径；单元测试不得访问真实网络。

创建 `src/xcode_cli/mcp/__init__.py`：

```python
"""MCP integration package."""
```

- [x] **Step 4: 实现 `config.py`**

建议数据结构：

```python
@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    type: str
    command: str
    args: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    enabled: bool = True
    tool_allowlist: tuple[str, ...] = ()
    tool_blocklist: tuple[str, ...] = ()
    read_only_tools: tuple[str, ...] = ()

@dataclass(frozen=True)
class MCPConfig:
    servers: tuple[MCPServerConfig, ...]
    max_mcp_output_chars: int = 20000
    warnings: tuple[str, ...] = ()
```

`load_mcp_config(project_root, env=None)` 只读取 `<project>/.xcode/mcp.json`。损坏 JSON 返回 empty config + warning 或抛可读异常由 `/mcp status` 捕获；不要让 `AgentRuntime` 初始化崩。

- [x] **Step 5: 实现 `trust.py`**

建议接口：

```python
def compute_server_fingerprint(project_key: str, server: MCPServerConfig) -> str: ...

class MCPTrustStore:
    def __init__(self, path: Path | None = None) -> None: ...
    def is_trusted(self, project_key: str, server: MCPServerConfig) -> bool: ...
    def trust(self, project_key: str, server: MCPServerConfig) -> str: ...
    def untrust(self, project_key: str, server_name: str) -> None: ...
```

写文件使用 JSON，字段中只保存 env keys，不保存 env values。

- [x] **Step 6: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_config.py tests/test_mcp_trust.py -q
```

Expected: PASS。

- [x] **Step 7: Review 检查点**

Codex review 重点：

- 未信任状态是否一定先于进程启动。
- trust store 是否完全不写项目目录。
- env secret 是否不会落盘。
- hash 变化是否会重新 untrusted。

