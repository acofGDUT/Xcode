# Skill Arguments Fallback Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Claude Code-style skill args fallback injection so `/skill-name extra instructions` remains visible to the model even when the skill body does not contain `$ARGUMENTS`.

**Architecture:** Keep the behavior centralized in `SkillPromptExpander.expand()`, because both user slash skill invocation and model `skill` tool invocation already flow through `SkillInvocationService`. Add focused tests at the expander boundary first, then cover the two public invocation paths to prevent regressions.

**Tech Stack:** Python 3.10+, pytest, existing `xcode_cli.skills` and slash command infrastructure.

---

Parent spec: [2026-06-15-skill-arguments-fallback-design.md](../specs/2026-06-15-skill-arguments-fallback-design.md)

## Scope

This plan only implements the fallback append behavior:

```text
ARGUMENTS:
<args>
```

It must not add `$0`, `$1`, `$foo`, `$ARGUMENTS[0]`, shell-like quoting, named parameters, or new frontmatter fields.

## File Structure

- Modify: `src/xcode_cli/skills/prompt.py`
  - Responsibility: expand skill prompt text from `SKILL.md`, replacing supported placeholders and appending fallback args when required.
- Modify: `tests/test_skill_prompt.py`
  - Responsibility: unit coverage for `SkillPromptExpander`.
- Modify: `tests/test_skill_prompt_command_flow.py`
  - Responsibility: user slash command path coverage.
- Modify: `tests/test_skill_tool.py`
  - Responsibility: model-invocable `skill` tool path coverage.
- Modify after implementation: `docs/superpowers/specs/2026-06-15-skill-arguments-fallback-design.md`
  - Responsibility: update status and actual verification evidence after code is complete.
- Modify after implementation: `docs/current/ROADMAP.md`
  - Responsibility: move the item from “已写 spec/plan，待实现” to the true implementation status.
- Optional after implementation: `docs/current/ARCHITECTURE.md`
  - Responsibility: update current skill expansion semantics if implementation is completed.
- Optional after implementation: `docs/current/PROGRESS.md`
  - Responsibility: record completion and verification evidence if implementation is completed.

## Constraints

- Keep the change in `SkillPromptExpander.expand()` unless tests reveal a real boundary issue.
- Preserve current `$ARGUMENTS` replacement exactly: if the body contains `$ARGUMENTS`, do not append an extra fallback block.
- Preserve `${XCODE_SKILL_DIR}` replacement.
- Do not change `SlashCommandDispatcher.dispatch()` parsing in this task.
- Do not change `SkillInvocationService` metadata shape.
- Do not change `SkillTool` barrier, blocked-tools, read-only flag, or audit metadata behavior.
- Do not make metadata visible as an extra LLM message.
- Do not update `ARCHITECTURE.md` until implementation and verification are actually complete.

## Task 1: SkillPromptExpander Fallback Behavior

**Risk layer:** P1

**Files:**
- Modify: `tests/test_skill_prompt.py`
- Modify: `src/xcode_cli/skills/prompt.py`

- [x] **Step 1: Add failing expander tests**

Add these tests to `tests/test_skill_prompt.py`:

```python
def test_appends_arguments_when_body_has_no_arguments_placeholder():
    result = SkillPromptExpander().expand(
        _skill(body="Review carefully."),
        "只检查登录模块，不要跑全量测试",
    )

    assert result.prompt == (
        "Review carefully.\n\n"
        "ARGUMENTS:\n"
        "只检查登录模块，不要跑全量测试"
    )


def test_does_not_append_arguments_when_placeholder_was_used():
    result = SkillPromptExpander().expand(
        _skill(body="Review this: $ARGUMENTS"),
        "src/foo.py",
    )

    assert result.prompt == "Review this: src/foo.py"
    assert "ARGUMENTS:" not in result.prompt


def test_does_not_append_arguments_when_args_are_blank():
    result = SkillPromptExpander().expand(
        _skill(body="Review carefully."),
        "   ",
    )

    assert result.prompt == "Review carefully."
```

- [x] **Step 2: Run RED verification**

Run:

