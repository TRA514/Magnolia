# Magnolia — Phase 9: The Factory (self-extension via meta-create-* skills) (Design)

**Date:** 2026-06-07
**Status:** Design approved (brainstorm complete) — ready for implementation plan
**Builds on:** Build-sequence steps 1–8 + the de-personalization phase, all merged to `main` (latest merge `de83385`).
**Master design:** `2026-06-05-pm-os-portability-design.md` §6 (the factory), §9 (design system = card schema + theme tokens), §11 step 8 (this is the **last** build-sequence phase).
**De-risked by:** `2026-06-07-depersonalization-design.md` — the engine exemplars are now clean + profile-driven, so the factory clones clean defaults by construction; `tests/test_engine_no_jay.py` is the standing guard.
**File-backed surface:** `2026-06-07-phase-8-workers-prompts-filebacked-design.md` — the Workers & Prompts tab is file-backed, so factory-authored workers surface there with zero extra wiring.

---

## Goal

Self-extension: headless (or interactive) Claude scaffolds a new **worker**, **card-type**, or **adapter** from embedded skeletons, following the design system, and presents the result as a **receipt card** in the board's own language — *"Built you an X → [preview]. Keep / Undo."* Undo is a silent `git revert`; git is never user-facing. Anything that writes to the outside world is **Tier 2** and gets exactly one plain-language confirm before its first external action.

The *feeling* is "the system built it for me, and it belongs." Achieved at **authoring time** (durable, reviewable, consistent, theme-aware by construction) — never at render time.

## Non-negotiables this phase must preserve

- **Generated artifacts hold no team/person specifics in their prose.** This is the line `test_engine_no_jay.py` enforces and the de-personalization phase paid down. The factory's skeletons use placeholders, "the operator," and instruct-to-read-profile prose — so generated artifacts are denylist-clean **by construction**.
- **Card schemas reference theme tokens only** (the §9 hard rule) — no raw color/radius/transition. Enforced by `card_schema.py`.
- **Simplicity is the architecture.** No new infrastructure: skills are markdown, the receipt is a markdown task file, Undo reuses the existing `undo_receipt` git-revert handler. No backend change for the receipt path.

---

## 1. Architecture: one core skill + three siblings

A small **`meta-factory-core`** skill defines the shared lifecycle and the capture-to-profile pattern. Three sibling skills own each artifact's gates:

| Skill | Scaffolds | Gate (the GREEN before commit) | Live verification |
|---|---|---|---|
| `meta-create-worker` | `scripts/workers/<name>.md` | frontmatter parses in `load_workers()` + `test_engine_no_jay.py` | appears in Phase-8 Workers & Prompts tab (free) |
| `meta-create-card-type` | a `cardTypes` entry in `ui/task-board/cardtypes/registry.json` | `python3 scripts/card_schema.py` (token-only) | Chrome render of the new type |
| `meta-create-adapter` | `scripts/adapters/<family>/<provider>.py` | `_contract.py` conformance (import + interface check) | unit-test the publish gate + dry-run confirm |

All three reference `meta-create-skill`'s TDD spine (RED-GREEN-REFACTOR + CSO-optimized descriptions) **by reference**, not duplication. Each is a `.md` under `.claude/skills/**`, so the skills *themselves* are scanned by `test_engine_no_jay.py` — their embedded skeletons must stay denylist-clean (placeholders, "the operator," profile-read instructions).

**Why three siblings, not one generalized skill:** the gates are genuinely different (frontmatter+denylist vs. token-only registry vs. contract+Tier-2). One mega-skill would be a sprawling conditional that fights the one-skill-per-PR cadence. Total inlining would let the shared mechanism rot. Core + siblings is the balance.

## 2. The shared factory lifecycle (`meta-factory-core`)

1. **Capture.** Gather the spec conversationally. Structured specifics that already have a profile home (Jira board/project/assignee/component/product_area) are read from `profile/integrations.yaml`. Any team/person specific that has **no** structured slot (e.g. "always set the Sprint field," "bug titles are prefixed `[Area]`," "Epic Link is mandatory") is written to a **free-form `conventions` slot in profile** — *never* into the artifact.
2. **Scaffold.** Produce the artifact from the skill's embedded skeleton (profile-read boilerplate + token-only references baked in).
3. **Gate (GREEN).** Run the artifact's gate. **Must pass before committing** — nothing non-conformant can land.
4. **Commit.** `git add <only the scaffolded files>` (precise staging — also fixes the `git add -A` carryover wart for factory commits) + commit. Capture the resulting sha.
5. **Emit receipt.** Write a `receipt` task `.md` to the human queue with `card_type: receipt`, `revert_commit: <sha>`, and `receipt_summary: "Built you an X → …"`. The factory is the emitter — **no backend change**: the existing `preview` body renderer already reads `receipt_summary`/`revert_commit` from task frontmatter.
6. **Keep / Undo.** The existing `keep` and `undo_receipt` (`git revert <revert_commit>`) handlers work untouched. Git stays invisible — the user only ever sees "Keep / Undo."

### Capture-to-profile in detail

The profile is the single home for *all* specifics — structured (fixed fields) and fuzzy (free-form `conventions`). The factory's job at creation is (a) scaffold a clean artifact and (b) capture any specifics into profile, extending the profile (adding a `conventions` block) rather than hardcoding into the artifact. This keeps generated artifacts guard-clean while still capturing real team nuance, and the nuance stays editable later in the Engine room.

