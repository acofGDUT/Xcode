# Task 07: Docs and Verification

**Risk layer:** P1/P2

## Goal

Run focused and full verification, then update current docs with actual implementation facts and evidence. Do not mark completion before evidence exists.

## Suggested Files

- Modify after verified implementation: `docs/current/ARCHITECTURE.md`
- Modify after verified implementation: `docs/current/PROGRESS.md`
- Modify after verified implementation: `docs/current/ROADMAP.md`
- Modify after verified implementation: `docs/current/DEVNOTES.md`
- Modify: `docs/superpowers/specs/2026-06-23-auto-memory-extraction-design.md`
- Modify: `docs/superpowers/plans/2026-06-23-auto-memory-extraction-plan.md`
- Modify task files in `docs/superpowers/plans/2026-06-23-auto-memory-extraction/`

## Constraints

- No implementation completion claim without real command output.
- `ARCHITECTURE.md` describes only code that exists.
- `ROADMAP.md` keeps remaining gaps, such as manual Windows verification if not executed.
- `PROGRESS.md` records evidence after verification, not planned commands.

## Steps

- [x] **Step 1: Run focused verification**

Run:

```text
pytest tests/test_memory.py tests/test_prompting_memory.py -q
pytest tests/test_memory_manifest.py -q
pytest tests/test_memory_extraction.py -q
pytest tests/test_memory_recall.py -q
pytest tests/test_agent_memory_hooks.py tests/test_agent_user_turn.py -q
pytest tests/test_external_turn.py tests/test_qqchat_service.py -q
```

Expected:

- All commands pass.
- If a command fails, stop and fix the failing behavior before updating docs.

- [x] **Step 2: Run full verification**

Run:

```text
python -m compileall -q src
pytest -q
git diff --check
```

Expected:

- `compileall` exits 0.
- Full pytest exits 0.
- `git diff --check` exits 0; Windows LF/CRLF warnings from Git are acceptable only if exit code is 0.

- [x] **Step 3: Update architecture with actual mechanisms**

In `docs/current/ARCHITECTURE.md`, update Memory 模型 section only after code lands. Include:

```markdown
- Auto memory directory now uses the same stable project key as session storage; legacy `<cwd.name>` memory directories remain read fallback.
- `MemoryManifestScanner` scans bounded frontmatter from topic `.md` files and excludes `MEMORY.md`.
- Local REPL successful turns run an internal `after_turn_success` hook; first consumer is `MemoryExtractionService`.
- QQchat/external turns do not trigger automatic long-term memory extraction.
- Relevant memory recall keeps `MEMORY.md` as常驻索引 and injects selected topic files as bounded system reminders.
```

Do not mention unimplemented behavior if any task was deferred.

- [x] **Step 4: Update progress with real evidence**

Append a new section to `docs/current/PROGRESS.md`:

```markdown
## NN. Auto memory 自动沉淀：2026-06-23

状态：代码实现和自动化回归已完成；如未执行原生 Windows 手工验收，明确写“未执行/未记录”。

本轮实现：
- ...

验证：
- `<actual command>`：`<actual result>`
```

Use real command outputs from Steps 1 and 2.

- [x] **Step 5: Update roadmap**

In `docs/current/ROADMAP.md`, remove or downgrade the `auto memory 自动沉淀` row only if implementation and verification are complete. If relevant recall or Windows manual verification remains open, keep a residual row with the real gap.

- [x] **Step 6: Update devnotes**

In `docs/current/DEVNOTES.md`, record durable review constraints:

```markdown
## NN. Auto memory extraction boundaries

**状态**：Mitigated 或 Resolved，按真实完成度填写。

- Internal after-turn hooks are code-registered only; skill hooks remain parsed but not executed.
- External turns do not auto-write memory.
- Explicit deny still blocks background memory writes.
- Relevant memory recall is bounded and no-tool; selector output is validated against manifest candidates.
```

- [x] **Step 7: Self-review docs**

Run:

```text
rg -n "待验证|基本完成|T[B]D|T[O]DO|planned|Expected: P[A]SS" docs/current docs/superpowers/specs/2026-06-23-auto-memory-extraction-design.md docs/superpowers/plans/2026-06-23-auto-memory-extraction-plan.md docs/superpowers/plans/2026-06-23-auto-memory-extraction
```

Expected:

- No vague completion wording.
- Plan checkboxes can remain unchecked only for tasks not completed; do not mark all tasks complete unless implementation and verification actually finished.

- [x] **Step 8: Final git status review**

Run:

```text
git status --short
git diff --stat
```

Expected:

- Only intended source, tests, and docs changed.
- No logs, secrets, cache files, or generated artifacts staged.

If committing is requested:

```text
git add src tests docs/current docs/superpowers/specs/2026-06-23-auto-memory-extraction-design.md docs/superpowers/plans/2026-06-23-auto-memory-extraction-plan.md docs/superpowers/plans/2026-06-23-auto-memory-extraction
git commit -m "feat: add auto memory extraction"
```

