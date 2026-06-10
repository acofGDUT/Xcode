# Task 2: 命名、schema 和 result 适配

> Parent plan: [2026-06-08-mcp-integration-plan.md](../2026-06-08-mcp-integration-plan.md)
> Spec: [2026-06-08-mcp-integration-design.md](../../specs/2026-06-08-mcp-integration-design.md)

**Risk layer:** P0。MCP server 提供的 tool name、inputSchema 和 result 都是不可信输入，不能让它们覆盖内置工具、打崩 schema 构建或把巨大/二进制输出塞进 `_history`。

**Files:**
- Create: `src/xcode_cli/mcp/naming.py`
- Create: `src/xcode_cli/mcp/schema.py`
- Create: `src/xcode_cli/mcp/result.py`
- Test: `tests/test_mcp_naming_schema.py`
- Test: `tests/test_mcp_result.py`

## Goal

实现 MCP tool 名称规范化、schema 防御式转换和 result 文本化截断。

## Steps

- [x] **Step 1: 写失败测试 `tests/test_mcp_naming_schema.py`**

覆盖：

- `filesystem` + `read_file` -> `mcp__filesystem__read_file`。
- `my-server`、`tool.name` 等非法字符转 `_`。
- 空 server/tool 名报错。
- sanitized 后同名冲突会返回 warning/skip，不覆盖。
- `inputSchema` 缺失 `type` 时补 `"object"`。
- `properties` 缺失时补 `{}`。
- `required` 非字符串数组时清空并 warning。
- 非 dict schema 被判 invalid 并 skip。

- [x] **Step 2: 写失败测试 `tests/test_mcp_result.py`**

覆盖：

- text content 拼接。
- structuredContent JSON 序列化。
- image/resource/audio 内容只生成 omitted 占位，不注入二进制。
- `isError=true` 输出以 `Tool error:` 开头。
- 超过 `max_mcp_output_chars` 会截断并追加 `[MCP output truncated: ...]`。

- [x] **Step 3: 实现 `naming.py`**

建议接口：

```python
VALID_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")

def sanitize_mcp_name(value: str) -> str: ...
def mcp_tool_name(server_name: str, tool_name: str) -> str: ...
```

不要在冲突时自动覆盖。需要 suffix 的策略可以留到 Phase 2；Phase 1 建议 skip + warning。

- [x] **Step 4: 实现 `schema.py`**

建议接口：

```python
@dataclass(frozen=True)
class SchemaConversionResult:
    parameters: dict[str, object] | None
    required: list[str]
    warnings: tuple[str, ...] = ()

def convert_input_schema(raw_schema: object) -> SchemaConversionResult: ...
```

转换结果供 `ToolDef(parameters=..., required=...)` 使用。

- [x] **Step 5: 实现 `result.py`**

建议接口：

```python
def render_mcp_tool_result(result: object, *, max_chars: int) -> str: ...
```

只输出文本；不要在 Phase 1 支持图片渲染、resource fetch 或 structured output 直通。

- [x] **Step 6: 运行聚焦测试**

Run:

```powershell
pytest tests/test_mcp_naming_schema.py tests/test_mcp_result.py -q
```

Expected: PASS。

