# Loop abstractions — taking Magnolia from "loops that run once" to "loops that descend"

> Brainstorm, 2026-06-12. Grounded in the current engine (trust ladder, judge, eval digest, cron, factory)
> and in the loss-function-development (LFD) framing: *stop prompting agents; design loops that prompt
> agents, give them a target to descend toward, fence the cheap paths, instrument everything, and force
> entropy on stall.* This doc maps that framing onto Magnolia and proposes the product ideas it unlocks.

## 1. Where Magnolia already sits on the loop ladder

The engine is further along than most systems — it already has loops at three altitudes:

| Loop | Today | Loop class |
|---|---|---|
| Judge → enforce → revise → re-dispatch | Live. Bounded at `max_revisions: 1`. Judge hands `judge_why` straight back to the agent. | Inner loop, **one step of descent** |
| Trust ladder graduation (`graduation_assess.py`, twice-weekly) | Live. Passive: waits for volume + approval + agreement to accrue. | Outer loop, **passive soak** |
| Weekly eval digest → improvement agent (`eval_digest.py` → eval-analyst) | Half-wired. Digest runs; the agent that proposes fixes is not. | Meta loop, **signal captured, no descent** |
| Cron daemon | Live. A scheduler of one-shot tasks, not of objectives. | Loop *scheduler*, not loop *controller* |

What's missing is the same thing in every row: **none of these loops hill-climb**. Each takes one step
(score once, revise once, report once) and parks for a human. The LFD framing says the step function is
the easy part — the product is the *loss function* (target + constraints + instruments + forced entropy)
and the *control plane* that lets a human own running loops the way the board lets them own tasks.

## 2. The thesis: Magnolia's moat is already built — it just isn't being spent

The LFD essay's closing argument: execution cost is collapsing to ~$0 wherever outputs are public; the
durable moat is **information asymmetry** — "the eval set nobody else can score against."

Magnolia's engine/profile/datasets split is *exactly* that architecture, built for a different reason
(portability). The engine is the commodity layer — shareable, forkable, denylist-clean. The private layer
is the asymmetry:

- Every 👍/👎 reaction and `human_react_note` is a labeled example of the operator's taste.
- Every edit the operator makes to a draft before sending is a (model output → preferred output) pair.
- Every meeting transcript is ground truth about what customers actually said.
- Judge↔human agreement % is **already computed weekly** — a loss function nobody is descending on.

Today this exhaust is consumed as *governance signal* (climb/demote the ladder) and then discarded as
training signal. The 10x move is to treat it as a **growing, versioned, private eval asset** — the thing
the loops descend against. Everything below builds on that.

## 3. Product ideas

### Idea 1 — The Objective: a fourth work primitive (the hill-climb card)

Today the system has tasks (one-shot), cron jobs (recurring one-shots), and recommendations. Add an
**objective**: a unit of work defined by a *measurable target and a budget* instead of a description.

```yaml
# datasets/objectives/OBJ-0007.md (frontmatter)
objective: "QBR brief for {customer} scores ≥ 9.0 on workflow-cs-prep rubric
            across all 4 persona lenses"
scorer: judge          # any deterministic or judge-backed instrument
bar: 9.0
budget: { wall_clock: "4h", usd: 5.00, cycles: 12 }
entropy: { stall_after: 2, action: "force-jump" }   # see Idea 5
tier: 1                # loops never write externally; only the existing shipper exit does
```

