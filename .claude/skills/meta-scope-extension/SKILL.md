---
name: meta-scope-extension
description: Use when /magnolia-build has an approved design and must decompose it onto the engine's extension surfaces — decides reuse vs extend vs build-new per surface and emits a build contract that briefs each subagent. Runs before the meta-create-* factories.
---

# Scope Extension — decompose onto the surfaces, then bind to the seams

You are the decomposition step in `/magnolia-build`. The brainstorm produced an
approved design; the factories (`meta-create-worker`, `meta-create-card-type`,
`meta-create-adapter`) can SCAFFOLD any one surface but they assume the
reuse-vs-new decision is already made. **You make that decision and route.** Your
output is a *build contract* the workflow hands to each subagent so it builds in the
right architectural layer instead of improvising in the wrong one.

You decide; the factories scaffold. Do not duplicate them — point at them.

## When to Use

- `/magnolia-build` has an approved design and is about to dispatch the build.
- Any time an ask touches more than the obvious one surface and you need to map it
  before code is written.
- **Not** for scaffolding a single known surface — that's the relevant
  `meta-create-*` factory directly.

## The four surfaces

Every engine extension lands on exactly one of these surfaces. Map each piece of the
approved design onto its surface and seam before deciding anything:

| Surface | What it is | File / seam |
|---|---|---|
| **adapter** | a new external system (a provider for project-management, transcripts, calendar, …) | `scripts/adapters/<family>/<provider>.py` |
| **worker** | autonomous handling of a kind of task | `scripts/workers/<name>.md` |
| **card** | a board surface | `ui/task-board/cardtypes/registry.json` (compose from existing pieces) OR `ui/task-board/js/card-registry.js` (a NEW signal / action / body renderer = JS work) |
| **platform / UI** | display formatting, OS specifics | existing code + `scripts/platform_lib.py` |

If a design names a single feature that spans several of these (e.g. "an agent that
files bugs and shows a receipt card"), split it: one row per surface.

## The reuse-first rule

Inventory what already exists BEFORE proposing anything new, per surface. Default to
**reuse**, then **extend**, and only then **build-new**:

- **workers** — list `scripts/workers/*.md` and ask "does one already match this kind
  of task?" Prefer reusing or extending an existing worker's `match` over scaffolding
  a near-duplicate.
- **cards** — enumerate the existing signals / actions / body-renderers (point at
  `meta-create-card-type`, which lists the real ones) and decide *compose-vs-JS-work*.
  If the card composes cleanly from existing pieces, it's a factory job. If it needs a
  **new** signal predicate, action handler, or body renderer, that is JavaScript work
  in `ui/task-board/js/card-registry.js` — flag it to the operator NOW. Do not let a
  subagent invent a registry entry that references a nonexistent piece; the
  design-system gate rejects it anyway, and the agent will have wasted a build pass.
- **adapters** — check `profile/integrations.yaml` and the existing
  `scripts/adapters/<family>/` directory. An existing family (or even an existing
  provider) may already cover the capability; a "new integration" is often a config
  selection, not a new module.

## External surface → delegate the probe first

If the design touches an external system, do NOT decide the adapter here. Delegate to
**`meta-integration-discovery`** first so the capability and mechanism (does the API /
MCP actually expose what the design assumes?) are validated. Only once discovery
confirms the mechanism do you write the adapter row of the build contract and route to
`meta-create-adapter`.

## The build contract (the output)

This is the artifact you write into the plan. For EACH touched surface, one row:

| Surface | Decision | Factory / seam to use | Gate that proves it |
|---|---|---|---|
| worker | reuse / extend / build-new | `meta-create-worker` → `scripts/workers/<name>.md` | `validate-worker` + `pytest` |
| card | reuse / extend / build-new (or → JS work) | `meta-create-card-type` → `registry.json` (compose) | `card_schema.py` |
| adapter | reuse / extend / build-new | `meta-integration-discovery` then `meta-create-adapter` | `validate-adapter` + `pytest` |
| platform / UI | reuse / extend | existing renderer + `scripts/platform_lib.py` seam | `portability_gate.py` + `pytest` |

Plus one **standing contract item that applies to every surface**:

> **Runtime output must be ASCII-safe** — use a hyphen, not an em-dash, and ASCII
> quotes. An em-dash garbles on Windows CP437 terminals and on cards. The portability
> gate cannot catch this because it lives in runtime-generated text, not source, so it
> must travel in the contract that briefs each subagent.

This contract is exactly what `/magnolia-build` hands each subagent. A subagent told
"compose a registry entry from these existing pieces, here's the gate, don't touch JS"
cannot wander the way one told "build a card" can — the contract pins the surface, the
seam, and the gate, so the agent has no room to improvise in the wrong layer.

## Iron Laws

1. **Never propose build-new where reuse fits** — inventory first, default to reuse,
   then extend, then new.
2. **Never let a card reference a piece that doesn't exist** — a new signal / action /
   body renderer is JS work in `card-registry.js`; hand it to engineering, mirroring
   `meta-create-card-type`'s hard boundary. Do not invent a registry entry the gate
   will reject.
3. **Capture team/person nuance to `profile/`, never the artifact** — read identity
   and team specifics via `profile_lib`; the contract instructs each subagent to do the
   same.
4. **Bind every surface to its seam** — OS specifics → `platform_lib`; identity →
   `profile_lib`; display → the renderer. The build contract names the seam per row.
5. **ASCII-safe runtime output** — hyphen not em-dash, ASCII quotes, on every surface.

## Related Skills

- **meta-create-worker** — scaffolds the worker surface once you've decided.
- **meta-create-card-type** — composes the card surface (and owns the compose-vs-JS boundary).
- **meta-create-adapter** — scaffolds the adapter surface after discovery validates it.
- **meta-integration-discovery** — probes an external system before the adapter is decided.
- **meta-factory-core** — the shared scaffold→capture→gate→commit→receipt lifecycle behind the factories.
