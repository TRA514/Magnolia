# Cadence — design brief + draft spec for the standing-loop subsystem

> 2026-06-12. This document is two things: **Part A** is a brief you can hand to a design/build agent
> (via `/magnolia-build`) to produce the detailed design — data model, UI, and scaffolding. **Part B**
> is the draft spec of the primitives, far enough along to iterate on and constrain the design agent.
> Companion thinking: `2026-06-12-loop-abstractions-brainstorm.md` (Cadence programs are the "standing
> objective" from that doc, made concrete).

---

# Part A — The brief

## Mission

Build the second organ of Magnolia. The task board is the **verbs of the operator's life** — discrete
items routed through their attention. Cadence is the **state of their program** — standing loops that
hold declared intent against observed reality on a schedule, and emit a verb onto the task board only
when something genuinely needs a human.

Cadence is an agentic TPM attached to the chief of staff: it tracks, reconciles, nudges, prepares, and
verifies — the convexity work where the last 5% of completeness carries most of the value (the one
dropped commitment is always the one that detonates).

The four seed loops it must support on day one (detailed in the Appendix):

1. **Roadmap & pipeline health** — initiatives move discovery → planning → execution on time, in the
   declared order, with enough refined work always in front of the team.
2. **Weekly prioritization & delivery** — a Monday priorities digest the system drafts and the operator
   tweaks; incoming priorities captured all week; every declared item gated by *"is it actually done?"*
   checks against ground truth (e.g. the PM tracker via the adapter seam).
3. **Did it work?** — every shipped feature's predicted metrics tracked weekly against actuals; closure
   fan-out (who asked for this → notify → hand off to marketing).
4. **EOS facilitation** — scorecard, rocks, issues, to-dos, L10 prep. Strictly a **facilitator, not a
   scribe**: the team updates their EOS sheet manually *on purpose*; this loop reads, prepares, and
   nudges — it never writes to manual-on-purpose sources.

## What the design agent must deliver

1. **Data model design** — finalize the schemas in Part B (program type registry, program instance
   file, observation ledger, cycle log, emitter playbooks) with worked examples for all four seed
   program types.
2. **Schema gate** — `scripts/program_schema.py`, the sibling of `card_schema.py`: validates the
   program-type registry (closed state-model set, theme-token-only presentation, instrumented
   checkpoints) and becomes part of invariant #2's green gates.
3. **UI design for the Cadence tab** — see the UI contract (Part B §6). Table-first, grouped by loop
   family, rendered entirely from the registry (no per-type hardcoded UI), theme tokens only.
4. **Sentinel + reconciler + emitter pipeline design** — how the observe → reconcile → emit cycle runs
   on the existing cron + dispatch substrate, and how emissions enter the existing task system.
5. **Factory extension** — `meta-create-program-type`, the fourth sibling under `meta-factory-core`
   (scaffold → capture-to-profile → gate-green → commit → Keep/Undo receipt).
6. **Build slices** — refine the slice plan in Part B §8 into a sequenced plan with verification steps
   per slice (live board e2e, per conventions).

## Non-negotiable philosophy constraints

These extend the existing invariants; the design must not bend them:

- **Files-based, local-first.** Programs are markdown files with YAML frontmatter under `datasets/`,
  exactly like tasks. Git is the history. No database.
- **One external-write seam.** Cadence performs **zero external writes** itself. Every outward action
  (nudge, digest send, escalation) is emitted as a task into the existing queues, governed by the
  existing judge, trust ladder, and Tier-2 confirm. No second shipper, no second ladder.
- **Declarative types, gated.** All flexibility lives in the program-type registry; instances are
  rigid. The registry is validated by a schema gate that runs with the green gates (invariant #2).
  Presentation references theme tokens only (invariant #3 extended).
- **Append-only evidence.** Observation ledgers and cycle logs are never deleted or rewritten
  (invariant #6 extended). Every observation cites its source (file + location).
- **Profile-driven identity** (invariant #1). No person, team, company, distro, or channel literal in
  the engine. Which program types are active is per-person (program packs, like skill packs). Routing
  targets (distro lists, channels) live in `profile/` via `profile_lib`.
- **Manual-on-purpose sources are read-only forever.** A source declared `mode: read` in a program
  type can never gain write access by configuration. The EOS sheet is the canonical example.
- **Fact vs. interpretation.** Program state mutates through exactly two doors: (a) adapter-grounded
  facts (e.g. tracker status changed) applied mechanically with an observation citing the evidence;
  (b) interpretations (off-track judgments, date-change proposals) emitted as proposal cards a human
  approves — climbing the existing trust ladder like any other action type.
- **No uninstrumented checkpoint.** Every date, target, or invariant a program declares must name how
  it is measured (an adapter query, a metric source, a deterministic check, or explicitly
  `human-attested`). A checkpoint without an instrument fails the schema gate. (This is the LFD
  instruments rule from the companion doc, made an invariant.)

## Why this shape (context for the agent)

The task-board side is easy to extend because its primitives are small, single-purpose, and gated:
workers scope, skills instruct, cards declare presentation, cron schedules, the judge scores, the
ladder governs, adapters write. Cadence must replicate that Lego quality with the same discipline:
**sentinels observe, the reconciler judges drift, emitters propose, programs remember.** No primitive
does two jobs. A future agent extending the system should be able to add a persona's whole world by
dropping one program-type entry and one pack reference — and should find it *structurally impossible*
to create an ungated write path or an unmeasurable promise.

---

# Part B — Draft spec (iterate on this)

## 1. The primitive vocabulary

| Primitive | Job | Analog on the task side |
|---|---|---|
| **Program** | A unit of custody: declared intent + dates + state, held over time | Task (but persistent) |
| **Program type** | Declarative shape: state model, phases/fields, cadence, sentinels, emitters, sources | Card type in `registry.json` |
| **State model** | One of a **closed set of four** behaviors a type builds on | (new — the fuck-up fence) |
| **Sentinel** | Reads sources asking one question: *did anything move a program?* Emits observations | Worker (reuses dispatch substrate, different contract) |
| **Observation** | Append-only, source-cited evidence entry on a program | Activity-log entry |
| **Reconciler** | Per cycle: declared vs. observed → drift verdict + state updates (facts) + proposals (interpretations) | Judge + enforce_lib |
| **Emitter** | Declarative `on: <condition> → action` playbook; all actions exit as tasks | shipper / card actions |
| **Cycle** | One heartbeat of a program: observe → reconcile → emit → log | Cron tick + receipt |
| **Program pack** | Persona-gated set of program types, active list in profile | Skill pack |

## 2. The four state models (closed set)

Types choose exactly one. New state models require a design doc and a gate change — deliberately hard.

| Model | Shape | Drift means | Seed examples |
|---|---|---|---|
| **pipeline** | Ordered phases, each with an entry/exit window | Phase overage, date slip, sequence violation, starved supply | Roadmap initiatives; launch checklists |
| **cycle** | Recurring steady-state with a cadence artifact; no phases | Artifact late/missing; captured items not reflected; declared items failing the is-it-done gate | Weekly priorities; L10 prep; scorecard digest |
| **target** | Metric(s) vs. expected trajectory over a window | Actual diverging from predicted beyond tolerance | Did-it-work scoreboard; EA ramp; forecast honesty |
| **register** | A set of items, each with an owner and a closure condition | Item aging past policy; orphaned items; closures unverified or uncommunicated | Customer-promise ledger; decision log; risk register; bug-queue aging |

Drift verdicts are uniform across models — `holding` / `drifting` / `broken` — so the UI, escalation
policy, and portfolio rollups never special-case a type. What *computes* the verdict is model-specific.

## 3. Program type — registry entry (draft schema)

`cadence/programtypes/registry.json`, validated by `scripts/program_schema.py`:

```json
{
  "id": "roadmap-initiative",
  "label": "Roadmap initiative",
  "family": "roadmap",
  "state_model": "pipeline",
  "phases": [
    { "id": "discovery",  "label": "Discovery",  "max_age_days": 21 },
    { "id": "planning",   "label": "Planning",   "max_age_days": 14 },
    { "id": "execution",  "label": "Execution" },
    { "id": "shipped",    "label": "Shipped" },
    { "id": "verified",   "label": "Verified", "terminal": true }
  ],
  "cadence": "weekly",
  "sources": [
    { "kind": "transcripts", "mode": "read" },
    { "kind": "project_management", "mode": "read", "via": "adapter" },
    { "kind": "team_threads", "mode": "read" }
  ],
  "sentinels": ["movement-watch", "tracker-truth"],
  "checkpoint_instruments": ["adapter:project_management", "human-attested"],
  "emitters": [
    { "on": "checkpoint_overdue", "action": "draft-message", "template": "nudge-owner" },
    { "on": "phase_overage",      "action": "propose-update", "template": "phase-stall" },
    { "on": "drift:broken",       "action": "escalate" }
  ],
  "presentation": { "chip_tokens": { "discovery": "--phase-early", "execution": "--phase-active" } }
}
```

Gate checks (minimum): `state_model` ∈ closed set; phases only on `pipeline`; every emitter `action`
∈ closed action set; every source has an explicit `mode`; `mode: read` sources have no write-capable
emitter targeting them; every checkpoint instrument resolvable; presentation uses theme tokens only;
no identity literals (denylist scan extends to `cadence/**`).

## 4. Program instance — file format (draft)

`datasets/programs/PROG-0007.md` — same frontmatter-plus-ledger pattern as tasks:

```markdown
---
program_id: PROG-0007
type: roadmap-initiative
title: "Payments reconciliation revamp"
owner_role: product            # role reference, never a name (invariant #1)
created: 2026-06-12T09:00:00Z
phase: discovery
phase_entered: 2026-06-12
checkpoints:
  - { id: discovery-exit, due: 2026-07-03, instrument: "human-attested", status: pending }
  - { id: ship, due: 2026-09-15, instrument: "adapter:project_management", status: pending }
links: { tracker_epic: "…", prd: "datasets/product/…" }
drift: holding                 # cached verdict from last cycle, for the UI
last_cycle: 2026-W24
---

## Intent
One paragraph: what this program holds and why it matters.

## Observations
### 2026-06-12T14:02Z — sentinel:movement-watch [status-signal] (confidence 0.8)
source: datasets/meetings/2026-06-11_product_…md (§Action Items)
claim: Discovery spike reported complete; design review is the gate to planning.

## Cycles
### 2026-W24 — holding
sentinels: tracker-truth ✓ · movement-watch ✓ (3 observations) · emitted: none ·
next checkpoint: discovery-exit in 21d
```

Observation `kind` is a closed enum: `status-signal | date-change | completion | commitment | risk |
metric | capture | blocker`. Observations are append-only and always cite a source. (`capture` is how
"things that come into me" land on a cycle program's inbox between digests.)

Open question for the design agent: single file per program vs. directory split
(`program.md` + `ledger.md`) once observation volume hurts — pick a threshold and a migration that
respects invariant #6.

## 5. The cycle pipeline (observe → reconcile → emit → log)

1. **Observe.** Cron fires the program's cadence (existing cron substrate; one job per family or per
   program — design agent decides). Sentinels run on the existing dispatch substrate (`claude -p`,
   worker-style scoping) but with a distinct contract: *output is observations conforming to the
   schema, stamped onto programs* — never artifacts, never tasks. Sentinels are defined like workers
   (`scripts/sentinels/*.md` or a `kind: sentinel` worker flag — design agent decides), declaring
   sources and the observation kinds they may emit. Note: sentinels ask a different question of the
   same exhaust the task-extraction pipeline reads (transcripts, threads, email). They share scan
   scheduling where convenient but share **no** output path.
2. **Reconcile.** `scripts/cadence/reconcile.py` per program: deterministic checks first (dates,
   adapter truth, aging policies), judged interpretation only where determinism can't reach
   (reusing `judge.py` machinery with cadence rubrics). Outputs: drift verdict, mechanical state
   updates (facts, each backed by a cited observation), and proposals (interpretations).
3. **Emit.** Match emitter playbook rules. **Every action becomes a task** in the existing queues:
   - `draft-message` → collab-queue task with drafted message (judge-scored, ladder-governed,
     Tier-2-gated like any `send-message`).
   - `produce-artifact` → generated digest/document (versioned, never overwritten) + a task carrying
     it. *Attachment slice:* add `attachments: [paths]` to task frontmatter and teach the messaging
     adapter to bundle them; degrade gracefully to inline links where a provider can't attach.
   - `escalate` → human-queue card with the program context and the ≤2-sentence "what I need from you."
   - `propose-update` → recommendation card whose accept applies the program mutation. This action
     type climbs the trust ladder: shadow (propose only) → supervised → autonomous (apply + receipt)
     — same `ladder_lib`, new action type, artifact-vs-action rules unchanged.
4. **Log.** Append the cycle entry: what was checked, observed, emitted, and the verdict. This is the
   program's iteration log and the audit trail.

Rate-limit fence (Goodhart guard from the brainstorm doc): per-person nudge caps and response-rate
counter-metrics are part of the emitter spec, not an afterthought. A nudge loop's loss function is
"commitments converge at minimal social cost," and the cheap path — nudge harder — must be fenced in
the schema (`max_nudges_per_person_per_week`), enforced by the reconciler, visible on the program.

## 6. UI contract — the Cadence tab

A sibling top-level tab to Now/Activity/Quality/Engine/Schedules. Rendered entirely from the registry
+ program frontmatter (like cards); theme tokens only; calm by default.

- **Table-first**, grouped by `family` (Roadmap · Weekly · Outcomes · EOS · …). One row per program:
  **headline · state chip** (type-specific label, token-colored) · **drift badge**
  (holding/drifting/broken — the only universal status) · **next checkpoint + date** ·
  **last cycle one-liner** · **needs-you count** (linking to the matching cards on Now).
- **Row expansion**: the time view (pipeline → phase timeline vs. windows; target → predicted-vs-actual
  sparkline; cycle → cadence history; register → aging distribution), the observation ledger with
  source links, and the emission history with outcomes (sent/approved/declined).
- **Steady-state is legible**: a `cycle` program that's simply healthy renders as quiet confirmation
  ("W24 digest sent Mon 08:10 · 9/9 declared items verified done"), not as emptiness.
- **The only buttons** mirror the system grammar: open the related cards, pause program, archive
  program (version-suffixed, never deleted), and the kill switch per program (instant stop of its
  emitters — generalizing the Quality-tab brake).
- Nothing on this tab performs an external action directly. Ever.

## 7. Personas via program packs

`cadence/packs.yaml` (or extend `.claude/packs.yaml` — design agent decides): named sets of program
types. `profile/config.yaml` gains `active_program_packs`. Seed packs:

- **pm**: `roadmap-initiative`, `weekly-priorities`, `did-it-work`, `launch-closure`
- **exec**: `eos-rock`, `eos-scorecard-digest`, `eos-l10-prep`, portfolio rollup
- **eng-lead** (later): sprint-health register, dependency watch
- A teammate forking the engine gets the types; their programs, sources, distros, and channels are
  theirs (profile + datasets). The asymmetry stays private; the machinery ships.

## 8. Build slices (vertical, each independently verifiable)

1. **Substrate**: program file format + `program_lib.py` CRUD + registry + `program_schema.py` gate
   wired into the green gates. Seed `weekly-priorities` + `roadmap-initiative` types. No UI, no agents
   — create/read programs via CLI, gate goes green.
2. **Cadence tab v1**: read-only table from program files. Manual frontmatter edits show up. (Board
   e2e verification per conventions.)
3. **First cycle, deterministic only**: cron-fired reconcile for `pipeline` — date/aging checks, drift
   verdicts, cycle logs, `escalate` emitter → human-queue card. No sentinels yet. *This alone is
   already a useful product: declared dates audited weekly.*
4. **Weekly digest loop end-to-end**: `cycle` model + `produce-artifact` + `draft-message` emitters →
   collab queue → existing send path. The Monday priorities drumbeat goes live.
5. **Sentinels**: `movement-watch` over transcripts (observations with citations), `tracker-truth`
   over the project-management adapter (mechanical fact updates). Observation ledger renders in UI.
6. **Proposal door + ladder**: `propose-update` recommendation cards; register the new action type
   with `ladder_lib`; shadow tier by default.
7. **`register` + `target` models**: promise ledger and did-it-work scoreboard types; Pendo/metric
   instruments for `target`.
8. **Attachments slice**: task `attachments:` + messaging adapter bundling + graceful degradation.
9. **EOS pack**: read-only sheet source, L10-prep cycle type, pre-L10 nudge emitters with rate caps.
10. **Factory**: `meta-create-program-type` under `meta-factory-core`; portfolio rollup card (weekly
    cross-program digest) last, once ≥2 families run.

## 9. Open questions for the design agent

- Single-file vs. directory-per-program threshold and migration (invariant #6-safe).
- Observation dedup/merge policy when multiple sentinels cite the same evidence.
- Reconciler determinism boundary: enumerate which checks per state model are deterministic vs.
  judged, and the cadence rubrics for the judged ones.
- Sentinel scheduling: piggyback existing transcript-processing scans vs. independent cron — cost vs.
  freshness.
- Cycle-program "capture inbox" UX: how mid-week captures are confirmed into next week's digest.
- Archive/rollover conventions for completed programs (quarter boundaries, EOS rock turnover).
- Cross-program awareness: where does "these two drifts share a root cause — the same undecided
  decision" live? (Likely the portfolio rollup, not the per-program reconciler — keep the reconciler
  single-program and dumb.)

---

# Appendix — seed loops mapped to primitives

| Loop (operator language) | Program type(s) | State model | Key sentinels | Key emitters |
|---|---|---|---|---|
| Roadmap & pipeline health | `roadmap-initiative` (one program per initiative) + a `pipeline-supply` target | pipeline (+ target) | movement-watch, tracker-truth | nudge-owner, phase-stall proposal, escalate |
| Weekly prioritization & delivery | `weekly-priorities` (one standing program) | cycle | capture-watch (email/threads/transcripts), tracker-truth (is-it-done gate) | produce-artifact (digest) → draft-message (team channel, attachment), escalate |
| Did it work? | `did-it-work` (one program per shipped feature) | target | metric-watch (Pendo), mention-watch (Zendesk/Gong for closure lists) | produce-artifact (scoreboard), draft-message (marketing handoff), propose-update (verified) |
| EOS facilitation | `eos-rock` (per rock), `eos-l10-prep` (cycle), `eos-scorecard-digest` (cycle) | pipeline/target + cycle | sheet-watch (read-only), transcript-watch, thread-watch | pre-L10 nudges (rate-capped), L10 issue-list artifact, escalate |
| Customer-promise ledger (ext.) | `promise-ledger` | register | gong/transcript commitment-watch, roadmap-truth | closure draft-message, escalate on silent breaks |
| Forecast honesty (ext.) | `forecast-honesty` | target | velocity instrument (existing estimate skill), tracker-truth | propose-update (date divergence), escalate |