The dispatcher runs the existing worker in a cycle: generate → score → log hypothesis → revise, until
bar met or budget exhausted. Both terminal states emit the existing card grammar — a **receipt** ("met
9.2 in 7 cycles, $1.80") or a **parked diagnosis** ("stalled at 8.1; best artifact attached; iteration
log explains why").

Why this wasn't possible before: `max_revisions: 1` exists because unbounded revision without budgets,
instruments, and stall detection is unsafe and unobservable. The objective primitive is what makes "loop
until good" a *governed* behavior instead of a runaway one. The quality ceiling changes category: today's
ceiling is "what the worker produces in ≤2 attempts"; an objective's ceiling is "what the worker can find
in 12 cycles of scored search" — routinely above the operator's own first draft.

Reuses: task frontmatter conventions, judge as scorer, `enforce_lib` revision mechanics, cron for
recurring objectives, card registry for the new card type (via `meta-create-card-type`).

### Idea 2 — Golden sets: distill the operator's exhaust into private loss functions

A new substrate, `datasets/evals/golden/<task-type>/`, populated automatically from three sources that
already exist in frontmatter and activity logs:

1. **Reaction pairs** — task input + artifact + 👍/👎 + note.
2. **Edit pairs** — for messages/tickets: the agent's draft vs. what the operator actually sent
   (`message_body` at draft time vs. ship time). Edit distance is a free, deterministic loss signal.
3. **Judge-proposed goldens** — already designed (high-score, high-agreement outputs proposed, human
   vets). Wire it.

Rules straight from the LFD playbook, enforced by a gate:

- **Blind**: a loop being scored against a golden set never reads the set — it gets aggregate scores and
  *category-level* miss summaries, never per-item answers. (Today's revision loop hands `judge_why`
  verbatim back to the agent — fine at n=1, but it is exactly the "learn by miss → keyword lure" cheat
  at n=many. Fix the seam now, before loops get longer.)
- **Wide**: a golden set below a minimum size (say 30) can't be used as a loop target, only as a smoke
  test — enumeration must not pay.
- **Held out**: every set keeps a validation split the loop is never scored on mid-run; final receipts
  report both numbers so overfitting is visible on the card.

This is the moat made explicit: a teammate who forks the engine gets all the machinery and none of the
ground truth. The operator's accumulated taste becomes a first-class, growing asset — arguably *the*
asset.

### Idea 3 — Judge self-calibration: descend on the agreement metric that already exists

The single highest-leverage loop, because every other loop inherits its quality. The judge is the loss
function for all agent work — and judge↔human agreement % is already computed per task-type, weekly,
with thresholds (70%/80%) that gate the entire trust ladder.

Today, if agreement is low, the system just… doesn't graduate. Instead: a recurring objective —
*"maximize judge↔human agreement on the held-out reaction history for task-type X"* — where the search
space is the judge's rubric/prompt (versioned in files+git, per the eval substrate design). Cycle:
propose rubric variant → re-score the historical reaction set blind → measure agreement on the
validation split → keep or discard.

The philosophy survives intact: UX_VISION says "no hand-tuning — governance is accept/reject only." This
*is* that promise, mechanized. The operator never edits a rubric; the descent happens underneath, and the
result surfaces as a recommendation card: "Judge rubric v3 for messages: agreement 71% → 88% on 60-day
held-out history. Accept / Reject." Goodhart fence: the judge's loss is *agreement with the human*, so
the cheap path ("score everything 10") is fenced by construction — sycophancy tanks agreement on every
👎 in the history.

Without this, the ladder's graduation bars are aspirational for any task-type where the stock rubric
mismatches the operator's taste. With it, the judge converges on each operator individually — which also
makes the *engine* better for every teammate who forks it, since the machinery (not the rubric) is what
ships.

### Idea 4 — Graduation campaigns: compress the trust soak from months to a weekend

The trust ladder's cost today is *calendar time*: Supervised→Autonomous needs 12 judged tasks + 85%
approval + 80% agreement, accrued passively at the rate real work happens to arrive. That's the "long
tail soak" the LFD essay says loops fast-forward: hundreds of edge cases in one optimization run instead
of a quarterly drip.

A **campaign** is an objective whose target is a graduation bar: *"get message-drafting to the
autonomous bar."* The loop replays the operator's historical asks (real inputs from done tasks — private
ground truth again), drafts in shadow, scores against the golden set + calibrated judge, improves the
worker prompt/skill selection between cycles, and assembles the same evidence pack `graduation_assess.py`
already produces — except generated deliberately overnight rather than awaited for two months.

