from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from xcode_cli.qqchat.events import QQ_EVENT_C2C_MESSAGE_CREATE, QQ_EVENT_GROUP_AT_MESSAGE_CREATE


QQ_API_BASE_URL = "https://api.sgroup.qq.com"
GROUP_AND_C2C_INTENTS = 1 << 25


def build_identify_payload(access_token: str, *, intents: int = GROUP_AND_C2C_INTENTS) -> dict[str, Any]:
    return {
        "op": 2,
        "d": {
            "token": f"QQBot {access_token}",
            "intents": intents,
            "shard": [0, 1],
            "properties": {
                "os": "windows",
                "browser": "xcode",
                "device": "xcode",
            },
        },
    }


def build_heartbeat_payload(seq: int | None) -> dict[str, Any]:
    return {"op": 1, "d": seq}


def build_resume_payload(access_token: str, *, session_id: str, seq: int | None) -> dict[str, Any]:
    return {
        "op": 6,
        "d": {"token": f"QQBot {access_token}", "session_id": session_id, "seq": seq},
    }


class UrllibGatewayTransport:
    def get_json(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        timeout: int = 10,
    ) -> tuple[int, object]:
        request = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, _decode_json_response(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _decode_json_response(exc.read())


class QQGatewayClient:
    def __init__(
        self,
        access_token_getter: Callable[[], str],
        *,
        transport=None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._access_token_getter = access_token_getter
        self._transport = transport or UrllibGatewayTransport()
        self._on_event = on_event
        self._on_status = on_status
        self._seq: int | None = None
        self._session_id: str | None = None
        self._last_access_token = ""
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._websocket_app = None

    @property
    def seq(self) -> int | None:
        return self._seq

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def fetch_gateway_url(self) -> str:
        access_token = self._get_access_token()
        headers = {"Authorization": f"QQBot {access_token}"}
        try:
            status, body = self._transport.get_json(f"{QQ_API_BASE_URL}/gateway", headers=headers, timeout=10)
        except Exception as exc:
            raise RuntimeError(f"QQ gateway request failed: {self._sanitize(str(exc))}") from exc

        if not 200 <= status < 300:
            reason = self._safe_reason(body)
            raise RuntimeError(f"QQ gateway request failed with status {status}: {reason}")
        if not isinstance(body, Mapping) or not isinstance(body.get("url"), str):
            raise RuntimeError("QQ gateway response missing websocket URL")
        return body["url"]

    def handle_payload(self, payload: dict[str, Any]) -> None:
        seq = payload.get("s")
        if isinstance(seq, int):
            self._seq = seq

        event_type = payload.get("t")
        if event_type == "READY":
            data = payload.get("d")
            if isinstance(data, Mapping) and isinstance(data.get("session_id"), str):
                self._session_id = data["session_id"]

        if payload.get("op") == 0 and event_type in {QQ_EVENT_C2C_MESSAGE_CREATE, QQ_EVENT_GROUP_AT_MESSAGE_CREATE}:
            if self._on_event is None:
                return
            try:
                self._on_event(payload)
            except Exception as exc:
                self._emit_status(f"QQ gateway event callback failed: {self._sanitize(str(exc))}")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        gateway_url = self.fetch_gateway_url()

        import websocket  # type: ignore[import-not-found]

        def on_open(ws) -> None:
            access_token = self._get_access_token()
            if self._session_id:
                payload = build_resume_payload(access_token, session_id=self._session_id, seq=self._seq)
            else:
                payload = build_identify_payload(access_token)
            ws.send(json.dumps(payload))

        def on_message(ws, message: str) -> None:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError as exc:
                self._emit_status(f"QQ gateway received invalid JSON: {exc.msg}")
                return
            if not isinstance(payload, dict):
                self._emit_status("QQ gateway received non-object payload")
                return
            self.handle_payload(payload)
            if payload.get("op") == 10:
                data = payload.get("d")
                if isinstance(data, Mapping):
                    interval = data.get("heartbeat_interval")
                    if isinstance(interval, (int, float)):
                        self._start_heartbeat(ws, float(interval) / 1000.0)

        def on_error(_ws, error: object) -> None:
            self._emit_status(f"QQ gateway websocket error: {self._sanitize(str(error))}")

        def on_close(_ws, _status_code, _message) -> None:
            self._emit_status("QQ gateway websocket closed")

        self._websocket_app = websocket.WebSocketApp(
            gateway_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        def run() -> None:
            try:
                self._websocket_app.run_forever()
            except Exception as exc:
                self._emit_status(f"QQ gateway run loop failed: {self._sanitize(str(exc))}")

        self._thread = threading.Thread(target=run, name="qq-gateway", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._websocket_app is not None:
            try:
                self._websocket_app.close()
            except Exception as exc:
                self._emit_status(f"QQ gateway close failed: {self._sanitize(str(exc))}")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _start_heartbeat(self, ws, interval_seconds: float) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        def run() -> None:
            while not self._stop_event.wait(interval_seconds):
                try:
                    ws.send(json.dumps(build_heartbeat_payload(self._seq)))
                except Exception as exc:
                    self._emit_status(f"QQ gateway heartbeat failed: {self._sanitize(str(exc))}")
                    return

        self._heartbeat_thread = threading.Thread(target=run, name="qq-gateway-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def _get_access_token(self) -> str:
        access_token = self._access_token_getter()
        self._last_access_token = access_token
        return access_token

    def _safe_reason(self, body: object) -> str:
        if isinstance(body, Mapping):
            for key in ("message", "msg", "error_description", "error"):
                value = body.get(key)
                if value:
                    return self._sanitize(str(value))[:200]
        return "request rejected"

    def _sanitize(self, message: str) -> str:
        if self._last_access_token:
            message = message.replace(self._last_access_token, "<redacted>")
        return message

    def _emit_status(self, message: str) -> None:
        if self._on_status is None:
            return
        try:
            self._on_status(message)
        except Exception:
            return


def _decode_json_response(data: bytes) -> object:
    if not data:
        return {}
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {"message": data.decode("utf-8", errors="replace")[:200]}