```text
pytest tests/test_skill_prompt.py::test_appends_arguments_when_body_has_no_arguments_placeholder tests/test_skill_prompt.py::test_does_not_append_arguments_when_placeholder_was_used tests/test_skill_prompt.py::test_does_not_append_arguments_when_args_are_blank -q
```

Expected:

- The first test fails because current `SkillPromptExpander.expand()` does not append fallback args.
- The other tests should pass or fail only because the new tests are not yet supported; fix typos before implementation if they error.

- [x] **Step 3: Implement minimal fallback in `SkillPromptExpander.expand()`**

Replace the current expansion block in `src/xcode_cli/skills/prompt.py`:

```python
prompt = skill.body.replace("$ARGUMENTS", args)
prompt = prompt.replace("${XCODE_SKILL_DIR}", str(skill.root))
return ExpandedSkillPrompt(prompt=prompt)
```

with:

```python
has_arguments_placeholder = "$ARGUMENTS" in skill.body
prompt = skill.body.replace("$ARGUMENTS", args)
prompt = prompt.replace("${XCODE_SKILL_DIR}", str(skill.root))
if args.strip() and not has_arguments_placeholder:
    prompt = prompt.rstrip() + f"\n\nARGUMENTS:\n{args}"
return ExpandedSkillPrompt(prompt=prompt)
```

Notes:

- Use `args.strip()` only to decide whether to append; preserve the original `args` text in the appended block.
- Use `skill.body` for placeholder detection so `${XCODE_SKILL_DIR}` does not affect parameter detection.

- [x] **Step 4: Run GREEN verification**

Run:

```text
pytest tests/test_skill_prompt.py -q
```

Expected:

- All `test_skill_prompt.py` tests pass.

## Task 2: User Slash Skill Path Regression

**Risk layer:** P1

**Files:**
- Modify: `tests/test_skill_prompt_command_flow.py`

- [x] **Step 1: Add failing slash command test**

Add this test to `tests/test_skill_prompt_command_flow.py`:

```python
def test_skill_dispatch_appends_args_when_body_has_no_placeholder():
    skill = Skill(
        name="review",
        display_name=None,
        description="Review code",
        body="Review carefully.",
        root=Path("D:/Xcode/.xcode/skills/review"),
    )
    registry = CommandRegistry.from_skills([skill])
    dispatcher = SlashCommandDispatcher(
        console=_console(),
        registry=registry,
        **_handlers(),
    )

    result = dispatcher.dispatch("/review 解释一下这个技能")

    assert result.kind == "prompt"
    assert result.turn_input.display_content == "/review 解释一下这个技能"
    assert result.turn_input.model_content == (
        "Review carefully.\n\n"
        "ARGUMENTS:\n"
        "解释一下这个技能"
    )
    assert result.turn_input.metadata["args"] == "解释一下这个技能"
```

- [x] **Step 2: Run focused slash command verification**

Run:

```text
pytest tests/test_skill_prompt_command_flow.py::test_skill_dispatch_appends_args_when_body_has_no_placeholder -q
```

Expected:

- Passes after Task 1 implementation.
- If it fails, inspect whether `CommandRegistry.from_skills()` or `SlashCommandDispatcher.dispatch()` bypasses `SkillInvocationService`.

- [x] **Step 3: Run existing command-flow tests**

Run:

```text
pytest tests/test_skill_prompt_command_flow.py -q
```

Expected:

- Existing `$ARGUMENTS` slash command tests remain unchanged.
- Session transcript test still stores display content and `metadata.model_content`.

## Task 3: Model Skill Tool Path Regression

**Risk layer:** P1

**Files:**
- Modify: `tests/test_skill_tool.py`

- [x] **Step 1: Add failing skill tool test**

Add this test to `tests/test_skill_tool.py`:

```python
def test_skill_tool_appends_args_when_body_has_no_placeholder():
    registry = ToolRegistry()
    service = SkillInvocationService(
        SkillCatalog(
            [_skill(body="Review carefully.")],
            builtin_commands=set(),
        )
    )
    registry.register(create_skill_tool(service))

    result = registry.execute(
        "skill",
        {"skill": "review", "args": "解释一下这个技能"},
    )

    assert '<xcode_loaded_skill name="review" source="model">' in result.content
    assert "Review carefully.\n\nARGUMENTS:\n解释一下这个技能" in result.content
    assert result.audit_metadata["args"] == "解释一下这个技能"
    assert result.blocked_tools == ["skill"]
```

