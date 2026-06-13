from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from xcode_cli.core.llm import LLMClient


def _setup_tmp_xcode_home(tmp_path: Path, monkeypatch) -> Path:
    import xcode_cli.paths

    xcode_dir = tmp_path / ".xcode"
    monkeypatch.setattr(xcode_cli.paths, "XCODE_DIR", xcode_dir, raising=True)
    xcode_dir.mkdir(parents=True, exist_ok=True)
    (xcode_dir / "config.json").write_text(
        json.dumps({"model": "test-model", "api_key": "test-key"}),
        encoding="utf-8",
    )
    for subdir in ("sessions", "skills", "bin"):
        (xcode_dir / subdir).mkdir(parents=True, exist_ok=True)
    return xcode_dir


def test_stream_error_while_iterating_returns_llm_error(tmp_path: Path, monkeypatch) -> None:
    _setup_tmp_xcode_home(tmp_path, monkeypatch)

    class BrokenStream:
        def __iter__(self):
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="partial",
                            tool_calls=None,
                        )
                    )
                ]
            )
            raise RuntimeError(
                "peer closed connection without sending complete message body "
                "(incomplete chunked read)"
            )

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **__: BrokenStream())
            )

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    streamed_tokens: list[str] = []
    response = LLMClient().complete(
        system_prompt="system",
        messages=[],
        tool_schemas=[],
        on_text_token=streamed_tokens.append,
    )

    assert streamed_tokens == ["partial"]
    assert response.tool_calls == []
    assert response.content.startswith("[v0] LLM request failed:")
    assert "incomplete chunked read" in response.content


def test_empty_tool_schemas_omits_tools_and_tool_choice(tmp_path: Path, monkeypatch) -> None:
    _setup_tmp_xcode_home(tmp_path, monkeypatch)
    captured_requests: list[dict] = []

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured_requests.append(kwargs)
            return iter([])

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    LLMClient().complete(system_prompt="system", messages=[], tool_schemas=[])

    assert "tools" not in captured_requests[0]
    assert "tool_choice" not in captured_requests[0]


def test_non_empty_tool_schemas_send_auto_tool_choice(tmp_path: Path, monkeypatch) -> None:
    _setup_tmp_xcode_home(tmp_path, monkeypatch)
    captured_requests: list[dict] = []
    tool_schemas = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured_requests.append(kwargs)
            return iter([])

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    LLMClient().complete(system_prompt="system", messages=[], tool_schemas=tool_schemas)

    assert captured_requests[0]["tools"] == tool_schemas
    assert captured_requests[0]["tool_choice"] == "auto"


def test_request_messages_drop_malformed_tool_calls_before_provider(tmp_path: Path, monkeypatch) -> None:
    _setup_tmp_xcode_home(tmp_path, monkeypatch)
    captured_requests: list[dict] = []

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured_requests.append(kwargs)
            return iter([])

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    messages = [
        {"role": "user", "content": "resume previous session"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "", "type": "function", "function": {"name": "", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "", "content": "old malformed result"},
    ]

    LLMClient().complete(system_prompt="system", messages=messages, tool_schemas=[])

    request_messages = captured_requests[0]["messages"]
    assert not any(message.get("role") == "tool" for message in request_messages)
    assert not any(message.get("tool_calls") for message in request_messages)


def test_streamed_tool_call_without_function_name_is_not_returned(tmp_path: Path, monkeypatch) -> None:
    _setup_tmp_xcode_home(tmp_path, monkeypatch)

    class FakeStream:
        def __iter__(self):
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_missing_name",
                                    function=SimpleNamespace(name="", arguments='{"path":"README.md"}'),
                                )
                            ],
                        )
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **__: FakeStream()))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    response = LLMClient().complete(system_prompt="system", messages=[], tool_schemas=[])

    assert response.tool_calls == []
