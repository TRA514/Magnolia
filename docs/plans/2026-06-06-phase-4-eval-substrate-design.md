# Magnolia Phase 4 — Eval & Judge Substrate off Docker + In-Box Crons

Date: 2026-06-06
Branch: `feat/phase-4-eval-substrate-crons`
Builds on: Phase 3 (PR #2, merged to `main` at `59a7949`)
Master design: `docs/plans/2026-06-05-pm-os-portability-design.md` §5 (eval & judge
substrate), §11 step 4 (build sequence). Phase 3 residual: `docs/plans/2026-06-06-phase-3-residual.md`.

This is build-sequence step 4: drop the Docker-LangFuse dependency (a non-starter for
non-technical teammates), move its four jobs to native zero-install homes, and wire the two
load-bearing in-box crons. The polished card rendering and the dispatch-behavior enforcement
of graduation tiers are deliberately **out of scope** here — they land with the Designer
commission (step 5/6).

---

## Guiding shape

The substrate already has its bones from Phases 1–3:

- `scripts/judge.py` already scores completed agent artifacts and writes the verdict to **task
  frontmatter** (`judge_score`, `judge_why`, `judge_dimensions`, `judge_kind`,
  `judge_rubric_version`, `judge_scored_at`). The "scores → frontmatter" half of §5 is done.
- `scripts/task_server.py::handle_quality` already aggregates judged tasks **from frontmatter**
  into the Quality tab. Its *only* LangFuse dependency is the human 👍/👎 half (agreement %),
  pulled from LangFuse trace scores.
- `ui/task-board/cardtypes/registry.json` declares `recommendation` / `receipt` / `graduation`
  card types; `card-registry.js::renderCardFromRegistry` already routes on `task.card_type`.
  The `diff` / `preview` / `agreement` body renderers exist but emit **empty placeholder divs**,
  and `_renderActions` wires only `mark_done` / `open_output` (per Phase 3 residual).
- `scripts/seed_default_crons.py` has a clean idempotent `DEFAULTS` list (the Monday Doctor
  cron) — the two new crons drop straight in.

So Phase 4 is **mostly rewiring data sources from LangFuse → frontmatter, plus filling in
handlers/renderers stubbed inert in Phase 3.** Net new code is modest; the risk is in the seams.

**LangFuse remains a silent opt-in for power users.** Where it was the *data source* it becomes
a *mirror*: when `LANGFUSE_SECRET_KEY` is set, the existing graceful-degradation wiring still
dual-writes trace scores and the legacy paths still light up. Jay's current setup survives
untouched; teammates never see it.

---

## The four LangFuse jobs, rehomed

| LangFuse job | Phase 4 home | Work |
|---|---|---|
| Prompt store + versions | `engine/` prompt files + git history | Already on disk (`judge.py` rubrics; worker `langfuse_prompt` names; `langfuse_setup.py` registers them). Light: document that files + git history **are** the store. No migration. |
| Execution traces | **Claude Code session JSONL (free)** | No writer to build — see "Correcting the design's trace claim" below. |
| Scores + annotations | **Task frontmatter** | `judge_*` already written. **New:** `human_react` / `human_react_note` / `human_reacted_at`, written from the task modal. Dual-write the LangFuse trace score when enabled. |
| The UI | **Quality tab** | Rewire `handle_quality` agreement % to read `human_react` from frontmatter (drop the LangFuse score pull as the *data source*; keep it as a mirror). Replace the hardcoded `phase: "Shadow"` label with the real ladder tier. |

### Correcting the design's trace claim

Master design §5 lists execution traces as "Local JSONL (already written today)." Verified: there
is **no JSONL writer in the repo**. What exists today is (a) `logs/dispatch-{task_id}.log` (a
`script -q` typescript, human-readable, which `judge.py` reads the tail of) and (b) opt-in
LangFuse `worker-execution` traces.

However, the claim is **substantially true for a reason I missed initially**: every `claude`
invocation — the dispatcher, the judge, the parsers — writes a full session-transcript **JSONL**
under `~/.claude/projects/<cwd-slug>/<session-uuid>.jsonl`, for free, by Claude Code itself. The
dev repo lacks dispatch-generated transcripts only because no headless dispatch has run here.

The catch: the dispatcher (`task_dispatch.py`) runs `claude` in *interactive* mode wrapped in
`script -q`, stdout/stderr to `DEVNULL` — it never captures the `session_id`, so there is
**no task → transcript join** today. For Phase 4 this does not matter (the eval loop runs off
frontmatter, and the dispatch log + activity log cover debugging). Documented as a **future
enhancement**: capture the dispatch `session_id` so the eval-analyst can read the actual
tool-call/reasoning transcript for deeper root-cause, not just the score. We do **not** build a
JSONL writer (YAGNI — nothing reads a new layer this phase) and we **correct the design doc's
wording** rather than chase the claim.

---

## Components (new + changed)

### 1. `human_react` write path
- **Endpoint:** `POST /api/tasks/{id}/react` → `task_lib` writes `human_react` (`up` | `down`),
  `human_react_note` (optional free text), `human_reacted_at` to frontmatter. Archive-aware
  (mirror `judge.py::write_back`).
- **Surface:** the task detail modal — where the operator already reviews agent output. The
  per-pipeline-step LangFuse thumbs become **one per-task react** (aligns with the per-task
  `judge_score`).
- **Mirror:** when `LANGFUSE_SECRET_KEY` is set, also score the worker-execution trace
  (`human-feedback` NUMERIC 1/0) + annotation, exactly as today. Silent; never required.

### 2. `eval_digest.py` rewrite (data source: frontmatter)
- Source becomes judged task frontmatter, not the LangFuse `/scores` endpoint.
- **Negative signal** = `judge_score < 7` (mirrors `JUDGE_GOOD_THRESHOLD`) **or**
  `human_react == down`. The `human_react_note` is the free-text annotation.
- **Cluster by step** (from `judge_kind` — document/message/meeting — plus worker and domain) and
  by worker / task-type. Recurring vs one-off preserved.
- **Output shape unchanged** (`digest.json` + `digest.md`, same keys: `by_step`, `by_worker`,
  `flagged`, `totals`) so the eval-analyst worker's contract holds. Stub-on-empty preserved; the
  `--days` / `--all` flags stay.
- The old LangFuse REST machinery is removed from the primary path. (If a power user wants
  LangFuse annotations folded in, that's a deferred enrichment, not Phase 4.)

### 3. `ladder_lib.py` + `datasets/evals/ladder.json`
- Per-task-type tier store: `shadow` → `gated` → `autonomous`. Runtime state, **gitignored**
  (like `datasets/cron/jobs.json`), idempotently initialized (mirror `seed_default_crons`'s
  `_ensure_cron_store`).
- Accessor module `ladder_lib.py` (style of `cron_lib` / `profile_lib`): `tier_of(task_type)`,
  `advance(task_type)`, `demote(task_type)`, `set_tier`, `all_tiers()`.
- **Thresholds live in config** (a block in `ladder.json` with code defaults), tunable without
  code changes. Defaults = **moderate**:
  - `shadow → gated`: ≥6 judged in rolling 60 days, ≥75% human-approval, ≥70% judge↔human agreement.
  - `gated → autonomous`: ≥12 judged, ≥85% approval, ≥80% agreement.
  - **Auto-demote** one rung if rolling agreement falls below the current tier's *entry* bar for
    2 consecutive weekly assessments.
- `handle_quality` reads `tier_of()` for the phase label, replacing the hardcoded `"Shadow"` /
  `"observe-only"`.
- **Advisory only this phase** — the tier is displayed and managed, but does **not** change
  dispatch/review behavior. Behavioral enforcement (auto-complete when autonomous, hold-for-review
  when gated) is deferred to the Review-surface work (Phase 6 territory).

### 4. `graduation_assess.py` (deterministic — no LLM)
- Reads frontmatter scores per task-type over the rolling window; computes human-approval rate
  (`human_react == up`, or `judge_score ≥ 7` where no react) and judge↔human agreement %.
- When a type clears its next-tier thresholds → **creates a `graduation` card** (a task with
  `card_type: graduation`) carrying tier, agreement %, approval %, n, and example task ids.
- When a graduated type's rolling metrics drop below its tier's entry bar for 2 consecutive
  assessments → **auto-demotes** in `ladder.json` (logs it; optionally a quiet receipt). Reversible
  by construction; a trust budget per task-type.
- Idempotent: doesn't re-card a type that already has an open graduation card for its current tier.

### 5. eval-analyst worker update
- Prose moves off "read LangFuse human annotations" → "read the frontmatter-based digest."
- **Emits one real, machine-applicable `.patch` per clustered change** (capped at ~3 clusters/week
  by signal strength; the rest noted in the digest, not carded), each as its **own
  `recommendation` card** (`card_type: recommendation`) with the patch path in frontmatter — not a
  single plain collab card. Per-change accept/reject; you can take the voice fix and drop the
  worker-scoping change. The worker still inspects the real target file before proposing the diff.

### 6. Card handlers + minimal renderers (frontend — deliberately plain; Phase 6 restyles)
- `recommendation` (body `diff`): render the `.patch` in a `<pre>`. **accept** →
  `POST /api/tasks/{id}/accept` → `git apply` the patch + commit → spawn a `receipt` card with
  Undo. **reject** → mark rejected + archive.
- `receipt` (body `preview`): show what changed. **keep** → dismiss. **undo** → `git revert` the
  apply commit (Git is never a user-facing concept; the button says "Undo").
- `graduation` (body `agreement`): tier, agreement %, approval %, n, example ids. **graduate** →
  `POST /api/tasks/{id}/graduate` → `ladder_lib.advance(task_type)`.
- **Write `task.card_type`** (read-only until now) from the crons/workers that create these cards.
- Renderers stay minimal/unstyled and are explicitly marked for Phase 6 restyling — **no throwaway
  polish.** The action handlers and their backend semantics are durable; Phase 6 rewrites
  rendering only.

This lights up **three** inert card types (recommendation → accept → receipt → undo is one
closed loop), not two.

### 7. Two default crons (`seed_default_crons.py` `DEFAULTS`)
- **Weekly self-improvement** — `0 9 * * 1` (after the Doctor cron), agent task → matched to the
  `eval-analyst` worker (its `title_patterns` already match "feedback-loop" / "self-improvement").
- **Graduation ladder** — weekly, runs `graduation_assess.py`. Because assessment is
  **deterministic**, the recommended mechanism is a **minimal worker that shells the script**
  (following the Doctor-cron "agent task runs a script" pattern) rather than adding a new
  script-job type to the cron system. This is the one place we choose the smaller change over the
  purer one; revisit if a true non-LLM cron job type is wanted later.

---

## Data flow

```
agent task completes ──► judge.py ──► judge_* frontmatter
                                          │
operator reviews in modal ──► /react ──► human_react frontmatter
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                                ▼
              handle_quality (Quality tab)        eval_digest.py / graduation_assess.py
              avg score, trend, dims,             (weekly crons, frontmatter source)
              agreement % (frontmatter),                  │
              ladder tier label                  ┌────────┴─────────┐
                                                 ▼                  ▼
                                      eval-analyst worker    graduation card
                                      → recommendation card  (graduate → ladder.json)
                                        (+ .patch)
                                            │
                                  accept → git apply + commit
                                            │
                                       receipt card
                                            │
                                       undo → git revert
```

LangFuse, when enabled, mirrors `judge_*` and `human_react` to trace scores — observability only,
never the board's data source.

## Error handling & philosophy

- Every new/changed script exits 0 on failure (mirrors `judge.py` / `eval_digest.py`); never
  blocks dispatch or completion.
- `git apply` / `git revert` run **only** on accept / undo (human-triggered) — honors "nothing
  auto-applies." A failed `git apply` (conflict) surfaces a plain-language error on the card with
  no partial state; the commit is atomic.
- Graduation is advisory + auto-demoting → safe to be wrong; it cannot break task flow this phase.
- Git stays invisible: cards speak "accept" / "keep" / "undo," never "commit" / "revert."

## Testing

`python3 -m pytest` (104 passing at Phase 3 close; target ~125+). New tests reuse
`tests/conftest.py::profile_root`:

- `eval_digest`: frontmatter clustering by step/worker; negative-signal selection; stub-on-empty.
- `ladder_lib`: advance/demote, tier_of defaults, config threshold read, idempotent store init.
- `graduation_assess`: threshold math, card creation, auto-demote, idempotent re-card guard.
- `human_react`: write-back (active + archived task), field shape, LangFuse-absent path.
- accept → `git apply` + commit → receipt; undo → `git revert` (exercised in a tmp git repo).
- `handle_quality`: agreement % from frontmatter with no LangFuse; tier label from `ladder.json`.

JS has **no test harness** (deliberate, per Phase 3 residual — this is a Python repo). The three
minimal renderers are gated by `scripts/card_schema.py` (registry validity) and an owed on-screen
visual pass of the live board (controller to arrange) — confirming each new card variant renders
and acts correctly.

## Out of scope (named)

- Dispatch-behavior enforcement of tiers (gated hold-for-review, autonomous auto-complete) — lands
  with the Review surface (Phase 6).
- Polished card rendering — Phase 6, post-Designer.
- A real JSONL execution-trace writer / task→transcript join — free traces exist; join is a future
  enhancement, no Phase 4 consumer.
- LangFuse annotation enrichment of the digest — deferred; frontmatter is the source.

## Reused, not rebuilt

`scripts/judge.py`, `scripts/eval_digest.py` (rewritten in place), `scripts/langfuse_client.py`
+ `langfuse_setup.py` (mirror path only), the `eval-analyst` worker, the Quality tab
(`ui/task-board/js/quality.js`), `seed_default_crons.py`'s `DEFAULTS` pattern, `cron_lib`,
`profile_lib`, and `tests/conftest.py::profile_root`.