- [x] **Step 2: Run focused skill tool verification**

Run:

```text
pytest tests/test_skill_tool.py::test_skill_tool_appends_args_when_body_has_no_placeholder -q
```

Expected:

- Passes after Task 1 implementation.
- Audit metadata still contains args, but not `model_content`.

- [x] **Step 3: Run full skill tool tests**

Run:

```text
pytest tests/test_skill_tool.py -q
```

Expected:

- `skill` tool remains read-only.
- Existing placeholder replacement still works.
- Disabled model invocation still returns an error.

## Task 4: Focused Regression, Full Validation, and Docs Closeout

**Risk layer:** P2

**Files:**
- Modify: `docs/superpowers/specs/2026-06-15-skill-arguments-fallback-design.md`
- Modify: `docs/current/ROADMAP.md`
- Optional modify: `docs/current/ARCHITECTURE.md`
- Optional modify: `docs/current/PROGRESS.md`

- [x] **Step 1: Run focused skill suite**

Run:

```text
pytest tests/test_skill_prompt.py tests/test_skill_prompt_command_flow.py tests/test_skill_tool.py tests/test_skill_invocation_service.py -q
```

Expected:

- All focused skill argument fallback and existing invocation tests pass.

- [x] **Step 2: Run source compile check**

Run:

```text
python -m compileall -q src
```

Expected:

- Exit code 0.

- [x] **Step 3: Run full regression**

Run:

```text
pytest -q
```

Expected:

- Full test suite passes.

- [x] **Step 4: Check whitespace and accidental files**

Run:

```text
git diff --check
git status --short
```

Expected:

- `git diff --check` exits 0.
- `git status --short` contains only intended code/test/doc changes and any pre-existing unrelated untracked files.

- [x] **Step 5: Update spec status**

In `docs/superpowers/specs/2026-06-15-skill-arguments-fallback-design.md`, replace the status block:

```markdown
> 状态：已写 spec，未实现，自动化回归未执行。
> 日期：2026-06-15
```

with a truthful implementation status, for example:

```markdown
> 状态：代码实现和自动化回归已完成。
> 日期：2026-06-15
```

Append the actual verification commands and results under the acceptance section. Do not write expected results as if they were actual results.

- [x] **Step 6: Update current docs**

If implementation and validation are complete:

- In `docs/current/ROADMAP.md`, remove the “skill args 兜底注入” pending row or change it to a completed/status note only if the project keeps short recently completed references there.
- In `docs/current/ARCHITECTURE.md`, update the skill expansion description so it says `SkillPromptExpander` replaces `$ARGUMENTS`, replaces `${XCODE_SKILL_DIR}`, and appends `ARGUMENTS:` when args are non-empty and no `$ARGUMENTS` placeholder exists.
- In `docs/current/PROGRESS.md`, record the completion date, behavior delivered, and actual verification commands.

- [x] **Step 7: Final review checklist**

Review implementation against the spec:

- `$ARGUMENTS` placeholder path does not append fallback.
- No-placeholder + non-empty args appends exactly one `ARGUMENTS:` block.
- Blank args do not append fallback.
- Slash skill and model skill tool paths both share the same expander behavior.
- No `$0/$1/$foo/$ARGUMENTS[0]` support was added.
- No session transcript display behavior was changed.
- No tool permission or skill barrier behavior was changed.

## Cross-task Validation

Minimum focused validation:

```text
pytest tests/test_skill_prompt.py tests/test_skill_prompt_command_flow.py tests/test_skill_tool.py tests/test_skill_invocation_service.py -q
```

Final validation:

```text
python -m compileall -q src
pytest -q
git diff --check
```

## Review Notes

- The most likely regression is accidentally appending `ARGUMENTS:` even when `$ARGUMENTS` was already used.
- The second likely regression is trimming user args in a way that changes the model-visible instruction. Only use trimming to decide emptiness.
- Keep this feature at P1 behavior-test coverage because it changes user-visible skill invocation semantics and model-invocable skill behavior.
