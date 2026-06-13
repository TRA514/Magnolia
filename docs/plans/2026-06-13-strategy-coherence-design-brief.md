# Strategy Coherence — design brief + draft spec for the conformance-testing organ

> 2026-06-13. **Part A** is a brief you can hand to a design/build agent (via `/magnolia-build`) to
> produce the detailed design. **Part B** is the draft spec of the primitives, far enough along to
> iterate on and constrain the design agent. This is **v1, written to be argued with.**
>
> Companion docs: `2026-06-12-cadence-design-brief.md` (Strategy Coherence is the **strategic sibling
> of the `portfolio-health` janitor** defined there — same self-hosting pattern, higher altitude) and
> `2026-06-12-loop-abstractions-brainstorm.md` (the standing-objective abstraction).
>
> **Hard dependency, stated up front:** Strategy Coherence is a *consumer* of Cadence's grounded
> substrate. It cannot be built before Cadence's program store, sentinels, reconciler, and the
> `target`/`register` models exist (Cadence slices 1–7). You build up, not down — a coherence checker
> standing on ungrounded documents is a confident-essay generator, the exact thing that erodes trust.
> Everything below assumes Cadence is real.

---

# Part A — The brief

## Mission

Build the **third altitude** of Magnolia. The task board is the **verbs** of the operator's life.
Cadence is the **state of their programs** — tactical custody, one loop per commitment. Strategy
Coherence is the **shape of the whole** — a continuous conformance test between the operator's
*declared strategy* (the spec) and their organization's *revealed behavior* (the implementation),
which flags where the implementation has drifted from the spec **without an approved spec change.**

Organizations drift from their stated strategy continuously and invisibly. No single decision causes
it — it accumulates from a thousand small sprint calls, meeting agendas, and deprioritizations, each
defensible alone, none ever declared. The operator finds out a quarter or a year later, in the
post-mortem: *"how did we spend a quarter and not move the thing we said mattered most?"* Strategy
Coherence is the smoke detector for that drift. It is the one strategic-altitude job that is **both
genuinely strategic and genuinely gradable**, because it reports a *present-tense fact*
("effort vector ≠ priority vector, right now") rather than a *future bet* ("this allocation will pay
off") — so it can be calibrated and trusted in a way that a "drive-the-bets" agent never can.

**What it is not.** It does not decide. It does not allocate. It does not answer judgment questions
as the operator. It asserts exactly one kind of thing: *"these two grounded representations have
drifted, and no decision on record explains why — real, or did we quietly change our minds?"* The
operator decides what to do with that. The only thing it makes is **incongruence undeniable.**

## What the design agent must deliver

1. **The `strategy-coherence` program type** — a new Cadence program type (Part B §3), recommended as
   a new **`coherence` state model** (the fifth, Part B §2), with the schema-gate changes that admits
   it. Justify the new state model or fold it onto `target`/`register` with evidence.
2. **The declared-intent vector schema** (Part B §4) — the minimal structured representation of "what
   we said we wanted," extracted from strategy artifacts and confirmed by the operator. This is the
   load-bearing, hardest piece; treat it as the center of the design, not an input.
3. **The revealed-behavior assembly** (Part B §5) — how the five behavior vectors are read *from
   Cadence's existing grounding* (program store, sentinels, did-it-work, meeting/ticket/metric
   sources). The surfacer is a consumer; it adds no new collectors.
4. **The five coherence checks as a closed set** (Part B §6) — each a comparison between a declared
   vector and a revealed vector, producing a cited divergence finding or silence, filtered through the
   decisions ledger.
5. **The decisions-of-record ledger** (Part B §7) — the append-only store of the operator's actual
   decisions, whose job here is the **noise filter** that separates reconciled divergence (we changed
   our mind, on record) from unreconciled drift (the gold).
6. **The divergence card + calibration loop** (Part B §8) — the finding's emission as a gated card,
   the accept/known split as the precision signal, and the strategic miss-audit as the recall signal.
7. **UI: the Coherence surface** (Part B §9) — jobs-to-be-done + data inventory only; private to the
   owner; rendered from the registry; theme tokens only.
8. **Build slices** (Part B §10) — sequenced on top of Cadence's slices, each independently verifiable.

## Non-negotiable philosophy constraints

