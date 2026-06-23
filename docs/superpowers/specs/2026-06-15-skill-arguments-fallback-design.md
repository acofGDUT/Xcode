# Skill Arguments Fallback Injection Design

> 状态：代码实现和自动化回归已完成。
> 日期：2026-06-15

## 背景

Xcode 当前已经支持用户用项目 skill 作为 slash prompt command：

```text
/review src/foo.py
```

调用链会解析 slash command 后面的文本为 `args`，并通过 `SkillInvocationService` 传给 `SkillPromptExpander`。如果 `SKILL.md` 正文显式包含 `$ARGUMENTS`，当前实现会把该占位符替换为用户输入的附加说明。

问题是：如果 skill 正文没有写 `$ARGUMENTS`，用户输入的附加说明只会进入 invocation metadata，不会进入 LLM 可见的 `model_content`。例如：

```text
/skill1 解释一下这个技能
```

如果 `skill1/SKILL.md` 没有 `$ARGUMENTS`，模型实际只看到 skill 正文，看不到“解释一下这个技能”。这会让用户感觉 `/skill-name 后面的说明` 没有被理解。

Claude Code 的对应语义是：当用户传入 args 但 skill 正文没有参数占位符时，把 args 作为兜底 `ARGUMENTS:` 块追加到 skill prompt 末尾。本设计只对齐这一项兜底逻辑。

## 目标

- 当用户或模型调用 skill 且传入非空 args 时，确保 args 一定进入展开后的 skill prompt。
- 保留现有 `$ARGUMENTS` 替换行为。
- 如果 skill 正文没有任何受支持的参数占位符，则在 prompt 末尾追加一个稳定、可读的参数块。
- 用户手动 slash skill 和模型主动 `skill` tool 调用共享同一语义。
- 保持 session transcript 继续显示原始 `/skill-name args`，LLM history 使用展开后的 hidden/model prompt。

## 非目标

- 不实现 `$ARGUMENTS[0]`、`$ARGUMENTS[1]`。
- 不实现 `$0`、`$1`。
- 不实现 `$foo` 命名参数。
- 不实现 shell-like quoting 或参数数组解析。
- 不新增 skill frontmatter 字段。
- 不改变 `allowed-tools`、`context=fork`、`user-invocable`、`disable-model-invocation` 的语义。
- 不把 args 注入 system prompt 或 skill listing。

## 当前约束

- `SlashCommandDispatcher.dispatch()` 当前用 `command.split()` 提取 head 和 args，args 会被空白归一化。
- `CommandRegistry.create_skill_slash_command()` 会把 args 传给 `SkillInvocationService.invoke_for_user()`。
- `SkillInvocationService` 同时服务用户 slash 调用和模型 `skill` tool 调用。
- `SkillPromptExpander.expand()` 当前只替换 `$ARGUMENTS` 和 `${XCODE_SKILL_DIR}`。
- `AgentRuntime._run_user_turn()` 会把 `turn.model_content` 放入 LLM `_history`，metadata 只用于 transcript/audit，不作为普通消息进入模型上下文。

## 用户可见行为

如果 skill 正文包含 `$ARGUMENTS`：

```markdown
请按照用户要求处理：

$ARGUMENTS
```

用户输入：

```text
/verify 只检查登录模块，不要跑全量测试
```

展开后仍是：

```text
请按照用户要求处理：

只检查登录模块，不要跑全量测试
```

如果 skill 正文不包含 `$ARGUMENTS`，但用户传入 args：

```markdown
请执行验证流程。
```

用户输入：

```text
/verify 只检查登录模块，不要跑全量测试
```

展开后应变为：

```text
请执行验证流程。

ARGUMENTS:
只检查登录模块，不要跑全量测试
```

如果用户没有传入 args，则不追加 `ARGUMENTS:` 块，避免给无参数调用增加噪音。

## 设计

改动集中在 `SkillPromptExpander.expand()`。

推荐规则：

1. 读取原始 skill body。
2. 判断原始 body 是否包含受支持的参数占位符。
3. 对 `$ARGUMENTS` 执行完整 args 替换。
4. 对 `${XCODE_SKILL_DIR}` 执行 skill 目录替换。
5. 如果原始 body 没有参数占位符，且 `args.strip()` 非空，则在最终 prompt 末尾追加：

```text

ARGUMENTS:
<args>
```

本轮“受支持的参数占位符”只包括 `$ARGUMENTS`。这样设计能精确解决当前缺口，同时不暗示 Xcode 已经支持位置参数或命名参数。

建议保留英文标签 `ARGUMENTS:`，理由是：

- 与 Claude Code 兜底语义接近。
- 不依赖项目 UI 语言。
- 技能正文可能是英文或多语言，英文元标签更像协议块。

