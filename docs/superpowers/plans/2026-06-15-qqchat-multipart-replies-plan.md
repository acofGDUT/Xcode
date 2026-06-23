# QQchat Multipart Replies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make QQchat split long assistant replies into multiple passive QQ text replies instead of truncating after `max_reply_chars`.

**Architecture:** Keep QQchat's current synchronous worker and reply client. Replace the single truncation helper with a segmentation helper in `service.py`, and send each segment with an incremented `msg_seq`.

**Tech Stack:** Python 3.10+, pytest, existing QQchat service/reply-client abstractions.

---

### Task 1: Segment QQchat Replies

**Files:**
- Modify: `tests/test_qqchat_service.py`
- Modify: `src/xcode_cli/qqchat/service.py`

- [x] **Step 1: Write the failing test**

Add a focused test showing that a six-character reply with `max_reply_chars=3` sends two messages and increments `msg_seq`:

```python
def test_reply_content_is_split_into_multiple_messages_with_incrementing_msg_seq():
    class LongReplyRunner(FakeRunner):
        def run(self, conversation_key, turn, *, tool_scope=None):
            return type("Result", (), {"text": "abcdef", "session_id": "session-1", "error": None})()

    replies = FakeReplyClient()
    cfg = QQChatConfig(app_id="app", client_secret="secret", max_reply_chars=3)
    service = QQChatService(gateway=FakeGateway(), runner=LongReplyRunner(), reply_client=replies, config=cfg)
    service.start()

    service.handle_gateway_event(_c2c_payload())
    _wait_until_idle(service)
    service.stop()

    assert [call[1] for call in replies.calls] == ["abc", "def"]
    assert [call[3] for call in replies.calls] == [1, 2]
    assert service.status()["sent_replies"] == 2
```

- [x] **Step 2: Verify RED**

Run:

```powershell
pytest tests/test_qqchat_service.py::test_reply_content_is_split_into_multiple_messages_with_incrementing_msg_seq -q
```

Expected: the test fails because current code sends only `["abc"]`.

- [x] **Step 3: Implement minimal code**

In `src/xcode_cli/qqchat/service.py`, replace the `_truncate_reply()` call site with iteration over reply parts:

```python
for index, content in enumerate(_split_reply(reply_text, self._config.max_reply_chars)):
    self._reply_client.send_text_reply(
        message.reply_target,
        content=content,
        msg_id=message.message_id,
        msg_seq=msg_seq + index,
    )
    self._sent_replies += 1
```

Replace `_truncate_reply()` with `_split_reply()`:

```python
def _split_reply(content: str, max_chars: int) -> list[str]:
    if not content:
        return []
    if max_chars <= 0 or len(content) <= max_chars:
        return [content]
    return [content[index : index + max_chars] for index in range(0, len(content), max_chars)]
```

- [x] **Step 4: Verify GREEN**

Run:

```powershell
pytest tests/test_qqchat_service.py::test_reply_content_is_split_into_multiple_messages_with_incrementing_msg_seq -q
pytest tests/test_qqchat_service.py -q
python -m compileall -q src
```

Expected: all commands pass.

- [x] **Step 5: Review docs**

If implementation passes, update the spec status line to:

```markdown
状态：代码实现和自动化回归已完成；真实 QQ 平台单聊/群聊多段回复验收未执行。
```

Do not claim real QQ platform completion without separate manual evidence.
