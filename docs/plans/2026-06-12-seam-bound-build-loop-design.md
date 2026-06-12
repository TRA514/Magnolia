# Seam-Bound Build Loop — Design

**Date:** 2026-06-12
**Status:** Approved (design)
**Author:** Jay Jenkins (+ Claude)

## Problem

`/magnolia-build` works well for a technical operator but lets less-technical
teammates' agents go off the rails when extending the engine. Three beta-user
post-mortems (2026-06-11, Josh Mulvihill) look like unrelated bugs but share one
root cause:

| Report | What the agent did | The seam it should have used |
|---|---|---|
| SLOT time display | Read agent-hand-written display text as source of truth | Format from structured data in the renderer |
| Em-dash encoding | Emitted `—` into runtime text → garbled on Windows CP437 | ASCII-safe output |
| Windows `.sh` hook | Hand-rolled an `is_windows` branch shelling Python→bash | `scripts/platform_lib.py` (the OS seam, already built) |

**Root cause:** the build loop never forces the agent to bind to the architecture's
existing seam before writing code, so it improvises in the wrong layer. A fourth
meta-failure: the beta user's fixes — plus `docs/analysis/`, `docs/changes/`,
`docs/post-mortems/`, `test-slot-formatting.html` — never returned to `main` and now
diverge. (De-prioritized: this is a local, no-PR project; the gate catching bad
patterns upstream matters more than merge ceremony.)

## Core principle

**Before any code is written, decompose the ask onto the engine's extension surfaces,
decide reuse-vs-extend-vs-new against what already exists, and hand each subagent the
*contract* for its surface.** The contract is the fairway. A subagent told "compose a
registry entry from these existing pieces, here's the gate, don't touch JS" cannot
wander the way one told "build a card" can.

The `meta-create-*` factories are already tight, but each assumes the *decision is
already made* — which surface, reuse-vs-new, and (for cards) whether the need even fits
composition or is JS work. That pre-factory decision layer is what's missing, and it's
exactly where beta users go off the rails.

## The loop (orchestrator rewrite)

```
preflight → ground in refs (+ the relevant architecture §)
  → brainstorm (WHAT)
  → scope-extension     ← NEW: decompose onto surfaces, reuse/extend/new, build-contract
  → writing-plans       (each task carries its surface's contract + gate + skeleton)
  → subagent build      (each subagent briefed with architecture-bound specificity)
  → portability gate + two-stage review (spec, then code-quality incl. seam adherence)
  → e2e verify
  → ship (local: gates green → commit; no PR ceremony)
```

## Components

### 1. `meta-scope-extension` (new sub-skill) — the decomposition brain

Runs after brainstorm. Maps the ask onto the four extension surfaces and, for each,
answers *reuse / extend / build-new* against an inventory of what exists:

- **adapter** (external system) → `scripts/adapters/<family>/<provider>.py`
- **worker** (autonomous task handling) → `scripts/workers/<name>.md`
- **card** (board surface) → `registry.json` (compose) OR `js/card-registry.js` (new
  piece = JS work)
- **UI / renderer / platform** (display formatting, OS seam) → existing code,
  `platform_lib`

It knows the composition boundaries (e.g. the card registry composes only from existing
signals/actions/bodies; a new one is JS work), so it flags that *early* rather than
letting an agent botch it. **Output: a build contract** — a section in the plan naming,
per surface, the decision + the exact factory/seam to use + the gate that proves it.
This is what the orchestrator briefs subagents from. Reuse-vs-create is this skill's
core (the "reuse-inventory" idea folded in — not a third skill).

### 2. `meta-integration-discovery` (new sub-skill) — the external-capability probe

Invoked by scope-extension only when a surface touches an external system (e.g. the
calendar-invite-triage case). Structures the exploration:

1. **Enumerate mechanisms** — connected MCP server? a CLI (`mgc`)? REST? What's already
   wired in `profile/integrations.yaml`?
2. **Validate the capability actually exists** — read-only probes (can M365 MCP read
   incoming invites? does `mgc` have the calendar command/scope?). Record what works.
3. **Confirm auth/scope reality** — what's authorized now, what needs consent (Tier-2),
   which scopes.
4. **Produce a findings doc** — mechanism chosen + why, capability evidence, auth/scope
   needs, gaps. Feeds `meta-create-adapter`'s capture step with the decision de-risked.

Prevents an agent confidently building an adapter against a capability that doesn't
exist or a mechanism that can't do the job.

### 3. `scripts/portability_gate.py` (one new gate) — the dumb-fast scan

Mirrors `test_engine_no_jay.py`: a denylist scan over the authored-code globs
(`scripts/**`, `.claude/skills/**`, `ui/task-board/js/**`, `scripts/adapters/**`).
Flags the leak-past-the-seam patterns:

- non-ASCII characters (em-dash etc.) in runtime-display string literals
- direct `.sh` / `bash` invocation; `subprocess` calling a shell script
- `os.name == 'nt'` / `sys.platform` branches **outside** `scripts/platform_lib.py`
- `start_new_session=`, hardcoded path separators, manual path string concatenation

Wired as a 4th gate that rides the existing `pytest` invocation. Allowlists
`platform_lib.py` itself. Closes the seam the portability epic left open.

**Implemented narrower than first sketched:** the gate scans runtime code (`.py`/`.js`) only and enforces the OS/shell structural rules (`.sh`/bash, `os.name`/`sys.platform`/`platform.system()`, `start_new_session`). The em-dash/smart-quote and path-separator rules were dropped -- markdown legitimately uses em-dashes, and the real em-dash bug lives in runtime-generated text the gate cannot see. That ASCII-safe-output discipline moved into the build-contract standing item in `meta-scope-extension` and the magnolia-build iron law. See the `portability_gate.py` module docstring and invariant #8 for the authoritative scope.

## Explicitly NOT building (YAGNI)

- **No structure-lint gate** — PR/divergence de-prioritized for a local project.
- **No structured-data-display gate** — un-gateable without false positives; lives in
  the scope contract + code-quality review stage instead.
- **Not touching the `meta-create-*` factories** — they're good; the new skills sit in
  front of them.

## Invariants honored

- New skills/gate stay denylist-clean (invariant #1, #4) — they read identity from
  `profile/`, capture nuance to the profile.
- The portability gate runs green before commits like the other three (invariant #2).
- All work on a branch; ship is local commit, no `main` commits mid-build (conventions).
```