**User narrative (Jira bug-filing worker):**
1. *"Build me a worker that files bugs to our Jira."*
2. `meta-create-worker` reads `integrations.yaml` → Jira already configured (board/project/assignee present).
3. For what's not in the schema, it asks: *"Anything specific about how your team files bugs — required fields, title format, labels?"* → *"Always set Sprint; prefix titles with `[Area]`."*
4. Factory writes that to `profile` (`project_management.jira.conventions`), **not** the worker.
5. Factory scaffolds a denylist-clean worker that reads target + conventions from profile.
6. Receipt card: *"Built you a bug-filing worker → [preview]. Keep / Undo."*
7. First time it actually posts → the Tier-2 *"okay to let it post to your Jira?"* confirm fires (§4).

## 3. Templates: embedded skeletons + gate-before-commit

Scaffold skeletons live **inside each skill** as fenced code blocks (mirrors how `meta-create-skill` embeds the SKILL.md structure it wants produced). The skeleton sets the right starting shape (profile-read boilerplate, token-only references, "the operator" voice); the artifact's **gate is the hard guarantee**, run before commit. No separate `templates/` directory — the real schemas (`card_schema.py`, `_contract.py`, the worker frontmatter contract) are the source of truth, and a parallel template copy would only drift from them. For the adapter, `scripts/adapters/project_management/asana.py` is already a contract-conformant stub and serves as the worked exemplar.

## 4. Tier-2 confirm (the adapter PR only)

Creating an adapter writes only local files → **Tier-1**, no confirm to scaffold. The Tier-2 moment is the **first time an adapter actually publishes externally**, so the gate lives on the *publish path*, not on authoring.

- Add a `confirmed: false` field to each integration block in `profile/integrations.yaml`.
- Add a thin gate around `adapters.get(...).publish()`: if `confirmed` is false, raise a typed `NeedsConfirmation` that **stops before any external call** and surfaces a Tier-2 confirm card on the **collab queue** (which already means "supervised agent action requiring human approval"). The card's confirm action flips `confirmed: true`. After that it posts freely — one confirm, ever, per integration.
- This is **general adapter infrastructure** (gates *any* adapter's first external write). `meta-create-adapter` simply scaffolds new adapters as `confirmed: false`. Onboarding/Doctor pre-set `confirmed: true` for an integration the user explicitly configured during setup, so the live Jira path is not retroactively blocked.

## 5. Sequencing: three risk-ordered PRs (Phase 7/8 cadence)

### PR1 — `meta-factory-core` + `meta-create-worker`
Establishes the whole spine on the lowest-risk artifact (a pure new `.md` → cleanest possible revert). Carries the `conventions` profile slot + capture-to-profile pattern (the Jira-bug-worker is the driver narrative). Free verification via the file-backed Workers tab.

### PR2 — `meta-create-card-type`
Scoped to **registry composition only** — a new card type assembled from existing slots / signals / body-renderers, preserving the "zero new render code" promise. (A genuinely novel body renderer/predicate needs hand-written JS and is explicitly out of scope.) Gate = `card_schema.py`; verification = Chrome render.

### PR3 — `meta-create-adapter` + Tier-2 publish gate
Scaffolds from the `asana.py` exemplar; gate = `_contract.py` conformance. Adds the general publish-path confirm gate (§4). Most careful PR — highest blast radius.

## 6. Testing & verification posture

- **Guard coverage is automatic:** generated workers land in `scripts/workers/` and generated skills/commands in `.claude/skills/**` — already scanned by `test_engine_no_jay.py`. The factory skills' own SKILL.md skeletons are likewise scanned, so they must be denylist-clean.
- **New unit tests:** the `conventions` profile accessor; the `integrations.yaml` schema additions (`conventions`, `confirmed`); the `NeedsConfirmation` publish gate (raises when unconfirmed, passes when confirmed).
- **Per-PR live verification:**
  - PR1 — drive the factory to scaffold a sample worker; confirm it parses, appears in the Workers tab (Chrome headless against `:8743`), the receipt card renders, and Undo reverts it.
  - PR2 — Chrome render of a new card type assembled from existing slots.
  - PR3 — unit-test the gate + a dry-run of the confirm flow.
- `python3 -m pytest`, `python3 scripts/card_schema.py`, and `tests/test_engine_no_jay.py` stay green throughout.
- **Process:** subagent-driven-development — fresh implementer per task + two-stage review (spec-compliance, then code-quality). PR1 → PR2 → PR3.

## 7. Out of scope (deferred)

- **Personalizing an arbitrary third-party dropped skill** the factory didn't author — a separate card-driven flow, lower value now that instruct-to-read-profile makes dropped skills runtime-profile-aware. One-line "future work" pointer in `meta-factory-core`.
- **Novel card body renderers/predicates** (anything needing hand-written JS) — `meta-create-card-type` is registry-composition-only.
- **Headless-dispatch entry point** as a first-class feature — the factory skills are invocable both interactively and (incidentally) via a dispatched task, but Phase 9 designs for the interactive/skill path; the receipt card is the async review surface either way.
- Pre-existing carryovers unchanged: dispatch-behavior ladder-tier enforcement, task→transcript session join, `description_patterns` in the regex matcher, `ladder.json` single-writer concurrency, unvalidated per-task `model:` override, tier-badge CSS variants, dead LangFuse list endpoints.

## Open questions (carry into planning)

- **`conventions` shape** — a free-text string vs. a small structured sub-map under each integration block. Lean: free-text markdown string the artifact is instructed to read verbatim (simplest, most flexible, on-philosophy). Confirm in planning.
- **Receipt queue** — human vs. a dedicated surface. Lean: human queue (the existing receipt flow already lands there).
- **`NeedsConfirmation` surfacing** — exact mechanism by which a raised exception during dispatch becomes a collab card (dispatch catch → write collab task) vs. the adapter writing the card itself. Resolve in the PR3 plan.
