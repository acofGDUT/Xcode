# Model-Invocable Skills Phase 2 Design

> 本文档定义 xcode skills Phase 2：模型可主动调用 skills。Phase 2 建立 compact skill listing、SkillTool 和共享 skill invocation 服务；不实现 fork、hooks、remote skills、skill search、bundled/plugin skills。

## 背景

Phase 1 已完成项目内 skill 目录包的手动调用：

```text
.xcode/skills/<skill-name>/SKILL.md
  -> SkillLoader
  -> user-invocable skill 注册为 /skill-name prompt command
  -> SlashCommandDispatcher
  -> UserTurnInput(display_content="/review args", model_content=展开后的 skill prompt)
  -> 普通 LLM/tool loop
```

Phase 2 的目标不是新增另一套 skill 语义，而是把 Phase 1 的加载、展开、metadata、allowed-tools 和 session/resume 能力抽成模型也能复用的核心服务。slash command 只是 skill 的用户入口；SkillTool 是 skill 的模型入口。

## 主流标准对齐

Claude Code 和 Codex skills 的共同设计方向是 progressive disclosure：

1. 模型常驻上下文只看到轻量 metadata。
2. metadata 主要包含 name、description、when_to_use。
3. 完整 `SKILL.md` body 只在 skill 被触发时加载。
4. `user-invocable` 控制用户能否通过 slash command 手动调用。
5. `disable-model-invocation` 控制模型能否通过 SkillTool 主动调用。
6. `allowed-tools` 采用 Claude-compatible 语义：表示 skill 声明需要/允许/可预授权的工具集合，不是 exhaustive whitelist；当前 Xcode 解析、归一化并记录它，但不靠它收窄工具可见性。

Phase 2 必须保留这些语义，尤其不能把“存在于 slash command registry”当成模型可调用的前置条件。

## 目标

- 模型能在 system reminder 中看到 compact skill listing。
- listing 只包含 skill id、description、when_to_use。
- listing 不包含完整 `SKILL.md` body，不包含 allowed-tools/hooks/paths/argument-hint。
- 模型能调用 `SkillTool(skill, args)` 主动加载 skill。
- `SkillTool` 复用 Phase 1 prompt expansion、metadata、allowed-tools 和 session/resume 逻辑。
- `user-invocable: false` 但 `disable-model-invocation: false` 的 skill 可被模型调用。
- `disable-model-invocation: true` 的 skill 不可被模型调用。
- `context: fork` 的 skill 在 Phase 2 不可被模型调用。
- SkillTool 不允许调用普通 built-in slash commands。
- SkillTool 成功加载 skill 后，本 user turn 剩余 LLM loop 不再暴露 `skill` 工具，避免递归调用。
- 完整 skill prompt 不展示为用户 transcript 内容。

## 非目标

- 不实现 `context: fork` 子 agent。
- 不执行 hooks。
- 不实现 remote skills、managed skills、plugin skills 或 MCP skills。
- 不实现 skill search/ranking，只做稳定排序和预算截断。
- 不改变 Phase 1 手动 `/skill-name` 的用户可见行为。

## 核心边界

### SkillCatalog

`SkillCatalog` 是 Phase 2 的 skill 查询中心。它从 `SkillLoader` 的结果构建，保存所有加载成功的 project skills。

职责：

- `find(name: str) -> Skill | None`，允许调用方传入 `review` 或 `/review`。
- `model_invocable_skills() -> list[Skill]`，排除 `disable-model-invocation: true`、`context: fork` 和 built-in command 冲突。
- `user_invocable_skills() -> list[Skill]`，只返回 `user-invocable: true` 且无 built-in command 冲突的 skill。
- `validate_model_invocation(name)` 返回清晰错误，不抛出到 agent 主循环。

`user-invocable` 和 `disable-model-invocation` 是两个独立开关：

| 字段组合 | slash command | SkillTool |
|----------|---------------|-----------|
| `user-invocable: true`, `disable-model-invocation: false` | 可以 | 可以 |
| `user-invocable: false`, `disable-model-invocation: false` | 不可以 | 可以 |
| `user-invocable: true`, `disable-model-invocation: true` | 可以 | 不可以 |
| `context: fork` | Phase 1 手动调用提示不支持 | Phase 2 拒绝 |

