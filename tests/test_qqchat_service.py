from xcode_cli.qqchat.service import QQChatService


class FakeGateway:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.on_event = None

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, conversation_key, turn, *, tool_scope=None):
        self.calls.append((conversation_key, turn, tool_scope))
        return type("Result", (), {"text": "assistant reply", "session_id": "session-1", "error": None})()


class FakeReplyClient:
    def __init__(self):
        self.calls = []

    def send_text_reply(self, target, *, content, msg_id, msg_seq):
        self.calls.append((target, content, msg_id, msg_seq))


def _c2c_payload(message_id="msg-1"):
    return {
        "op": 0,
        "t": "C2C_MESSAGE_CREATE",
        "id": "event-1",
        "d": {"id": message_id, "content": "你好", "author": {"user_openid": "user-openid"}},
    }


def test_start_is_idempotent():
    gateway = FakeGateway()
    service = QQChatService(gateway=gateway, runner=FakeRunner(), reply_client=FakeReplyClient())

    service.start()
    service.start()

    assert gateway.started == 1
    assert service.status()["state"] == "running"


def test_stop_closes_gateway():
    gateway = FakeGateway()
    service = QQChatService(gateway=gateway, runner=FakeRunner(), reply_client=FakeReplyClient())

    service.start()
    service.stop()

    assert gateway.stopped == 1
    assert service.status()["state"] == "stopped"


def test_handle_event_runs_external_turn_and_replies():
    runner = FakeRunner()
    replies = FakeReplyClient()
    service = QQChatService(gateway=FakeGateway(), runner=runner, reply_client=replies)

    service.handle_gateway_event(_c2c_payload())

    assert runner.calls[0][0] == "qq:c2c:user-openid"
    assert runner.calls[0][2].visible_tools == ("read_file", "grep", "glob", "task_list")
    assert runner.calls[0][2].execution_allowlist == ("read_file", "grep", "glob", "task_list")
    assert runner.calls[0][2].remote_approval is False
    assert replies.calls[0][1] == "assistant reply"
    assert replies.calls[0][2] == "msg-1"


def test_duplicate_event_does_not_call_runner_twice():
    runner = FakeRunner()
    service = QQChatService(gateway=FakeGateway(), runner=runner, reply_client=FakeReplyClient())

    service.handle_gateway_event(_c2c_payload("msg-1"))
    service.handle_gateway_event(_c2c_payload("msg-1"))

    assert len(runner.calls) == 1
