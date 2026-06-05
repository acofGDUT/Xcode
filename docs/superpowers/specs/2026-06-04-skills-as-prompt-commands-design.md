# Skills As Prompt Commands 设计规格

> 本文档定义 xcode skills 第一阶段的产品边界和架构方案。第一阶段目标是把项目内 `.xcode/skills/<skill-name>/SKILL.md` 加载成 prompt slash command，而不是实现完整 SkillTool、fork agent、hooks 或插件生态。

## 背景目标

xcode 需要加入类似 Claude Code 的 skills 能力，用于把可复用的 agent 行为沉淀为项目内文件。第一阶段采用最小但可扩展的核心模型：

```text
.xcode/skills/<skill-name>/SKILL.md
  -> 磁盘加载
  -> 解析 Claude-style frontmatter
  -> 转成 SlashCommand(kind="prompt", source="skill")
  -> 合并进 slash command registry
  -> 用户输入 /skill-name args
  -> 展开 skill prompt
  -> 作为 model-visible hidden/meta message 进入普通 agent turn
```

这个阶段只支持 xcode 项目目录：

```text
<project>/.xcode/skills/<skill-name>/SKILL.md
```

暂时不自动读取 `.claude/skills`、用户目录、managed skills、bundled skills、plugin skills 或 MCP skills。迁移 Claude skill 时，用户可以把文件复制到 `.xcode/skills/` 并把 `${CLAUDE_SKILL_DIR}` 改成 `${XCODE_SKILL_DIR}`。

主流 Agent Skills 的共同方向是：skill 是一个目录包，`SKILL.md` 负责 metadata、触发描述和入口说明，目录内可以附带 scripts、references、templates、assets 等 supporting files；agent 先看到轻量 metadata，再在需要时加载完整内容，避免把所有 skill 一次性塞进上下文。xcode Phase 1 只实现用户手动调用，但文件格式、metadata、目录结构、权限边界和 session 记录必须为 Phase 2 的模型主动调用留出位置。

## 关键决策

### 1. 删除旧 skill 壳子

现有 `SkillManager` / `skill.json` / `enabled_skills` / system prompt 注入只是早期壳子，不作为兼容目标。Phase 1 应移除旧模型，避免出现两套 skill 语义：

- 不再要求 skill 目录包含 `skill.json`。
- 不再把 enabled skills 的完整 `SKILL.md` 全量注入 system prompt。
- 不再使用 `Config.enabled_skills` 控制 Phase 1 skill 是否注入 prompt。
- CLI / REPL 的 `/skill` 可以保留为查看项目 skills 的入口，但语义应改为基于 `.xcode/skills/*/SKILL.md` 的新 loader。

### 2. skill 是 prompt command，不是 runtime 分支

skill 加载后应成为普通 slash command registry 的一部分：

```python
SlashCommand(
    name=skill_dir_name,
    kind="prompt",
    description=skill.description,
    handler=get_prompt_for_command,
    source="skill",
)
```

命令名使用目录名：

```text
.xcode/skills/review/SKILL.md -> /review
```

frontmatter 里的 `name` 只作为 display name，不作为命令名。

Phase 1 的 `/skill-name` 是 manual invocation layer。它用于先打通加载、展开、权限和 transcript，不代表完整主流 skills 已完成。Phase 2 的 `SkillTool` 和 skill metadata listing 才负责 model-invoked skills。

命令冲突必须有确定策略：

- built-in slash commands 优先，例如 `/help`、`/init`、`/context`、`/skill`。
- 如果 `.xcode/skills/init/SKILL.md` 或 `.xcode/skills/help/SKILL.md` 这类 skill 与 built-in command 冲突，该 skill 仍可加载 metadata，但不得注册为 slash command。
- 冲突应出现在 `/skill validate` 的 notice 中，便于用户重命名目录。

### 3. 完整解析 metadata，分阶段消费

Phase 1 需要解析并保存 Claude-style 字段，但只消费其中一部分。

建议数据结构：

```python
@dataclass(frozen=True)
class Skill:
    name: str
    display_name: str | None
    description: str
    body: str
    root: Path

    allowed_tools: list[str]
    argument_hint: str | None
    argument_names: list[str]
    when_to_use: str | None

    model: str | None
    effort: str | None
    disable_model_invocation: bool
    user_invocable: bool
    context: str | None
    agent: str | None
    paths: list[str]
    hooks: dict[str, Any] | None

    raw_frontmatter: dict[str, Any]
```

Phase 1 立即消费：

| 字段 | 行为 |
|------|------|
| `description` | `/help`、命令补全、`/skill list` 展示 |
| `allowed-tools` | 当前 skill turn 的工具白名单 |
| `argument-hint` | 命令补全展示 |
| `arguments` | 解析保存；第一版不做具名参数替换 |
| `when_to_use` | 解析保存；Phase 2 SkillTool 使用 |
| `user-invocable` | 是否注册为用户可直接调用的 slash command，默认 `true` |
| `disable-model-invocation` | 解析保存；Phase 2 SkillTool 使用 |