### SkillInvocationService

`SkillInvocationService` 复用 Phase 1 prompt expansion，但不依赖 slash command。

输入：

```python
skill_name: str
args: str | None
source: Literal["user", "model"]
```

输出：

```python
SkillInvocation(
    display_content: str,
    model_content: str,
    model_metadata: dict[str, object],
    audit_metadata: dict[str, object],
)
```

metadata 分成两类，避免 session event 重复保存完整 prompt：

- `model_metadata` 用于 user slash command 路径，允许包含 `model_content`，保证 Phase 1 `/resume` 可以把隐藏 prompt 恢复为 user message。
- `audit_metadata` 用于 SkillTool 路径和额外 `skill_invocation` event，不包含完整 prompt，只记录审计和复现索引。

`model_metadata` 必须包含：

```json
{
  "kind": "skill_invocation",
  "source": "user|model",
  "skill": "review",
  "args": "src/foo.py",
  "source_path": "D:/Xcode/.xcode/skills/review/SKILL.md",
  "skill_source_hash": "sha256:...",
  "allowed_tools": ["read_file", "grep"],
  "model_content": "展开后的 skill prompt"
}
```

`audit_metadata` 必须包含：

```json
{
  "kind": "skill_invocation",
  "source": "user|model",
  "skill": "review",
  "args": "src/foo.py",
  "source_path": "D:/Xcode/.xcode/skills/review/SKILL.md",
  "skill_source_hash": "sha256:...",
  "allowed_tools": ["read_file", "grep"]
}
```

`allowed_tools` 只有在 skill 声明 `allowed-tools` 时才出现，值为归一化后的工具名列表。它是 metadata，不是运行时工具白名单。

### SkillTool

新增模型工具 `skill`。

Schema：

```json
{
  "skill": "review",
  "args": "src/foo.py"
}
```

校验规则：

- `skill` 非空。
- 允许去掉开头 `/`。
- skill 必须存在于 `SkillCatalog`。
- 不能是普通 built-in command。
- `disable-model-invocation != true`。
- `context != fork`。
- 不要求 skill 是 visible slash command。

调用行为：

1. 通过 `SkillInvocationService.invoke_for_model()` 展开 skill。
2. 返回模型可见 tool result，包含 loaded skill marker 和完整 skill prompt。
3. tool result 不直接渲染完整 prompt 到 UI，只显示摘要，例如 `loaded skill review`。
4. 将 skill 的 `allowed_tools` 作为 permission/audit metadata 保存，不作为 tool schemas 或 execution 白名单。
5. 成功加载 skill 后，本 user turn 剩余 LLM loop 不再暴露 `skill` 工具，避免递归调用 SkillTool；即使该 skill 没有声明 `allowed-tools` 也必须禁用 `skill` 工具。
6. SkillTool 是 tool batch barrier；同一 assistant response 中排在 SkillTool 后面的 sibling tool calls 必须被拒绝，要求模型在 loaded skill prompt 生效后的下一步再调用。
7. 写入 session skill invocation audit metadata，支持 resume/compact。

### Loaded Skill Marker

SkillTool 返回内容必须带 marker，避免模型重复调用同一个 skill：

```text
<xcode_loaded_skill name="review" source="model">
...展开后的 skill prompt...
</xcode_loaded_skill>
```

system guidance 必须告诉模型：

- 当当前 turn 已存在 loaded skill marker 时，直接遵循已加载 skill，不要再次调用 SkillTool。
- 只有当 available skill clearly matches 用户任务时才调用。
- 弱匹配或猜测匹配不要调用。

实现层也必须兜底：SkillTool 成功返回 loaded skill marker 后，后续 tool schema 过滤和 execution 层都必须排除 `skill` 工具，不能只依赖 prompt guidance；同批 sibling tools 也必须经过 barrier，不得在 skill prompt 生效前继续执行。

## Skill Listing 预算

Phase 2 采用接近 Claude Code 的 listing 预算规则：

```python
SKILL_BUDGET_CONTEXT_PERCENT = 0.01
CHARS_PER_TOKEN = 4
DEFAULT_CHAR_BUDGET = 8_000
MAX_LISTING_DESC_CHARS = 250
```

预算计算：