Crucially, **nothing about the safety model changes**: the campaign produces *evidence*, the human still
confirms the graduation card, artifacts still hard-stop at Supervised, auto-ship stays behind the
default-OFF flag and the Tier-2 confirm. The campaign compresses the evidence-gathering, not the consent.
(Honest caveat to carry into design: replayed-shadow evidence is weaker than live-traffic evidence — a
campaign should unlock a *provisional* rung that confirms with the first N live tasks, not skip the live
check entirely.)

This changes what onboarding feels like: a new user's first week can include "Magnolia ran 40 shadow
drafts against your sent-mail voice overnight; here's where it's trustworthy and where it isn't" instead
of "use it for two months and find out."

### Idea 5 — The loop control plane: a Loops tab and the instruments invariant

"A constraint without an instrument is a vibe." If loops become long-running, the board must make them
*calm* — which is Magnolia's signature move. A **Loops tab** (sibling to Quality), one row per live
objective:

- **Gradient, not just score**: score trajectory per cycle, plus *score-per-dollar* and
  *score-per-hour* — so a 0.1%-per-cycle knob-turner is visibly stalled even though the metric "moves."
- **Budget burn**: wall-clock, USD, tokens, cycles — consumed vs. cap, projected exhaustion.
- **Iteration log**: hypothesis → expected failure mode → observed result, per cycle (the LFD log,
  written by the loop itself; survives compaction; doubles as the audit trail invariant #6 wants).
- **Overfit telemetry**: train-vs-validation split divergence, flagged when they part ways.
- **Controls**: pause · kill (generalizing the Quality tab's existing kill switch) · **shake** (inject a
  forced-entropy turn: "same idea harder is banned; make a non-obvious jump") · tighten budget.

And the engine-side rule, proposed as a *new invariant*: **every constraint a loop runs under must have a
CLI instrument the loop itself can read** (`scripts/loop_lib.py budget`, `…score`, `…elapsed`). Agents
have no sense of time or money; the harness must lend them one. This also gives the gates something to
enforce — an objective whose constraints lack instruments fails validation the same way a card with a
hardcoded color does.

### Idea 6 — `meta-create-objective`: the factory writes the loss function

Writing good loss functions is a skill (target large enough that enumeration doesn't pay; blind the
answer key; cap the budgets; pick the instrument at the right resolution). The LFD essay's own conclusion
is that this is a job for agents — the meta-meta-prompt.

Magnolia already has the exact pattern: the factory. A fourth sibling, `meta-create-objective`, under
`meta-factory-core`'s lifecycle (scaffold → capture → gate-green → commit → Keep/Undo receipt):

1. Interview the operator (or ingest a PRD/strategy memo) for the *outcome*, not the spec.
2. Draft the four LFD pieces: target + scorer, constraints (time/USD/cycles/surface), instruments
   (which CLI commands the loop reads), entropy schedule (stall threshold, reflection cadence).
3. Run the **fence linter** (the gate for this artifact type): Can the loop see its answer key? Is the
   eval set enumerable (< minimum size)? Is any budget uncapped? Does any step write externally without
   the Tier-2 seam? Any "yes" is a red gate.
4. Emit the objective as a Keep/Undo receipt.

The operator's role shifts one level up the stack — from approving *artifacts* to approving *objective
definitions* — which is precisely the "you own the loss function, agents own both loops" division of
labor.

### Idea 7 — Coverage objectives: hill-climb the PM corpus itself

Everything above improves *how work gets done*. This one aims the loop at the *product job itself*, using
the dataset moat directly. Coverage objectives are loss functions over the operator's own corpus:

- **Signal coverage**: "every customer ask in the last quarter's transcripts is either represented in
  the backlog/roadmap or explicitly declined-with-reason." Scorer: extraction + matching over
  `datasets/meetings/` (semantic, via the existing qmd search). The loop crawls, clusters, matches, and
  proposes backlog deltas as recommendation cards until uncovered-ask count descends to zero.
- **Evidence freshness**: "no roadmap line rests on evidence older than 2 quarters" — the research
  expiry machinery already tracks staleness; a loop can descend on it instead of a human noticing.
- **Content mode**: drafts hill-climbed against the *existing deterministic gates* — citation
  compliance, grade-8 readability, link verification, voice score — which are exactly the
  "pixel-diff-not-LLM-vibes" instruments the playbook calls for. They're currently pass/fail gates run
  once; as loop targets they become quality floors that drafts converge to unattended.

The asymmetry point lands hardest here: any competitor can run the same workflow skills. Nobody else has
this operator's two years of transcripts to score coverage against.

### Idea 8 — Loops on loops: the improvement agent becomes the loop orchestrator

The roadmap's "improvement agent" (eval_digest → eval-analyst → proposal) is currently conceived as a
weekly fix-proposer. Reframe it as the **outer-loop controller** — the agent whose *objects* are the
other loops:

- Reads the Loops tab's own telemetry (the meta-instrument: "how much is this optimization costing per
  point of gain?").
- Reallocates: kills stalled objectives, proposes budget moves toward loops with live gradients,
  schedules judge-recalibration objectives when agreement drifts, proposes new golden-set splits when
  overfit telemetry fires.
- Surfaces exactly one thing to the human: a weekly **portfolio card** — "3 loops converged (receipts
  attached), 1 stalled (diagnosis), judge calibration drifting on tickets (campaign proposed).
  Accept / Adjust."