These extend the existing invariants and Cadence's constraints; the design must not bend them:

- **Read-only, zero external writes.** Strategy Coherence performs no external action. Every output is
  a card emitted into the existing task queues, governed by the existing judge, trust ladder, and
  Tier-2 confirm (invariant #5). It reads; it never writes outward. No new shipper, no new ladder.
- **Two independently grounded sides per check.** A coherence finding is never a comparison of a
  document to itself. The declared side is grounded in stated artifacts; the revealed side is grounded
  in behavioral evidence. The finding *is* the delta between two grounded vectors, with citations on
  both sides. A check that cannot cite both sides does not fire.
- **Surface, never resolve.** The system makes incongruence visible and stops. It never auto-resolves
  an intent/behavior conflict, never rewrites the strategy, never reallocates. Resolution is a human
  judgment that may correctly run *against* the evidence for reasons the system can't see.
- **Reconciled vs. unreconciled is the whole game.** Divergence explained by a decision-of-record is
  *suppressed*. Only divergence with no reconciling decision is surfaced. The decisions ledger is the
  precision mechanism; without it the surfacer cries wolf on every known trade-off and gets muted in a
  week.
- **Private to the owner.** "Your revealed priorities contradict your stated strategy" is true,
  useful, and socially radioactive. It surfaces to the strategy's owner, who decides what to do with
  it. It never broadcasts org-misalignment into a shared channel. (Same fact/interpretation boundary
  Cadence draws, at higher stakes.)
- **Append-only, citable, never deleted** (invariant #6). The decisions ledger and the findings log
  are append-only. Append-only fences the retroactive "we always meant to do that" rewrite of intent.
- **Profile-driven identity** (invariant #1). Strategy, owners, and routing targets come from
  artifacts and `profile/` via `profile_lib`. No person/team/company literal in the engine.
- **Declared, gated, theme-tokens-only** (invariants #2, #3). The type and its checks live in the
  gated registry; the `coherence` state model is a closed addition requiring a gate change;
  presentation references theme tokens only.
- **Honest confidence.** Revealed vectors are noisy (story points lie; not all work is ticketed;
  meeting-time is a proxy). Findings carry confidence from witness weight (independence, staleness,
  coverage). The surfacer fires on strong, multi-witness divergence and stays quiet on marginal
  signal. Cry-wolf risk lives entirely here.

## Why this shape (context for the agent)

The seductive version of this feature is "an agent that holds the whole picture and drives strategy."
That version is a mirage: strategic *decisions* resolve in quarters-to-years, confounded, N=1, so the
calibration machinery that makes Magnolia trustworthy cannot run at that altitude, and the agent can
never earn a track record. This feature deliberately changes the verb from **decide** to **detect a
present-tense conformance fact**, which is the move that makes a strategic-altitude capability
buildable and trustworthy. Hold that line: every time a check wants to opine on what the operator
*should* do, it has drifted out of scope. Its entire job is the delta and the question.

The mechanism is not new. **A coherence check is Cadence's `sources-disagree` contradiction door
pointed at a new pair of sources** — "what we said we'd do" vs. "what we're actually doing." Reuse
that machinery; do not invent a parallel one.

---

# Part B — Draft spec (iterate on this)

## 1. The primitive vocabulary (delta from Cadence)

| Primitive | Job | Relation to Cadence |
|---|---|---|
| **Declared-intent vector** | The minimal structured "what we said we wanted": priority ranking, intended allocation, target+theory-of-change, key bets | New. The `coherence` program's declared state (analogous to a pipeline's checkpoints) |
| **Revealed-behavior vector** | The grounded "what's actually happening," per behavior dimension | Assembled from Cadence sentinels / did-it-work / program store — no new collectors |
| **Coherence check** | One comparison: declared vector vs. revealed vector → divergence or silence | New. A closed set of five (§6) |
| **Decisions-of-record ledger** | Append-only store of actual decisions; here, the noise filter for reconciled drift | New, but reusable system-wide |
| **Divergence finding** | A cited delta between two grounded vectors + the standing question | Emitted as an existing gated card |
| **Strategy-coherence program** | The standing portfolio-altitude loop that runs the checks each cycle | A Cadence program; strategic sibling of `portfolio-health` |

## 2. The `coherence` state model (recommended fifth model)

Cadence defines a closed set of four state models (pipeline / cycle / target / register). Strategy
Coherence is the test case for whether a fifth is warranted. **Recommendation: yes, add `coherence`.**

| Model | Shape | Drift means |
|---|---|---|
| **coherence** | A set of **declared vectors** held against a set of **revealed vectors** over a window | A declared/revealed pair diverges beyond tolerance **and no decision-of-record explains the gap** |

Why not fold onto existing models:
- **Not `target`** — `target` compares one metric to its *own* expected trajectory. Coherence compares
  *two independently grounded representations* of the same intent (a plan vs. a behavior), with the
  decisions-ledger reconciliation filter. The witness shape and the filter are genuinely different.
- **Not `register`** — `register` ages a set of owned items to closure. Coherence has no items to
  close; its unit is the *delta between vectors*, recomputed each cycle.

Adding a state model is deliberately hard (a design doc + a `program_schema.py` gate change) — this
document is that design doc. Drift verdicts stay uniform across all five models
(`holding` / `drifting` / `broken` / `blind`) so the UI and escalation policy never special-case a
type; what *computes* the verdict is model-specific (here: the §6 checks).

**Open decision for the design agent:** confirm the new model vs. a `target`-with-vector-instruments
compromise, with a worked example either way.

## 3. Program type — registry entry (draft)

`cadence/programtypes/registry.json`, validated by `scripts/program_schema.py` (extended for
`coherence`):

```json
{
  "id": "strategy-coherence",
  "label": "Strategy coherence",
  "family": "strategy",
  "state_model": "coherence",
  "cadence": "weekly",
  "horizon": "annual+quarterly",
  "intent_sources": [
    { "kind": "strategy_doc",       "mode": "read" },
    { "kind": "eos_vto",            "mode": "read" },
    { "kind": "roadmap_planned",    "mode": "read" },
    { "kind": "decisions_ledger",   "mode": "read" }
  ],
  "behavior_sources": [
    { "kind": "program_store",      "mode": "read", "via": "program_lib" },
    { "kind": "project_management",  "mode": "read", "via": "adapter" },
    { "kind": "meetings",           "mode": "read" },
    { "kind": "customer_signal",    "mode": "read", "via": "adapter" },
    { "kind": "metrics",            "mode": "read", "via": "adapter" }
  ],
  "checks": [
    "intent-vs-allocation",
    "intent-vs-outcome",
    "intent-vs-external-reality",
    "intent-vs-intent",
    "declared-done-vs-actually-done"
  ],
  "reconciliation_filter": "decisions_ledger",
  "emitters": [
    { "on": "divergence:confirmed", "action": "escalate",        "template": "coherence-divergence" }
  ],
  "presentation": { "chip_tokens": { "holding": "--coh-holding", "drifting": "--coh-drift", "broken": "--coh-broken" } }
}
```

Gate checks (minimum, on top of Cadence's): `state_model == coherence` admits the `checks` block;
every `check` ∈ the closed set (§6); every source has an explicit `mode: read` (a coherence type may
declare **no** write-capable source or emitter — it is read-only by construction); `reconciliation_filter`
resolvable; all emitter actions are non-external (`escalate` / `propose-update` only — never
`draft-message` to an external audience in v1); presentation theme-tokens only; denylist scan over
`cadence/**` extended.

## 4. The declared-intent vector (the hard center)

The quality of the whole capability is gated here. Strategy lives as prose; checks need structure. The
discipline: extract the **minimal comparable spine**, operator-confirmed — not a universal goal-graph
(that's the over-generalization we explicitly rejected; see the conversation that birthed this doc).
Only the structure a check actually consumes earns its place.

```yaml
# the declared state of the strategy-coherence program, confirmed by the operator
intent:
  horizon: "2026"
  priorities:                      # ranked — the ranking IS the claim
    - { id: P1, statement: "Enterprise expansion", rank: 1 }
    - { id: P2, statement: "Activation",           rank: 2 }
    - { id: P3, statement: "Platform reliability",  rank: 3 }
  intended_allocation:             # rough declared share of capacity/attention; bands, not false precision
    - { priority: P1, share_band: "40-60%" }
    - { priority: P2, share_band: "20-30%" }
    - { priority: P3, share_band: "10-20%" }
  theories_of_change:              # the bet under each priority + its leading indicator
    - { priority: P2, lever: "cut onboarding 5→3 steps", leading_metric: "activation_rate", instrument: "adapter:pendo" }
  key_bets:
    - { id: B1, statement: "Win on configurability vs. competitor X", premise_check: "intent-vs-external-reality" }
  assumptions:                     # cross-plan premises that other plans must not contradict
    - { id: A1, statement: "New pricing ships Q2", referenced_by: ["roadmap_planned", "gtm_plan"] }
```

Extraction is an **agent pass over the intent sources** that proposes this spine; the operator
confirms or corrects it on a grounding card (reusing Cadence's grounding-pass pattern, §7.5 there).
The corrections are calibration data. **No uninstrumented intent:** every `theory_of_change` names a
`leading_metric` + `instrument`, or it can't be checked by `intent-vs-outcome` and the gate flags it.

## 5. The revealed-behavior vectors (assembled, not collected)

Each check needs a *revealed* counterpart to its declared vector. All of these are read from grounding
Cadence already produces — Strategy Coherence is a pure consumer:

| Revealed vector | Source (existing) | Known noise |
|---|---|---|
| **Effort allocation** | `project_management` adapter: where active work/units sit, mapped to priorities | story points lie; un-ticketed work invisible |
| **Attention distribution** | `meetings` corpus: meeting time/agendas by topic | proxy for attention only |
| **Customer-signal distribution** | `customer_signal` adapter (Gong/Zendesk) + Pendo Listen: what customers actually push on | sampling/recency bias |
| **Outcome movement** | `metrics`/Pendo: did each theory-of-change's leading metric move | confounded; lag |
| **Declared-done reality** | `program_store` + did-it-work checkpoints: is "handled" actually handled | depends on instrument coverage |

Mapping work/signal to priorities (the `P1..Pn` buckets) is itself a judged step with error bars —
the design must specify how a unit of work is attributed to a priority (tags? epic→priority binding?
an attribution pass?) and how unattributable work is reported (an "unmapped X%" residual is itself a
coherence signal — effort going somewhere no declared priority claims).

## 6. The five checks (closed set)

Each check: declared vector `D`, revealed vector `R`, compute divergence, **suppress if a
decision-of-record reconciles it**, else emit a finding at the computed confidence.

1. **`intent-vs-allocation`** — declared priority/allocation vs. revealed effort+attention.
   *"P1 (rank 1, intended 40–60%) is getting ~12% of revealed effort; the unmapped residual is 31%."*
   The flagship. Catches drift no one decided.
2. **`intent-vs-outcome`** — theory-of-change activity exists, but the leading metric is flat past
   tolerance over the window. *"Activation work shipped for 8 weeks; `activation_rate` unmoved — the
   theory of change may be failing and nothing is treating it as a problem."*
3. **`intent-vs-external-reality`** — a key bet's premise vs. external signal. *"Bet B1 assumes we win
   on configurability; 9/12 customer calls this quarter are about integrations, which no priority
   covers — the market may be contradicting the premise."*
4. **`intent-vs-intent`** — two declared plans whose assumptions are mutually inconsistent.
   *"`roadmap_planned` assumes new pricing ships Q2 (A1); `gtm_plan` assumes old pricing through Q3 —
   these can't both hold."* Pure logic check; high precision; cheap.
5. **`declared-done-vs-actually-done`** — Cadence's is-it-done gate at system scale. *"Three
   initiatives marked complete in the roadmap have open did-it-work checkpoints failing."*

**Determinism boundary:** `intent-vs-intent` and `declared-done-vs-actually-done` are largely
deterministic (logic + checkpoint status). `intent-vs-allocation`, `-outcome`, `-external-reality`
require attribution/judgment and reuse `judge.py` with coherence rubrics — spend judgment only where
arithmetic can't reach, exactly as Cadence's reconciler does. Enumerate per-check determinism in the
design.

## 7. The decisions-of-record ledger (the noise filter)

`datasets/decisions/` — append-only, one entry per decision, each citing its evidence (a strategy
session, an accepted proposal, a Slack thread the operator confirmed):

```yaml
- id: DEC-0042
  date: 2026-05-20
  statement: "Pause enterprise initiatives this quarter; absorb the SMB outage remediation."
  affects_priorities: [P1]
  expires: 2026-09-30          # a decision can be time-boxed; after expiry, the divergence re-surfaces
  source: "datasets/meetings/2026-05-20_strategy_…md"
```

Its job in this feature: when a check computes divergence on P1, it asks the ledger *"is there a
standing decision that explains P1 getting 12%?"* If yes (DEC-0042, unexpired) → **suppressed**
(reconciled divergence, you changed your mind on record). If no → **surfaced** (unreconciled drift,
the gold). This is the entire difference between a useful surfacer and an annoying one.

Capture follows the existing pattern: decisions are *proposed* into the ledger from the evidence
stream (strategy sessions, the operator's accept/reject on coherence cards) and the operator confirms
— nuance captured to a durable store, never inferred from a generated artifact (invariant #4).
Append-only (invariant #6) means intent can't be silently rewritten to erase a drift.

> The ledger is reusable beyond this feature (it's also how a future "answer as me" briefer would know
> the operator's positions of record). Scope v1 to what Strategy Coherence needs: statement, affected
> priorities/bets, evidence citation, optional expiry.

## 8. The divergence card + calibration

**Emission.** A confirmed divergence becomes an `escalate` card on the human queue (private to the
owner): the two grounded vectors with citations, the magnitude, the confidence, and the standing
question — *"P1 is getting 12% of effort against a 40–60% intent and no decision explains it. Real, or
did we change our minds?"* Three responses, which **are** the calibration signal:

- **"Real — didn't realize"** → true positive. The card converts to whatever action the operator wants
  (a task, a strategy-session trigger). Nothing suppressed.
- **"Intentional / known"** → false positive → writes a decision-of-record (DEC-…) and auto-suppresses
  the recurrence. The system just learned the exception.
- **"Wrong read"** → the attribution/grounding was off → binding/attribution correction, calibration
  data for the check.

**Precision** is the known/real split above — fast, present-tense feedback. **Recall** is the
strategic **miss-audit**: when a painful post-mortem happens ("we under-delivered on P1 all year"),
the `portfolio-health` janitor (or this program's own audit) walks back — was the drift visible in the
behavioral evidence, and did the surfacer stay silent? A silent miss is the expensive error; logging
it tunes thresholds and, like Cadence's ladder, can demote a check to advisory. Recall feedback is
slower (post-mortems are rare) but it's the signal that earns trust in the "all clear."

**Trust ladder.** `coherence-divergence` registers as its own action type in `ladder_lib`, shadow by
default. It never auto-acts (it only escalates to a human), so it stays advisory — but its
precision/recall calibration is what tells the operator how much to weight it.

## 9. UI — the Coherence surface

A view (own tab, or a card on Now — design's call), **jobs-to-be-done + data inventory only**, private
to the owner, rendered from the registry + program files, theme tokens only (invariant #3).

- **Job to be done:** answer *"is what we're doing still what we said we'd do — and where has it
  silently drifted?"* at a glance.
- **The standing read:** per priority/bet, declared vs. revealed side by side, drift verdict
  (`holding/drifting/broken/blind`), and whether a decision-of-record reconciles any gap.
- **Per-finding:** the two cited vectors, magnitude, confidence, the question, and the response
  actions (§8). Linkable out to the underlying evidence (the epics, the calls, the metric series).
- **The fence (§8.4 of Cadence applies):** no percent-complete theater, no priority scores invented by
  the system, no people/workload views, no auto-resolution UI. If an element can't cite a declared and
  a revealed vector, remove it. The surface reports deltas; it never renders a recommendation.

## 10. Build slices (on top of Cadence, each independently verifiable)

0. **Prereq:** Cadence slices 1–7 (program store, reconciler, sentinels, `target` + `register`,
   proposal door + ladder). Strategy Coherence does not start before this.
1. **Intent vector + ledger substrate**: the §4 schema + extraction/grounding pass + the §7 decisions
   ledger + `program_schema.py` gate for the `coherence` model. No checks yet — confirm an intent
   vector and a decision via CLI; gate goes green.
2. **The two deterministic checks**: `intent-vs-intent` and `declared-done-vs-actually-done` (logic +
   checkpoint status), divergence cards, the known/real/wrong response loop writing the ledger.
   *This alone is useful: cross-plan contradictions and false "done"s, caught weekly.*
3. **`intent-vs-allocation`**: the attribution pass (work/attention → priorities), the unmapped
   residual, judged divergence with confidence. The flagship lands.
4. **`intent-vs-outcome`**: theory-of-change leading-metric tracking (reuses did-it-work instruments).
5. **`intent-vs-external-reality`**: customer-signal distribution vs. key-bet premises.
6. **Coherence surface UI** + the strategic miss-audit wired into `portfolio-health`.
7. **Factory**: `strategy-coherence` becomes a documented type producible via `meta-create-program-type`.

## 11. Open questions for the design agent

- **Intent-vector fidelity:** how much structure is "minimal"? Is ranked priorities + allocation bands
  + theories-of-change + assumptions enough, or is one missing (e.g., explicit anti-goals)?
- **Attribution:** how is a unit of work/attention mapped to a priority — binding, tags, or a judged
  pass? How is the unmapped residual surfaced without becoming noise?
- **Allocation truth:** is tracker effort a good-enough revealed-effort proxy for v1, or is it so noisy
  it should ship behind an explicit confidence floor?
- **Decision expiry & scope:** do decisions reconcile a *specific* divergence or a whole priority? How
  granular before the ledger becomes bookkeeping?
- **Multi-owner strategy:** v1 is single-owner/private. When two leaders hold different intent vectors
  (the bottom-up/top-down "lands in the middle" case), is the divergence between *their* vectors itself
  a check — and how is that surfaced without weaponizing it? (Likely out of v1; note the seam.)
- **Cadence vs. cadence:** weekly is probably too noisy for strategy; is the right heartbeat monthly
  with an on-demand "pre-QBR" refresh? Anchor to human strategic rhythms, not the sweep.
- **The new state model:** is `coherence` genuinely the fifth, or does a `target`-with-vector
  compromise hold? (Decide with a worked example both ways — §2.)

## 12. Success criteria (how we know it worked)

This is **not a throughput multiplier** and the metrics must not pretend otherwise. Its value is
*avoided catastrophic misallocation* — lumpy, high-EV, mostly invisible until it prevents the one
"we drifted for a year" post-mortem. Honest measures:

- **Precision:** share of surfaced divergences the operator marks "real, didn't realize" (target: high
  enough that the operator reads every card; cry-wolf kills the feature).
- **Recall (the one that matters):** strategic misses caught by post-mortem audit that the surfacer
  *should* have flagged from the evidence and didn't (target: trending to zero).
- **Lead time:** for true-positive drifts, how many weeks earlier than the operator would otherwise
  have noticed (the actual value created).
- **Trust proxy:** does the operator act on "all clear" — i.e., stop manually re-auditing strategy
  alignment? That behavior change is the real success, and it only comes from recall being trustworthy.

---

# Appendix — the five checks, worked

| Check | Declared vector | Revealed vector | Example finding | Determinism |
|---|---|---|---|---|
| intent-vs-allocation | ranked priorities + allocation bands | effort + attention by priority (+ unmapped residual) | "P1 rank-1, 40–60% intended, 12% actual; 31% unmapped" | judged (attribution) |
| intent-vs-outcome | theory-of-change + leading metric | metric movement over window | "8wk activation work, metric flat — theory failing" | mostly deterministic (instrumented) |
| intent-vs-external-reality | key-bet premise | customer-signal distribution | "premise = configurability; 9/12 calls = integrations" | judged |
| intent-vs-intent | cross-plan assumptions | (the plans themselves) | "pricing Q2 vs. old-pricing-through-Q3 conflict" | deterministic (logic) |
| declared-done-vs-actually-done | roadmap "complete" flags | did-it-work checkpoint status | "3 'done' initiatives have failing checkpoints" | deterministic (status) |

**One-line for the build agent:** you are building continuous conformance testing between declared
strategy and revealed behavior. The only thing it ever asserts is *"these two have drifted and no
decision explains why."* It surfaces; it never decides. It stands entirely on Cadence's grounding —
build it last, build it read-only, and make its precision the operator's reason to believe its silence.