```text
如果 config.max_tokens 可用：
  char_budget = int(max_tokens * SKILL_BUDGET_CONTEXT_PERCENT * CHARS_PER_TOKEN)
否则：
  char_budget = DEFAULT_CHAR_BUDGET
```

xcode 当前默认 `max_tokens=128000`，因此默认 listing 预算约为：

```text
128000 * 0.01 * 4 = 5120 chars
```

格式化策略：

1. 候选 skill 稳定按 skill id 排序。
2. skill id 来自 `.xcode/skills/<skill-name>` 目录名，也是 SkillTool 的 `skill` 入参；frontmatter `name` 只作为 display name，不作为调用 id。
3. 先尝试完整输出 `skill id + description + when_to_use`。
4. 如果超过预算，每条 skill 的 `description + when_to_use` 截断到 `MAX_LISTING_DESC_CHARS`。
5. 如果仍超过预算，退化为只显示 skill id。
6. 如果 name-only 仍超过预算，只保留预算内条目，并追加 omitted count。
7. listing 不包含完整 body、allowed-tools、hooks、paths、argument-hint、source_path 或 hash。

Phase 2 暂无 bundled skills，因此不实现 bundled 优先级；保留代码结构以便未来增加 source priority。

## System Prompt Guidance

system prompt 新增一个 skills reminder section，仅当存在 model-invocable skills 时注入。

内容包括：

- Available skills 列表。
- 调用 `skill` tool 的规则。
- 不要弱匹配调用。
- 不要猜 skill 名。
- 不要用 SkillTool 调 built-in commands。
- 已有 loaded skill marker 时不重复调用。

## allowed-tools 语义

xcode 的 `allowed-tools` 与 Claude Code 对齐：它是 skill 声明的工具需求/允许/可预授权集合，不是收窄工具集的白名单：

- SkillTool 加载 skill 后，当前 turn 后续 LLM request 沿用默认工具集合，但必须排除 `skill` 工具，防止递归调用。
- `allowed-tools` 只用于 permission hint / audit metadata / 未来 trust policy，不用于当前 tool schemas 或 execution 白名单。
- 如果后续需要严格限制工具可见性，应设计独立字段，例如 `tool-scope`、`visible-tools` 或 `restricted-tools`，不要复用 Claude skill 的 `allowed-tools`。
- PermissionManager 的 deny/ask/allow 仍然生效。
- 即使 skill 声明 `write_file`、`edit_file`、`run_shell`，也不能自动绕过现有审批；是否预授权必须由独立 trust policy 明确设计。

## Session / Resume / Compact

Phase 2 采用直接保存模型可见内容的策略：

- tool message 保存 loaded skill marker + expanded prompt，用于 resume 后恢复模型上下文。
- 额外写入 `skill_invocation` event，保存 audit metadata 和 allowed_tools，不保存完整 prompt，不需要用户 UI 展示完整 prompt。
- `/compact` 使用当前 `_history`，其中已经包含 tool message，因此 compact 能保留 skill 指令上下文。

## 验收标准

- 模型 system prompt 能看到 compact skill listing。
- listing 不包含完整 `SKILL.md` body。
- listing 不包含 allowed-tools/hooks/paths/argument-hint。
- listing 按 1% context 预算生成，支持 250 chars 单 skill summary 截断和 name-only 降级。
- 模型能调用 `skill(skill, args)`。
- SkillTool 能调用 `user-invocable: false` 但 `disable-model-invocation: false` 的 skill。
- SkillTool 拒绝 `disable-model-invocation: true`。
- SkillTool 拒绝 `context: fork`。
- SkillTool 拒绝 built-in command 名称。
- SkillTool 复用 Phase 1 prompt expansion，支持 `$ARGUMENTS` 和 `${XCODE_SKILL_DIR}`。
- SkillTool 成功加载 skill 后，本 user turn 后续 tool schemas 不再包含 `skill`。
- SkillTool 调用后完整 prompt 不作为用户消息显示。
- SkillTool 调用后 allowed-tools 不收窄当前 turn 后续工具 schemas 和执行层，只作为 permission/audit metadata 保留。
- SkillTool 是 barrier，同批后续 sibling tool calls 不会执行。
- `skill_invocation` audit event 不包含完整 `model_content`。
- session/resume/compact 保留 skill invocation 上下文。
