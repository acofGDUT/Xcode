# QQchat 多段回复设计

状态：代码实现和自动化回归已完成；真实 QQ 平台单聊/群聊多段回复验收未执行。
日期：2026-06-15
风险层级：P1。该改动影响 QQchat 外部入口的用户可见回复行为，但不改变工具权限、LLM 调用、session/history 或 QQ 鉴权边界。

## 背景

当前 QQchat 在发送被动回复前使用 `max_reply_chars` 截断 assistant 文本，并且只调用一次 QQ 被动回复接口。长回答会丢失尾部内容。用户已确认目标行为：按 `max_reply_chars` 自动切段，连续发送多条 QQ 被动回复，`msg_seq` 递增。

## 目标行为

- `max_reply_chars > 0` 时，QQchat 将回复文本切成若干段，每段长度不超过 `max_reply_chars`。
- 每段都调用一次 `send_text_reply()`。
- 第一段使用当前 dedupe 分配的 `msg_seq`。
- 后续段依次使用 `msg_seq + 1`、`msg_seq + 2`。
- `max_reply_chars <= 0` 时保留现有语义：不切段，整段发送一次。
- 空回复不发送。
- external turn error 仍发送安全中文 fallback；fallback 如超过限制，也走同一分段逻辑。

## 非目标

- 不改变 QQ 平台鉴权、gateway reconnect、事件 normalize、dedupe 或 timeout 策略。
- 不改变 LLM 生成长度和 prompt。
- 不新增远程危险工具审批能力。
- 不引入 asyncio。
- 不实现主动推送、富媒体或跨窗口继续发送。

## 设计

在 `src/xcode_cli/qqchat/service.py` 中用分段 helper 替换 `_truncate_reply()` 的单段截断语义。`_process_message()` 获取 `reply_text` 后生成 `reply_parts`，逐段调用 `reply_client.send_text_reply()`，并用 `msg_seq + index` 发送。

`sent_replies` 统计实际成功发送的 QQ 回复条数，而不是原始 user message 数。若某一段发送失败，当前 `_process_message()` 的外层异常处理会记录 `last_error`，后续段不会继续发送；这保持现有“发送失败不冒泡打崩 worker”的边界。

## 验收

自动化回归：

```powershell
pytest tests/test_qqchat_service.py::test_reply_content_is_split_into_multiple_messages_with_incrementing_msg_seq -q
pytest tests/test_qqchat_service.py -q
python -m compileall -q src
```

完成后可按风险选择补全量：

```powershell
pytest -q
```

真实 QQ 平台验收仍需另行记录，自动化测试不能替代真实单聊/群聊平台验证。