如果未来要本地化显示，可以另开 spec；本轮不做。

## 安全与可靠性

- args 来自用户输入或模型 `skill` tool 参数，不应作为 trusted instruction 提权；它只是技能 prompt 的一部分。
- 不改变工具权限、审批、blocked tools 或 skill barrier 语义。
- 不把 args 写入 system prompt，避免扩大指令优先级。
- 不改变 transcript 展示：用户仍看到 `/skill-name args`，不会把完整 skill body刷屏显示。
- args 已经会进入 metadata；本改动只是确保模型可见 prompt 中也包含它。

## 兼容性

- 现有包含 `$ARGUMENTS` 的 skill 行为不变。
- 现有没有 `$ARGUMENTS` 且无 args 的 skill 行为不变。
- 现有没有 `$ARGUMENTS` 但用户传了 args 的 skill 会新增 `ARGUMENTS:` 兜底块，这是预期行为变化。
- `metadata["args"]`、`metadata["model_content"]` 和 `skill_source_hash` 继续按现有结构保存。
- `/resume` 仍优先使用 transcript 里的 `metadata.model_content` 恢复 hidden prompt；新行为只影响实施后的新 skill invocation，不迁移旧 transcript。

## 被拒绝的替代方案

- 实现 `$0/$1/$foo/$ARGUMENTS[0]`：超出本轮目标，会引入参数拆分、转义、命名参数语法和兼容性问题。
- 把 args 作为单独 user message 追加到 history：会改变 turn 数量和 transcript/replay 语义，风险大于必要收益。
- 把 args 注入 system prompt：会错误提升用户附加说明的优先级。
- 要求所有 skill 作者手动添加 `$ARGUMENTS`：不能解决已有 skill 的可用性问题，也不符合用户对 `/skill-name 后面说明` 的直觉。
- 追加中文 `用户附加说明：`：可读性好，但与 Claude Code 的 `ARGUMENTS:` 语义不完全一致；本轮优先做最小对齐。

## 验收标准

- `SkillPromptExpander.expand()` 在 body 包含 `$ARGUMENTS` 时仍只替换占位符，不额外追加 `ARGUMENTS:`。
- body 不包含 `$ARGUMENTS` 且 args 非空时，展开 prompt 末尾包含：

```text
ARGUMENTS:
<args>
```

- body 不包含 `$ARGUMENTS` 且 args 为空或全空白时，不追加 `ARGUMENTS:`。
- 用户 slash skill 路径 `/review 解释一下这个技能` 的 `turn_input.model_content` 能包含兜底 args。
- 模型 `skill(skill="review", args="...")` 工具路径返回的 `<xcode_loaded_skill>` 内容能包含兜底 args。
- session transcript 仍保存 display content `/review ...`，并在 `metadata.model_content` 中保存展开后的 prompt。

建议自动化验证：

```text
pytest tests/test_skill_prompt.py tests/test_skill_prompt_command_flow.py tests/test_skill_tool.py tests/test_skill_invocation_service.py -q
```

实现完成后再按影响范围追加：

```text
python -m compileall -q src
pytest -q
```

实际验证结果：

- TDD RED：`pytest tests/test_skill_prompt.py::test_appends_arguments_when_body_has_no_arguments_placeholder tests/test_skill_prompt.py::test_does_not_append_arguments_when_placeholder_was_used tests/test_skill_prompt.py::test_does_not_append_arguments_when_args_are_blank -q`，结果为 `1 failed, 2 passed`，失败原因是无 `$ARGUMENTS` 时尚未追加兜底参数块。
- Expander 回归：`pytest tests/test_skill_prompt.py -q`，`5 passed`。
- Slash command focused 回归：`pytest tests/test_skill_prompt_command_flow.py::test_skill_dispatch_appends_args_when_body_has_no_placeholder -q`，`1 passed`。
- Slash command 文件回归：`pytest tests/test_skill_prompt_command_flow.py -q`，`6 passed`。
- Skill tool focused 回归：`pytest tests/test_skill_tool.py::test_skill_tool_appends_args_when_body_has_no_placeholder -q`，`1 passed`。
- Skill tool 文件回归：`pytest tests/test_skill_tool.py -q`，`4 passed`。
- Focused skill suite：`pytest tests/test_skill_prompt.py tests/test_skill_prompt_command_flow.py tests/test_skill_tool.py tests/test_skill_invocation_service.py -q`，`18 passed`。
- 编译检查：`python -m compileall -q src`，退出码 0。
- 全量回归：`pytest -q`，`565 passed`。
- Whitespace 检查：`git diff --check`，退出码 0；仅输出 Windows LF/CRLF 行尾转换提示。

## 待确认问题

- 暂无。本轮需求明确为只增加 Claude Code 风格的无占位符兜底追加逻辑。
