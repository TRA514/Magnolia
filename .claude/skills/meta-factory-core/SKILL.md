---
name: meta-factory-core
description: Use when scaffolding a new worker, card-type, or adapter (the meta-create-* factory skills) - establishes the shared scaffold→capture→gate→commit→receipt lifecycle and the capture-to-profile rule
---

# Factory Core

The shared mechanism behind `meta-create-worker`, `meta-create-card-type`, and
`meta-create-adapter`. Read this first; the sibling skill owns the artifact-specific
gate. The factory builds at **authoring time** — durable, reviewable, theme-aware by
construction — never at render time.

## The Core Principle

The factory scaffolds a **clean** artifact and captures every team/person specific
into the **profile**, never into the artifact. This is the same line
`tests/test_engine_no_jay.py` enforces: generated workers/skills/commands must read
identity and team facts from `profile/` (instruct-to-read-profile), so they stay
denylist-clean by construction.

This is Test-Driven scaffolding — it reuses `meta-create-skill`'s RED-GREEN-REFACTOR
spine: define the gate, scaffold to pass it, then commit only when green.

## The Lifecycle (every factory skill follows this)

1. **Capture.** Gather the spec conversationally. Structured specifics that already
   have a profile home (e.g. Jira board/project/assignee in
   `profile/integrations.yaml`) are read, not asked. Fuzzy team nuance with no
   structured field ("always set Sprint", "titles prefixed [Area]") is written to a
   free-form `conventions` slot in the profile via
   `profile_lib.set_integration_conventions(category, text, provider=…)` — **never
   written into the artifact.**
2. **Scaffold.** Produce the artifact from the sibling skill's embedded skeleton
   (profile-read boilerplate + token-only references baked in).
3. **Gate (GREEN).** Run the artifact's gate (the sibling skill names it). It MUST
   pass before committing — nothing non-conformant lands.
4. **Commit + receipt.** Call the shared helper:
   `python3 scripts/factory_lib.py commit-and-receipt --summary "<one-liner>" --kind <worker|card-type|adapter> <file> [<file> …]`
   It stages **only** those files (never `git add -A`), commits, captures the sha,
   and emits a `receipt` card with `revert_commit` + `receipt_summary`.
5. **Hand back.** Tell the operator in plain language: *"Built you an X → check the
   receipt card. Keep / Undo."* **Never mention git.** Undo is the existing
   `undo_receipt` git-revert handler; the board only shows Keep / Undo.

## Iron Laws

1. **NEVER write team/person specifics into the artifact** — capture to profile.
2. **NEVER commit before the gate is green.**
3. **Stage only the scaffolded files** — use `factory_lib`, never `git add -A`.
4. **Git is never user-facing** — speak in Keep / Undo, never commits/reverts.

## Tier-2 (adapters only)

Creating an artifact writes local files only → Tier-1, no confirm. Anything that
writes to the **outside world** (an adapter's first `publish`) is **Tier-2** and gets
exactly one plain-language confirm before its first external action — see
`meta-create-adapter`. Workers and card-types are Tier-1.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Baking the board id / team nuance into the worker | Capture it to `profile/` via `set_integration_conventions`; the artifact reads it |
| `git add -A` then commit | Use `factory_lib commit-and-receipt` with explicit files |
| Telling the operator "I committed / reverted" | Say "Keep / Undo on the card" |
| Committing before the gate passes | Gate first; commit only when green |

## Deferred (future work)

Personalizing an **arbitrary third-party skill someone drops in** (that the factory
did not author) to the operator's team/voice is a separate card-driven flow, not part
of the factory. Instruct-to-read-profile already makes dropped skills runtime
profile-aware.

## Related Skills

- **meta-create-skill**: the TDD spine these factories reuse (RED-GREEN-REFACTOR + CSO).
- **meta-create-worker** / **meta-create-card-type** / **meta-create-adapter**: the siblings.
