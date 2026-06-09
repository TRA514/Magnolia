# Trust-ladder passive signal + first-hop tuning — design

**Date:** 2026-06-09
**Status:** Approved, ready for implementation
**Scope:** `scripts/graduation_assess.py`, `scripts/ladder_lib.py`, `scripts/seed_default_crons.py` (+ tests)

## Problem

The trust-ladder promotion gate (audited 2026-06-09) has three weaknesses, surfaced
while reviewing defaults before opening Magnolia to beta users:

1. **Graduation depends entirely on explicit thumbs.** The agreement metric is computed
   only over tasks the human reacted to (👍/👎). A user who never reacts produces
   `agreement = 0.0` → nothing ever graduates, no matter how good the judge is.
2. **The agreement gate has no sample-size floor.** `min_judged` governs *judged* tasks,
   not *reacted* ones, so a type can graduate on a single lucky reaction (6 judged tasks
   the judge liked + 1 agreeing 👍 = 100% agreement on n=1).
3. **The judge self-votes in approval.** When the human is passive, `no reaction + judge≥7`
   counts as an approval — the metric meant to validate the judge is partly written by the
   judge.

Separately, the first-hop sample size (`min_judged=6`) makes graduation slow to *show up*
for a new user, who wants to feel the ladder move early.

Context that lowers the stakes: **the ladder is advisory today** — `tier_of` is read only
for a display label and the graduate-card handler; nothing in dispatch/review gates on
tier. So the gate's only current job is to *collect judge↔human agreement data*. That makes
this a safe time to loosen the first hop and to introduce a passive signal whose noise
profile we can observe before tiers ever gate real autonomy.

## Approach

Learn from **what the user does with a card** (passive), not only explicit thumbs. A card
the human terminally accepts (Done / Send / Publish) with little or no chat back-and-forth
is a clean, *human-authored* approval signal — and a cleaner one than a thumbs-up, because
they put their name on the outcome.

This is sound because of the status lifecycle: `agent:complete` leaves `status="open"`
(only flips `agent_status` into the review bucket); **`status="done"` is set only by a human
action** (`complete_task` actor=human, or the Send/Publish path that stamps `message_sent_at`
and requires the Tier-2 confirm). So "done" reliably means the human accepted — the agent
finishing never trips it.

## Changes

### 1. Implicit-approval signal (the substantive change)

A pure, deterministic helper in `graduation_assess.py` (no new write path; reads only fields
and the chat transcript that already exist):

```
effective_react(task):
    if task.human_react in ("up", "down"):        return task.human_react   # explicit wins
    if task.status == "done" and user_chat_turns(task) <= FRICTION_MAX:
        return "up"                                                          # clean accept
    return None                                                              # open / abandoned / high-friction
```

- `user_chat_turns(task)` = count of `role == "user"` events from
  `chat_transcript.read_events(task_id)`.
- `FRICTION_MAX = 1` — accepted after at most one follow-up question still counts as clean.
- **Synthesizes only "up", never "down."** Explicit 👎 stays the only hard negative.
  Abandonment and heavy iteration are too ambiguous to punish; the positive case is what
  stalls graduation, so that is what the passive signal fills.

`_metrics()` switches from raw `human_react` to `effective_react`:
- **Approval** = `effective_react == "up"` (explicit 👍 *or* clean human accept). This drops
  the judge self-vote: a no-reaction + judge≥7 task no longer counts as approval unless the
  human actually accepted it.
- **Agreement** keeps its shape but uses `effective_react`, so implicit-ups participate. A
  clean accept on a judge-low task is a real disagreement signal (judge too harsh) — exactly
  the data the beta is meant to gather.

### 2. `min_reacted` floor on the agreement gate

Add `min_reacted` to `DEFAULT_THRESHOLDS` per hop. Promotion requires
`reacted >= min_reacted` *in addition to* the existing `min_judged` / `min_approval` /
`min_agreement` bars. Kills the one-lucky-click promotion.

- `shadow_to_supervised`: `min_reacted = 3`
- `supervised_to_autonomous`: `min_reacted = 6`

Implicit-ups count toward `reacted` (that is the point — the floor becomes reachable
passively).

### 3. `min_judged` 6 → 4 on the first hop

`shadow_to_supervised.min_judged = 4` (was 6). Second hop unchanged at 12. Rationale: the
first hop lands in "supervised," where a human still reviews — a fast first hop is cheap even
in a future enforcing world. The autonomy hop (removes the human) keeps the larger sample.

### 4. Twice-weekly assessment

In `seed_default_crons.py`, the Graduation-ladder default changes
`30 9 * * 1` → `30 9 * * 1,4` (Mon + Thu 9:30), `cron_human` updated to match. New beta users
get twice-weekly on seed. Existing seeded installs keep their schedule (jobs.json is
per-person, gitignored, matched by name) — no migration (YAGNI; beta = new users).

## Safety / reversibility

- Still fully advisory — zero operational blast radius (no autonomy is unlocked by a tier).
- `effective_react` and `user_chat_turns` are pure and unit-tested.
- Thresholds stay config-overridable via `datasets/evals/ladder.json`.
- No schema migration: reads existing `human_react` / `status` fields + the existing sidecar
  transcript.
- Engine stays de-personalized — no identity literals (invariant #1).

## Testing (TDD)

- `effective_react` truth table: explicit up/down wins; `status="open"` → None; `done`+0
  turns → up; `done`+2 turns → None; `done`+explicit 👎 → down; `done`+1 turn → up.
- `user_chat_turns`: 0 when no transcript; counts only `role=="user"`.
- `_metrics`: self-vote no longer inflates approval; implicit-ups count in approval and
  agreement; `reacted` includes implicit-ups.
- `assess`: `min_reacted` blocks promotion below the floor and passes at/above it; first hop
  fires at `min_judged=4`; second hop still needs 12.
- `seed_default_crons`: graduation `cron_expr == "30 9 * * 1,4"`.
- Green gates: `pytest`, `card_schema.py` → `registry.json OK`, `test_engine_no_jay.py`.