That's the 100x shape: gradient descent all the way down, with the human holding the loss functions and
the kill switches. The board's center of gravity migrates from "tasks I must review" to "objectives I
have defined and evidence they're being met" — relief, not dread, at a higher altitude.

## 4. Safety: how the invariants extend (none weaken)

- **Loops are Tier-1 by construction.** No cycle step writes externally; the *only* exit to the world
  remains `shipper.autoship` → `adapters.publish()` → Tier-2 confirm. A 30-hour loop has exactly the
  same blast radius as a 30-second task: zero, until the existing gate.
- **Budgets are fences, not suggestions** — enforced by the harness (the dispatcher kills at cap), not
  by asking the model to stop. New invariant candidate: *no uninstrumented constraint, no uncapped
  budget*.
- **Receipts and iteration logs are append-only** (invariant #6 already covers this; loops make it pull
  its weight as the audit trail of *how* an artifact was found, not just that it was).
- **The kill switch generalizes**: Quality tab demotes a task-type; Loops tab kills an objective. Both
  instant, both reversible.
- **Campaign evidence is provisional** — replay-graduation unlocks a probationary rung confirmed by the
  first N live tasks (see Idea 4 caveat).

## 5. Sequencing (recommendation, not a plan)

1. **Golden-set substrate (Idea 2)** — pure capture, zero risk, and every other idea is downstream of
   having private ground truth in scoreable shape. Start accumulating now; value compounds.
2. **Objective primitive + minimal instruments (Ideas 1 + 5's `loop_lib`)** — raise `max_revisions`
   from "a constant" to "a governed budget." Card type via the existing factory.
3. **Judge self-calibration (Idea 3)** — first real descent loop; bounded scope; the metric and the
   data already exist; everything else inherits the win.
4. **Loops tab (Idea 5)** — once ≥2 loop kinds exist, visibility becomes the bottleneck.
5. **Campaigns (Idea 4), then `meta-create-objective` (Idea 6), then coverage objectives (Idea 7),
   then the orchestrator (Idea 8)** — each needs the substrate below it.

The one-line summary: Magnolia already built the safe harness and the trust governance that loop-running
systems lack; the LFD framing supplies what Magnolia lacks — targets to descend toward, budgets with
instruments, entropy on stall, and eval sets distilled from the one thing no one else has: the operator's
own exhaust.
