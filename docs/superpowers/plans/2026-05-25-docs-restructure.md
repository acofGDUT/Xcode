# Documentation Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize Xcode project documentation so detailed content is preserved while each document has one clear responsibility.

**Architecture:** Archive the previous root-level documents under `docs/old/`, create the current authoritative set under `docs/current/`, and keep root-level documents as lightweight compatibility entrypoints. Move the date plan into `docs/journal/` so it becomes a work log rather than a primary project document.

**Tech Stack:** Markdown documentation only; no runtime code changes.

---

### Task 1: Archive Current Documents

**Files:**
- Create: `docs/old/2026-05-25-before-docs-restructure/`
- Copy: `README.md`, `ARCHITECTURE.md`, `PROGRESS.md`, `ROADMAP.md`, `DEVNOTES.md`, `AGENTS.md`, `CLAUDE.md`, `日期计划.md`

- [x] **Step 1: Create archive directories**

Run:

```powershell
New-Item -ItemType Directory -Force -Path docs/old/2026-05-25-before-docs-restructure,docs/current,docs/journal,docs/superpowers/plans
```

Expected: directories exist.

- [x] **Step 2: Copy current root documents into archive**

Run:

```powershell
Copy-Item -LiteralPath README.md,ARCHITECTURE.md,PROGRESS.md,ROADMAP.md,DEVNOTES.md,AGENTS.md,CLAUDE.md,日期计划.md -Destination docs/old/2026-05-25-before-docs-restructure -Force
```

Expected: archived copies preserve the previous content.

### Task 2: Create Current Authoritative Document Set

**Files:**
- Create: `docs/current/README.md`
- Create: `docs/current/ARCHITECTURE.md`
- Create: `docs/current/ROADMAP.md`
- Create: `docs/current/PROGRESS.md`
- Create: `docs/current/DEVNOTES.md`

- [x] **Step 1: Write the new documentation index**

Create `docs/current/README.md` with the current documentation map and reading order.

- [x] **Step 2: Write current architecture**

Create `docs/current/ARCHITECTURE.md` with component relationships, runtime flows, memory model, context model, approval model, and known current boundaries.

- [x] **Step 3: Write current roadmap**

Create `docs/current/ROADMAP.md` with future work and concrete implementation sketches for unfinished capabilities.

- [x] **Step 4: Write progress history**

Create `docs/current/PROGRESS.md` with phase-by-phase development history, current state, blockers, and next steps.

- [x] **Step 5: Write development notes**

Create `docs/current/DEVNOTES.md` with known issues, design decisions, and validation risks.

### Task 3: Keep Root-Level Compatibility Entrypoints

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `ROADMAP.md`
- Modify: `PROGRESS.md`
- Modify: `DEVNOTES.md`
- Modify: `日期计划.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [x] **Step 1: Keep root README as public entrypoint**

Root `README.md` remains useful for GitHub and points readers to `docs/current/`.

- [x] **Step 2: Replace detailed root docs with pointers**

Root architecture, roadmap, progress, devnotes, and date plan files point to their authoritative locations.

- [x] **Step 3: Update agent guidance**

`AGENTS.md` and `CLAUDE.md` now reference the `docs/current/` reading order.

### Task 4: Verify Documentation Links

**Files:**
- Inspect: all modified Markdown files

- [x] **Step 1: Check git diff**

Run:

```powershell
git diff --stat
```

Expected: only documentation and archive files changed.

- [x] **Step 2: Search for stale root-only reading order**

Run:

```powershell
rg "PROGRESS.md|ROADMAP.md|ARCHITECTURE.md|DEVNOTES.md|日期计划.md" README.md AGENTS.md CLAUDE.md docs/current
```

Expected: references either point to `docs/current/` or intentionally mention root compatibility files.
