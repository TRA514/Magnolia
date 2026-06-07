# Magnolia Phase 5 — UI Commission Spec (Design)

**Date:** 2026-06-06
**Status:** Design approved (brainstorm complete) — brief written, ready to commission
**Branch:** `feat/phase-5-ui-commission-spec`
**Builds on:** Phases 1–4 (merged to `main` at `4d3f5a2`)
**Master design:** `2026-06-05-pm-os-portability-design.md` §6 (factory / declarative card
registry), §9 (design system = card schema + theme tokens), §11 step 5.
**Supersedes (as the working spec):** `2026-06-05-pm-os-ui-spec.md` — the *seed* spec written
during the original brainstorm, **before** Phases 1–4 existed. This pass turns that seed into a
build-ready commission grounded in the real registry, endpoints, and projected fields.
**Deliverable:** `2026-06-06-phase-5-designer-commission-brief.md` (the portable brief).

---

## What Phase 5 is

Build-sequence step 5: **write the UI commission spec → commission the design (Claude Designer).**
The prerequisites are now all defined and *functional with real data*: the profile schema (Phase 1),
the declarative card registry + theme tokens (Phase 3), and the three new card kinds —
recommendation, receipt, graduation — which Phase 4 wired to real handlers but rendered
**deliberately minimal/unstyled**, explicitly deferring polish to this design pass.

The deliverable is a **portable, self-contained commission brief** the Designer builds a
**mock-API frontend** against, returning design-system-matching **CSS / HTML / JS**. We reconcile
the mock APIs and mismatches and **integrate in Phase 6** — not this phase. Backend work on later
steps proceeds in parallel.

## Decisions (from brainstorm)

1. **Commission scope: targeted, drop-in.** Spec *only* the undesigned surfaces, built strictly
   against the existing token contract. **Not** a full board redesign — honors the non-negotiable
   *"evolve `ui/task-board/`, don't rewrite as React,"* and keeps Phase-6 integration risk low.
2. **Spec form: one commission doc.** The surfaces share the card shell + token contract heavily;
   one doc keeps the design system coherent (per-surface docs would duplicate and drift). A single
   Designer commission gains nothing from fragmentation.
3. **Commission mechanism: a portable brief.** Not a copy-paste-ready artifact and not a subagent
   dispatch — a document that states *what needs designing, what each surface does, what it exposes,
   the APIs each card type connects to, the data that lands on each card, and the verbs/buttons.*
   The Designer builds against a mock API; we pick up the returned frontend and run with it.
4. **Onboarding: no new designed surface.** See the think-through below.

## The undesigned surface area (what the brief covers)

- **The card-registry renderer's visual treatment** — the generic shell + slot system exists and
  renders the `task` type correctly; it needs the full **state design** (default, hover, expanded,
  agent-running, needs-human, complete, failed, error/degraded, success-after-action) and the
  score-chip tone classes.
- **The three new card kinds** — `recommendation` (body `diff`), `receipt` (body `preview`),
  `graduation` (body `agreement`). Wired to real endpoints; currently placeholder divs.
- **The Profile/Config room (in Engine)** — the one genuinely net-new surface. No HTTP API exists
  yet (only the `profile_lib` Python module), so its endpoints are documented as **proposed**.
- **The Quality trust dashboard** — reads real data (agreement %, real ladder tier, disagreements)
  but renders as a bare row list; restyle into a calm trust surface.

## Onboarding think-through (verified against the live code)

The seed spec imagined dedicated "onboarding cards." **They are not needed as a new surface.**
Onboarding is the Phase-2 conversational concierge (type `onboard me` in Claude Code); the board
chapter of it is just **ordinary tasks rendered through the existing `task` card type**:

- *"Draft your voice profile"* → an **agent** task → **Start agent** → review → **Approve & archive**.
- *"Set up Otter or Granola"* → a **collab** task → agent proposes → human runs/approves.

Verified in the live UI: the **dispatch/approve verbs already live in the modal footer** —
`Start agent` (when `canDispatch`: an open collab/agent task), `Rerun agent`, `Approve & archive`
(when `agent_status === 'complete'`). Collab tasks already get a **"Needs Your Action"** lane label.
`agent_status` already carries the calm states the tutorial needs (`running` / `needs-human` /
`complete` / `failed`), each with human-readable modal copy.

So the concierge sets the system up in Claude Code, launches the user into the board, and they
**learn the system by disposing of their first real cards** — through affordances that already
exist. **The Designer designs nothing new for onboarding.**

**The one carry-forward this surfaces:** those `agent_status` states and the collab
approve/dispatch affordances are *load-bearing for the calm first-run feel* (the seed spec's
"agent-running pulse, not a spinner farm"). They exist but are minimally styled — so the brief's
**card-shell states** section hands them to the Designer as **existing states to render calmly**,
even though they are not new work.

## Folded-in residual: the owed Phase-4 visual pass

Phase 4 left an on-screen visual pass owed (no JS test harness, by design). Folded into Phase 5 as
a **verification step after the brief is written** (it validates the *existing baseline* the
Designer integrates against; it does not block the hand-off): on dev `:8743`, confirm all card
variants render and accept→receipt→undo / graduate / react work, and acted-on cards leave the board.

## Out of scope (unchanged from Phase 4 deferrals)

Dispatch-behavior enforcement of ladder tiers (gated hold-for-review, autonomous auto-complete) →
later; task→transcript join (capture dispatch `session_id`) → future; `description_patterns`
ignored by the regex worker-matcher → substrate cleanup; `ladder.json` single-writer concurrency →
documented, no flock. None are pulled into Phase 5.