`description` 是主流 skill discovery 的核心字段。Phase 1 可以从正文第一行 fallback，但 `/skill validate` 必须把缺失 description 标为 warning，避免后续 Phase 2 的模型发现质量变差。

Phase 1 只解析保存，不执行：

| 字段 | Phase 1 策略 |
|------|--------------|
| `model` | 保存，不切换模型 |
| `effort` | 保存，不改变 reasoning/effort |
| `context: fork` | 保存；用户手动调用时报 unsupported |
| `agent` | 保存，不启动专用 agent |
| `paths` | 保存，不做动态发现或自动激活 |
| `hooks` | 保存，绝不执行 |

## Prompt 展开规则

用户输入：

```text
/review src/foo.py
```

流程：

```text
SlashCommandDispatcher
  -> 找到 skill prompt command
  -> SkillPromptExpander.expand(skill, args)
  -> 替换变量
  -> 返回 UserTurnInput(display_content="/review src/foo.py", model_content=展开后的 skill prompt, metadata=skill 调用信息)
  -> AgentRuntime._run_user_turn()
  -> _run_llm_loop()
```

第一版必须支持：

```text
$ARGUMENTS -> 原始 args 字符串
${XCODE_SKILL_DIR} -> 当前 skill 根目录绝对路径
```

第一版不支持：

```text
${CLAUDE_SKILL_DIR}
具名参数替换
路径条件自动激活
模型主动发现/调用
```

## Skill 目录包与 progressive disclosure

每个 skill 是一个目录包，而不只是一个孤立 markdown 文件：

```text
.xcode/skills/review/
  SKILL.md
  references/
  scripts/
  templates/
  assets/
```

Phase 1 只自动读取 `SKILL.md`。其他 supporting files 不自动加载进 prompt，也不在启动时扫描内容；`SKILL.md` 可以通过 `${XCODE_SKILL_DIR}` 指向这些文件，由模型在 skill prompt 指令下按需使用 `read_file`、`grep`、`run_shell` 等工具读取或执行。这保留了主流 skills 的 progressive disclosure：metadata 轻量发现，完整说明按需加载，参考资料和脚本进一步按需读取。

Phase 1 不执行 scripts，也不信任 hooks。scripts 只有在展开后的 skill prompt 明确要求，并且模型通过正常 `run_shell` 工具调用、经过当前权限系统时，才可能执行。

## UI 与 transcript

skill markdown 正文不应作为普通用户输入刷到 UI transcript 中。用户界面只显示简短调用：

```text
/review src/foo.py
```

模型实际看到的是展开后的 skill prompt。为了支持这一点，`_run_user_turn()` 应从 `str` 参数扩展为轻量结构：

```python
@dataclass(frozen=True)
class UserTurnInput:
    display_content: str
    model_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] | None = None
```

普通用户输入使用：

```python
UserTurnInput(
    display_content=user_input,
    model_content=user_input,
)
```

skill 调用使用：

```python
UserTurnInput(
    display_content="/review src/foo.py",
    model_content=expanded_skill_prompt,
    metadata={
        "kind": "skill_invocation",
        "skill": "review",
        "args": "src/foo.py",
        "source_path": "D:/Xcode/.xcode/skills/review/SKILL.md",
    },
    allowed_tools=["read_file", "grep", "run_shell"],
)
```

transcript 应记录一条可恢复的 skill invocation event。它可以包含展开 prompt 或可恢复引用，但不应把完整 skill markdown 当作普通用户消息展示。

为了避免 `/resume` 后丢失 skill 指令，session event 必须保存模型实际看到的 hidden/model content，或保存足以恢复同一内容的 snapshot。Phase 1 采用更直接的策略：

```json
{
  "type": "message",
  "role": "user",
  "content": "/review src/foo.py",
  "metadata": {
    "kind": "skill_invocation",
    "skill": "review",
    "args": "src/foo.py",
    "source_path": "D:/Xcode/.xcode/skills/review/SKILL.md",
    "model_content": "展开后的 skill prompt",
    "skill_source_hash": "sha256:3f6c1a0d"
  }
}
```

UI 和轻量 user history 使用 `content`。恢复 `_history` 时，如果存在 `metadata.model_content`，应使用它作为该轮 user message 的模型上下文；否则退回 `content`。

## allowed-tools 权限边界

`allowed-tools` 是当前 skill turn 的临时工具白名单。Phase 1 至少要做到两层保护：

1. 传给 LLM 的 tool schemas 只包含白名单工具。
2. tool execution 层再次校验，防止模型或历史状态调用未允许工具。

字段值可以使用 xcode 内部工具名，也可以使用 Claude-style 工具名。解析时应大小写不敏感，并支持逗号分隔、inline list 和 YAML 多行 list。

