# `/resume` 恢复后最近对话渲染设计

> 本文定义 `/resume` 成功恢复 session 后，在终端中展示最新 checkpoint 之后用户与助手最近对话记录的增量能力。当前任务只写 spec 和 plan，不直接修改功能代码。

## 背景

当前 `/resume` 选中 session 后只打印恢复摘要：

- 是否从 checkpoint 恢复。
- 恢复消息数。
- 估算 token。
- 最近一条用户输入。

这能证明 `_history` 已恢复，但用户看不到“这次 session 最近聊到了哪里”。如果 session 曾经 compact，真正对继续工作最有帮助的是最新 checkpoint 之后的用户输入和助手最终回复。用户希望 resume 后直接看到这些最近对话，而不是只看到一条 `Latest user input`。

## 目标

- `/resume` 成功恢复后，在终端中渲染最新 checkpoint 之后的所有 user/assistant 对话。
- user 内容使用 transcript 中的 UI/display 内容，不使用 `metadata.model_content`，避免把 skill hidden prompt 或展开后的长 prompt 刷给用户。
- assistant 内容只展示最终文本回复；跳过只有 `tool_calls`、没有文本 `content` 的 assistant 中间消息。
- 跳过 tool result、system checkpoint summary、`skill_invocation` audit event 等非对话事件。
- 不改变 `SessionResumeBuilder` 当前构造 LLM `_history` 的语义；该功能只影响用户可见渲染。
- 非 TTY 和 TTY `/resume` 都应在恢复成功后看到同样的最近对话记录。

## 非目标

- 不做 CLI `--resume` / `--continue`。
- 不改变 transcript schema。
- 不实现 rollback/fork。
- 不把 tool 调用详情、tool result 或压缩 summary 全量展示给用户。
- 不重新运行 LLM，也不把渲染内容写回 session transcript。

## 数据来源

第一版从选中 session 的 transcript JSONL 读取事件。

规则：

- 如果存在 `compaction_checkpoint`，以最新一条 checkpoint 为边界，只收集其后的 `message` events。
- 如果不存在 checkpoint，收集 transcript 中所有 `message` events。
- 只保留 `role in {"user", "assistant"}` 的消息。
- user 消息保留 event 原始 `content`，即 UI 可见输入。
- assistant 消息仅当 `content` 是非空字符串时保留。
- 对于 skill prompt command，transcript 的 user event 可能带 `metadata.model_content`；UI replay 必须忽略它，只显示 `/skill-name args` 这样的 display content。

建议新增 UI 专用数据结构，避免和模型 history 混用：

```python
@dataclass(frozen=True)
class ResumeReplayMessage:
    role: str
    content: str
```

建议 helper：

```python
def build_resume_replay_messages(transcript_path: Path) -> list[ResumeReplayMessage]:
    ...
```

## 渲染设计

`ResumeCommandService.run()` 在 `SessionResumeBuilder.build()` 成功且返回 `ResumeResult` 后，读取 replay messages 并渲染：

```text
Recent conversation since checkpoint:

you
  ...

assistant
  ...
```

实现可以复用 `ShellUI` 的用户/助手 bubble，也可以在 `ResumeCommandService` 内部用轻量 Rich 文本渲染。推荐优先保持小改动：

- 新增 `_render_recent_conversation(messages)`。
- 使用固定标题 `Recent conversation since checkpoint:`。
- 每条消息按 role 分块显示。
- 内容使用 `markup=False` 或 `Text`，避免用户输入中的 `[xxx]` 被 Rich 当作 markup。
- 不截断消息内容；这是用户明确要求“checkpoint 后的所有用户和助手对话”。如后续发现过长影响体验，再单独设计折叠或配置。

无可展示消息时不报错，可打印：

```text
No user/assistant messages after the latest checkpoint.
```

## 边界

- 该 replay 是给人看的 UI 摘要，不参与 LLM `_history`。
- `SessionResumeBuilder` 仍然可以为了 token budget 裁剪模型 history；UI replay 第一版按 transcript checkpoint 边界展示，不受 token budget 裁剪影响。
- 如果 transcript 中 checkpoint 后有大量消息，第一版仍按用户要求全部展示；真实终端体验需要在手工验收中观察。
- 如果 assistant 最后一轮正在 tool call 中断状态，只有 tool_call 中间消息且没有最终 assistant 文本，则只展示已有 user 消息，不生成占位回复。

## 测试要求

本轮属于 P1 用户可见行为，session resume 属于核心状态路径，测试按 P0 认真覆盖数据边界。

必须补自动化测试：

- 有 checkpoint 时，只 replay 最新 checkpoint 之后的 user/assistant 文本。
- 无 checkpoint 时，replay transcript 中的 user/assistant 文本。
- assistant tool_call-only 消息不展示，后续 assistant final text 展示。
- tool message、system message、`skill_invocation` event 不展示。
- user skill invocation 只展示 display content，不展示 `metadata.model_content`。
- `/resume` 成功后会调用最近对话渲染；失败、取消、无 session 不渲染。
- replay 渲染不修改返回的 `history`，也不追加 transcript event。

建议验证命令：

```powershell
python -m py_compile src\xcode_cli\core\conversation\resume.py src\xcode_cli\core\session_resume.py
pytest tests\test_resume.py tests\test_agent_resume_command.py tests\test_session_resume.py -q
git diff --check
```

## 手工验收

PowerShell/cmd.exe 都应补记录：

- 准备一个有 checkpoint 的 session，checkpoint 后至少包含两轮 user/assistant 对话。
- 输入 `/resume`，选择该 session。
- 确认恢复摘要之后能看到 checkpoint 后的所有 user/assistant 对话。
- 确认 tool result 不出现在 replay 中。
- 确认 skill prompt command 只显示用户输入的 `/skill args`，不显示展开后的 hidden prompt。

未完成真实 Windows 手工验收时，只能声明自动化覆盖和本地渲染逻辑通过，不能声称终端体验已经完整验收。
