from xcode_cli.qqchat.gateway import (
    GROUP_AND_C2C_INTENTS,
    QQGatewayClient,
    build_heartbeat_payload,
    build_identify_payload,
    build_resume_payload,
)


class FakeGatewayTransport:
    def __init__(self):
        self.calls = []

    def get_json(self, url, headers=None, timeout=10):
        self.calls.append((url, headers or {}, timeout))
        return 200, {"url": "wss://api.sgroup.qq.com/websocket/"}


def test_group_and_c2c_intents_bitmask():
    assert GROUP_AND_C2C_INTENTS == 1 << 25


def test_fetch_gateway_url_calls_openapi_gateway():
    transport = FakeGatewayTransport()
    client = QQGatewayClient(access_token_getter=lambda: "token", transport=transport)

    assert client.fetch_gateway_url() == "wss://api.sgroup.qq.com/websocket/"

    url, headers, _timeout = transport.calls[0]
    assert url == "https://api.sgroup.qq.com/gateway"
    assert headers["Authorization"] == "QQBot token"


def test_identify_payload_uses_qqbot_token_and_intents():
    payload = build_identify_payload("token")

    assert payload["op"] == 2
    assert payload["d"]["token"] == "QQBot token"
    assert payload["d"]["intents"] == 1 << 25
    assert payload["d"]["shard"] == [0, 1]
    assert payload["d"]["properties"]["os"] == "windows"


def test_heartbeat_payload_uses_latest_seq_or_null():
    assert build_heartbeat_payload(None) == {"op": 1, "d": None}
    assert build_heartbeat_payload(42) == {"op": 1, "d": 42}


def test_resume_payload_uses_session_id_and_seq():
    payload = build_resume_payload("token", session_id="session-1", seq=99)

    assert payload == {
        "op": 6,
        "d": {"token": "QQBot token", "session_id": "session-1", "seq": 99},
    }


def test_handle_ready_saves_session_and_seq():
    client = QQGatewayClient(access_token_getter=lambda: "token", transport=FakeGatewayTransport())

    client.handle_payload({"op": 0, "s": 7, "t": "READY", "d": {"session_id": "session-1"}})

    assert client.session_id == "session-1"
    assert client.seq == 7


def test_dispatch_event_is_forwarded_to_callback():
    seen = []
    client = QQGatewayClient(
        access_token_getter=lambda: "token",
        transport=FakeGatewayTransport(),
        on_event=seen.append,
    )
    payload = {"op": 0, "s": 8, "t": "C2C_MESSAGE_CREATE", "d": {"id": "msg-1"}}

    client.handle_payload(payload)

    assert client.seq == 8
    assert seen == [payload]


def test_event_callback_error_is_reported_without_raising():
    statuses = []

    def fail(_payload):
        raise RuntimeError("callback failed")

    client = QQGatewayClient(
        access_token_getter=lambda: "token",
        transport=FakeGatewayTransport(),
        on_event=fail,
        on_status=statuses.append,
    )

    client.handle_payload({"op": 0, "s": 9, "t": "C2C_MESSAGE_CREATE", "d": {"id": "msg-1"}})

    assert client.seq == 9
    assert "callback failed" in statuses[0]


def test_gateway_error_masks_token():
    class ErrorTransport(FakeGatewayTransport):
        def get_json(self, url, headers=None, timeout=10):
            return 401, {"message": "bad secret-token"}

    client = QQGatewayClient(access_token_getter=lambda: "secret-token", transport=ErrorTransport())

    try:
        client.fetch_gateway_url()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "secret-token" not in message
    assert "401" in message