| frontmatter 值 | xcode 工具 |
|----------------|-----------|
| `read` / `Read` / `read_file` | `read_file` |
| `write` / `Write` / `write_file` | `write_file` |
| `edit` / `Edit` / `edit_file` | `edit_file` |
| `grep` / `Grep` | `grep` |
| `glob` / `Glob` | `glob` |
| `shell` / `bash` / `Bash` / `run_shell` | `run_shell` |
| `task` / `Task` / `dispatch_agent` | `dispatch_agent` |

未知工具名不应导致加载失败，但执行时不会放行。`allowed-tools` 为空或缺失时，表示沿用当前默认工具集合。

xcode 采用保守权限模型：`allowed-tools` 只收窄当前 turn 的可用工具集合，不自动提升权限。即使某个 skill 声明了 `write_file`、`edit_file` 或 `run_shell`，仍必须服从现有 `PermissionManager` 的 session/project/global allow/ask/deny 规则。显式 `deny` 永远优先。

这与 Claude Code 的“skill 激活后可按 allowed-tools 放行”的体验不同，但更符合 xcode 当前安全架构。后续如果要支持“信任某个 skill 后免审”，应单独设计 skill trust policy，而不是把它隐含在 `allowed-tools` 中。

## 错误处理

| 场景 | 行为 |
|------|------|
| skill 目录没有 `SKILL.md` | 跳过该目录 |
| frontmatter YAML 解析失败 | 跳过该 skill，并通过 debug/system notice 显示原因 |
| `description` 缺失 | 从正文第一段或第一行提取 fallback |
| skill 名与 built-in command 冲突 | 加载 metadata，但不注册 slash command；`/skill validate` 显示 notice |
| `user-invocable: false` | 加载 metadata，但不出现在 `/help` / completion，也不能被用户直接执行 |
| `context: fork` | 加载 metadata；用户调用时报 `This skill requires fork execution, which is not supported yet.` |
| `hooks` | 解析保存，不执行 |
| unknown `/skill-name` | 按普通 unknown command 处理 |

## 建议模块边界

| 文件 | 职责 |
|------|------|
| `src/xcode_cli/skills/model.py` | `Skill` / `SkillLoadError` 等纯数据结构 |
| `src/xcode_cli/skills/loader.py` | 从 `.xcode/skills/*/SKILL.md` 加载并解析 metadata |
| `src/xcode_cli/skills/prompt.py` | prompt 变量替换和 unsupported 检查 |
| `src/xcode_cli/skills/validation.py` | skill 规范检查：description 缺失、命令冲突、未知工具、unsupported 字段提示 |
| `src/xcode_cli/core/commands/registry.py` | 合并 built-in commands 与 skill commands |
| `src/xcode_cli/core/commands/slash.py` | 静态 built-in command metadata 和 completion 数据结构 |
| `src/xcode_cli/core/commands/dispatcher.py` | 只负责分发 registry 中的 command |
| `src/xcode_cli/core/turn.py` | `UserTurnInput` 与 turn metadata |
| `src/xcode_cli/core/agent.py` | 注入 registry，复用 `_run_user_turn()` |
| `src/xcode_cli/core/tool_registry.py` | 支持按 allowed tool names 返回 schemas |
| `src/xcode_cli/core/tooling/execution.py` | 执行层支持当前 turn allowed-tools 兜底 |

## 验收标准

- 能从 `.xcode/skills/*/SKILL.md` 加载 skill。
- 能解析 Claude-style frontmatter 并保存 metadata。
- 支持 `allowed-tools: Read, Grep, Glob`、inline list 和多行 list。
- 支持 skill 目录内 references/scripts/templates/assets 等 supporting files，但只按需读取，不自动注入上下文。
- 旧 `skill.json` / `enabled_skills` / system prompt 全量注入路径被移除。
- user-invocable skill 注册成 `SlashCommand(kind="prompt", source="skill")`。
- skill 与 built-in command 冲突时不覆盖 built-in command，并能通过 `/skill validate` 看到 notice。
- `/help` 和 slash completion 能看到 user-invocable skills。
- `user-invocable: false` 不出现在 `/help` 或 completion 中，也不能被用户直接执行。
- `/skill-name args` 能展开 prompt。
- `$ARGUMENTS` / `${XCODE_SKILL_DIR}` 能正确替换。
- `allowed-tools` 能限制当前 agent turn 的 tool schemas 和 tool execution。
- `allowed-tools` 不绕过现有 allow/ask/deny 权限规则。
- skill prompt 不直接污染 UI transcript。
- session/resume 后能知道这个 turn 使用过哪个 skill，并能恢复该 turn 的 hidden/model prompt。
- `context: fork` / `hooks` 等未实现字段不会被静默错误执行。
- focused tests 和全量 `pytest` 通过。

## Phase 2 预留

第二阶段再做模型主动调用：

```text
Skill metadata listing
  -> system reminder / attachment
  -> model sees available skills
  -> model calls SkillTool(skill, args)
  -> SkillTool validates + permission check
  -> expands skill prompt
  -> injects into current turn
```

Phase 2 才需要解决“模型怎么知道有哪些 skills”。Phase 1 用户手动 `/skill-name` 不需要把 skill 列表塞进 system prompt。
